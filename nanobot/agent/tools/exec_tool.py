# """
# 全新 ExecTool - 分层安全执行器
# 包含：安全分类、Docker沙箱、队列式确认管理
# """

# import asyncio
# import os
# from pathlib import Path
# import re
# import hashlib
# import tempfile
# import shutil
# import sys
# from dataclasses import dataclass, field
# from datetime import datetime, timedelta
# from enum import Enum, auto
# from fnmatch import fnmatch
# from typing import Optional, Dict, List, Tuple, Callable, Deque, Any
# from collections import deque
# from nanobot.agent.tools.confirm import ConfirmManager, ConfirmResult
# from nanobot.agent.tools.base import Tool
# from loguru import logger


# # === 安全分类模块 ===

# class RiskLevel(Enum):
#     """风险等级"""
#     SAFE = auto()
#     NORMAL = auto()
#     DANGEROUS = auto()
#     FORBIDDEN = auto()


# @dataclass(frozen=True)
# class CommandPattern:
#     """命令模式定义"""
#     name: str
#     pattern: str
#     risk_level: RiskLevel
#     allowed_args: Optional[List[str]] = None
#     requires_network: bool = False
#     max_execution_time: int = 180
    
#     def matches(self, command: str) -> bool:
#         cmd_base = command.strip().split()[0] if command.strip() else ""
#         return fnmatch(cmd_base, self.pattern)


# # 安全命令白名单
# SAFE_COMMANDS: List[CommandPattern] = [
#     CommandPattern("ls", "ls", RiskLevel.SAFE, max_execution_time=30),
#     CommandPattern("cat", "cat", RiskLevel.SAFE),
#     CommandPattern("head", "head", RiskLevel.SAFE),
#     CommandPattern("tail", "tail", RiskLevel.SAFE),
#     CommandPattern("grep", "grep", RiskLevel.SAFE),
#     CommandPattern("find", "find", RiskLevel.SAFE, max_execution_time=60),
#     CommandPattern("pwd", "pwd", RiskLevel.SAFE),
#     CommandPattern("echo", "echo", RiskLevel.SAFE),
#     CommandPattern("ps", "ps", RiskLevel.SAFE),
#     CommandPattern("df", "df", RiskLevel.SAFE),
#     CommandPattern("du", "du", RiskLevel.SAFE, max_execution_time=30),
#     CommandPattern("file", "file", RiskLevel.SAFE),
#     CommandPattern("which", "which", RiskLevel.SAFE),
#         # Windows 命令（新增）
#     CommandPattern("dir", "dir", RiskLevel.SAFE, max_execution_time=30),
#     CommandPattern("type", "type", RiskLevel.SAFE),
#     CommandPattern("cd", "cd", RiskLevel.SAFE),  # 添加 cd
#     CommandPattern("echo", "echo", RiskLevel.SAFE),
#     CommandPattern("findstr", "findstr", RiskLevel.SAFE),  # Windows 版 grep
# ]

# # 需确认命令
# CONFIRM_COMMANDS: List[CommandPattern] = [
#     CommandPattern("git", "git", RiskLevel.NORMAL, requires_network=True),
#     CommandPattern("mkdir", "mkdir", RiskLevel.NORMAL),
#     CommandPattern("touch", "touch", RiskLevel.NORMAL),
#     CommandPattern("cp", "cp", RiskLevel.NORMAL),
#     CommandPattern("mv", "mv", RiskLevel.NORMAL),
#     CommandPattern("rm", "rm", RiskLevel.NORMAL),
#     CommandPattern("chmod", "chmod", RiskLevel.NORMAL),
#     CommandPattern("curl", "curl", RiskLevel.DANGEROUS, requires_network=True),
#     CommandPattern("wget", "wget", RiskLevel.DANGEROUS, requires_network=True),
#         # Windows（新增）
#     CommandPattern("md", "md", RiskLevel.NORMAL),      # mkdir
#     CommandPattern("rd", "rd", RiskLevel.NORMAL),      # rmdir
#     CommandPattern("del", "del", RiskLevel.NORMAL),    # rm
#     CommandPattern("copy", "copy", RiskLevel.NORMAL),  # cp
#     CommandPattern("move", "move", RiskLevel.NORMAL),  # mv
#     CommandPattern("python", "python", RiskLevel.NORMAL),
#     CommandPattern("venv", "venv", RiskLevel.NORMAL),
#     CommandPattern("pip", "pip", RiskLevel.DANGEROUS, requires_network=True),
#     CommandPattern("npm", "npm", RiskLevel.DANGEROUS, requires_network=True),
# ]

