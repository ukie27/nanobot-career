# nanobot/agent/tools/exec_tool.py
"""
全新 ExecTool - 分层安全执行器
"""

import os
import time
from dataclasses import dataclass
from typing import Optional, Dict

from .exec_security import SecurityClassifier, RiskLevel
from .exec_sandbox import DockerSandbox, SandboxConfig
from .exec_confirm import CentralizedConfirm, ConfirmResult


@dataclass
class ExecResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    risk_level: str
    confirmed: bool
    security_blocked: bool = False
    block_reason: str = ""


class ExecTool:
    """
    分层安全执行器
    集成集中式确认系统
    """
    
    def __init__(self, sandbox_config: Optional[SandboxConfig] = None):
        self.classifier = SecurityClassifier()
        self.sandbox = DockerSandbox(sandbox_config)
        self.confirm = CentralizedConfirm()
        self.stats = {
            "total": 0,
            "blocked": 0,
            "confirmed": 0,
            "denied": 0,
            "timeout": 0
        }
    
    async def execute(
        self,
        command: str,
        working_dir: Optional[str] = None,
        session_key: Optional[str] = None,
        env_vars: Optional[Dict] = None
    ) -> ExecResult:
        """
        执行命令入口
        
        Args:
            command: 要执行的命令
            working_dir: 工作目录
            session_key: 会话标识（用于确认隔离）
            env_vars: 环境变量
        """
        start_time = time.time()
        self.stats["total"] += 1
        
        working_dir = working_dir or os.getcwd()
        session_key = session_key or "default"
        
        # === Step 1: 安全分类 ===
        risk_level, pattern, block_reason = self.classifier.classify(command)
        
        if risk_level == RiskLevel.FORBIDDEN:
            self.stats["blocked"] += 1
            return ExecResult(
                success=False,
                stdout="",
                stderr=f"[SECURITY] 命令被拒绝: {block_reason}",
                exit_code=-1,
                execution_time=0,
                risk_level="FORBIDDEN",
                confirmed=False,
                security_blocked=True,
                block_reason=block_reason
            )
        
        # === Step 2: 确认流程（如需要）===
        requires_confirm = risk_level in (RiskLevel.NORMAL, RiskLevel.DANGEROUS)
        confirmed = False
        
        if requires_confirm:
            # 发送确认提示（需要外部回调来实际发送消息）
            confirm_prompt = self._format_confirm_prompt(command, risk_level.name, 60)
            await self._send_confirm_prompt(session_key, confirm_prompt)
            
            # 等待用户确认（挂起）
            result = await self.confirm.request_confirm(
                session_key=session_key,
                command=command,
                risk_level=risk_level.name,
                timeout=60 if risk_level == RiskLevel.NORMAL else 120
            )
            
            if result == ConfirmResult.TIMEOUT:
                self.stats["timeout"] += 1
                return ExecResult(
                    success=False,
                    stdout="",
                    stderr="[SECURITY] 确认超时，命令已取消",
                    exit_code=-1,
                    execution_time=time.time() - start_time,
                    risk_level=risk_level.name,
                    confirmed=False,
                    security_blocked=True,
                    block_reason="confirmation_timeout"
                )
            
            if result == ConfirmResult.DENY:
                self.stats["denied"] += 1
                return ExecResult(
                    success=False,
                    stdout="",
                    stderr="[SECURITY] 用户拒绝执行",
                    exit_code=-1,
                    execution_time=time.time() - start_time,
                    risk_level=risk_level.name,
                    confirmed=False,
                    security_blocked=True,
                    block_reason="user_denied"
                )
            
            confirmed = True
            self.stats["confirmed"] += 1
        
        # === Step 3: Docker 沙箱执行 ===
        try:
            sandbox_result = await self.sandbox.execute(
                command=command,
                working_dir=working_dir,
                network_required=pattern.requires_network if pattern else False
            )
            
            execution_time = time.time() - start_time
            
            return ExecResult(
                success=sandbox_result["success"],
                stdout=sandbox_result["stdout"],
                stderr=sandbox_result["stderr"],
                exit_code=sandbox_result["exit_code"],
                execution_time=execution_time,
                risk_level=risk_level.name,
                confirmed=confirmed
            )
            
        except Exception as e:
            return ExecResult(
                success=False,
                stdout="",
                stderr=f"[ERROR] 执行失败: {str(e)}",
                exit_code=-1,
                execution_time=time.time() - start_time,
                risk_level=risk_level.name,
                confirmed=confirmed
            )
    
    def _format_confirm_prompt(self, command: str, risk_level: str, timeout: int) -> str:
        """格式化确认提示"""
        emoji = "⚠️" if risk_level == "NORMAL" else "🔴"
        
        return f"""{emoji} 执行确认请求 [{risk_level}]

即将执行: `{command}`

⏱️ 请在 {timeout} 秒内回复:
  ✅ 同意执行: 输入 `\\是` 或 `\\yes`
  ❌ 拒绝执行: 输入 `\\否` 或 `\\no`

⚠️ 输入其他内容将视为普通聊天消息，本次请求将保持等待状态。
⏳ 超时将自动取消执行。"""
    
    async def _send_confirm_prompt(self, session_key: str, prompt: str):
        """
        发送确认提示
        由外部注入回调实现
        """
        if self.send_message_callback:
            await self.send_message_callback(session_key, prompt)
    
    # 回调注入点
    send_message_callback: Optional[callable] = None
    
    def set_send_message_callback(self, callback):
        self.send_message_callback = callback
    
    def try_resolve_confirm(self, session_key: str, content: str) -> bool:
        """
        供 AgentLoop 调用，尝试解析确认
        返回是否是确认命令
        """
        is_confirm, _ = self.confirm.try_resolve(session_key, content)
        return is_confirm
    
    def get_stats(self) -> Dict:
        return self.stats.copy()