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

import argparse
import asyncio
import operator
# 屏蔽 absl 库的 STDERR 警告
import os
import traceback
import uuid
from typing import Literal

import nest_asyncio
from halo import Halo
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from langchain_community.tools.playwright.utils import create_async_playwright_browser
from langchain_core.messages import AnyMessage, AIMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, START, END
from rich.panel import Panel
from typing_extensions import TypedDict, Annotated

from completion_handler import setup_completion
from input_handler import input_manager
from shared_console import console
from tools.common_tools import ask
from tools.execute_command_tool import execute_command, curl
from tools.math_tools import multiply, add, divide
from tools.search_tool import tavily_search, parse_webpage_to_markdown
from utils.command_exec import run_command
from utils.directory_config import EXCLUDE_DIRECTORIES

os.environ.setdefault('ABSL_LOGGING_VERBOSITY', '1')  # 只显示 WARNING 及以上级别
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')  # 屏蔽 TensorFlow 信息和警告

# 定义颜色常量
CYAN = "\033[96m"
RESET = "\033[0m"

# 全局 LLM 变量，将在 main 函数中初始化
llm = None
llm_with_tools = None
browser_tools = None

base_tools = [add, multiply, divide, execute_command, tavily_search, parse_webpage_to_markdown, ask, curl]

# 初始时不加载浏览器工具
tools = base_tools
browser_tools = None
browser_loaded = False

# 本地会话存储
local_sessions = {}


def get_terminal_display_lines():
    """获取终端可用于显示内容的行数"""
    try:
        terminal_height = console.size.height
        return max(10, terminal_height - 8)
    except:
        # 如果获取终端大小失败，使用默认值
        return 20


def load_browser_tools():
    """按需加载浏览器工具"""
    global browser_tools, tools, browser_loaded

    if browser_loaded:
        return True

    try:
        # 导入 nest_asyncio 来处理异步事件循环冲突
        nest_asyncio.apply()

        # 直接调用 create_async_playwright_browser，它已经是同步函数
        async_browser = create_async_playwright_browser(headless=False)

        toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=async_browser)
        browser_tools = toolkit.get_tools()

        # 更新工具列表
        tools = base_tools + browser_tools
        tools_by_name.update({tool.name: tool for tool in browser_tools})
        browser_loaded = True

        console.print(f"✅ 已成功加载 {len(browser_tools)} 个浏览器工具", style="green")
        console.print(f"🔧 当前工具总数: {len(tools)}", style="cyan")
        return True

    except ImportError as e:
        console.print(f"❌ 浏览器工具加载失败: {str(e)}", style="red")
        console.print("💡 要启用浏览器功能，请重新运行安装脚本: bash install.sh", style="yellow")
        console.print("💡 或者手动安装: pip install -e .[browser] && playwright install", style="yellow")
        return False


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
- parse_webpage_to_markdown 可以用来解析一个url 页面的内容，且响应速度很快
- 在你的认知中 playwright == 浏览器

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
- 针对浏览器场景的操作需要，如果 playwright 已经启动你可以使用 playwright 完成这些任务

## 当前目录结构
{directory_tree}

## 当前是否开启 playwright
{browser_loaded}

