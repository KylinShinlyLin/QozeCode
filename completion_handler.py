
# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-
# """
# 自动补全处理器模块
# 负责处理终端输入时的自动补全功能
# """
#
# import subprocess
# import shlex
# import glob
# import os
# import readline
# import subprocess
# import shlex
# import glob
# import os
#
#
# def setup_completion():
#     """设置自动补全配置"""
#     # 清除任何可能的readline历史干扰
#     if hasattr(readline, 'clear_history'):
#         readline.clear_history()
#
#     # 设置readline配置，确保提示符安全
#     if hasattr(readline, 'set_startup_hook'):
#         readline.set_startup_hook(None)
#
#     # 配置简洁的自动补全
#     if hasattr(readline, 'set_completer') and hasattr(readline, 'parse_and_bind'):
#         readline.set_completer(completer)
#         readline.parse_and_bind("tab: complete")
#         # 设置补全时的分隔符
#         readline.set_completer_delims(' \t\n`!@#$%^&*()=+[{]}\\|;:\'\",<>?')
#
#         # 配置更简洁的补全显示
#         try:
#             readline.parse_and_bind("set show-all-if-unmodified on")  # 只在未修改时显示所有
#             readline.parse_and_bind("set completion-ignore-case on")  # 忽略大小写
#             readline.parse_and_bind("set page-completions off")  # 不分页显示补全
#             readline.parse_and_bind("set completion-query-items 1000")  # 很高的阈值，基本不询问
#             readline.parse_and_bind("set print-completions-horizontally on")  # 水平显示补全
#             readline.parse_and_bind("set show-all-if-ambiguous off")  # 不自动显示所有匹配项
#         except:
#             pass  # 如果不支持这些选项，忽略错误
#
#
# def completer(text, state):
#     """自动补全函数 - 彻底修复感叹号问题"""
#     options = []
#
#     # 处理带感叹号前缀的命令补全
#     if text.startswith('!') or text.startswith('！'):
#         # 计算连续感叹号的数量
#         exclamation_prefix = ""
#         clean_text = text
#
#         # 提取所有开头的感叹号
#         for char in text:
#             if char in '!！':
#                 exclamation_prefix += char
#             else:
#                 break
#
#         # 去掉感叹号前缀得到实际的命令文本
#         clean_text = text[len(exclamation_prefix):]
#
#         if clean_text:
#             try:
#                 # 使用bash的补全功能 - 获取以clean_text开头的命令
#                 result = subprocess.run(
#                     ['bash', '-c',
#                      f'compgen -c -- {shlex.quote(clean_text)} | grep "^{shlex.quote(clean_text)}" | head -8'],
#                     capture_output=True,
#                     text=True,
#                     timeout=1
#                 )
#
#                 if result.returncode == 0:
#                     completions = result.stdout.strip().split('\n')
#                     # 过滤掉空行并添加原始的感叹号前缀
#                     for completion in completions:
#                         if completion and completion.strip():
#                             options.append(exclamation_prefix + completion.strip())
#
#             except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
#                 pass
#         else:
#             # 如果只有感叹号，显示最常用的几个命令
#             # 保持原始的感叹号前缀
#             common_commands = ['ls', 'cd', 'pwd', 'git', 'python']
#             options = [exclamation_prefix + cmd for cmd in common_commands]
#
#     else:
#         # 没有感叹号前缀时的补全逻辑 - 支持当前目录文件补全
#         # 1. 文件路径补全（包括当前目录和空输入）
#         try:
#             # 处理波浪号
#             if text.startswith('~'):
#                 expanded_text = os.path.expanduser(text)
#             else:
#                 expanded_text = text
#
#             # 获取匹配的文件和目录，限制数量
#             matches = glob.glob(expanded_text + '*')
#             for match in matches[:8]:  # 增加文件补全数量
#                 # 如果是目录，添加斜杠
#                 if os.path.isdir(match):
#                     options.append(match + '/')
#                 else:
#                     options.append(match)
#         except:
#             pass
#
#         # 2. 如果没有文件匹配且输入长度>=2，尝试命令补全
#         if not options and text and len(text) >= 2:
#             try:
#                 result = subprocess.run(
#                     ['bash', '-c',
#                      f'compgen -c -- {shlex.quote(text)} | grep "^{shlex.quote(text)}" | head -5'],
#                     capture_output=True,
#                     text=True,
#                     timeout=1
#                 )
#
#                 if result.returncode == 0:
#                     completions = result.stdout.strip().split('\n')
#                     for completion in completions:
#                         if completion and completion.strip():
#                             options.append(completion.strip())
#             except:
#                 pass
#
#     # 返回匹配的选项
#     try:
#         return options[state]
#     except IndexError:
#         return None
#
#
# '''
# 自动补全部分
# '''
#
# # def create_completer():
# #     """
# #     创建并返回自动补全函数
# #
# #     Returns:
# #         function: 自动补全函数
# #     """
# #
# #     def completer(text, state):
# #         """自动补全函数 - 彻底修复感叹号问题"""
# #         options = []
# #
# #         # 处理特殊关键字补全
# #         if text.lower() in ['l', 'li', 'lin', 'line']:
# #             options.append('line')
# #
# #         # 处理特殊关键字补全
# #         if text.lower() in ['br', 'bro', 'brow', 'brows', 'browse', 'browser']:
# #             options.append('browser')
# #
# #         # 处理带感叹号前缀的命令补全
# #         if text.startswith('!') or text.startswith('！'):
# #             # 计算连续感叹号的数量
# #             exclamation_prefix = ""
# #             clean_text = text
# #
# #             # 提取所有开头的感叹号
# #             for char in text:
# #                 if char in '!！':
# #                     exclamation_prefix += char
# #                 else:
# #                     break
# #
# #             # 去掉感叹号前缀得到实际的命令文本
# #             clean_text = text[len(exclamation_prefix):]
# #
# #             if clean_text:
# #                 try:
# #                     # 使用bash的补全功能 - 获取以clean_text开头的命令
# #                     result = subprocess.run(
# #                         ['bash', '-c',
# #                          f'compgen -c -- {shlex.quote(clean_text)} | grep "^{shlex.quote(clean_text)}" | head -8'],
# #                         capture_output=True,
# #                         text=True,
# #                         timeout=1
# #                     )
# #
# #                     if result.returncode == 0:
# #                         completions = result.stdout.strip().split('\n')
# #                         # 过滤掉空行并添加原始的感叹号前缀
# #                         for completion in completions:
# #                             if completion and completion.strip():
# #                                 options.append(exclamation_prefix + completion.strip())
# #
# #                 except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
# #                     pass
# #             else:
# #                 # 如果只有感叹号，显示最常用的几个命令
# #                 # 保持原始的感叹号前缀
# #                 common_commands = ['ls', 'cd', 'pwd', 'git', 'python']
# #                 options = [exclamation_prefix + cmd for cmd in common_commands]
# #
# #         else:
# #             # 没有感叹号前缀时的补全逻辑 - 支持当前目录文件补全
# #             # 1. 文件路径补全（包括当前目录和空输入）
# #             try:
# #                 # 处理波浪号
# #                 if text.startswith('~'):
# #                     expanded_text = os.path.expanduser(text)
# #                 else:
# #                     expanded_text = text
# #
# #                 # 获取匹配的文件和目录，限制数量
# #                 matches = glob.glob(expanded_text + '*')
# #                 for match in matches[:8]:  # 增加文件补全数量
# #                     # 如果是目录，添加斜杠
# #                     if os.path.isdir(match):
# #                         options.append(match + '/')
# #                     else:
# #                         options.append(match)
# #             except:
# #                 pass
# #
# #             # 2. 如果没有文件匹配且输入长度>=2，尝试命令补全
# #             if not options and text and len(text) >= 2:
# #                 try:
# #                     result = subprocess.run(
# #                         ['bash', '-c',
# #                          f'compgen -c -- {shlex.quote(text)} | grep "^{shlex.quote(text)}" | head -5'],
# #                         capture_output=True,
# #                         text=True,
# #                         timeout=1
# #                     )
# #
# #                     if result.returncode == 0:
# #                         completions = result.stdout.strip().split('\n')
# #                         for completion in completions:
# #                             if completion and completion.strip():
# #                                 options.append("!" + completion.strip())
# #                 except:
# #                     pass
# #
# #         # 返回匹配的选项
# #         try:
# #             return options[state]
# #         except IndexError:
# #             return None
# #
# #     return completer
#
#
# # def setup_readline_completion(completer_func):
# #     """
# #     配置readline自动补全
# #
# #     Args:
# #         completer_func: 自动补全函数
# #     """
# #     import readline
# #
# #     if hasattr(readline, 'set_completer') and hasattr(readline, 'parse_and_bind'):
# #         readline.set_completer(completer_func)
# #         readline.parse_and_bind("tab: complete")
# #         # 设置补全时的分隔符
# #         readline.set_completer_delims(' \t\n`!@#$%^&*()=+[{]}\\|;:\'\",<>?')
# #
# #         # 配置更简洁的补全显示
# #         try:
# #             readline.parse_and_bind("set show-all-if-unmodified on")  # 只在未修改时显示所有
# #             readline.parse_and_bind("set completion-ignore-case on")  # 忽略大小写
# #             readline.parse_and_bind("set page-completions off")  # 不分页显示补全
# #             readline.parse_and_bind("set completion-query-items 1000")  # 很高的阈值，基本不询问
# #             readline.parse_and_bind("set print-completions-horizontally on")  # 水平显示补全
# #             readline.parse_and_bind("set show-all-if-ambiguous off")  # 不自动显示所有匹配项
# #         except:
# #             pass  # 如果不支持这些选项，忽略错误
