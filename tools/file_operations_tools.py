import re
from langchain_core.tools import tool
from rich.console import Console
from rich.panel import Panel
# 导入共享的 console 实例
from shared_console import console


@tool
def read_file(file_path: str, encoding: str = "utf-8") -> str:
    """Read the content of a file and return it as a string.
    
    Args:
        file_path: The path to the file to read
        encoding: The encoding to use when reading the file (default: utf-8)
    
    Returns:
        The content of the file as a string, or an error message if the file cannot be read
    """
    try:
        # # 显示读取文件的面板
        # read_panel = Panel(
        #     f"📖 正在读取文件: [bold cyan]{file_path}[/bold cyan]",
        #     title="[bold yellow]文件读取[/bold yellow]",
        #     border_style="blue",
        #     padding=(0, 1)
        # )
        # console.print(read_panel)

        with open(file_path, 'r', encoding=encoding) as file:
            content = file.read()

        # 显示成功面板
        success_panel = Panel(
            f"📖 文件: [bold cyan]{file_path}[/bold cyan]\n"
            f"📄 文件大小: {len(content)} 字符\n"
            f"📄 行数: {len(content.splitlines())} 行",
            title="[bold bright_yellow]文件读取 - 成功[/bold bright_yellow]",
            border_style="bright_yellow",
            padding=(0, 1)
        )
        console.print(success_panel)

        return content

    except FileNotFoundError:
        error_msg = f"❌ 文件未找到: {file_path}"
        error_panel = Panel(
            f"📖 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
            f"❌ [bold red]文件未找到[/bold red]",
            title="[bold red]文件读取 - 失败[/bold red]",
            border_style="red",
            padding=(0, 1)
        )
        console.print(error_panel)
        return error_msg

    except PermissionError:
        error_msg = f"❌ 权限不足，无法读取文件: {file_path}"
        error_panel = Panel(
            f"📖 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
            f"❌ [bold red]权限不足[/bold red]",
            title="[bold red]文件读取 - 失败[/bold red]",
            border_style="red",
            padding=(0, 1)
        )
        console.print(error_panel)
        return error_msg

    except UnicodeDecodeError as e:
        error_msg = f"❌ 编码错误，无法使用 {encoding} 编码读取文件: {file_path}\n错误详情: {str(e)}"
        error_panel = Panel(
            f"📖 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
            f"❌ [bold red]编码错误[/bold red]\n\n"
            f"📄 尝试的编码: {encoding}\n"
            f"📄 错误详情: {str(e)}",
            title="[bold red]文件读取 - 失败[/bold red]",
            border_style="red",
            padding=(0, 1)
        )
        console.print(error_panel)
        return error_msg

    except Exception as e:
        error_msg = f"❌ 读取文件时发生错误: {str(e)}"
        error_panel = Panel(
            f"📖 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
            f"❌ [bold red]发生异常[/bold red]\n\n"
            f"📄 错误信息: {str(e)}",
            title="[bold red]文件读取 - 异常[/bold red]",
            border_style="red",
            padding=(0, 1)
        )
        console.print(error_panel)
        return error_msg


