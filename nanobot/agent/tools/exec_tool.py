"""
全新 ExecTool - 分层安全执行器
包含：安全分类、Docker沙箱、队列式确认管理
"""

import asyncio
import os
from pathlib import Path
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
from loguru import logger


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
        network_required: bool = False,
        mount_mode: str = "ro"
    ) -> Dict[str, Any]:
        """在 Docker 沙箱中执行命令"""
        if not await self.check_docker():
            raise RuntimeError("Docker 不可用")
        
        network = "bridge" if network_required else self.config.network_mode
        
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--tmpfs", "/tmp:size=100m,noexec,nosuid",  # 内存临时文件，自动清理
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
    
    def __init__(
            self, 
            sandbox_config: Optional[SandboxConfig] = None,
            working_dir: str | None = None,
            allowed_base_dirs: Optional[List[str]] = None,
            confirm:ConfirmManager = None
    ):
        self.classifier = SecurityClassifier()
        self.sandbox = DockerSandbox(sandbox_config)
        self.confirm = confirm or ConfirmManager()

        self.working_dir = working_dir
        self.allowed_base_dirs = list(allowed_base_dirs or [])
        if self.working_dir not in self.allowed_base_dirs:
            self.allowed_base_dirs.append(self.working_dir)

        self._default_channel = None
        self._default_chat_id = None
        self.session_key = None
        
        # 回调注入点
        self.send_message_callback: Optional[Callable[[str, str, str], asyncio.Future]] = None
    
    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return """安全命令执行工具（Docker Linux 沙箱），支持沙箱执行和用户确认。
        - 读取模式：传入普通目录路径，该目录将以只读方式挂载
        - 写入模式：传入目标目录下的 "docker_output" 目录路径，如目标目录是 "C:\\Users\\Project", 则传入 "C:\\Users\\Project\\docker_output", "docker_output" 目录将自动创建并以可写方式挂载
        - 注意：docker_output 目录由工具自动创建，无需手动创建
        - 示例读取: command="cat file.txt" 或 "type file.txt", working_dir="C:\\Users\\Project"
        - 示例写入: command="echo 'hello' > new_file.txt" 或 "echo hello > new_file.txt", working_dir="C:\\Users\\Project\\docker_output"
        - """

    @property
    def parameters(self) -> dict[str, Any]:
        bases = ", ".join(self.allowed_base_dirs) if self.allowed_base_dirs else "未设置"
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的shell命令，如 'ls -la' 或 'cat file.txt'，所有命令必须是 Linux 格式"
                },
                "working_dir": {
                    "type": "string", 
                    "description": f"""工作目录，需要是绝对路径。首先要判断是读操作还是写入操作，然后根据以下规则生成路径：
                    - 读取操作：传入目标目录路径
                    - 写入操作：传入目标目录下的'docker_output'子目录
                    - docker_output目录将由工具自动创建，不需要手动创建
                    - 允许的基目录:{bases}"""
                }
            },
            "required": ["command"]
        }

    @property
    def exclusive(self) -> bool:
        return False  # 命令执行应该是独占的

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
        working_dir: str | None = None,
        **kwargs: Any,  # 接受其他参数，保持兼容性
        
    ) -> str:
        """
        执行命令入口，返回字符串结果
        
        Returns:
            执行结果字符串（成功或错误信息）
        """

        cwd = working_dir or self.working_dir
        # if not Path(cwd).is_dir():
        #     return f"[ERROR] working_dir 必须是目录，不能是文件: {cwd}"
        
        # 安全分类
        risk_level, pattern, block_reason = self.classifier.classify(command)
        
        if risk_level == RiskLevel.FORBIDDEN:
            return f"[SECURITY] 命令被拒绝: {block_reason}"

        # 验证目录合法性
        real_path, is_valid = self._validate_path(cwd)
        if not is_valid:
            allowed_list = ", ".join(self.allowed_base_dirs)
            return f"[SECURITY] 工作目录 '{cwd}' 不在允许范围内。允许的目录: {allowed_list}"
        
        # 使用规范化后的路径
        cwd = real_path

        # 检查是否是写入操作（路径以 docker_output 结尾）
        is_write_mode = cwd.rstrip(os.sep).endswith("docker_output")
        # 如果是写入模式，确保目录存在
        if is_write_mode:
            os.makedirs(cwd, exist_ok=True)
            mount_mode = "rw"  # 可写
        else:
            mount_mode = "ro"  # 只读


        # 确认流程（如需要）
        requires_confirm = risk_level in (RiskLevel.NORMAL, RiskLevel.DANGEROUS)
        logger.info("requires_confirm: {}", requires_confirm)
        
        if requires_confirm:
            # 请求确认（队列式，会挂起等待）
            result = await self.confirm.request_confirm(
                channel=self._default_channel,
                chat_id=self._default_chat_id,
                command=command,
                risk_level=risk_level.name,
                timeout=60 if risk_level == RiskLevel.NORMAL else 120
            )
            logger.info("requires_confirm_result: {}", result)
            
            if result == ConfirmResult.TIMEOUT:
                return "[SECURITY] 确认超时，命令已取消"
            
            if result == ConfirmResult.DENY:
                return "[SECURITY] 用户拒绝执行"
        
        # Docker 沙箱执行 
        try:
            sandbox_result = await self.sandbox.execute(
                command=command,
                working_dir=cwd,
                network_required=pattern.requires_network if pattern else False,
                mount_mode=mount_mode
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
    
    def _validate_path(self, target_dir: str) -> Tuple[str, bool]:
        """简化版：保持原始路径，验证时统一用 Path.resolve()"""
        try:
            # 展开 ~
            expanded = os.path.expanduser(target_dir)
            
            # 获取绝对路径（保持系统原生格式）
            abs_path = Path(expanded).resolve()
            
            # 验证（同样转换基目录）
            for base in self.allowed_base_dirs:
                if not base:
                    continue
                
                base_abs = Path(os.path.expanduser(base)).resolve()
                
                # 检查是否以 base 开头（字符串检查，注意分隔符）
                base_str = str(base_abs)
                target_str = str(abs_path)
                
                # 统一使用正斜杠比较
                if target_str.replace("\\", "/").startswith(base_str.replace("\\", "/")):
                    return str(abs_path), True
            
            return str(abs_path), False
            
        except Exception:
            return target_dir, False

    def cancel_session(self, channel: str, chat_id: str):
        """取消会话的所有待处理确认"""
        self.confirm.cancel_session(channel, chat_id)