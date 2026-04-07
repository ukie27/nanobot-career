"""
全新 ExecTool - 分层安全执行器
包含：安全分类、Docker沙箱、队列式确认管理
"""

import asyncio
import os
import re
import hashlib
import tempfile
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from fnmatch import fnmatch
from typing import Optional, Dict, List, Tuple, Callable, Deque, Any
from collections import deque
from nanobot.agent.tools.exec_confirm import ConfirmManager, ConfirmResult
from nanobot.agent.tools.base import Tool


# === 安全分类模块 ===

class RiskLevel(Enum):
    """风险等级"""
    SAFE = auto()
    NORMAL = auto()
    DANGEROUS = auto()
    FORBIDDEN = auto()


@dataclass(frozen=True)
class CommandPattern:
    """命令模式定义"""
    name: str
    pattern: str
    risk_level: RiskLevel
    allowed_args: Optional[List[str]] = None
    requires_network: bool = False
    max_execution_time: int = 300
    
    def matches(self, command: str) -> bool:
        cmd_base = command.strip().split()[0] if command.strip() else ""
        return fnmatch(cmd_base, self.pattern)


# 安全命令白名单
SAFE_COMMANDS: List[CommandPattern] = [
    CommandPattern("ls", "ls", RiskLevel.SAFE, max_execution_time=30),
    CommandPattern("cat", "cat", RiskLevel.SAFE),
    CommandPattern("head", "head", RiskLevel.SAFE),
    CommandPattern("tail", "tail", RiskLevel.SAFE),
    CommandPattern("grep", "grep", RiskLevel.SAFE),
    CommandPattern("find", "find", RiskLevel.SAFE, max_execution_time=60),
    CommandPattern("pwd", "pwd", RiskLevel.SAFE),
    CommandPattern("echo", "echo", RiskLevel.SAFE),
    CommandPattern("ps", "ps", RiskLevel.SAFE),
    CommandPattern("df", "df", RiskLevel.SAFE),
    CommandPattern("du", "du", RiskLevel.SAFE, max_execution_time=30),
    CommandPattern("file", "file", RiskLevel.SAFE),
    CommandPattern("which", "which", RiskLevel.SAFE),
]

# 需确认命令
CONFIRM_COMMANDS: List[CommandPattern] = [
    CommandPattern("git", "git", RiskLevel.NORMAL, requires_network=True),
    CommandPattern("mkdir", "mkdir", RiskLevel.NORMAL),
    CommandPattern("touch", "touch", RiskLevel.NORMAL),
    CommandPattern("cp", "cp", RiskLevel.NORMAL),
    CommandPattern("mv", "mv", RiskLevel.NORMAL),
    CommandPattern("rm", "rm", RiskLevel.NORMAL),
    CommandPattern("chmod", "chmod", RiskLevel.NORMAL),
    CommandPattern("pip", "pip", RiskLevel.DANGEROUS, requires_network=True),
    CommandPattern("npm", "npm", RiskLevel.DANGEROUS, requires_network=True),
    CommandPattern("curl", "curl", RiskLevel.DANGEROUS, requires_network=True),
    CommandPattern("wget", "wget", RiskLevel.DANGEROUS, requires_network=True),
]

# 绝对禁止
FORBIDDEN_PATTERNS: List[str] = [
    r"mkfs\.",
    r"fdisk",
    r"dd\s+if=/dev/(zero|random|urandom)",
    r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;?",
    r"rm\s+-rf\s*/",
    r">?\s*/etc/passwd",
    r">?\s*/etc/shadow",
]