@tool
def grep_search(pattern: str, file_path: str, case_sensitive: bool = True, line_numbers: bool = True,
                context_lines: int = 0) -> str:
    """Search for a pattern in a file using grep-like functionality.
    
    Args:
        pattern: The pattern to search for (supports regular expressions)
        file_path: The path to the file to search in
        case_sensitive: Whether the search should be case sensitive (default: True)
        line_numbers: Whether to include line numbers in the output (default: True)
        context_lines: Number of context lines to show around matches (default: 0)
    
    Returns:
        The search results with matching lines, or an error message if the search fails
    """
    try:
        # 显示搜索面板
        search_panel = Panel(
            f"🔍 正在搜索: [bold cyan]{pattern}[/bold cyan]\n"
            f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n"
            f"🔤 区分大小写: {'是' if case_sensitive else '否'}\n"
            f"📊 显示行号: {'是' if line_numbers else '否'}\n"
            f"📄 上下文行数: {context_lines}",
            title="[bold yellow]文件搜索[/bold yellow]",
            border_style="blue",
            padding=(0, 1)
        )
        console.print(search_panel)

        # 读取文件内容
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
        except Exception as e:
            error_msg = f"❌ 无法读取文件: {str(e)}"
            error_panel = Panel(
                f"🔍 搜索模式: [bold cyan]{pattern}[/bold cyan]\n"
                f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
                f"❌ [bold red]文件读取失败[/bold red]\n\n"
                f"📄 错误信息: {str(e)}",
                title="[bold red]文件搜索 - 失败[/bold red]",
                border_style="red",
                padding=(0, 1)
            )
            console.print(error_panel)
            return error_msg

        # 编译正则表达式
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            error_msg = f"❌ 正则表达式错误: {str(e)}"
            error_panel = Panel(
                f"🔍 搜索模式: [bold cyan]{pattern}[/bold cyan]\n"
                f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
                f"❌ [bold red]正则表达式错误[/bold red]\n\n"
                f"📄 错误信息: {str(e)}",
                title="[bold red]文件搜索 - 失败[/bold red]",
                border_style="red",
                padding=(0, 1)
            )
            console.print(error_panel)
            return error_msg

        # 搜索匹配行
        matches = []
        for i, line in enumerate(lines):
            if regex.search(line):
                matches.append(i)

        if not matches:
            no_match_panel = Panel(
                f"🔍 搜索模式: [bold cyan]{pattern}[/bold cyan]\n"
                f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
                f"ℹ️  [bold yellow]未找到匹配项[/bold yellow]",
                title="[bold yellow]文件搜索 - 无结果[/bold yellow]",
                border_style="yellow",
                padding=(0, 1)
            )
            console.print(no_match_panel)
            return f"在文件 {file_path} 中未找到匹配模式 '{pattern}' 的内容"

        # 构建结果
        result_lines = []
        result_lines.append(f"在文件 '{file_path}' 中找到 {len(matches)} 个匹配项:")
        result_lines.append("=" * 50)

        # 收集需要显示的行（包括上下文）
        lines_to_show = set()
        for match_line in matches:
            start = max(0, match_line - context_lines)
            end = min(len(lines), match_line + context_lines + 1)
            for i in range(start, end):
                lines_to_show.add(i)

        # 按行号排序
        sorted_lines = sorted(lines_to_show)

        # 格式化输出
        prev_line = -2
        for line_num in sorted_lines:
            # 如果行号不连续，添加分隔符
            if line_num > prev_line + 1:
                if prev_line >= 0:
                    result_lines.append("--")

            line_content = lines[line_num]

            # 标记匹配行
            if line_num in matches:
                if line_numbers:
                    result_lines.append(f"{line_num + 1:4d}:* {line_content}")
                else:
                    result_lines.append(f"* {line_content}")
            else:
                if line_numbers:
                    result_lines.append(f"{line_num + 1:4d}:  {line_content}")
                else:
                    result_lines.append(f"  {line_content}")

            prev_line = line_num

        result = "\n".join(result_lines)

        # 显示成功面板
        success_panel = Panel(
            f"🔍 搜索模式: [bold cyan]{pattern}[/bold cyan]\n"
            f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
            f"✅ [bold green]搜索完成![/bold green]\n\n"
            f"📊 找到匹配项: {len(matches)} 个",
            title="[bold green]文件搜索 - 成功[/bold green]",
            border_style="green",
            padding=(0, 1)
        )
        console.print(success_panel)

        return result

    except Exception as e:
        error_msg = f"❌ 搜索时发生错误: {str(e)}"
        error_panel = Panel(
            f"🔍 搜索模式: [bold cyan]{pattern}[/bold cyan]\n"
            f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
            f"❌ [bold red]发生异常[/bold red]\n\n"
            f"📄 错误信息: {str(e)}",
            title="[bold red]文件搜索 - 异常[/bold red]",
            border_style="red",
            padding=(0, 1)
        )
        console.print(error_panel)
        return error_msg
