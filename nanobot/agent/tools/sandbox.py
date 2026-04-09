
# === Docker沙箱模块 ===

# @dataclass
# class SandboxConfig:
#     """沙箱配置"""
#     image: str = "nanobot-sandbox:latest"
#     memory_limit: str = "512m"
#     cpu_quota: int = 50000
#     network_mode: str = "none"
#     max_execution_time: int = 300


# class DockerSandbox:
#     """Docker 沙箱执行器"""
    
#     def __init__(self, config: SandboxConfig = None):
#         self.config = config or SandboxConfig()
#         self._docker_available: Optional[bool] = None
    
#     async def check_docker(self) -> bool:
#         """检查 Docker 是否可用"""
#         if self._docker_available is not None:
#             return self._docker_available
        
#         try:
#             proc = await asyncio.create_subprocess_exec(
#                 "docker", "version",
#                 stdout=asyncio.subprocess.DEVNULL,
#                 stderr=asyncio.subprocess.DEVNULL
#             )
#             await asyncio.wait_for(proc.wait(), timeout=5)
#             self._docker_available = proc.returncode == 0
#         except Exception:
#             self._docker_available = False
#         return self._docker_available
    
    # async def execute(
    #     self,
    #     command: str,
    #     working_dir: str,
    #     network_required: bool = False,
    #     mount_mode: str = "ro"
    # ) -> Dict[str, Any]:
    #     """在 Docker 沙箱中执行命令"""
    #     if not await self.check_docker():
    #         raise RuntimeError("Docker 不可用")
        
    #     network = "bridge" if network_required else self.config.network_mode
        
    #     docker_cmd = [
    #         "docker", "run",
    #         "--rm",
    #         "--tmpfs", "/tmp:size=100m,noexec,nosuid",  # 内存临时文件，自动清理
    #         "--network", network,
    #         "--memory", self.config.memory_limit,
    #         "--memory-swap", self.config.memory_limit,
    #         "--cpu-quota", str(self.config.cpu_quota),
    #         "--pids-limit", "100",
    #         "--security-opt", "no-new-privileges:true",
    #         "--cap-drop", "ALL",
    #         "-v", f"{working_dir}:/workspace:{mount_mode}",
    #         "-w", "/workspace",
    #         self.config.image,
    #         "/bin/sh", "-c", command
    #     ]
        
    #     proc = await asyncio.create_subprocess_exec(
    #         *docker_cmd,
    #         stdout=asyncio.subprocess.PIPE,
    #         stderr=asyncio.subprocess.PIPE
    #     )
        
    #     try:
    #         stdout, stderr = await asyncio.wait_for(
    #             proc.communicate(),
    #             timeout=self.config.max_execution_time
    #         )
            
    #         return {
    #             "success": proc.returncode == 0,
    #             "stdout": stdout.decode('utf-8', errors='replace')[:100000],
    #             "stderr": stderr.decode('utf-8', errors='replace')[:10000],
    #             "exit_code": proc.returncode
    #         }
    #     except asyncio.TimeoutError:
    #         proc.kill()
    #         return {
    #             "success": False,
    #             "stdout": "",
    #             "stderr": f"执行超时（>{self.config.max_execution_time}秒）",
    #             "exit_code": -1
    #         }
