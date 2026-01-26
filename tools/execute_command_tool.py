import asyncio
import os
import signal
import platform
from langchain_core.tools import tool
from rich.panel import Panel

# 移除 shared_console 的直接引用，防止直接打印破坏 TUI
# from shared_console import console 

@tool
async def execute_command(command: str, timeout: int = 120) -> str:
    """Execute a command in the current system environment and return the output with real-time progress.

    Args:
        command: The command to execute (e.g., "ls -la", "python script.py", "npm install")
        timeout: Maximum execution time in seconds (default: 120)

    Returns:
        The command output including both stdout and stderr
    """
    
    # 简单的清理命令字符串
    command = command.strip()
    if not command:
        return "❌ Empty command"

    try:
        # 使用 asyncio.create_subprocess_shell 非阻塞执行
        # 设置 preexec_fn 为 setsid 以便能终止整个进程组 (Linux/macOS)
        preexec = os.setsid if platform.system() != "Windows" else None
        
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, # 将 stderr 合并到 stdout
            preexec_fn=preexec,
            limit=1024*1024 # 增加 buffer limit 防止大量输出卡死
        )

        output_lines = []
        
        async def read_stream(stream):
            while True:
                line = await stream.readline()
                if not line:
                    break
                # 解码并去除末尾换行
                decoded_line = line.decode('utf-8', errors='replace').rstrip()
                output_lines.append(decoded_line)

        # 设置超时等待
        try:
            # 等待进程完成或超时
            await asyncio.wait_for(read_stream(process.stdout), timeout=timeout)
            return_code = await asyncio.wait_for(process.wait(), timeout=5) # 给一点额外时间让进程退出
            
        except asyncio.TimeoutError:
            # 超时处理
            if platform.system() != "Windows":
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                process.terminate()
            
            return f"❌ 命令执行超时 ({timeout}秒)\n已捕获输出:\n" + "\n".join(output_lines)

        full_output = "\n".join(output_lines)
        
        if return_code != 0:
            return f"[RUN_FAILED] (Exit Code: {return_code})\n{full_output}"
            
        return full_output

    except Exception as e:
        # 不要直接 print，而是返回错误信息让 Agent 显示
        return f"❌ 执行命令时发生系统错误: {str(e)}"
