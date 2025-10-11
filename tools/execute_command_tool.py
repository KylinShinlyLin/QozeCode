import signal
import subprocess
import threading
import time
import json
from typing import Optional, Dict, Any

from langchain_core.tools import tool
from rich.live import Live
from rich.panel import Panel

# 导入共享的 console 实例
from shared_console import console


@tool
def execute_command(command: str, timeout: int = 3600) -> str:
    """Execute a command in the current system environment and return the output with real-time progress.
    
    Args:
        command: The command to execute (e.g., "ls -la", "python script.py", "npm install")
        timeout: Maximum execution time in seconds (default: 30)
    
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

        # 创建初始面板
        initial_panel = Panel(
            f"🚀 正在执行命令: [bold cyan]{command}[/bold cyan]\n\n⏳ 等待输出...",
            title="[bold yellow]命令执行[/bold yellow]",
            border_style="blue",
            padding=(0, 1)
        )

        # 使用 Live 实时显示输出
        with Live(initial_panel, console=console, refresh_per_second=10) as live:
            # 实时读取输出
            try:
                while True:
                    # 检查是否超时
                    if time.time() - start_time > timeout:
                        timeout_msg = f"\n⚠️  命令执行超时 ({timeout}秒)"
                        output_lines.append(timeout_msg)

                        # 更新面板显示超时信息
                        current_output = '\n'.join(output_lines)
                        updated_panel = Panel(
                            f"🚀 执行命令: [bold cyan]{command}[/bold cyan]\n\n"
                            f"⚠️  [bold red]执行超时[/bold red]\n\n"
                            f"\n```bash\n{current_output}\n```",
                            title="[bold red]命令执行 - 超时[/bold red]",
                            border_style="red",
                            padding=(0, 2)
                        )
                        live.update(updated_panel)
                        break

                    # 非阻塞读取
                    try:
                        output = process.stdout.readline()
                        if output == '' and process.poll() is not None:
                            break
                        if output:
                            output_lines.append(output)

                            # 实时更新面板
                            current_output = '\n'.join(output_lines)
                            execution_time = time.time() - start_time

                            updated_panel = Panel(
                                f"🚀 执行命令: [bold cyan]{command}[/bold cyan]\n\n"
                                f"⏱️  运行时间: {execution_time:.1f}秒\n\n"
                                f"\n```bash\n{current_output}\n```",
                                title="[bold yellow]命令执行中...[/bold yellow]",
                                border_style="blue",
                                padding=(0, 2)
                            )
                            live.update(updated_panel)

                    except Exception as e:
                        error_msg = f"读取输出时出错: {e}"
                        output_lines.append(error_msg)

                        # 更新面板显示错误信息
                        current_output = '\n'.join(output_lines)
                        error_panel = Panel(
                            f"🚀 执行命令: [bold cyan]{command}[/bold cyan]\n\n"
                            f"❌ [bold red]读取错误[/bold red]\n\n"
                            f"\n```bash\n{current_output}\n```",
                            title="[bold red]命令执行 - 错误[/bold red]",
                            border_style="red",
                            padding=(0, 2)
                        )
                        live.update(error_panel)
                        break

            except KeyboardInterrupt:
                interrupt_msg = "\n⚠️  用户中断命令执行"
                output_lines.append(interrupt_msg)
                process.terminate()

                # 更新面板显示中断信息
                current_output = '\n'.join(output_lines)
                interrupt_panel = Panel(
                    f"🚀 执行命令: [bold cyan]{command}[/bold cyan]\n\n"
                    f"⚠️  [bold yellow]用户中断[/bold yellow]\n\n"
                    f"📄 输出:\n{current_output}",
                    title="[bold yellow]命令执行 - 已中断[/bold yellow]",
                    border_style="red",
                    padding=(0, 2)
                )
                live.update(interrupt_panel)

            # 等待进程完成或确认已终止
            try:
                return_code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                return_code = -1

            # 收集完整输出
            full_output = '\n'.join(output_lines)
            execution_time = time.time() - start_time

            # 显示最终结果
            if return_code == 0:
                final_panel = Panel(
                    f"🚀 执行命令: [bold cyan]{command}[/bold cyan]\n"
                    f"✅ [bold green]执行成功![/bold green] (耗时: {execution_time:.2f}秒)",
                    title="[bold green]命令执行 - 成功[/bold green]",
                    border_style="green",
                    padding=(0, 2)
                )

            elif return_code == -1:
                final_panel = Panel(
                    f"🚀 执行命令: [bold cyan]{command}[/bold cyan]\n"
                    f"⚠️  [bold yellow]执行超时被终止[/bold yellow] (超时: {timeout}秒)\n"
                    f"📄 已获取输出:\n{full_output}",
                    title="[bold yellow]命令执行 - 超时[/bold yellow]",
                    border_style="red",
                    padding=(0, 2)
                )

            else:
                final_panel = Panel(
                    f"🚀 执行命令: [bold cyan]{command}[/bold cyan]\n"
                    f"❌ [bold red]执行失败[/bold red] (返回码: {return_code}, 耗时: {execution_time:.2f}秒)\n",
                    # f"📄 输出:\n{full_output}",
                    title="[bold red]命令执行 - 失败[/bold red]",
                    border_style="red",
                    padding=(0, 2)
                )

            # 更新为最终面板并保持显示一段时间
            live.update(final_panel)
            time.sleep(1)  # 让用户看到最终结果

        return full_output

    except Exception as e:
        error_msg = f"❌ 执行命令时发生错误: {str(e)}"

        # 显示错误面板
        error_panel = Panel(
            f"🚀 执行命令: [bold cyan]{command}[/bold cyan]\n"
            f"❌ [bold red]发生异常[/bold red]\n\n"
            f"📄 错误信息:\n{str(e)}",
            title="[bold red]命令执行 - 异常[/bold red]",
            border_style="red",
            padding=(0, 2)
        )
        console.print(error_panel)

        return error_msg


@tool
def curl(
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
        follow_redirects: bool = True,
        verify_ssl: bool = True,
        silent: bool = True  # 默认改为 True，静默执行
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

        # 显示执行信息
        cmd_str = " ".join(curl_cmd)
        initial_panel = Panel(
            f"🌐 正在执行 HTTP 请求: [bold cyan]{method.upper()} {url}[/bold cyan]\n\n"
            f"⏳ 等待响应...",
            title="[bold yellow]HTTP 请求[/bold yellow]",
            border_style="blue",
            padding=(0, 1)
        )

        start_time = time.time()

        with Live(initial_panel, console=console, refresh_per_second=4) as live:
            # 执行 curl 命令
            process = subprocess.Popen(
                curl_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            try:
                stdout, stderr = process.communicate(timeout=timeout + 5)
                execution_time = time.time() - start_time

                # 解析响应
                response_info = stderr  # curl 的详细信息在 stderr 中
                response_body = stdout

                # 提取状态码
                status_code = "Unknown"
                for line in response_info.split('\n'):
                    if '< HTTP/' in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            status_code = parts[2]
                        break

                # 判断请求是否成功
                is_success = process.returncode == 0

                if is_success:
                    # 成功面板
                    final_panel = Panel(
                        f"🌐 HTTP 请求: [bold cyan]{method.upper()} {url}[/bold cyan]\n"
                        f"✅ [bold green]请求成功![/bold green] (状态码: {status_code}, 耗时: {execution_time:.2f}秒)\n"
                        f"📄 响应大小: {len(response_body)} 字符",
                        title="[bold green]HTTP 请求 - 成功[/bold green]",
                        border_style="green",
                        padding=(0, 2)
                    )
                else:
                    # 失败面板
                    final_panel = Panel(
                        f"🌐 HTTP 请求: [bold cyan]{method.upper()} {url}[/bold cyan]\n"
                        f"❌ [bold red]请求失败[/bold red] (返回码: {process.returncode}, 耗时: {execution_time:.2f}秒)",
                        title="[bold red]HTTP 请求 - 失败[/bold red]",
                        border_style="red",
                        padding=(0, 2)
                    )

                live.update(final_panel)
                time.sleep(1)  # 让用户看到结果

                # 返回完整响应信息
                full_response = f"=== HTTP Response Info ===\n{response_info}\n\n=== Response Body ===\n{response_body}"
                return full_response

            except subprocess.TimeoutExpired:
                process.kill()
                timeout_panel = Panel(
                    f"🌐 HTTP 请求: [bold cyan]{method.upper()} {url}[/bold cyan]\n"
                    f"⚠️  [bold yellow]请求超时[/bold yellow] (超时: {timeout}秒)",
                    title="[bold yellow]HTTP 请求 - 超时[/bold yellow]",
                    border_style="red",
                    padding=(0, 2)
                )
                live.update(timeout_panel)
                time.sleep(1)
                return f"❌ HTTP 请求超时: {url}"

    except Exception as e:
        error_msg = f"❌ 执行 HTTP 请求时发生错误: {str(e)}"

        # 显示错误面板
        error_panel = Panel(
            f"🌐 HTTP 请求: [bold cyan]{method.upper()} {url}[/bold cyan]\n"
            f"❌ [bold red]发生异常[/bold red]\n\n"
            f"📄 错误信息:\n{str(e)}",
            title="[bold red]HTTP 请求 - 异常[/bold red]",
            border_style="red",
            padding=(0, 2)
        )
        console.print(error_panel)

        return error_msg
