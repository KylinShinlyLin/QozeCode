import signal
import subprocess
import threading
import time
import json
from typing import Optional, Dict, Any

from langchain_core.tools import tool
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel

# 导入共享的 console 实例
from shared_console import console


@tool
def execute_command(command: str, timeout: int = 600) -> str:
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

        # 使用Progress显示执行状态
        with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                TimeElapsedColumn(),
                refresh_per_second=30,
                console=console,
                transient=False  # 保留进度条直到完成
        ) as progress:

            # 创建进度任务
            task = progress.add_task(f"正在执行: {command[:50]}{'...' if len(command) > 50 else ''}", total=None)

            try:
                # 静默收集输出，不显示内容
                while True:
                    current_time = time.time()
                    elapsed_time = current_time - start_time

                    # 检查是否超时
                    if elapsed_time > timeout:
                        progress.update(task,
                                        description=f"[red]执行超时: {command[:40]}{'...' if len(command) > 40 else ''}")
                        process.kill()

                        # 显示超时结果Panel
                        timeout_panel = Panel(
                            f"⚠️ 命令执行超时 ({timeout}秒)\n"
                            f"命令: [cyan]{command}[/cyan]",
                            title="[bold red]执行超时[/bold red]",
                            border_style="red",
                            padding=(0, 1)
                        )
                        console.print(timeout_panel)
                        return f"❌ 命令执行超时 ({timeout}秒)"

                    # 非阻塞读取输出（不显示）
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break

                    if output:
                        output_lines.append(output.rstrip())

                    # 更新进度描述
                    progress.update(task,
                                    description=f"  正在执行: [cyan]{command[:40]}{'...' if len(command) > 40 else ''}[cyan] ({len(output_lines)}行)")

                # 等待进程完成
                return_code = process.wait()
                # execution_time = time.time() - start_time

                # 更新最终状态
                if return_code == 0:
                    progress.update(task,
                                    description=f"  ✅ [cyan] {command[:40]}{'...' if len(command) > 40 else ''}[cyan]")
                else:
                    progress.update(task,
                                    description=f"  ❌ [cyan] {command[:40]}{'...' if len(command) > 40 else ''}[cyan]")

                # 收集完整输出
                full_output = '\n'.join(output_lines)

                return full_output

            except KeyboardInterrupt:
                progress.update(task,
                                description=f"[yellow]⚠️ 用户中断: {command[:40]}{'...' if len(command) > 40 else ''}")
                process.terminate()

                interrupt_panel = Panel(
                    f"⚠️ 用户中断命令执行\n"
                    f"命令: [cyan]{command}[/cyan]\n"
                    f"耗时: [yellow]{time.time() - start_time:.2f}秒[/yellow]",
                    title="[bold yellow]执行中断[/bold yellow]",
                    border_style="yellow",
                    padding=(0, 1)
                )
                console.print(interrupt_panel)
                return "⚠️ 用户中断命令执行"

            except Exception as e:
                progress.update(task,
                                description=f"[red]❌ 执行异常: {command[:40]}{'...' if len(command) > 40 else ''}")

                error_panel = Panel(
                    f"❌ 命令执行异常\n"
                    f"命令: [cyan]{command}[/cyan]\n"
                    f"错误: [red]{str(e)}[/red]\n"
                    f"耗时: [yellow]{time.time() - start_time:.2f}秒[/yellow]",
                    title="[bold red]执行异常[/bold red]",
                    border_style="red",
                    padding=(0, 1)
                )
                console.print(error_panel)
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


