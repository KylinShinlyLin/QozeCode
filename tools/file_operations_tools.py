import os
import re
import shutil
import tempfile
from typing import Dict, List

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


# @tool
# def grep_search(pattern: str, file_path: str, case_sensitive: bool = True, line_numbers: bool = True,
#                 context_lines: int = 0) -> str:
#     """Search for a pattern in a file using grep-like functionality.
#
#     Args:
#         pattern: The pattern to search for (supports regular expressions)
#         file_path: The path to the file to search in
#         case_sensitive: Whether the search should be case sensitive (default: True)
#         line_numbers: Whether to include line numbers in the output (default: True)
#         context_lines: Number of context lines to show around matches (default: 0)
#
#     Returns:
#         The search results with matching lines, or an error message if the search fails
#     """
#     try:
#         # 显示搜索面板
#         search_panel = Panel(
#             f"🔍 正在搜索: [bold cyan]{pattern}[/bold cyan]\n"
#             f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n"
#             f"🔤 区分大小写: {'是' if case_sensitive else '否'}\n"
#             f"📊 显示行号: {'是' if line_numbers else '否'}\n"
#             f"📄 上下文行数: {context_lines}",
#             title="[bold bold]文件搜索[/bold bold]",
#             border_style="blue",
#             padding=(0, 1)
#         )
#         console.print(search_panel)
#
#         # 读取文件内容
#         try:
#             with open(file_path, 'r', encoding='utf-8') as file:
#                 lines = file.readlines()
#         except Exception as e:
#             error_msg = f"❌ 无法读取文件: {str(e)}"
#             error_panel = Panel(
#                 f"🔍 搜索模式: [bold cyan]{pattern}[/bold cyan]\n"
#                 f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                 f"❌ [bold red]文件读取失败[/bold red]\n\n"
#                 f"📄 错误信息: {str(e)}",
#                 title="[bold red]文件搜索 - 失败[/bold red]",
#                 border_style="red",
#                 padding=(0, 1)
#             )
#             console.print(error_panel)
#             return error_msg
#
#         # 编译正则表达式
#         flags = 0 if case_sensitive else re.IGNORECASE
#         try:
#             regex = re.compile(pattern, flags)
#         except re.error as e:
#             error_msg = f"❌ 正则表达式错误: {str(e)}"
#             error_panel = Panel(
#                 f"🔍 搜索模式: [bold cyan]{pattern}[/bold cyan]\n"
#                 f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                 f"❌ [bold red]正则表达式错误[/bold red]\n\n"
#                 f"📄 错误信息: {str(e)}",
#                 title="[bold red]文件搜索 - 失败[/bold red]",
#                 border_style="red",
#                 padding=(0, 1)
#             )
#             console.print(error_panel)
#             return error_msg
#
#         # 搜索匹配行
#         matches = []
#         for i, line in enumerate(lines):
#             if regex.search(line):
#                 matches.append(i)
#
#         if not matches:
#             no_match_panel = Panel(
#                 f"🔍 搜索模式: [bold cyan]{pattern}[/bold cyan]\n"
#                 f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                 f"ℹ️  [bold yellow]未找到匹配项[/bold yellow]",
#                 title="[bold yellow]文件搜索 - 无结果[/bold yellow]",
#                 border_style="yellow",
#                 padding=(0, 1)
#             )
#             console.print(no_match_panel)
#             return f"在文件 {file_path} 中未找到匹配模式 '{pattern}' 的内容"
#
#         # 构建结果
#         result_lines = []
#         result_lines.append(f"在文件 '{file_path}' 中找到 {len(matches)} 个匹配项:")
#         result_lines.append("=" * 50)
#
#         # 收集需要显示的行（包括上下文）
#         lines_to_show = set()
#         for match_line in matches:
#             start = max(0, match_line - context_lines)
#             end = min(len(lines), match_line + context_lines + 1)
#             for i in range(start, end):
#                 lines_to_show.add(i)
#
#         # 按行号排序
#         sorted_lines = sorted(lines_to_show)
#
#         # 格式化输出
#         prev_line = -2
#         for line_num in sorted_lines:
#             # 如果行号不连续，添加分隔符
#             if line_num > prev_line + 1:
#                 if prev_line >= 0:
#                     result_lines.append("--")
#
#             line_content = lines[line_num]
#
#             # 标记匹配行
#             if line_num in matches:
#                 if line_numbers:
#                     result_lines.append(f"{line_num + 1:4d}:* {line_content}")
#                 else:
#                     result_lines.append(f"* {line_content}")
#             else:
#                 if line_numbers:
#                     result_lines.append(f"{line_num + 1:4d}:  {line_content}")
#                 else:
#                     result_lines.append(f"  {line_content}")
#
#             prev_line = line_num
#
#         result = "\n".join(result_lines)
#
#         # 显示成功面板
#         success_panel = Panel(
#             f"🔍 搜索模式: [bold cyan]{pattern}[/bold cyan]\n"
#             f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#             f"✅ [bold green]搜索完成![/bold green]\n\n"
#             f"📊 找到匹配项: {len(matches)} 个",
#             title="[bold green]文件搜索 - 成功[/bold green]",
#             border_style="green",
#             padding=(0, 1)
#         )
#         console.print(success_panel)
#
#         return result
#
#     except Exception as e:
#         error_msg = f"❌ 搜索时发生错误: {str(e)}"
#         error_panel = Panel(
#             f"🔍 搜索模式: [bold cyan]{pattern}[/bold cyan]\n"
#             f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#             f"❌ [bold red]发生异常[/bold red]\n\n"
#             f"📄 错误信息: {str(e)}",
#             title="[bold red]文件搜索 - 异常[/bold red]",
#             border_style="red",
#             padding=(0, 1)
#         )
#         console.print(error_panel)
#         return error_msg


