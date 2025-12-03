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
# import os
import traceback
import uuid
from typing import Literal
import platform
import os
import socket
# import nest_asyncio
# from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
# from langchain_community.tools.playwright.utils import create_async_playwright_browser
from langchain_core.messages import AnyMessage, AIMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_core.messages import ToolMessage
from langgraph.graph import StateGraph, START, END
from rich.panel import Panel
from typing_extensions import TypedDict, Annotated

from completion_handler import setup_completion
from input_handler import input_manager
from input_processor import InputProcessor
from shared_console import console
from stream_output import StreamOutput
# from tools.common_tools import ask
from tools.execute_command_tool import execute_command
from tools.math_tools import multiply, add, divide
from tools.search_tool import tavily_search, get_webpage_to_markdown
from utils.directory_tree import get_directory_tree
from utils.system_prompt import get_system_prompt

os.environ.setdefault('ABSL_LOGGING_VERBOSITY', '1')  # 只显示 WARNING 及以上级别
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')  # 屏蔽 TensorFlow 信息和警告

# 定义颜色常量
CYAN = "\033[96m"
RESET = "\033[0m"

# 全局 LLM 变量，将在 main 函数中初始化
llm = None
llm_with_tools = None
browser_tools = None

base_tools = [add, multiply, divide, execute_command, tavily_search, get_webpage_to_markdown]

# 初始时不加载浏览器工具
tools = base_tools
browser_loaded = False
plan_mode = False
# 当前会话
conversation_state = {"messages": [], "llm_calls": 0}


def get_terminal_display_lines():
    """获取终端可用于显示内容的行数"""
    try:
        terminal_height = console.size.height
        return max(10, terminal_height - 8)
    except:
        # 如果获取终端大小失败，使用默认值
        return 20


tools_by_name = {tool.name: tool for tool in tools}


# Step 1: Define state

class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int


# Step 2: Define model node
def llm_call(state: dict):
    # messages = state["messages"]
    system_release = ''
    system_info = platform.system()
    system_version = "unknown"
    current_dir = os.getcwd()
    username = os.getenv('USER', 'unknown')
    hostname = socket.gethostname()

    shell = home_dir = "unknown"
    machine_type = processor = "unknown"
    directory_tree = "无法获取目录结构"
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
        directory_tree = get_directory_tree(current_dir)

    except Exception:
        print("获取设备信息异常")

    system_msg = get_system_prompt(system_info=system_info, system_release=system_release,
                                   system_version=system_version, machine_type=machine_type, processor=processor,
                                   hostname=hostname, username=username, shell=shell, current_dir=current_dir,
                                   home_dir=home_dir, directory_tree=directory_tree, plan_mode=plan_mode)

    # # 过滤掉之前的 SystemMessage，只保留最新的，并清理文本
    # non_system_messages = []
    # for msg in messages:
    #     if not isinstance(msg, SystemMessage):
    #         non_system_messages.append(msg)
    #
    # final_messages = [system_msg] + non_system_messages
    # print(f"请求AI上下文:{final_messages}")

    # converted_messages = []
    # for msg in state["messages"]:
    #     if isinstance(msg, AIMessage):
    #         # 根据您的需求构建 JSON 对象
    #         json_msg = msg.model_dump()
    #         json_msg['reasoning_content'] = msg.additional_kwargs['reasoning_content']
    #         print(f"AIMessage={json_msg}")
    #         converted_messages.append(json_msg)
    #     else:
    #         converted_messages.append(msg)  # 其他类型消息保持不变
    #
    # # 然后使用 converted_messages
    #
    # return {
    #     "messages": [
    #         llm_with_tools.invoke([SystemMessage(content=system_msg)] + converted_messages)
    #     ],
    #     "llm_calls": state.get('llm_calls', 0) + 1
    # }

    # print(f"messages={[
    #                       SystemMessage(
    #                           content=system_msg
    #                       )
    #                   ]
    #                   + state["messages"]}")
    # print(f"llm_with_tools={llm_with_tools}")
    return {
        "messages": [
            llm_with_tools.invoke(
                [
                    SystemMessage(
                        content=system_msg
                    )
                ]
                + state["messages"]
            )
        ],
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
            if tool_call["name"] in ["tavily_search", "get_webpage_to_markdown"]:
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
    global plan_mode
    os.system('cls' if os.name == 'nt' else 'clear')
    combined_panel = Panel(
        f"[bold dim cyan]✦ Welcome to QozeCode 0.2.3[/bold dim cyan]\n\n"
        f"[bold white]模型:[/bold white][bold cyan] {model_name or 'Unknown'}[bold cyan]\n"
        f"[bold white]使用提示:[/bold white]\n"
        f"[dim][bold white]  • 输入 [bold]'q'[/bold]、[bold]'quit'[/bold] 或 [bold]'exit'[/bold] 退出 [/dim] [bold white]\n"
        f"[dim][bold white]  • !开头会直接执行例如：!ls [/dim] [bold white]",
        border_style="dim white",
        title_align="center",
        expand=False
    )
    console.print(combined_panel)

    # 初始化处理器
    input_processor = InputProcessor(input_manager)
    stream_output = StreamOutput(agent)

    while True:
        try:
            # 设置自动补全
            setup_completion()
            # 输入处理
            user_input = await input_processor.get_user_input(session_id, plan_mode)

            if user_input.lower() in ['quit', 'exit', '退出', 'q']:
                console.print("👋 再见！", style="bold cyan")
                return

            if user_input.lower() in ['plan']:
                plan_mode = True
                console.print("进入计划模式")
                continue

            # 空输入，继续循环
            if user_input == "":
                continue

            # 创建用户消息
            user_message = HumanMessage(content=user_input)
            # 更新对话状态
            current_state = {
                "messages": conversation_state["messages"] + [user_message],
                "llm_calls": conversation_state["llm_calls"]
            }
            # 流式输出
            await stream_output.stream_response(model_name, current_state, conversation_state)

        except KeyboardInterrupt:
            console.print("\n\n👋 程序被用户中断", style="yellow")
            break

        except Exception as e:
            traceback.print_exc()
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
    try:
        # 初始化选择的模型（仅构建客户端，不做网络验证）
        with console.status("[bold cyan]正在初始化模型...", spinner="dots"):
            # 延迟导入以避免启动时加载模型相关重依赖
            from model_initializer import initialize_llm
            global llm, llm_with_tools
            llm = initialize_llm(model_name)
            # 初始化带工具的 LLM
            llm_with_tools = llm.bind_tools(tools)
        # 启动聊天循环
        asyncio.run(start_chat_with_session(session_id, model_name))

    except KeyboardInterrupt:
        console.print("\n\n👋 程序被用户中断", style="yellow")
    except Exception as e:
        console.print(f"\n❌ 启动失败: {str(e)}", style="red")
