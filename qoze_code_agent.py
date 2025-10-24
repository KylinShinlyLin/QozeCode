#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright 2025 QozeCode

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

# 屏蔽 absl 库的 STDERR 警告
import os

os.environ.setdefault('ABSL_LOGGING_VERBOSITY', '1')  # 只显示 WARNING 及以上级别
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')  # 屏蔽 TensorFlow 信息和警告

import argparse
import asyncio
import operator
import re
import time
import traceback
import uuid
from typing import Literal

from langchain_core.messages import AnyMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, START, END
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt
from typing_extensions import TypedDict, Annotated

from config_manager import ensure_model_credentials
from shared_console import console
from tools.common_tools import ask
from tools.execute_command_tool import execute_command, curl
from tools.math_tools import multiply, add, divide
from tools.tavily_search_tool import tavily_search
from utils.command_exec import run_command
from utils.directory_config import EXCLUDE_DIRECTORIES

# # 导入浏览器工具
# try:
#     from tools.browser_tools import (
#         navigate_browser,
#         click_element,
#         extract_text,
#         extract_hyperlinks,
#         get_elements,
#         current_page,
#         navigate_back,
#         close_browser
#     )
#
#     BROWSER_TOOLS_AVAILABLE = True
#
# except ImportError as e:
#     BROWSER_TOOLS_AVAILABLE = False
#     console.print(f"⚠️ 浏览器工具不可用: {str(e)}", style="yellow")
#     console.print("💡 要启用浏览器功能，请安装: pip install playwright langchain-community", style="yellow")
#     console.print("💡 然后运行: playwright install", style="yellow")

# 本地会话存储
local_sessions = {}


# toolkit = FileManagementToolkit(
#     selected_tools=["list_directory"],
# )


def clean_text(text: str) -> str:
    """清理文本中的无效UTF-8字符和代理字符"""
    if not isinstance(text, str):
        return str(text)

    try:
        # 移除代理字符（surrogates）
        text = text.encode('utf-8', 'ignore').decode('utf-8')

        # 移除其他可能有问题的字符
        text = re.sub(r'[\uD800-\uDFFF]', '', text)  # 移除代理字符
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)  # 移除控制字符

        return text
    except Exception as e:
        console.print(f"⚠️  文本清理失败: {e}", style="yellow")
        # 如果清理失败，返回安全的ASCII版本
        return text.encode('ascii', 'ignore').decode('ascii')


def clean_message(message):
    """清理消息对象中的文本内容"""
    if hasattr(message, 'content') and message.content:
        if isinstance(message.content, str):
            message.content = clean_text(message.content)
        elif isinstance(message.content, list):
            for item in message.content:
                if isinstance(item, dict) and 'text' in item:
                    item['text'] = clean_text(item['text'])
    return message


# 全局 LLM 变量，将在 main 函数中初始化
llm = None
llm_with_tools = None

base_tools = [add, multiply, divide, execute_command, tavily_search, ask, curl]
# base_tools = [add, multiply, divide, execute_command, tavily_search, ask, curl]
# base_tools += toolkit.get_tools()
# # 判断是否有浏览器操作依赖
# if BROWSER_TOOLS_AVAILABLE:
#     browser_tool_list = [
#         navigate_browser,
#         click_element,
#         extract_text,
#         extract_hyperlinks,
#         get_elements,
#         current_page,
#         navigate_back
#     ]
#     base_tools += browser_tool_list

# # 添加浏览器工具（如果可用）
# if BROWSER_TOOLS_AVAILABLE:
#     browser_tool_list = [
#         navigate_browser,
#         click_element,
#         extract_text,
#         extract_hyperlinks,
#         get_elements,
#         current_page,
#         navigate_back
#     ]
#     tools = base_tools + browser_tool_list
#     console.print(f"🔧 已加载 {len(tools)} 个工具 (包含浏览器工具)", style="cyan")
# else:
#     tools = base_tools
#     console.print(f"🔧 已加载 {len(tools)} 个工具 (不包含浏览器工具)", style="cyan")
tools = base_tools
tools_by_name = {tool.name: tool for tool in tools}