@tool
def edit_file(
        file_path: str,
        edits: List[Dict],
        encoding: str = "utf-8",
        backup: bool = True,
        validate_only: bool = False
) -> str:
    """
    高效的文件编辑工具，支持大文件和复杂编辑操作。
    
    Args:
        file_path: 要编辑的文件路径
        edits: 编辑操作列表，支持以下操作类型：
            - {"type": "replace", "start_line": 5, "end_line": 7, "content": "新内容"}
            - {"type": "insert", "line": 3, "content": "插入的内容"}
            - {"type": "delete", "start_line": 10, "end_line": 12}
            - {"type": "append", "content": "追加到文件末尾的内容"}
            - {"type": "prepend", "content": "添加到文件开头的内容"}
        encoding: 文件编码 (默认: utf-8)
        backup: 是否创建备份文件 (默认: True)
        validate_only: 仅验证操作是否有效，不实际执行 (默认: False)
    
    Returns:
        编辑结果信息或错误消息
    """
    try:
        # 显示编辑开始面板
        edit_panel = Panel(
            f"🚀 正在编辑文件: [bold cyan]{file_path}[/bold cyan]\n"
            f"📝 编辑操作数量: {len(edits)}\n"
            f"💾 创建备份: {'是' if backup else '否'}\n"
            f"🔍 验证模式: {'是' if validate_only else '否'}",
            title="[bold yellow]高效文件编辑[/bold yellow]",
            border_style="blue",
            padding=(0, 1)
        )
        console.print(edit_panel)

        # 检查文件是否存在
        if not os.path.exists(file_path):
            error_msg = f"❌ 文件未找到: {file_path}"
            error_panel = Panel(
                f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
                f"❌ [bold red]文件不存在[/bold red]",
                title="[bold red]文件编辑 - 失败[/bold red]",
                border_style="red",
                padding=(0, 1)
            )
            console.print(error_panel)
            return error_msg

        # 获取文件信息
        file_size = os.path.getsize(file_path)

        # 验证和预处理编辑操作
        validated_edits, validation_errors = _validate_and_normalize_edits(edits, file_path, encoding)

        if validation_errors:
            error_msg = f"❌ 编辑操作验证失败:\n" + "\n".join(validation_errors)
            error_panel = Panel(
                f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
                f"❌ [bold red]操作验证失败[/bold red]\n\n" +
                "\n".join(f"• {error}" for error in validation_errors),
                title="[bold red]文件编辑 - 验证失败[/bold red]",
                border_style="red",
                padding=(0, 1)
            )
            console.print(error_panel)
            return error_msg

        if validate_only:
            success_panel = Panel(
                f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
                f"✅ [bold green]所有编辑操作验证通过![/bold green]\n\n"
                f"📊 待执行操作: {len(validated_edits)} 个",
                title="[bold green]编辑验证 - 成功[/bold green]",
                border_style="green",
                padding=(0, 1)
            )
            console.print(success_panel)
            return "✅ 编辑操作验证通过，可以安全执行"

        # 创建备份
        backup_path = None
        if backup:
            backup_path = f"{file_path}.backup"
            try:
                shutil.copy2(file_path, backup_path)
            except Exception as e:
                error_msg = f"❌ 无法创建备份文件: {str(e)}"
                error_panel = Panel(
                    f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
                    f"❌ [bold red]备份创建失败[/bold red]\n\n"
                    f"📄 错误信息: {str(e)}",
                    title="[bold red]文件编辑 - 失败[/bold red]",
                    border_style="red",
                    padding=(0, 1)
                )
                console.print(error_panel)
                return error_msg

        # 执行编辑操作
        try:
            if file_size > 1024 * 1024:  # 大于1MB的文件使用流式处理
                result = _execute_edits_streaming(file_path, validated_edits, encoding)
            else:
                result = _execute_edits_memory(file_path, validated_edits, encoding)

            # 显示成功面板
            success_panel = Panel(
                f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
                f"✅ [bold green]编辑完成![/bold green]\n\n"
                f"📊 执行的操作: {len(validated_edits)} 个\n"
                f"📄 文件大小: {file_size} → {os.path.getsize(file_path)} 字节\n"
                f"💾 备份文件: {backup_path if backup_path else '无'}",
                title="[bold green]文件编辑 - 成功[/bold green]",
                border_style="green",
                padding=(0, 1)
            )
            console.print(success_panel)

            return result

        except Exception as e:
            # 如果编辑失败且有备份，尝试恢复
            if backup_path and os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, file_path)
                    error_msg = f"❌ 编辑失败，已从备份恢复: {str(e)}"
                except:
                    error_msg = f"❌ 编辑失败且无法恢复: {str(e)}"
            else:
                error_msg = f"❌ 编辑失败: {str(e)}"

            error_panel = Panel(
                f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
                f"❌ [bold red]编辑执行失败[/bold red]\n\n"
                f"📄 错误信息: {str(e)}",
                title="[bold red]文件编辑 - 失败[/bold red]",
                border_style="red",
                padding=(0, 1)
            )
            console.print(error_panel)
            return error_msg

    except Exception as e:
        error_msg = f"❌ 编辑文件时发生未预期错误: {str(e)}"
        error_panel = Panel(
            f"📁 文件: [bold cyan]{file_path}[/bold cyan]\n\n"
            f"❌ [bold red]发生异常[/bold red]\n\n"
            f"📄 错误信息: {str(e)}",
            title="[bold red]文件编辑 - 异常[/bold red]",
            border_style="red",
            padding=(0, 1)
        )
        console.print(error_panel)
        return error_msg