@tool
def curl(
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
        follow_redirects: bool = True,
        verify_ssl: bool = True
) -> str:
    """Execute HTTP requests using curl command with enhanced functionality.
    
    Args:
        url: The URL to request
        method: HTTP method (GET, POST, PUT, DELETE, PATCH, etc.)
        headers: Optional dictionary of headers to include
        data: Raw data to send in request body
        json_data: JSON data to send (will be serialized and set Content-Type)
        timeout: Request timeout in seconds (default: 30)
        follow_redirects: Whether to follow redirects (default: True)
        verify_ssl: Whether to verify SSL certificates (default: True)
    
    Returns:
        The HTTP response including headers and body
    """

    try:
        # 构建 curl 命令
        curl_cmd = ["curl"]

        # 添加基本选项
        curl_cmd.extend(["-v", "-s", "-S"])  # verbose, silent, show errors
        curl_cmd.extend(["--max-time", str(timeout)])

        # 设置 HTTP 方法
        if method.upper() != "GET":
            curl_cmd.extend(["-X", method.upper()])

        # 处理重定向
        if follow_redirects:
            curl_cmd.append("-L")

        # 处理 SSL 验证
        if not verify_ssl:
            curl_cmd.append("-k")

        # 添加头部信息
        if headers:
            for key, value in headers.items():
                curl_cmd.extend(["-H", f"{key}: {value}"])

        # 处理 JSON 数据
        if json_data:
            curl_cmd.extend(["-H", "Content-Type: application/json"])
            curl_cmd.extend(["-d", json.dumps(json_data)])
        elif data:
            curl_cmd.extend(["-d", data])

        # 添加 URL
        curl_cmd.append(url)

        start_time = time.time()

        # 使用Progress显示请求状态
        with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                TimeElapsedColumn(),
                console=console,
                transient=False  # 保留进度条直到完成
        ) as progress:

            # 创建进度任务
            task = progress.add_task(f"HTTP请求: {method.upper()} {url[:50]}{'...' if len(url) > 50 else ''}",
                                     total=None)

            try:
                # 执行 curl 命令
                process = subprocess.Popen(
                    curl_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )

                # 等待命令完成，同时更新进度
                while process.poll() is None:
                    elapsed_time = time.time() - start_time

                    # 检查超时
                    if elapsed_time > timeout:
                        progress.update(task,
                                        description=f"[red]请求超时: {method.upper()} {url[:40]}{'...' if len(url) > 40 else ''}")
                        process.kill()

                        timeout_panel = Panel(
                            f"⚠️ HTTP请求超时 ({timeout}秒)\n"
                            f"请求: [cyan]{method.upper()} {url}[/cyan]",
                            title="[bold red]请求超时[/bold red]",
                            border_style="red",
                            padding=(0, 1)
                        )
                        console.print(timeout_panel)
                        return f"❌ HTTP请求超时 ({timeout}秒)"

                    # 更新进度描述
                    progress.update(task,
                                    description=f"HTTP请求: {method.upper()} {url[:40]}{'...' if len(url) > 40 else ''}")
                    time.sleep(0.5)

                # 获取结果
                stdout, stderr = process.communicate()
                return_code = process.returncode
                execution_time = time.time() - start_time

                # 更新最终状态
                if return_code == 0:
                    progress.update(task,
                                    description=f"[green]✅ 请求成功: {method.upper()} {url[:40]}{'...' if len(url) > 40 else ''}")
                else:
                    progress.update(task,
                                    description=f"[red]❌ 请求失败: {method.upper()} {url[:40]}{'...' if len(url) > 40 else ''}")

                # 显示请求结果Panel
                if return_code == 0:
                    result_panel = Panel(
                        f"✅ HTTP请求成功\n"
                        f"请求: [cyan]{method.upper()} {url}[/cyan]\n"
                        f"耗时: [green]{execution_time:.2f}秒[/green]\n"
                        f"响应大小: [blue]{len(stdout)}字符[/blue]",
                        title="[bold green]请求成功[/bold green]",
                        border_style="green",
                        padding=(0, 1)
                    )
                else:
                    result_panel = Panel(
                        f"❌ HTTP请求失败\n"
                        f"请求: [cyan]{method.upper()} {url}[/cyan]\n"
                        f"返回码: [red]{return_code}[/red]\n"
                        f"耗时: [yellow]{execution_time:.2f}秒[/yellow]",
                        title="[bold red]请求失败[/bold red]",
                        border_style="red",
                        padding=(0, 1)
                    )

                console.print(result_panel)

                # 返回完整响应
                if stderr:
                    return f"{stdout}\n\n--- STDERR ---\n{stderr}"
                return stdout

            except KeyboardInterrupt:
                progress.update(task,
                                description=f"[yellow]⚠️ 用户中断: {method.upper()} {url[:40]}{'...' if len(url) > 40 else ''}")
                if 'process' in locals():
                    process.terminate()

                interrupt_panel = Panel(
                    f"⚠️ 用户中断HTTP请求\n"
                    f"请求: [cyan]{method.upper()} {url}[/cyan]\n"
                    f"耗时: [yellow]{time.time() - start_time:.2f}秒[/yellow]",
                    title="[bold yellow]请求中断[/bold yellow]",
                    border_style="yellow",
                    padding=(0, 1)
                )
                console.print(interrupt_panel)
                return "⚠️ 用户中断HTTP请求"

            except Exception as e:
                progress.update(task,
                                description=f"[red]❌ 请求异常: {method.upper()} {url[:40]}{'...' if len(url) > 40 else ''}")

                error_panel = Panel(
                    f"❌ HTTP请求异常\n"
                    f"请求: [cyan]{method.upper()} {url}[/cyan]\n"
                    f"错误: [red]{str(e)}[/red]\n"
                    f"耗时: [yellow]{time.time() - start_time:.2f}秒[/yellow]",
                    title="[bold red]请求异常[/bold red]",
                    border_style="red",
                    padding=(0, 1)
                )
                console.print(error_panel)
                return f"❌ HTTP请求异常: {str(e)}"

    except Exception as e:
        error_panel = Panel(
            f"❌ 发送HTTP请求时发生错误\n"
            f"请求: [cyan]{method.upper()} {url}[/cyan]\n"
            f"错误: [red]{str(e)}[/red]",
            title="[bold red]系统错误[/bold red]",
            border_style="red",
            padding=(0, 1)
        )
        console.print(error_panel)
        return f"❌ 发送HTTP请求时发生错误: {str(e)}"