# Step 1: Define state

class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int


# Step 2: Define model node
def llm_call(state: dict):
    import platform
    import os
    import socket
    import subprocess

    messages = state["messages"]
    # current_time = time.strftime("%Y-%m-%d %H:%M:%S")

    # 获取系统信息
    try:
        # 基本系统信息
        system_info = platform.system()
        system_version = platform.version()
        system_release = platform.release()
        machine_type = platform.machine()
        processor = platform.processor()

        # 当前工作目录
        current_dir = os.getcwd()

        # 用户信息
        username = os.getenv('USER') or os.getenv('USERNAME') or 'unknown'

        # 主机名
        hostname = socket.gethostname()

        # 环境变量中的重要信息
        shell = os.getenv('SHELL', 'unknown')
        home_dir = os.getenv('HOME', 'unknown')

        # 获取当前目录树结构（智能限制深度和长度）
        try:

            # 智能判断目录深度：根据当前目录路径决定扫描深度
            path_depth = len(current_dir.split(os.sep))
            if path_depth <= 3:  # 接近根目录
                max_depth = 3
            elif path_depth <= 5:  # 中等深度
                max_depth = 4
            else:  # 深层目录
                max_depth = 5

            # 设置最大输出长度限制（约2000个字符，避免token溢出）
            MAX_TREE_LENGTH = 3000

            if system_info == "Windows":
                # Windows 使用 tree 命令，限制深度
                tree_result = subprocess.run(['tree', '/F', '/A', f'/L:{max_depth}'],
                                             capture_output=True, text=True, cwd=current_dir, timeout=10)
            else:
                # Unix-like 系统使用 tree 命令，如果没有则使用 find
                try:
                    # 使用 -I 参数排除指定目录，限制深度
                    exclude_pattern = '|'.join(EXCLUDE_DIRECTORIES)
                    tree_result = subprocess.run(['tree', '-L', str(max_depth), '-a', '-I', exclude_pattern],
                                                 capture_output=True, text=True, cwd=current_dir, timeout=10)
                except FileNotFoundError:
                    # 如果没有 tree 命令，使用 find 作为备选，并手动过滤
                    find_cmd = ['find', '.', '-maxdepth', str(max_depth)]
                    # 为每个排除目录添加 -not -path 条件
                    for exclude_dir in EXCLUDE_DIRECTORIES:
                        find_cmd.extend(['-not', '-path', f'*/{exclude_dir}/*'])
                        find_cmd.extend(['-not', '-name', exclude_dir])
                    find_cmd.extend(['-type', 'd'])

                    tree_result = subprocess.run(find_cmd, capture_output=True, text=True, cwd=current_dir, timeout=10)

            if tree_result.returncode == 0:
                raw_tree = tree_result.stdout.strip()

                # 智能截断：如果输出过长，进行截断并添加提示
                if len(raw_tree) > MAX_TREE_LENGTH:
                    # 按行分割，保留前面的行
                    lines = raw_tree.split('\n')
                    truncated_lines = []
                    current_length = 0

                    for line in lines:
                        if current_length + len(line) + 1 > MAX_TREE_LENGTH - 100:  # 预留空间给提示信息
                            break
                        truncated_lines.append(line)
                        current_length += len(line) + 1

                    directory_tree = '\n'.join(truncated_lines)
                    directory_tree += f"\n\n... (目录结构过大，已截断显示前 {len(truncated_lines)} 行)"
                    directory_tree += f"\n💡 提示: 当前在 {current_dir}，建议在具体项目目录中执行以获得更详细的结构信息"
                else:
                    directory_tree = raw_tree
            else:
                directory_tree = "无法获取目录结构"
        except subprocess.TimeoutExpired:
            directory_tree = "目录结构获取超时（目录过大）"
        except Exception:
            directory_tree = "无法获取目录结构"

    except Exception:
        # 如果获取系统信息失败，使用基本信息
        system_info = platform.system()
        system_version = "unknown"
        current_dir = os.getcwd()
        username = os.getenv('USER', 'unknown')
        hostname = socket.gethostname()

        shell = home_dir = "unknown"
        machine_type = processor = "unknown"
        directory_tree = "无法获取目录结构"

    # 确保 SystemMessage 在开头
    system_msg = SystemMessage(
        content=f'''
你一名专业的终端AI agent 助手，你当前正运行在当前电脑的终端中
- 你需要根据我的诉求，利用当前支持的tools帮我完成复杂的任务

## 系统环境信息
**操作系统**: {system_info} {system_release} ({system_version})
**架构**: {machine_type}
**处理器**: {processor}
**主机名**: {hostname}
**用户**: {username}
**Shell**: {shell}

## 当前环境
**工作目录**: {current_dir}
**用户主目录**: {home_dir}

## 工作原则
- 不要去虚构不存在的内容
- 为了加快回复速度，可以一个命令执行多个操作节约时间
- 或者避免大量 token 的浪费，需要查找的内容，尽量避免读取整个文件
- 写入修改文件的时候也避免整个文件重写，可以使用 grep + sed 组合来定位和修改特定内容
- 始终考虑当前的系统环境和资源限制
- 文件编辑尽量有限使用提供个工具方式操作
- 在执行可能影响系统的操作前，先评估风险
- 优先使用适合当前操作系统的命令和工具
- 提供准确、实用的建议和解决方案
- 保持对用户数据和隐私的尊重
- 我为了保证任务完成质量，需要对执行结果进行检查
- 你可以使用python脚本，帮我处理Excel相关的任务

## 当前目录结构
{directory_tree}

请根据用户的需求，充分利用你的工具和当前系统环境来提供最佳的帮助。
''')

    # 过滤掉之前的 SystemMessage，只保留最新的，并清理文本
    non_system_messages = []
    for msg in messages:
        if not isinstance(msg, SystemMessage):
            cleaned_msg = clean_message(msg)
            non_system_messages.append(cleaned_msg)

    final_messages = [system_msg] + non_system_messages

    return {
        "messages": [llm_with_tools.invoke(final_messages)],
        "llm_calls": state.get('llm_calls', 0) + 1
    }