def _validate_and_normalize_edits(edits: List[Dict], file_path: str, encoding: str) -> tuple:
    """验证和标准化编辑操作"""
    validated_edits = []
    errors = []

    # 获取文件行数
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            line_count = sum(1 for _ in f)
    except Exception as e:
        return [], [f"无法读取文件获取行数: {str(e)}"]

    for i, edit in enumerate(edits):
        if not isinstance(edit, dict):
            errors.append(f"编辑操作 {i + 1}: 必须是字典类型")
            continue

        edit_type = edit.get('type')
        if not edit_type:
            errors.append(f"编辑操作 {i + 1}: 缺少 'type' 字段")
            continue

        if edit_type not in ['replace', 'insert', 'delete', 'append', 'prepend']:
            errors.append(f"编辑操作 {i + 1}: 不支持的操作类型 '{edit_type}'")
            continue

        # 验证具体操作
        if edit_type in ['replace', 'delete']:
            start_line = edit.get('start_line')
            end_line = edit.get('end_line', start_line)

            if not isinstance(start_line, int) or start_line < 1:
                errors.append(f"编辑操作 {i + 1}: start_line 必须是大于0的整数")
                continue

            if not isinstance(end_line, int) or end_line < start_line:
                errors.append(f"编辑操作 {i + 1}: end_line 必须是大于等于start_line的整数")
                continue

            if start_line > line_count or end_line > line_count:
                errors.append(f"编辑操作 {i + 1}: 行号超出文件范围 (文件共{line_count}行)")
                continue

        elif edit_type == 'insert':
            line = edit.get('line')
            if not isinstance(line, int) or line < 1 or line > line_count + 1:
                errors.append(f"编辑操作 {i + 1}: line 必须在1到{line_count + 1}之间")
                continue

        # 标准化编辑操作
        normalized_edit = edit.copy()
        if edit_type in ['replace', 'insert', 'append', 'prepend']:
            content = edit.get('content', '')
            if not isinstance(content, str):
                errors.append(f"编辑操作 {i + 1}: content 必须是字符串")
                continue
            # 确保内容以换行符结尾（除非是空内容）
            if content and not content.endswith('\n'):
                normalized_edit['content'] = content + '\n'

        validated_edits.append(normalized_edit)

    # 按操作位置排序（从后往前执行，避免行号变化）
    def get_sort_key(edit):
        edit_type = edit['type']
        if edit_type in ['replace', 'delete']:
            return edit['start_line']
        elif edit_type == 'insert':
            return edit['line']
        elif edit_type == 'prepend':
            return 0
        else:  # append
            return float('inf')

    validated_edits.sort(key=get_sort_key, reverse=True)

    return validated_edits, errors