请根据用户的需求，充分利用你的工具和当前系统环境来提供最佳的帮助。
''')

    # 过滤掉之前的 SystemMessage，只保留最新的，并清理文本
    non_system_messages = []
    for msg in messages:
        if not isinstance(msg, SystemMessage):
            # cleaned_msg = clean_message(msg)
            non_system_messages.append(msg)

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
        try:

            # 检查是否是异步工具
            if tool_call["name"] in ["tavily_search", "parse_webpage_to_markdown"]:
                observation = await tool.ainvoke(tool_call["args"])
            else:
                observation = tool.invoke(tool_call["args"])
            result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
        except Exception as e:
            traceback.print_exc()
            error_msg = f"  ❌ '{tool_call['name']}' 调用失败，错误信息:{e}"
            console.print(error_msg, style="red")
            result.append(ToolMessage(content=error_msg, tool_call_id=tool_call["id"]))
    return {"messages": result}


# Step 4: Define logic to determine whether to end
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
            # cleaned_msg = clean_message(msg)
            cleaned_messages.append(msg)
        conversation_state["messages"] = cleaned_messages

    combined_panel = Panel(
        f"[bold cyan]✦ Welcome to QozeCode 0.2.1[/bold cyan]\n"
        f"[bold white]模型:[/bold white][bold cyan] {model_name or 'Unknown'}[bold cyan]\n"
        f"[bold white]使用提示:[/bold white]\n"
        f"[dim][bold white]  • 输入 [bold]'q'[/bold]、[bold]'quit'[/bold] 或 [bold]'exit'[/bold] 退出 [/dim] [bold white]\n"
        f"[dim][bold white]  • !开头会直接执行例如：!ls [/dim] [bold white]",
        border_style="dim white",
        title="",
        title_align="center",
        expand=False
    )
    console.print(combined_panel)

    while True:
        try:
            # 使用更安全的输入方式，完全避免提示符被删除的问题
            import readline
            import sys
            import glob

            # 设置自动补全
            setup_completion()

            from completion_handler import create_completer, setup_readline_completion

            # 创建自动补全函数
            completer = create_completer()

            # 配置readline自动补全
            setup_readline_completion(completer)

            user_input = None
            try:
                # 显示提示信息
                console.print("\n")
                console.print("[bold cyan]您：[bold cyan]")
                console.print("[dim]💡 直接输入内容，回车执行请求（输入 'line' 进入多行编辑模式）[/dim]")

                # 首先使用单行输入
                user_input = input().strip()

                # 如果用户输入 'line'，则切换到多行编辑模式
                if user_input.lower() == 'line':
                    console.print("[dim]💡 已进入多行编辑模式，输入内容后按 [Ctrl+D] 提交[/dim]")
                    user_input = await input_manager.get_user_input()

                if user_input.lower() in ['quit', 'exit', '退出', 'q']:
                    # 保存最终状态到本地存储
                    local_sessions[session_id] = conversation_state
                    console.print("👋 再见！", style="bold cyan")
                    return

                # 如果没有任何输入，显示提示并继续
                if not user_input:
                    console.print("💡 请输入您的问题或指令", style="dim")
                    continue


            except (UnicodeDecodeError, UnicodeError, KeyboardInterrupt) as e:
                if isinstance(e, KeyboardInterrupt):
                    raise e  # 重新抛出键盘中断

            if user_input.lower() == 'clear':
                conversation_state["messages"] = []
                conversation_state["llm_calls"] = 0
                local_sessions[session_id] = conversation_state
                console.clear()
                continue

            # 处理 /browser 命令
            if user_input.strip().lower() == 'browser':
                if load_browser_tools():
                    console.print("🎉 浏览器工具已启用！", style="green")
                else:
                    console.print("⚠️ 浏览器工具启用失败，请检查安装。", style="yellow")
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

            # 检查空输入 - 如果为空则直接继续循环，不显示任何提示
            if not user_input:
                continue

            # 创建用户消息
            user_message = HumanMessage(content=user_input)

            # 更新对话状态
            current_state = {
                "messages": conversation_state["messages"] + [user_message],
                "llm_calls": conversation_state["llm_calls"]
            }

            current_response_text = ""  # 当前流式响应的文本
            need_point = True
            has_response = False

            async for message_chunk, metadata in agent.astream(current_state, stream_mode="messages",
                                                               config={"recursion_limit": 150}):

                # 1. 检查消息是否是 ToolMessage 类型
                if isinstance(message_chunk, ToolMessage):
                    continue

                if message_chunk.content:
                    # 提取文本内容
                    chunk_text = ''
                    if isinstance(message_chunk.content, list):
                        for content_item in message_chunk.content:
                            if isinstance(content_item, dict) and 'type' in content_item and content_item.get(
                                    'type') == 'text':
                                text_content = content_item.get('text', '')
                                chunk_text += text_content
                    elif isinstance(message_chunk.content, str):
                        text_content = message_chunk.content
                        chunk_text += text_content

                    if chunk_text != '':
                        has_response = True
                        print(f"{CYAN}●{RESET} {chunk_text}" if need_point else chunk_text, end='', file=sys.stderr)
                        need_point = False
                        current_response_text += chunk_text

                if hasattr(message_chunk, 'response_metadata') and message_chunk.response_metadata:
                    if 'finish_reason' in message_chunk.response_metadata:
                        # need_point = True
                        if has_response:
                            print("\n", end='')
                        has_response = False
                        continue

                ai_response = AIMessage(content=current_response_text)
                conversation_state["messages"].extend([user_message, ai_response])
                conversation_state["llm_calls"] += 1
                # todo 任务结束
                local_sessions[session_id] = conversation_state




        except KeyboardInterrupt:
            console.print("\n\n👋 程序被用户中断", style="yellow")
            # 保存状态到本地存储
            local_sessions[session_id] = conversation_state
            break

        except Exception as e:
            console.print(f"\n❌ 发生错误: {str(e)}", style="red")


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

    try:
        # 初始化选择的模型（仅构建客户端，不做网络验证）
        with console.status("[bold cyan]正在初始化模型...", spinner="dots"):
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
        console.print(f"\n❌ 启动失败: {str(e)}", style="red")