# Step 3: Define tool node
async def tool_node(state: dict):
    """Performs the tool call"""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]

        # 检查是否是异步工具
        if tool_call["name"] in ["tavily_search", "navigate_browser", "click_element",
                                 "extract_text", "extract_hyperlinks", "get_elements",
                                 "current_page", "navigate_back"]:
            observation = await tool.ainvoke(tool_call["args"])
        else:
            observation = tool.invoke(tool_call["args"])

        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result}


# Step 4: Define logic to determine whether to end

# Conditional edge function to route to the tool node or end based upon whether the LLM made a tool call
def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]
    last_message = messages[-1]
    # If the LLM makes a tool call, then perform an action
    if last_message.tool_calls:
        return "tool_node"
    # Otherwise, we stop (reply to the user)
    return END


# Step 5: Build agent
# Build workflow
agent_builder = StateGraph(MessagesState)

# Add nodes
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)

# Add edges to connect nodes
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    ["tool_node", END]
)
agent_builder.add_edge("tool_node", "llm_call")

# Compile the agent
agent = agent_builder.compile()


# 多轮对话函数
async def chat_loop(session_id: str = None, model_name: str = None):
    # 如果没有提供 session_id，生成一个新的
    if not session_id:
        session_id = str(uuid.uuid4())

    # 尝试从本地存储加载历史上下文
    conversation_state = {"messages": [], "llm_calls": 0}
    if session_id in local_sessions:
        conversation_state = local_sessions[session_id]
        # 清理历史消息中的无效字符
        cleaned_messages = []
        for msg in conversation_state["messages"]:
            cleaned_msg = clean_message(msg)
            cleaned_messages.append(cleaned_msg)
        conversation_state["messages"] = cleaned_messages

    combined_panel = Panel(
        f"[bold cyan]🚀 QozeCode Agent[/bold cyan]\n"
        f"[bold white]模型:[/bold white] [bold yellow]{model_name or 'Unknown'}[/bold yellow]\n"
        f"[bold white]状态:[/bold white] [bold green]启动成功 [/bold green] \n"
        f"[bold white]💡 使用提示:[/bold white]\n"
        f"[dim]  • 输入问题开始对话\n"
        f"  • 输入 [bold]'q'[/bold]、[bold]'quit'[/bold] 或 [bold]'exit'[/bold] 退出\n"
        f"  • !开头会直接执行例如：!ls\n"
        f"  • 支持多轮对话和上下文记忆\n",
        border_style="cyan",
        title="[bold green]启动完成[/bold green]",
        title_align="center",
        padding=(1, 1),
        expand=False
    )
    console.print(combined_panel)

    while True:
        try:
            # 使用更安全的输入方式，完全避免提示符被删除的问题
            import readline
            import sys
            import glob

            # 定义自动补全函数
            def completer(text, state):
                """自动补全函数 - 彻底修复感叹号问题"""
                import subprocess
                import shlex
                import glob
                import os

                options = []

                # 处理带感叹号前缀的命令补全
                if text.startswith('!') or text.startswith('！'):
                    # 计算连续感叹号的数量
                    exclamation_prefix = ""
                    clean_text = text

                    # 提取所有开头的感叹号
                    for char in text:
                        if char in '!！':
                            exclamation_prefix += char
                        else:
                            break

                    # 去掉感叹号前缀得到实际的命令文本
                    clean_text = text[len(exclamation_prefix):]

                    if clean_text:
                        try:
                            # 使用bash的补全功能 - 获取以clean_text开头的命令
                            result = subprocess.run(
                                ['bash', '-c',
                                 f'compgen -c -- {shlex.quote(clean_text)} | grep "^{shlex.quote(clean_text)}" | head -8'],
                                capture_output=True,
                                text=True,
                                timeout=1
                            )

                            if result.returncode == 0:
                                completions = result.stdout.strip().split('\n')
                                # 过滤掉空行并添加原始的感叹号前缀
                                for completion in completions:
                                    if completion and completion.strip():
                                        options.append(exclamation_prefix + completion.strip())

                        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                            pass
                    else:
                        # 如果只有感叹号，显示最常用的几个命令
                        # 保持原始的感叹号前缀
                        common_commands = ['ls', 'cd', 'pwd', 'git', 'python']
                        options = [exclamation_prefix + cmd for cmd in common_commands]

                else:
                    # 没有感叹号前缀时的补全逻辑 - 支持当前目录文件补全
                    # 1. 文件路径补全（包括当前目录和空输入）
                    try:
                        # 处理波浪号
                        if text.startswith('~'):
                            expanded_text = os.path.expanduser(text)
                        else:
                            expanded_text = text

                        # 获取匹配的文件和目录，限制数量
                        matches = glob.glob(expanded_text + '*')
                        for match in matches[:8]:  # 增加文件补全数量
                            # 如果是目录，添加斜杠
                            if os.path.isdir(match):
                                options.append(match + '/')
                            else:
                                options.append(match)
                    except:
                        pass

                    # 2. 如果没有文件匹配且输入长度>=2，尝试命令补全
                    if not options and text and len(text) >= 2:
                        try:
                            result = subprocess.run(
                                ['bash', '-c',
                                 f'compgen -c -- {shlex.quote(text)} | grep "^{shlex.quote(text)}" | head -5'],
                                capture_output=True,
                                text=True,
                                timeout=1
                            )

                            if result.returncode == 0:
                                completions = result.stdout.strip().split('\n')
                                for completion in completions:
                                    if completion and completion.strip():
                                        options.append("!" + completion.strip())
                        except:
                            pass

                # 返回匹配的选项
                try:
                    return options[state]
                except IndexError:
                    return None

                else:
                    # 没有感叹号前缀时的补全逻辑 - 支持当前目录文件补全
                    # 1. 文件路径补全（包括当前目录和空输入）
                    try:
                        # 处理波浪号
                        if text.startswith('~'):
                            expanded_text = os.path.expanduser(text)
                        else:
                            expanded_text = text

                        # 获取匹配的文件和目录，限制数量
                        matches = glob.glob(expanded_text + '*')
                        for match in matches[:8]:  # 增加文件补全数量
                            # 如果是目录，添加斜杠
                            if os.path.isdir(match):
                                options.append(match + '/')
                            else:
                                options.append(match)
                    except:
                        pass

                    # 2. 如果没有文件匹配且输入长度>=2，尝试命令补全
                    if not options and text and len(text) >= 2:
                        try:
                            result = subprocess.run(
                                ['bash', '-c',
                                 f'compgen -c -- {shlex.quote(text)} | grep "^{shlex.quote(text)}" | head -5'],
                                capture_output=True,
                                text=True,
                                timeout=1
                            )

                            if result.returncode == 0:
                                completions = result.stdout.strip().split('\n')
                                for completion in completions:
                                    if completion and completion.strip():
                                        options.append("!" + completion.strip())
                        except:
                            pass

                # 返回匹配的选项
                try:
                    return options[state]
                except IndexError:
                    return None

            try:
                # 清除任何可能的readline历史干扰
                if hasattr(readline, 'clear_history'):
                    readline.clear_history()

                # 设置readline配置，确保提示符安全
                if hasattr(readline, 'set_startup_hook'):
                    readline.set_startup_hook(None)

                # 配置简洁的自动补全
                if hasattr(readline, 'set_completer') and hasattr(readline, 'parse_and_bind'):
                    readline.set_completer(completer)
                    readline.parse_and_bind("tab: complete")
                    # 设置补全时的分隔符
                    readline.set_completer_delims(' \t\n`!@#$%^&*()=+[{]}\\|;:\'",<>?')

                    # 配置更简洁的补全显示
                    try:
                        readline.parse_and_bind("set show-all-if-unmodified on")  # 只在未修改时显示所有
                        readline.parse_and_bind("set completion-ignore-case on")  # 忽略大小写
                        readline.parse_and_bind("set page-completions off")  # 不分页显示补全
                        readline.parse_and_bind("set completion-query-items 1000")  # 很高的阈值，基本不询问
                        readline.parse_and_bind("set print-completions-horizontally on")  # 水平显示补全
                        readline.parse_and_bind("set show-all-if-ambiguous off")  # 不自动显示所有匹配项
                    except:
                        pass  # 如果不支持这些选项，忽略错误

                # 先显示提示符，然后在新行获取输入
                console.print("[bold rgb(255,165,0)]您：[/bold rgb(255,165,0)]", )
                user_input = input().strip()

                # 清理可能的编码问题
                user_input = clean_text(user_input)

            except (UnicodeDecodeError, UnicodeError, KeyboardInterrupt) as e:
                if isinstance(e, KeyboardInterrupt):
                    raise e  # 重新抛出键盘中断
                # 如果遇到编码错误，回退到Rich的Prompt.ask
                console.print("\n")  # 换行
                try:
                    user_input = Prompt.ask(
                        "[bold cyan]您[/bold cyan]",
                        console=console,
                        default="",
                        show_default=False
                    ).strip()
                    user_input = clean_text(user_input)
                except Exception:
                    user_input = ""

            # 优雅处理空输入：静默跳过，保持界面整洁
            if not user_input:
                continue

            if user_input.lower() == 'clear':
                conversation_state["messages"] = []
                conversation_state["llm_calls"] = 0
                local_sessions[session_id] = conversation_state
                console.clear()
                continue

            if user_input.startswith('!') or user_input.startswith('！'):
                # 去掉所有开头的感叹号，避免多个感叹号导致命令执行失败
                command = user_input.lstrip('!！').strip()
                if not command:
                    console.print("⚠️ 请输入要执行的命令，如: ! ls -la", style="yellow")
                    continue

                # 使用独立命令执行器，实时输出并返回完整内容
                output = run_command(command)

                # 合并为一条用户消息
                combined_content = f"command:{command}\n\nresult:{output}"
                conversation_state["messages"].extend([
                    HumanMessage(content=combined_content)
                ])
                local_sessions[session_id] = conversation_state
                continue

            # 在有效输入后添加视觉分隔，提升可读性
            console.print()

            # 检查退出命令
            if user_input.lower() in ['quit', 'exit', '退出', 'q']:
                # 保存最终状态到本地存储
                local_sessions[session_id] = conversation_state
                console.print("👋 再见！", style="bold cyan")
                break

            # 检查空输入 - 如果为空则直接继续循环，不显示任何提示
            if not user_input:
                continue

            # 清理用户输入
            user_input = clean_text(user_input)

            # 创建用户消息
            user_message = HumanMessage(content=user_input)

            # 更新对话状态
            current_state = {
                "messages": conversation_state["messages"] + [user_message],
                "llm_calls": conversation_state["llm_calls"]
            }

            # 创建进度指示器
            with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    TimeElapsedColumn(),
                    refresh_per_second=20,
                    console=console,
                    # transient=False  # 完成后自动清除
            ) as progress:
                # 添加任务进度
                task_id = progress.add_task("🚀 正在处理您的请求...", total=None)

                # 使用Live来实时更新显示
                with Live(console=console, refresh_per_second=30) as live:  # 降低刷新频率从10到4
                    # 收集完整的响应消息
                    response_messages = []
                    last_update_time = 0
                    update_interval = 0.01  # 最小更新间隔250ms，避免过于频繁的更新
                    current_response_text = ""  # 当前流式响应的文本
                    complete_responses = []  # 存储已完成的响应段落

                    # 使用流式处理
                    async for message_chunk, metadata in agent.astream(current_state, stream_mode="messages",
                                                                       config={"recursion_limit": 150}):
                        # print(message_chunk)
                        # 更新进度状态
                        if hasattr(message_chunk, 'tool_calls') and message_chunk.tool_calls:
                            # 检测到工具调用，更新进度描述
                            tool_names = [call['name'] for call in message_chunk.tool_calls]
                            progress.update(task_id, description=f"🔧 正在执行工具: {', '.join(tool_names)}")
                        elif message_chunk.content:
                            # 检测到内容生成，更新进度描述
                            progress.update(task_id, description="💭 正在生成回复...")

                        # print(message_chunk)
                        # 1. 检查消息是否是 ToolMessage 类型
                        if isinstance(message_chunk, ToolMessage):
                            # 检查工具名称
                            if hasattr(message_chunk, 'name') and message_chunk.name in ['execute_command', 'curl']:
                                continue
                            # 检查工具调用ID中是否包含这些工具
                            elif hasattr(message_chunk, 'tool_call_id'):
                                # 可以根据需要添加更多检查逻辑
                                continue

                        # 检查是否有 finish_reason
                        has_finish_reason = False
                        if hasattr(message_chunk, 'response_metadata') and message_chunk.response_metadata:
                            if 'finish_reason' in message_chunk.response_metadata:
                                live.update("")
                                has_finish_reason = True

                        if message_chunk.content:
                            # 收集响应消息
                            response_messages.append(message_chunk)
                            # 提取文本内容
                            chunk_text = ""
                            if isinstance(message_chunk.content, list):
                                for content_item in message_chunk.content:
                                    if isinstance(content_item, dict) and 'type' in content_item and content_item.get(
                                            'type') == 'text':
                                        text_content = content_item.get('text', '')
                                        # 清理文本内容
                                        text_content = clean_text(text_content)
                                        chunk_text += text_content
                            elif isinstance(message_chunk.content, str):
                                text_content = message_chunk.content
                                # 清理文本内容
                                text_content = clean_text(text_content)
                                chunk_text += text_content

                            # 累积当前响应文本
                            current_response_text += chunk_text

                            # 防抖机制：限制更新频率
                            current_time = time.time()
                            if current_time - last_update_time >= update_interval:
                                # 在文件顶部，clean_text函数之后添加这些辅助函数
                                def get_terminal_display_lines():
                                    """获取终端可用于显示内容的行数"""
                                    try:
                                        terminal_height = console.size.height
                                        # 预留空间给Panel边框(2行)、标题(1行)、padding(2行)、其他UI元素(3行)
                                        return max(10, terminal_height - 8)
                                    except:
                                        # 如果获取终端大小失败，使用默认值
                                        return 20

                                # 添加滚动显示的辅助函数
                                def create_scrollable_markdown(text: str, show_scroll_info: bool = True) -> Markdown:
                                    """创建可滚动的Panel，自动显示最新内容"""
                                    try:
                                        if not text.strip():
                                            return Markdown("正在思考...", style="blue")

                                        max_lines = get_terminal_display_lines()
                                        lines = text.split('\n')

                                        if len(lines) <= max_lines:
                                            display_text = text
                                        else:
                                            if show_scroll_info:
                                                # 显示滚动指示器和最新内容
                                                total_lines = len(lines)
                                                scroll_indicator = f"内容较长，显示最新 {max_lines} 行 (共 {total_lines} 行)"
                                                display_lines = [scroll_indicator, ""] + lines[-max_lines:]
                                                display_text = '\n'.join(display_lines)
                                            else:
                                                # 不显示滚动指示器，直接显示最新内容
                                                display_text = '\n'.join(lines[-max_lines:])
                                        return Markdown(display_text, style="rgb(0,191,255)", justify="left",
                                                        hyperlinks=True)
                                    except Exception as e:
                                        # 如果创建Panel失败，返回简单的错误Panel
                                        return Markdown(f"显示错误: {str(e)}", style="red")

                                # 实时更新显示
                                if current_response_text:
                                    try:
                                        # 构建完整的显示文本（包括之前完成的响应）
                                        full_display_text = ""

                                        # 添加已完成的响应
                                        for i, completed_text in enumerate(complete_responses):
                                            full_display_text += completed_text
                                            if i < len(complete_responses) - 1:
                                                full_display_text += "\n---\n"

                                        # 添加当前正在流式的响应
                                        if complete_responses and current_response_text:
                                            full_display_text += "\n---\n"
                                        full_display_text += current_response_text

                                        updated_markdown = create_scrollable_markdown(full_display_text)
                                        live.update(updated_markdown)
                                        last_update_time = current_time
                                    except Exception as e:
                                        # 如果更新失败，记录错误但继续处理
                                        console.print(f"更新显示时出错: {str(e)}", style="red")

                        # 如果检测到 finish_reason，创建完整的 Panel
                        if has_finish_reason and current_response_text.strip():
                            try:
                                # 将当前响应添加到完成列表
                                complete_responses.append(current_response_text)

                                # 构建包含所有已完成响应的显示文本
                                all_completed_text = ""
                                for i, completed_text in enumerate(complete_responses):
                                    all_completed_text += completed_text
                                    if i < len(complete_responses) - 1:
                                        all_completed_text += "\n\n---\n\n"

                                complete_markdown = Markdown(current_response_text, style="rgb(0,191,255)",
                                                             justify="left",
                                                             hyperlinks=True)
                                console.print(complete_markdown)

                                # 重置当前响应文本，准备接收下一段流式内容
                                current_response_text = ""
                                complete_responses = []

                            except Exception as e:
                                console.print(f"创建完整回复Panel时出错: {str(e)}", style="red")

                    # 最终处理：如果还有未完成的响应文本
                    if current_response_text.strip():
                        complete_responses.append(current_response_text)

                    # 合并所有响应文本
                    response_text = "\n\n---\n\n".join(complete_responses) if len(complete_responses) > 1 else (
                        complete_responses[0] if complete_responses else "")

                    # 显示最终的完整回复
                    if response_text:
                        # try:
                        #     final_complete_markdown = Markdown(response_text, style="blue", justify="left")
                        #     live.update(final_complete_markdown)
                        #
                        # except Exception as e:
                        #     console.print(f"显示最终完整回复时出错: {str(e)}", style="red")

                        from langchain_core.messages import AIMessage
                        # 创建AI消息对象，只包含文本内容
                        ai_response = AIMessage(content=response_text)
                        # 更新对话状态，使用简化的响应消息
                        conversation_state["messages"].extend([user_message, ai_response])
                    else:
                        # 如果没有文本内容，仍然保存原始响应
                        conversation_state["messages"].extend([user_message] + response_messages)

                    conversation_state["llm_calls"] += 1

                    # 标记任务完成
                    progress.update(task_id, description="✅ 任务完成", completed=True)

                    # 实时保存状态到本地存储
                    local_sessions[session_id] = conversation_state

        except KeyboardInterrupt:
            console.print("\n\n👋 程序被用户中断", style="yellow")
            # 保存状态到本地存储
            local_sessions[session_id] = conversation_state
            break
        except Exception as e:
            console.print(f"\n❌ 发生错误: {str(e)}", style="red")
            # 如果是编码错误，尝试清理会话数据
            if "utf-8" in str(e).lower() or "surrogate" in str(e).lower():
                console.print("🔧 检测到编码问题，正在清理会话数据...", style="yellow")
                # 清理所有历史消息
                cleaned_messages = []
                for msg in conversation_state.get("messages", []):
                    try:
                        cleaned_msg = clean_message(msg)
                        cleaned_messages.append(cleaned_msg)
                    except:
                        console.print(f"⚠️  跳过无法清理的消息", style="dim yellow")
                        continue
                conversation_state["messages"] = cleaned_messages
                local_sessions[session_id] = conversation_state
                console.print("✅ 会话数据已清理，请重新输入", style="green")
            else:
                traceback.print_exc()


