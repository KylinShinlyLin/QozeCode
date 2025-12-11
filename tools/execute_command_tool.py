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
def execute_command(command: str, timeout: int = 360) -> str:
    """Execute a command in the current system environment and return the output with real-time progress.
    
    Args:
        command: The command to execute (e.g., "ls -la", "python script.py", "npm install")
        timeout: Maximum execution time in seconds (default: 3600)
    
    Returns:
        The command output including both stdout and stderr
    """

    try:
        # 使用 subprocess.Popen 来实时获取输出
        command_str = command[:66]
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

        with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                CustomTimeElapsedColumn(style="rgb(65,170,65)"),
                console=console,
                transient=False
        ) as progress:
            task = progress.add_task(
                f"[bold dim cyan] 正在执行: {command[:66]}{'...' if len(command) > 66 else ''} [/bold dim cyan]",
                total=None)
            try:

                while True:
                    current_time = time.time()
                    elapsed_time = current_time - start_time

                    # 检查是否超时
                    if elapsed_time > timeout:
                        process.kill()

                        progress.update(task,
                                        description=f"[bold red]✗ ⚠️ 命令执行超时 ({timeout}秒) {command_str} [/bold red]")
                        return f"❌ 命令执行超时 ({timeout}秒)"

                    # 非阻塞读取输出（不显示）
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break

                    if output:
                        output_lines.append(output.rstrip())
                # 等待进程完成
                return_code = process.wait()

                if return_code == 0:
                    progress.update(task,
                                    description=f"[bold green]✓[/bold green] [bold dim cyan] command: {command_str} [/bold dim cyan]")
                else:
                    progress.update(task, description=f"[bold red]✗ 执行失败: {command_str} [/bold red]")
                full_output = '\n'.join(output_lines)
                return full_output

            except Exception as e:
                progress.update(task, description=f"[bold red]✗ 命令执行异常: {command_str} [/bold red]")
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