# # 绝对禁止
# FORBIDDEN_PATTERNS: List[str] = [
#     r"mkfs\.",
#     r"fdisk",
#     r"dd\s+if=/dev/(zero|random|urandom)",
#     r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;?",
#     r"rm\s+-rf\s*/",
#     r">?\s*/etc/passwd",
#     r">?\s*/etc/shadow",

#     r"format\s+", r"fdisk", r"diskpart",
#     r"reg\s+(add|delete|import|export)",
#     r"net\s+(user|localgroup|share)",
#     r"sc\s+(config|delete)",
#     r"schtasks",
#     r"powershell.*-ExecutionPolicy\s+Bypass",
#     r"Invoke-Expression", r"IEX",
#     r"certutil.*-urlcache",  # 下载工具
#     r"bitsadmin",  # 下载工具
#     r"mshta",  # 执行脚本
#     r"rundll32",  # 执行 DLL
#     r"regsvr32",  # 注册 DLL

#     r'^\s*env\s*$',
#     r'^\s*printenv\s*$',
#     r'^\s*set\s*$',  # Windows 环境变量显示
# ]


# class SecurityClassifier:
#     """命令安全分类器"""
    
#     # 1. 控制字符（空字节、换行等）
#     CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
    
#     # 2. 复合命令操作符（移除有问题的 \\$）
#     COMPOUND_PATTERN = re.compile(
#         r'&&|'           # 逻辑与
#         r'\|\||'         # 逻辑或  
#         r';|'            # 分号
#         r'\||'           # 管道
#         r'>>|<<|'        # 双重重定向
#         r'>|<|'          # 单重定向
#         r'\$\(|'         # 命令替换 $()
#         r'\$\{|'         # 变量扩展 ${
#         r'`|'            # 反引号
#         r'[\n\r]'        # 换行符（关键！）
#     )
    
#     # 3. 路径遍历（增强版）
#     PATH_TRAVERSAL_PATTERN = re.compile(
#         r'\.\./|/\.\./|^\.\./|\.\.$|'
#         r'\.\.\\|\\\.\.\\|^\.\.\\|'
#         r'\.\.//|//\.\./|'
#         r'[.]{3,}'
#     )

#     def __init__(self):
#         self.safe_patterns = SAFE_COMMANDS
#         self.confirm_patterns = CONFIRM_COMMANDS
#         self.forbidden_regex = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_PATTERNS]
    
#     def classify(self, command: str) -> Tuple[RiskLevel, Optional[CommandPattern], str]:
#         """分类命令"""
#         # 检测控制字符
#         ctrl_match = self.CONTROL_CHARS.search(command)
#         if ctrl_match:
#             char = repr(ctrl_match.group())
#             return RiskLevel.FORBIDDEN, None, f"[控制字符] 禁止: {char}"
        
#         # 检测复合命令
#         compound_match = self.COMPOUND_PATTERN.search(command)
#         if compound_match:
#             return RiskLevel.FORBIDDEN, None, "[复合命令] 禁止"
        
#         # 路径遍历检测
#         if self.PATH_TRAVERSAL_PATTERN.search(command):
#             return RiskLevel.FORBIDDEN, None, "[路径遍历] 禁止"

#         # 检查禁止模式
#         for pattern in self.forbidden_regex:
#             if pattern.search(command):
#                 return RiskLevel.FORBIDDEN, None, f"匹配禁止模式: {pattern.pattern}"
        
#         # 检查安全白名单
#         for pattern in self.safe_patterns:
#             if pattern.matches(command):
#                 if self._validate_args(command, pattern):
#                     return RiskLevel.SAFE, pattern, ""
        
#         # 检查需确认列表
#         for pattern in self.confirm_patterns:
#             if pattern.matches(command):
#                 return pattern.risk_level, pattern, ""
        
#         # Default-Deny
#         return RiskLevel.FORBIDDEN, None, "命令不在白名单中（Default-Deny）"
    
