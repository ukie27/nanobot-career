"""
队列式集中安全确认系统
支持同一会话的多个顺序确认
"""

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional, Dict, Tuple, Callable, Deque
from collections import deque
from loguru import logger


class ConfirmResult(Enum):
    """确认结果"""
    ALLOW = auto()
    DENY = auto()
    TIMEOUT = auto()
    CANCELLED = auto()


@dataclass
class PendingConfirm:
    """单个确认请求"""
    request_id: str
    command: str
    future: asyncio.Future
    timeout: int  # 原始超时配置
    expires_at: Optional[datetime] = None


@dataclass
class SessionQueue:
    """会话的确认队列"""
    confirms: Deque[PendingConfirm] = field(default_factory=deque)
    processing: bool = False


class ConfirmManager:
    """
    队列式集中确认管理器
    
    特性：
    - 支持同一会话的多个顺序确认（队列）
    - 不同会话完全并发
    - 通过回调发送提示
    - 超时由队列处理器统一控制
    """
    
    # 确认命令正则模式
    CONFIRM_PATTERNS = [
        r'^\\是$',
        r'^\\yes$',
    ]
    
    # 拒绝命令正则模式
    DENY_PATTERNS = [
        r'^\\否$',
        r'^\\no$',
    ]
    
    def __init__(self):
        # {session_key: SessionQueue}
        self._sessions: Dict[str, SessionQueue] = {}
        self._lock = asyncio.Lock()
        
        # 回调：发送提示给用户
        self.send_prompt_callback: Optional[Callable[[str, str, str], asyncio.Future]] = None
    
    def set_send_prompt_callback(self, callback: Callable[[str, str, str], asyncio.Future]):
        """设置发送提示的回调"""
        self.send_prompt_callback = callback
    
    async def request_confirm(
        self,
        channel: str,
        chat_id: str,
        command: str,
        timeout: int = 60
    ) -> ConfirmResult:
        """
        请求用户确认
        将请求加入队列，等待队列处理器处理。
        
        Args:
            session_key: 会话标识
            command: 要执行的命令
            timeout: 超时秒数（由队列处理器使用）
        
        Returns:
            确认结果
        """
        # 创建 Future 用于接收结果
        future = asyncio.get_event_loop().create_future()
        
        session_key = f"{channel}:{chat_id}"

        pending = PendingConfirm(
            request_id=f"{session_key}_{uuid.uuid4().hex[:6]}",
            command=command,
            future=future,
            expires_at=None,
            timeout=timeout
        )
        
        async with self._lock:
            # 获取或创建会话队列
            if session_key not in self._sessions:
                self._sessions[session_key] = SessionQueue()
            
            queue = self._sessions[session_key]
            queue.confirms.append(pending)
            
            # 启动队列处理器（如果未运行）
            if not queue.processing:
                queue.processing = True
                # 后台运行，不 await
                asyncio.create_task(self._process_queue(channel, chat_id))
        
        # 无限等待，不设置超时
        # 超时由 _process_queue 控制，通过设置 future 结果来唤醒
        try:
            result = await future
            return result
        except asyncio.CancelledError:

            return ConfirmResult.CANCELLED
    
    async def _process_queue(self, channel: str, chat_id: str):
        """
        队列处理器：顺序处理同一会话的所有确认请求
        
        不同会话的队列处理器可以并发运行。
        统一控制超时计时。
        """

        session_key = f"{channel}:{chat_id}"

        while True:
            # 获取当前请求
            async with self._lock:
                queue = self._sessions.get(session_key)
                if not queue or not queue.confirms:
                    # 队列空，停止处理
                    if queue:
                        queue.processing = False
                    return
                
                pending = queue.confirms[0]
            
            # 轮到处理时才开始计时
            if pending.expires_at is None:
                pending.expires_at = datetime.now() + timedelta(seconds=pending.timeout)

            # 发送提示给用户
            if self.send_prompt_callback:
                try:
                    await self.send_prompt_callback(
                        channel,
                        chat_id,
                        self._format_prompt(pending, len(queue.confirms))
                    )
                except Exception as e:
                    # 发送失败，记录但继续
                    print(f"发送确认提示失败: {e}")
            
            # 计算剩余时间
            remaining = (pending.expires_at - datetime.now()).total_seconds()
            # 确保最小等待时间，避免负值或极小值
            remaining = max(remaining, 0.001)  # 至少 1ms

            # 等待用户响应或超时
            try:
                await asyncio.wait_for(
                    self._wait_for_future(pending.future),
                    timeout=remaining
                )
            except asyncio.TimeoutError:
                if not pending.future.done():
                    pending.future.set_result(ConfirmResult.TIMEOUT)
            except asyncio.CancelledError:
                # 如果是取消，检查是否是因为超时导致的
                # 重新抛出或处理
                logger.info("！！！cancel")
                if not pending.future.done():
                    pending.future.set_result(ConfirmResult.TIMEOUT)

            # 处理完成，从队列移除
            async with self._lock:
                if queue.confirms and queue.confirms[0] == pending:
                    queue.confirms.popleft()
                
                # 检查是否还有请求
                if not queue.confirms:
                    queue.processing = False
                    return
                # 否则继续循环处理下一个
    
    async def _wait_for_future(self, future: asyncio.Future):
        """等待 Future 完成"""
        if future.done():
            return
        await future
    
    def try_resolve(self, channel: str, chat_id: str, content: str) -> Tuple[bool, Optional[bool]]:
        """
        尝试解析用户输入为确认命令
        
        Args:
            session_key: 会话标识
            content: 用户输入内容
        
        Returns:
            (is_confirm_command, decision)
            - (False, None): 不是确认命令
            - (True, True): 确认执行
            - (True, False): 拒绝执行
            - (True, None): 是确认命令，但没有匹配的请求或已过期
        """
        session_key = f"{channel}:{chat_id}"

        # 解析决策
        decision = self._parse_decision(content.strip())
        if decision is None:
            return (False, None)
        
        # 找到会话队列
        queue = self._sessions.get(session_key)
        if not queue or not queue.confirms:
            return (True, None)  # 是确认命令，但没有待处理请求
        
        # 只处理队列中的第一个（当前正在等待的）
        pending = queue.confirms[0]
        
        # 设置结果，唤醒 request_confirm
        if not pending.future.done():
            result = ConfirmResult.ALLOW if decision else ConfirmResult.DENY
            pending.future.set_result(result)
            return (True, decision)
        
        return (True, None)  # 已处理过
    
    def _parse_decision(self, content: str) -> Optional[bool]:
        """
        解析用户输入的决策
        
        Returns:
            True: 确认
            False: 拒绝
            None: 不是确认命令
        """
        # 确认命令
        for pattern in self.CONFIRM_PATTERNS:
            if re.match(pattern, content, re.IGNORECASE):
                return True
        
        # 拒绝命令
        for pattern in self.DENY_PATTERNS:
            if re.match(pattern, content, re.IGNORECASE):
                return False
        
        return None
    
    def _format_prompt(self, pending: PendingConfirm, queue_len: int) -> str:
        """
        格式化确认提示
        
        Args:
            pending: 待确认的请求
            queue_len: 队列长度
        
        Returns:
            提示文本
        """
        # 队列位置信息
        position_info = ""
        if queue_len > 1:
            position_info = f"\n📋 队列中还有 {queue_len - 1} 个请求等待处理"
        
        # 剩余时间
        remaining = int((pending.expires_at - datetime.now()).total_seconds())
        remaining = max(0, remaining)
        
        
        return f"""执行确认请求 {position_info}

即将执行: `{pending.command}`
请求ID: `{pending.request_id}`

剩余时间: {remaining}秒

请回复:
  同意执行: 输入 `\\是` 或 `\\yes`
  拒绝执行: 输入 `\\否` 或 `\\no`

输入其他内容将视为普通聊天消息，本次请求保持等待状态。
超时将自动取消执行。"""
    
    def cancel_session(self, channel: str, chat_id: str, reason: str = "会话结束"):
        """
        取消会话的所有待处理确认
        
        用于会话断开或清理时调用。
        
        Args:
            channel: 频道
            chat_id: 聊天ID
            reason: 取消原因
        """
        session_key = f"{channel}:{chat_id}"
        queue = self._sessions.get(session_key)
        if not queue:
            return
        
        # 取消所有待处理的 future
        for pending in queue.confirms:
            if not pending.future.done():
                pending.future.set_exception(asyncio.CancelledError(reason))
        
        # 清理
        del self._sessions[session_key]
    
    def get_session_stats(self, channel: str, chat_id: str) -> Optional[Dict]:
        """
        获取会话的统计信息
        
        Args:
            channel: 频道
            chat_id: 聊天ID
        
        Returns:
            统计信息字典，或 None
        """
        session_key = f"{channel}:{chat_id}"
        queue = self._sessions.get(session_key)
        if not queue:
            return None
        
        return {
            "pending_count": len(queue.confirms),
            "processing": queue.processing,
            "current_request": queue.confirms[0].request_id if queue.confirms else None
        }