async def start_chat_with_session(session_id: str = None, model_name: str = None):
    """启动带会话 ID 的聊天"""
    await chat_loop(session_id, model_name)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='QozeCode Agent - AI编程助手')
    parser.add_argument(
        '--model',
        choices=['claude-4', 'gemini', 'gpt-5'],
        default='gemini',
        help='选择要使用的AI模型 (默认: gemini)'
    )
    parser.add_argument(
        '--session-id',
        default='123',
        help='会话ID (默认: 123)'
    )
    return parser.parse_args()


def handleRun(model_name: str = None, session_id: str = None):
    """主函数 - 支持直接传入参数或从命令行解析"""
    global llm, llm_with_tools

    # 如果没有直接传入参数，则解析命令行参数
    if model_name is None or session_id is None:
        args = parse_arguments()
        model_name = model_name or args.model
        session_id = session_id or args.session_id

    # # 先进行凭证交互式输入与保存，避免在加载状态下阻塞输入
    # try:
    #     ensure_model_credentials(model_name)
    # except KeyboardInterrupt:
    #     return
    # except Exception as e:
    #     console.print(f"\n❌ {model_name} 凭证验证失败: {str(e)}", style="red")

    try:
        # 初始化选择的模型（仅构建客户端，不做网络验证）
        with console.status("[bold green]正在初始化模型...", spinner="dots"):
            # 延迟导入以避免启动时加载模型相关重依赖
            from model_initializer import initialize_llm
            llm = initialize_llm(model_name)
            # 初始化带工具的 LLM
            llm_with_tools = llm.bind_tools(tools)
        # 启动聊天循环
        asyncio.run(start_chat_with_session(session_id, model_name))

    except KeyboardInterrupt:
        console.print("\n\n👋 程序被用户中断", style="yellow")
    except Exception as e:
        # traceback.print_exc()
        console.print(f"\n❌ 启动失败: {str(e)}", style="red")