#     def _validate_args(self, command: str, pattern: CommandPattern) -> bool:
#         """验证参数安全性"""
#         parts = command.split()
#         for part in parts[1:]:
#             if ".." in part:
#                 return False
#             if part.startswith("-") and pattern.allowed_args:
#                 if not any(part.startswith(a) for a in pattern.allowed_args):
#                     return False
#         return True


# # ==================== ExecTool 主类 ====================

# @dataclass
# class ExecResult:
#     """执行结果"""
#     success: bool
#     stdout: str
#     stderr: str
#     exit_code: int
#     execution_time: float
#     risk_level: str
#     confirmed: bool
#     security_blocked: bool = False
#     block_reason: str = ""


# class ExecTool(Tool):
#     """
#     分层安全执行器
#     集成：安全分类 +  队列式确认
#     """
    
#     def __init__(
#             self, 
#             # sandbox_config: Optional[SandboxConfig] = None,
#             working_dir: str | None = None,
#             allowed_base_dirs: Optional[List[str]] = None,
#             confirm:ConfirmManager = None,
#             timeout: int = 60,
#             path_append: str = "",
#     ):
#         self.classifier = SecurityClassifier()
#         # self.sandbox = DockerSandbox(sandbox_config)
#         self.confirm = confirm or ConfirmManager()
#         self.timeout = timeout
#         self.path_append = path_append

#         self.working_dir = working_dir
#         self.allowed_base_dirs = list(allowed_base_dirs or [])
#         if self.working_dir not in self.allowed_base_dirs:
#             self.allowed_base_dirs.append(self.working_dir)

#         self._default_channel = None
#         self._default_chat_id = None
#         self.session_key = None
        
#         # 回调注入点
#         self.send_message_callback: Optional[Callable[[str, str, str], asyncio.Future]] = None
    
#     _MAX_OUTPUT = 10_000

#     @property
#     def name(self) -> str:
#         return "exec"

#     @property
#     def description(self) -> str:
#         return """安全命令执行工具"""

#     @property
#     def parameters(self) -> dict[str, Any]:
#         bases = ", ".join(self.allowed_base_dirs) if self.allowed_base_dirs else "未设置"
#         return {
#             "type": "object",
#             "properties": {
#                 "command": {
#                     "type": "string",
#                     "description": "shell命令, 只支持单条命令，不支持 && 或 | 等复合命令,命令中不要包含路径"
#                 },
#                 "working_dir": {
#                     "type": "string", 
#                     "description": f"""工作目录（可选，必须为绝对路径），必须是以下目录之一（或其子目录）: {bases}"""
#                 }
#             },
#             "required": ["command"]
#         }

#     @property
#     def exclusive(self) -> bool:
#         return False  # 命令执行应该是独占的

#     def set_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
#         """Set the current message context."""
#         self._default_channel = channel
#         self._default_chat_id = chat_id
#         if self._default_channel and self._default_chat_id:
#            self.session_key = f"{self._default_channel}:{self._default_chat_id}"

#     def set_send_message_callback(self, callback: Callable[[str, str, str], asyncio.Future]):
#         """设置发送消息的回调（由 AgentLoop 注入）"""
#         self.send_message_callback = callback
#         # 同时设置到 ConfirmManager
#         self.confirm.set_send_prompt_callback(callback)

#     async def execute(
#         self,
#         command: str,
#         working_dir: str | None = None,
        
#         **kwargs: Any,  # 接受其他参数，保持兼容性
        
#     ) -> str:
#         """
#         执行命令入口，返回字符串结果
        
#         Returns:
#             执行结果字符串（成功或错误信息）
#         """

#         cwd = working_dir or self.working_dir
        
#         # 安全分类
#         risk_level, pattern, block_reason = self.classifier.classify(command)
        
#         if risk_level == RiskLevel.FORBIDDEN:
#             return f"[SECURITY] 命令被拒绝: {block_reason}"

#         # 验证目录合法性
#         real_path, is_valid = self._validate_path(cwd)
#         if not is_valid:
#             allowed_list = ", ".join(self.allowed_base_dirs)
#             return f"[SECURITY] 工作目录 '{cwd}' 不在允许范围内。允许的目录: {allowed_list}"
        
