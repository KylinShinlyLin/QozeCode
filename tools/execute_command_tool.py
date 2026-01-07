import signal
import signal
import subprocess
import threading
import time
import traceback

from langchain_core.tools import tool
from rich.panel import Panel
from rich.progress import Progress, TextColumn, TimeElapsedColumn, SpinnerColumn

# 导入共享的 console 实例
from shared_console import console, CustomTimeElapsedColumn

# 定义颜色常量
CYAN = "\033[36m"
RESET = "\033[0m"


@tool
def execute_command(command: str, timeout: int = 120) -> str:
    """Execute a command in the current system environment and return the output with real-time progress.
    
    Args:
        command: The command to execute (e.g., "ls -la", "python script.py", "npm install")
        timeout: Maximum execution time in seconds (default: 3600)
    
    Returns:
        The command output including both stdout and stderr
    """

    try:
        # 使用 subprocess.Popen 来实时获取输出
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
            preexec_fn=None if subprocess.os.name == 'nt' else lambda: signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        )

        output_lines = []
        start_time = time.time()

        def kill_process_after_timeout():
            """在超时后终止进程"""
            time.sleep(timeout)
            if process.poll() is None:  # 进程仍在运行
                try:
                    process.terminate()
                    time.sleep(2)  # 给进程2秒时间优雅退出
                    if process.poll() is None:
                        process.kill()  # 强制终止
                except:
                    pass

        # 启动超时监控线程
        timeout_thread = threading.Thread(target=kill_process_after_timeout, daemon=True)
        timeout_thread.start()

        try:

            while True:
                current_time = time.time()
                elapsed_time = current_time - start_time

                # 检查是否超时
                if elapsed_time > timeout:
                    process.kill()
                    return f"❌ 命令执行超时 ({timeout}秒)"

                # 非阻塞读取输出（不显示）
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break

                if output:
                    output_lines.append(output.rstrip())
            # 等待进程完成
            full_output = '\n'.join(output_lines)
            return_code = process.wait()
            if return_code != 0:
                full_output = "[RUN_FAILED]" + full_output
            return full_output
        except Exception as e:
            traceback.print_exc()  # 打印完整堆栈到控制台
            return f"❌ 命令执行异常: {str(e)}"

    except Exception as e:
        error_panel = Panel(
            f"❌ 执行命令时发生错误\n"
            f"命令: [cyan]{command}[/cyan]\n"
            f"错误: [red]{str(e)}[/red]",
            title="[bold red]系统错误[/bold red]",
            border_style="red",
            padding=(0, 1)
        )
        console.print(error_panel)
        return f"❌ 执行命令时发生错误: {str(e)}"