class SecurityClassifier:
    """命令安全分类器"""
    
    def __init__(self):
        self.safe_patterns = SAFE_COMMANDS
        self.confirm_patterns = CONFIRM_COMMANDS
        self.forbidden_regex = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_PATTERNS]
    
    def classify(self, command: str) -> Tuple[RiskLevel, Optional[CommandPattern], str]:
        """分类命令"""
        # 检查禁止模式
        for pattern in self.forbidden_regex:
            if pattern.search(command):
                return RiskLevel.FORBIDDEN, None, f"匹配禁止模式: {pattern.pattern}"
        
        # 检查安全白名单
        for pattern in self.safe_patterns:
            if pattern.matches(command):
                if self._validate_args(command, pattern):
                    return RiskLevel.SAFE, pattern, ""
        
        # 检查需确认列表
        for pattern in self.confirm_patterns:
            if pattern.matches(command):
                return pattern.risk_level, pattern, ""
        
        # Default-Deny
        return RiskLevel.FORBIDDEN, None, "命令不在白名单中（Default-Deny）"
    
    def _validate_args(self, command: str, pattern: CommandPattern) -> bool:
        """验证参数安全性"""
        parts = command.split()
        for part in parts[1:]:
            if ".." in part:
                return False
            if part.startswith("-") and pattern.allowed_args:
                if not any(part.startswith(a) for a in pattern.allowed_args):
                    return False
        return True


# === Docker沙箱模块 ===

@dataclass
class SandboxConfig:
    """沙箱配置"""
    image: str = "nanobot-sandbox:latest"
    memory_limit: str = "512m"
    cpu_quota: int = 50000
    network_mode: str = "none"
    max_execution_time: int = 300


class DockerSandbox:
    """Docker 沙箱执行器"""
    
    def __init__(self, config: SandboxConfig = None):
        self.config = config or SandboxConfig()
        self._docker_available: Optional[bool] = None
    
    async def check_docker(self) -> bool:
        """检查 Docker 是否可用"""
        if self._docker_available is not None:
            return self._docker_available
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
            self._docker_available = proc.returncode == 0
        except Exception:
            self._docker_available = False
        return self._docker_available
    
    async def execute(
        self,
        command: str,
        working_dir: str,
        network_required: bool = False
    ) -> Dict[str, Any]:
        """在 Docker 沙箱中执行命令"""
        if not await self.check_docker():
            raise RuntimeError("Docker 不可用")
        
        # 检查是否是写入操作（路径以 docker_output 结尾）
        is_write_mode = working_dir.endswith("/docker_output") or working_dir.endswith("\\docker_output")
        # 如果是写入模式，确保目录存在
        if is_write_mode:
            import os
            os.makedirs(working_dir, exist_ok=True)
            mount_mode = "rw"  # 可写
        else:
            mount_mode = "ro"  # 只读

        network = "bridge" if network_required else self.config.network_mode
        
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--network", network,
            "--memory", self.config.memory_limit,
            "--memory-swap", self.config.memory_limit,
            "--cpu-quota", str(self.config.cpu_quota),
            "--pids-limit", "100",
            "--security-opt", "no-new-privileges:true",
            "--cap-drop", "ALL",
            "-v", f"{working_dir}:/workspace:{mount_mode}",
            "-w", "/workspace",
            self.config.image,
            "/bin/sh", "-c", command
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.config.max_execution_time
            )
            
            return {
                "success": proc.returncode == 0,
                "stdout": stdout.decode('utf-8', errors='replace')[:100000],
                "stderr": stderr.decode('utf-8', errors='replace')[:10000],
                "exit_code": proc.returncode
            }
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行超时（>{self.config.max_execution_time}秒）",
                "exit_code": -1
            }

# ==================== ExecTool 主类 ====================

@dataclass
class ExecResult:
    """执行结果"""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    risk_level: str
    confirmed: bool
    security_blocked: bool = False
    block_reason: str = ""