def _execute_edits_memory(file_path: str, edits: List[Dict], encoding: str) -> str:
    """在内存中执行编辑操作（适用于小文件）"""
    # 读取所有行
    with open(file_path, 'r', encoding=encoding) as f:
        lines = f.readlines()

    operations_performed = []

    for edit in edits:
        edit_type = edit['type']

        if edit_type == 'replace':
            start_line = edit['start_line'] - 1  # 转换为0-based
            end_line = edit.get('end_line', edit['start_line']) - 1
            content = edit.get('content', '')

            lines[start_line:end_line + 1] = [content] if content else []
            operations_performed.append(f"替换第 {start_line + 1}-{end_line + 1} 行")

        elif edit_type == 'insert':
            line = edit['line'] - 1  # 转换为0-based
            content = edit.get('content', '')

            lines.insert(line, content)
            operations_performed.append(f"在第 {line + 1} 行插入内容")

        elif edit_type == 'delete':
            start_line = edit['start_line'] - 1
            end_line = edit.get('end_line', edit['start_line']) - 1

            del lines[start_line:end_line + 1]
            operations_performed.append(f"删除第 {start_line + 1}-{end_line + 1} 行")

        elif edit_type == 'append':
            content = edit.get('content', '')
            lines.append(content)
            operations_performed.append("追加内容到文件末尾")

        elif edit_type == 'prepend':
            content = edit.get('content', '')
            lines.insert(0, content)
            operations_performed.append("在文件开头插入内容")

    # 写入文件
    with open(file_path, 'w', encoding=encoding) as f:
        f.writelines(lines)

    result = f"✅ 文件编辑成功!\n"
    result += f"📁 文件: {file_path}\n"
    result += f"📊 执行了 {len(operations_performed)} 个编辑操作:\n"
    for op in operations_performed:
        result += f"  • {op}\n"

    return result