#         # 使用规范化后的路径
#         cwd = real_path

#         # 确认流程（如需要）
#         requires_confirm = risk_level in (RiskLevel.NORMAL, RiskLevel.DANGEROUS)
#         logger.info("requires_confirm: {}", requires_confirm)
        
#         if requires_confirm:
#             # 请求确认（队列式，会挂起等待）
#             result = await self.confirm.request_confirm(
#                 channel=self._default_channel,
#                 chat_id=self._default_chat_id,
#                 command=command,
#                 risk_level=risk_level.name,
#                 timeout=60 if risk_level == RiskLevel.NORMAL else 120
#             )
#             logger.info("requires_confirm_result: {}", result)
            
#             if result == ConfirmResult.TIMEOUT:
#                 return "[SECURITY] 确认超时，命令已取消"
            
#             if result == ConfirmResult.CANCELLED:
#                 return "[SECURITY] 确认被取消，命令已取消"
            
#             if result == ConfirmResult.DENY:
#                 return "[SECURITY] 用户拒绝执行"
        
#         env = os.environ.copy()
#         if self.path_append:
#             env["PATH"] = env.get("PATH", "") + os.pathsep + self.path_append
#         try:
#             process = await asyncio.create_subprocess_shell(
#                 command,
#                 stdout=asyncio.subprocess.PIPE,
#                 stderr=asyncio.subprocess.PIPE,
#                 cwd=cwd,
#                 env=env,
#             )

#             try:
#                 stdout, stderr = await asyncio.wait_for(
#                     process.communicate(),
#                     timeout=pattern.max_execution_time if pattern else self.timeout,
#                 )
#             except asyncio.TimeoutError:
#                 process.kill()
#                 try:
#                     await asyncio.wait_for(process.wait(), timeout=5.0)
#                 except asyncio.TimeoutError:
#                     pass
#                 finally:
#                     if sys.platform != "win32":
#                         try:
#                             os.waitpid(process.pid, os.WNOHANG)
#                         except (ProcessLookupError, ChildProcessError) as e:
#                             logger.debug("Process already reaped or not found: {}", e)
#                 return f"Error: Command timed out after {pattern.max_execution_time} seconds"

#             output_parts = []

#             if stdout:
#                 output_parts.append(stdout.decode("utf-8", errors="replace"))

#             if stderr:
#                 stderr_text = stderr.decode("utf-8", errors="replace")
#                 if stderr_text.strip():
#                     output_parts.append(f"STDERR:\n{stderr_text}")

#             output_parts.append(f"\nExit code: {process.returncode}")

#             result = "\n".join(output_parts) if output_parts else "(no output)"

#             # Head + tail truncation to preserve both start and end of output
#             max_len = self._MAX_OUTPUT
#             if len(result) > max_len:
#                 half = max_len // 2
#                 result = (
#                     result[:half]
#                     + f"\n\n... ({len(result) - max_len:,} chars truncated) ...\n\n"
#                     + result[-half:]
#                 )

#             return result

#         except Exception as e:
#             return f"Error executing command: {str(e)}"
    
#     def _validate_path(self, target_dir: str) -> Tuple[str, bool]:
#         """简化版：保持原始路径，验证时统一用 Path.resolve()"""
#         try:
#             # 展开 ~
#             expanded = os.path.expanduser(target_dir)
            
#             # 获取绝对路径（保持系统原生格式）
#             abs_path = Path(expanded).resolve()
            
#             # 验证（同样转换基目录）
#             for base in self.allowed_base_dirs:
#                 if not base:
#                     continue
                
#                 base_abs = Path(os.path.expanduser(base)).resolve()
                
#                 # 检查是否以 base 开头（字符串检查，注意分隔符）
#                 base_str = str(base_abs)
#                 target_str = str(abs_path)
                
#                 # 统一使用正斜杠比较
#                 if target_str.replace("\\", "/").startswith(base_str.replace("\\", "/")):
#                     return str(abs_path), True
            
#             return str(abs_path), False
            
#         except Exception:
#             return target_dir, False

#     def cancel_session(self, channel: str, chat_id: str):
#         """取消会话的所有待处理确认"""
#         self.confirm.cancel_session(channel, chat_id)