class ExecTool(Tool):
    """
    分层安全执行器
    集成：安全分类 + Docker沙箱 + 队列式确认
    """
    
    def __init__(self, sandbox_config: Optional[SandboxConfig] = None):
        self.classifier = SecurityClassifier()
        self.sandbox = DockerSandbox(sandbox_config)
        self.confirm = ConfirmManager()
        self._default_channel = None
        self._default_chat_id = None
        self.session_key = None
        
        # 统计
        self.stats = {
            "total": 0,
            "blocked": 0,
            "confirmed": 0,
            "denied": 0,
            "timeout": 0
        }
        
        # 回调注入点
        self.send_message_callback: Optional[Callable[[str, str, str], asyncio.Future]] = None
    
    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return """安全命令执行工具，支持沙箱执行和用户确认。
        - 读取模式：传入普通目录路径，如 "/home/user/project" 或 "C:\\Users\\Project"，该目录将以只读方式挂载
        - 写入模式：传入 "docker_output" 目录路径，如 "/home/user/project/docker_output" 或 "C:\\Users\\Project\\docker_output"，该目录将自动创建并以可写方式挂载
        - 注意：docker_output 目录由工具自动创建，无需手动创建
        - 示例读取: command="cat file.txt" 或 "type file.txt", working_dir="/home/user/project" 或 "C:\\Users\\Project"
        - 示例写入: command="echo 'hello' > new_file.txt" 或 "echo hello > new_file.txt", working_dir="/home/user/project/docker_output" 或 "C:\\Users\\Project\\docker_output"
        - 支持安全分类和用户确认机制"""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的shell命令"
                },
                "working_dir": {
                    "type": "string", 
                    "description": """工作目录路径。
                    - 读取操作：传入目标目录路径，如 '/home/user/project'
                    - 写入操作：传入目标目录下的'docker_output'子目录，如 '/home/user/project/docker_output'
                    - docker_output目录将由工具自动创建"""
                }
            },
            "required": ["command"]
        }

    @property
    def exclusive(self) -> bool:
        return True  # 命令执行应该是独占的

    def set_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Set the current message context."""
        self._default_channel = channel
        self._default_chat_id = chat_id
        if self._default_channel and self._default_chat_id:
           self.session_key = f"{self._default_channel}:{self._default_chat_id}"

    def set_send_message_callback(self, callback: Callable[[str, str, str], asyncio.Future]):
        """设置发送消息的回调（由 AgentLoop 注入）"""
        self.send_message_callback = callback
        # 同时设置到 ConfirmManager
        self.confirm.set_send_prompt_callback(callback)
    
    async def execute(
        self,
        command: str,
        working_dir: Optional[str] = None,
        **kwargs: Any  # 接受其他参数，保持兼容性
    ) -> str:
        """
        执行命令入口，返回字符串结果
        
        Returns:
            执行结果字符串（成功或错误信息）
        """
        import time
        start_time = time.time()
        
        self.stats["total"] += 1
        working_dir = working_dir or os.getcwd()
        
        # === Step 1: 安全分类 ===
        risk_level, pattern, block_reason = self.classifier.classify(command)
        
        if risk_level == RiskLevel.FORBIDDEN:
            self.stats["blocked"] += 1
            return f"[SECURITY] 命令被拒绝: {block_reason}"
        
        # === Step 2: 确认流程（如需要）===
        requires_confirm = risk_level in (RiskLevel.NORMAL, RiskLevel.DANGEROUS)
        
        if requires_confirm:
            # 请求确认（队列式，会挂起等待）
            result = await self.confirm.request_confirm(
                channel=self._default_channel,
                chat_id=self._default_chat_id,
                command=command,
                risk_level=risk_level.name,
                timeout=60 if risk_level == RiskLevel.NORMAL else 120
            )
            
            if result == ConfirmResult.TIMEOUT:
                self.stats["timeout"] += 1
                return "[SECURITY] 确认超时，命令已取消"
            
            if result == ConfirmResult.DENY:
                self.stats["denied"] += 1
                return "[SECURITY] 用户拒绝执行"
        
        # === Step 3: Docker 沙箱执行 ===
        try:
            sandbox_result = await self.sandbox.execute(
                command=command,
                working_dir=working_dir,
                network_required=pattern.requires_network if pattern else False
            )
            
            # 格式化输出为字符串
            output = []
            if sandbox_result["stdout"]:
                output.append(sandbox_result["stdout"])
            if sandbox_result["stderr"]:
                output.append(f"[stderr] {sandbox_result['stderr']}")
            
            if sandbox_result["exit_code"] != 0:
                output.append(f"[exit code: {sandbox_result['exit_code']}]")
            
            return "\n".join(output) if output else "(无输出)"
            
        except Exception as e:
            return f"[ERROR] 执行失败: {str(e)}"
    def get_stats(self) -> Dict[str, int]:
        """获取执行统计"""
        return self.stats.copy()
    
    def cancel_session(self, channel: str, chat_id: str):
        """取消会话的所有待处理确认"""
        self.confirm.cancel_session(channel, chat_id)