def _execute_edits_streaming(file_path: str, edits: List[Dict], encoding: str) -> str:
    """使用流式处理执行编辑操作（适用于大文件）"""
    # 创建临时文件
    temp_fd, temp_path = tempfile.mkstemp(suffix='.tmp', dir=os.path.dirname(file_path))

    try:
        operations_performed = []
        current_line = 1

        with open(file_path, 'r', encoding=encoding) as input_file, \
                os.fdopen(temp_fd, 'w', encoding=encoding) as output_file:

            # 处理 prepend 操作
            for edit in edits:
                if edit['type'] == 'prepend':
                    content = edit.get('content', '')
                    output_file.write(content)
                    operations_performed.append("在文件开头插入内容")

            # 逐行处理文件
            for line in input_file:
                # 检查是否有针对当前行的操作
                skip_line = False

                for edit in edits:
                    edit_type = edit['type']

                    if edit_type == 'insert' and edit['line'] == current_line:
                        content = edit.get('content', '')
                        output_file.write(content)
                        operations_performed.append(f"在第 {current_line} 行插入内容")

                    elif edit_type == 'replace':
                        start_line = edit['start_line']
                        end_line = edit.get('end_line', start_line)

                        if start_line <= current_line <= end_line:
                            if current_line == start_line:
                                # 只在第一行写入替换内容
                                content = edit.get('content', '')
                                if content:
                                    output_file.write(content)
                                operations_performed.append(f"替换第 {start_line}-{end_line} 行")
                            skip_line = True

                    elif edit_type == 'delete':
                        start_line = edit['start_line']
                        end_line = edit.get('end_line', start_line)

                        if start_line <= current_line <= end_line:
                            skip_line = True
                            if current_line == start_line:
                                operations_performed.append(f"删除第 {start_line}-{end_line} 行")

                # 如果不跳过，写入原行
                if not skip_line:
                    output_file.write(line)

                current_line += 1

            # 处理 append 操作
            for edit in edits:
                if edit['type'] == 'append':
                    content = edit.get('content', '')
                    output_file.write(content)
                    operations_performed.append("追加内容到文件末尾")

        # 替换原文件
        shutil.move(temp_path, file_path)

        result = f"✅ 文件编辑成功!\n"
        result += f"📁 文件: {file_path}\n"
        result += f"📊 执行了 {len(operations_performed)} 个编辑操作:\n"
        for op in operations_performed:
            result += f"  • {op}\n"

        return result

    except Exception as e:
        # 清理临时文件
        try:
            os.unlink(temp_path)
        except:
            pass
        raise e

