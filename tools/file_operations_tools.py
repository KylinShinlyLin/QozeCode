# from langchain_core.tools import tool
# from rich.panel import Panel
#
# # 导入共享的 console 实例
# from shared_console import console


# @tool
# def read_file(file_path: str, encoding: str = "utf-8") -> str:
#     """Read the content of a file and return it as a string.
#
#     Args:
#         file_path: The path to the file to read
#         encoding: The encoding to use when reading the file (default: utf-8)
#
#     Returns:
#         The content of the file as a string, or an error message if the file cannot be read
#     """
#     try:
#         with open(file_path, 'r', encoding=encoding) as file:
#             content = file.read()
#
#         # 显示成功面板
#         success_panel = Panel(
#             f"📖 文件: [bold cyan]{file_path}[/bold cyan]\n"
#             f"📄 文件大小: {len(content)} 字符\n"
#             f"📄 行数: {len(content.splitlines())} 行",
#             title="[bold bright_yellow]文件读取 - 成功[/bold bright_yellow]",
#             border_style="bright_yellow",
#             padding=(0, 1)
#         )
#         console.print(success_panel)
#
#         return content
#
#     except FileNotFoundError:
#         error_msg = f"❌ 文件未找到: {file_path}"
#         error_panel = Panel(
#             f"📖 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#             f"❌ [bold red]文件未找到[/bold red]",
#             title="[bold red]文件读取 - 失败[/bold red]",
#             border_style="red",
#             padding=(0, 1)
#         )
#         console.print(error_panel)
#         return error_msg
#
#     except PermissionError:
#         error_msg = f"❌ 权限不足，无法读取文件: {file_path}"
#         error_panel = Panel(
#             f"📖 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#             f"❌ [bold red]权限不足[/bold red]",
#             title="[bold red]文件读取 - 失败[/bold red]",
#             border_style="red",
#             padding=(0, 1)
#         )
#         console.print(error_panel)
#         return error_msg
#
#     except UnicodeDecodeError as e:
#         error_msg = f"❌ 编码错误，无法使用 {encoding} 编码读取文件: {file_path}\n错误详情: {str(e)}"
#         error_panel = Panel(
#             f"📖 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#             f"❌ [bold red]编码错误[/bold red]\n\n"
#             f"📄 尝试的编码: {encoding}\n"
#             f"📄 错误详情: {str(e)}",
#             title="[bold red]文件读取 - 失败[/bold red]",
#             border_style="red",
#             padding=(0, 1)
#         )
#         console.print(error_panel)
#         return error_msg
#
#     except Exception as e:
#         error_msg = f"❌ 读取文件时发生错误: {str(e)}"
#         error_panel = Panel(
#             f"📖 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#             f"❌ [bold red]发生异常[/bold red]\n\n"
#             f"📄 错误信息: {str(e)}",
#             title="[bold red]文件读取 - 异常[/bold red]",
#             border_style="red",
#             padding=(0, 1)
#         )
#         console.print(error_panel)
#         return error_msg