# 保持原有的 edit_file 函数作为向后兼容
# def edit_file(file_path: str, edits: list, encoding: str = "utf-8", backup: bool = True) -> str:
#     """Intelligently edit a file by modifying only specified parts without rewriting the entire file.
#
#     Args:
#         file_path: Path to the file to be edited
#         edits: List of edit operations, each edit operation is a dictionary containing the following keys:
#             - type: Edit type ("replace", "insert", "delete", "append")
#             - start_line: Starting line number (1-based, only valid for replace and delete)
#             - end_line: Ending line number (1-based, only valid for replace and delete, optional)
#             - content: New content (only valid for replace, insert, append)
#             - position: Insert position line number (1-based, only valid for insert)
#         encoding: File encoding (default: utf-8)
#         backup: Whether to create a backup file (default: True)
#
#     Returns:
#         Edit result information, or error message
#
#     Edit operation examples:
#         - Replace lines: {"type": "replace", "start_line": 5, "end_line": 7, "content": "new content\\n"}
#         - Insert line: {"type": "insert", "position": 3, "content": "inserted new line\\n"}
#         - Delete lines: {"type": "delete", "start_line": 10, "end_line": 12}
#         - Append content: {"type": "append", "content": "content appended to end of file\\n"}
#     """
#     try:
#         # 显示编辑开始面板
#         edit_panel = Panel(
#             f"✏️  正在编辑文件: [bold cyan]{file_path}[/bold cyan]\n"
#             f"📝 编辑操作数量: {len(edits)}\n"
#             f"💾 创建备份: {'是' if backup else '否'}",
#             title="[bold yellow]文件编辑[/bold yellow]",
#             border_style="blue",
#             padding=(0, 1)
#         )
#         console.print(edit_panel)
#
#         # 读取原文件内容
#         try:
#             with open(file_path, 'r', encoding=encoding) as file:
#                 lines = file.readlines()
#         except FileNotFoundError:
#             error_msg = f"❌ 文件未找到: {file_path}"
#             error_panel = Panel(
#                 f"✏️  文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                 f"❌ [bold red]文件未找到[/bold red]",
#                 title="[bold red]文件编辑 - 失败[/bold red]",
#                 border_style="red",
#                 padding=(0, 1)
#             )
#             console.print(error_panel)
#             return error_msg
#         except Exception as e:
#             error_msg = f"❌ 无法读取文件: {str(e)}"
#             error_panel = Panel(
#                 f"✏️  文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                 f"❌ [bold red]文件读取失败[/bold red]\n\n"
#                 f"📄 错误信息: {str(e)}",
#                 title="[bold red]文件编辑 - 失败[/bold red]",
#                 border_style="red",
#                 padding=(0, 1)
#             )
#             console.print(error_panel)
#             return error_msg
#
#         # 创建备份
#         if backup:
#             backup_path = f"{file_path}.backup"
#             try:
#                 with open(backup_path, 'w', encoding=encoding) as backup_file:
#                     backup_file.writelines(lines)
#             except Exception as e:
#                 error_msg = f"❌ 无法创建备份文件: {str(e)}"
#                 error_panel = Panel(
#                     f"✏️  文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                     f"❌ [bold red]备份创建失败[/bold red]\n\n"
#                     f"📄 错误信息: {str(e)}",
#                     title="[bold red]文件编辑 - 失败[/bold red]",
#                     border_style="red",
#                     padding=(0, 1)
#                 )
#                 console.print(error_panel)
#                 return error_msg
#
#         # 验证编辑操作格式
#         for i, edit in enumerate(edits):
#             if not isinstance(edit, dict) or 'type' not in edit:
#                 error_msg = f"❌ 编辑操作 {i + 1} 格式错误: 缺少 'type' 字段"
#                 error_panel = Panel(
#                     f"✏️  文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                     f"❌ [bold red]编辑操作格式错误[/bold red]\n\n"
#                     f"📄 错误信息: 编辑操作 {i + 1} 缺少 'type' 字段",
#                     title="[bold red]文件编辑 - 失败[/bold red]",
#                     border_style="red",
#                     padding=(0, 1)
#                 )
#                 console.print(error_panel)
#                 return error_msg
#
#         # 按操作类型和位置排序编辑操作（从后往前处理，避免行号变化影响）
#         sorted_edits = []
#         for edit in edits:
#             edit_type = edit['type']
#             if edit_type in ['replace', 'delete']:
#                 start_line = edit.get('start_line', 1)
#                 sorted_edits.append((start_line, edit))
#             elif edit_type == 'insert':
#                 position = edit.get('position', 1)
#                 sorted_edits.append((position, edit))
#             elif edit_type == 'append':
#                 sorted_edits.append((len(lines) + 1, edit))
#             else:
#                 error_msg = f"❌ 不支持的编辑类型: {edit_type}"
#                 error_panel = Panel(
#                     f"✏️  文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                     f"❌ [bold red]不支持的编辑类型[/bold red]\n\n"
#                     f"📄 支持的类型: replace, insert, delete, append\n"
#                     f"📄 当前类型: {edit_type}",
#                     title="[bold red]文件编辑 - 失败[/bold red]",
#                     border_style="red",
#                     padding=(0, 1)
#                 )
#                 console.print(error_panel)
#                 return error_msg
#
#         # 按行号倒序排序，从后往前处理
#         sorted_edits.sort(key=lambda x: x[0], reverse=True)
#
#         # 执行编辑操作
#         modified_lines = lines.copy()
#         operations_performed = []
#
#         for line_num, edit in sorted_edits:
#             edit_type = edit['type']
#
#             if edit_type == 'replace':
#                 start_line = edit['start_line'] - 1  # 转换为0-based
#                 end_line = edit.get('end_line', edit['start_line']) - 1
#                 content = edit.get('content', '')
#
#                 if start_line < 0 or end_line >= len(modified_lines) or start_line > end_line:
#                     error_msg = f"❌ 替换操作行号超出范围: {start_line + 1}-{end_line + 1}"
#                     error_panel = Panel(
#                         f"✏️  文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                         f"❌ [bold red]行号超出范围[/bold red]\n\n"
#                         f"📄 文件总行数: {len(modified_lines)}\n"
#                         f"📄 尝试替换: {start_line + 1}-{end_line + 1}",
#                         title="[bold red]文件编辑 - 失败[/bold red]",
#                         border_style="red",
#                         padding=(0, 1)
#                     )
#                     console.print(error_panel)
#                     return error_msg
#
#                 # 确保内容以换行符结尾（如果不是空内容）
#                 if content and not content.endswith('\n'):
#                     content += '\n'
#
#                 # 替换指定行
#                 modified_lines[start_line:end_line + 1] = [content] if content else []
#                 operations_performed.append(f"替换第 {start_line + 1}-{end_line + 1} 行")
#
#             elif edit_type == 'insert':
#                 position = edit['position'] - 1  # 转换为0-based
#                 content = edit.get('content', '')
#
#                 if position < 0 or position > len(modified_lines):
#                     error_msg = f"❌ 插入位置超出范围: {position + 1}"
#                     error_panel = Panel(
#                         f"✏️  文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                         f"❌ [bold red]插入位置超出范围[/bold red]\n\n"
#                         f"📄 文件总行数: {len(modified_lines)}\n"
#                         f"📄 尝试插入位置: {position + 1}",
#                         title="[bold red]文件编辑 - 失败[/bold red]",
#                         border_style="red",
#                         padding=(0, 1)
#                     )
#                     console.print(error_panel)
#                     return error_msg
#
#                 # 确保内容以换行符结尾
#                 if content and not content.endswith('\n'):
#                     content += '\n'
#
#                 # 在指定位置插入
#                 modified_lines.insert(position, content)
#                 operations_performed.append(f"在第 {position + 1} 行插入内容")
#
#             elif edit_type == 'delete':
#                 start_line = edit['start_line'] - 1  # 转换为0-based
#                 end_line = edit.get('end_line', edit['start_line']) - 1
#
#                 if start_line < 0 or end_line >= len(modified_lines) or start_line > end_line:
#                     error_msg = f"❌ 删除操作行号超出范围: {start_line + 1}-{end_line + 1}"
#                     error_panel = Panel(
#                         f"✏️  文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                         f"❌ [bold red]行号超出范围[/bold red]\n\n"
#                         f"📄 文件总行数: {len(modified_lines)}\n"
#                         f"📄 尝试删除: {start_line + 1}-{end_line + 1}",
#                         title="[bold red]文件编辑 - 失败[/bold red]",
#                         border_style="red",
#                         padding=(0, 1)
#                     )
#                     console.print(error_panel)
#                     return error_msg
#
#                 # 删除指定行
#                 del modified_lines[start_line:end_line + 1]
#                 operations_performed.append(f"删除第 {start_line + 1}-{end_line + 1} 行")
#
#             elif edit_type == 'append':
#                 content = edit.get('content', '')
#
#                 # 确保内容以换行符结尾
#                 if content and not content.endswith('\n'):
#                     content += '\n'
#
#                 # 追加到文件末尾
#                 modified_lines.append(content)
#                 operations_performed.append("追加内容到文件末尾")
#
#         # 写入修改后的内容
#         try:
#             with open(file_path, 'w', encoding=encoding) as file:
#                 file.writelines(modified_lines)
#         except Exception as e:
#             error_msg = f"❌ 无法写入文件: {str(e)}"
#             error_panel = Panel(
#                 f"✏️  文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#                 f"❌ [bold red]文件写入失败[/bold red]\n\n"
#                 f"📄 错误信息: {str(e)}",
#                 title="[bold red]文件编辑 - 失败[/bold red]",
#                 border_style="red",
#                 padding=(0, 1)
#             )
#             console.print(error_panel)
#             return error_msg
#
#         # 显示成功面板
#         success_panel = Panel(
#             f"✏️  文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#             f"✅ [bold green]编辑完成![/bold green]\n\n"
#             f"📊 执行的操作:\n" + "\n".join(f"  • {op}" for op in operations_performed) + "\n\n"
#                                                                                          f"📄 原文件行数: {len(lines)}\n"
#                                                                                          f"📄 修改后行数: {len(modified_lines)}\n"
#                                                                                          f"💾 备份文件: {file_path + '.backup' if backup else '无'}",
#             title="[bold green]文件编辑 - 成功[/bold green]",
#             border_style="green",
#             padding=(0, 1)
#         )
#         console.print(success_panel)
#
#         result = f"✅ 文件编辑成功!\n"
#         result += f"📁 文件: {file_path}\n"
#         result += f"📊 执行了 {len(operations_performed)} 个编辑操作:\n"
#         for op in operations_performed:
#             result += f"  • {op}\n"
#         result += f"📄 文件行数变化: {len(lines)} → {len(modified_lines)}"
#         if backup:
#             result += f"\n💾 备份文件已创建: {file_path}.backup"
#
#         return result
#
#     except Exception as e:
#         error_msg = f"❌ 编辑文件时发生错误: {str(e)}"
#         error_panel = Panel(
#             f"✏️  文件: [bold cyan]{file_path}[/bold cyan]\n\n"
#             f"❌ [bold red]发生异常[/bold red]\n\n"
#             f"📄 错误信息: {str(e)}",
#             title="[bold red]文件编辑 - 异常[/bold red]",
#             border_style="red",
#             padding=(0, 1)
#         )
#         console.print(error_panel)
#         return error_msg
