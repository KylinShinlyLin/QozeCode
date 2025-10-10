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
# 添加 rich 库用于美化界面
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from typing_extensions import TypedDict, Annotated

from config_manager import ensure_model_credentials
from shared_console import console
# 顶部导入区域
from tools.execute_command_tool import execute_command
from tools.file_operations_tools import read_file, grep_search
from tools.math_tools import multiply, add, divide
# 导入工具函数
from tools.tavily_search_tool import tavily_search
# from tools.common_tools import ask, confirm, request_auth
from utils.command_exec import run_command

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
#     console.print("✅ 浏览器工具已加载", style="green")
# except ImportError as e:
#     BROWSER_TOOLS_AVAILABLE = False
#     console.print(f"⚠️ 浏览器工具不可用: {str(e)}", style="yellow")
#     console.print("💡 要启用浏览器功能，请安装: pip install playwright langchain-community", style="yellow")
#     console.print("💡 然后运行: playwright install", style="yellow")

# 本地会话存储
local_sessions = {}


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

# Augment the LLM with tools
# base_tools = [add, multiply, divide, execute_command, tavily_search, read_file, grep_search, ask, confirm, request_auth]
base_tools = [add, multiply, divide, execute_command, tavily_search, read_file, grep_search]
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

    messages = state["messages"]
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")

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

    except Exception as e:
        traceback.print_exc()
        # 如果获取系统信息失败，使用基本信息
        system_info = platform.system()
        system_version = "unknown"
        current_dir = os.getcwd()
        username = os.getenv('USER', 'unknown')
        hostname = socket.gethostname()

        shell = home_dir = "unknown"
        machine_type = processor = "unknown"

    # 确保 SystemMessage 在开头
    system_msg = SystemMessage(
        content=f'''
你一名专业的终端AI agent 助手，你当前正运行在当前电脑的终端中
- 你需要根据我的诉求，利用当前的tools在终端中帮我完成复杂的任务 

## 系统环境信息
**操作系统**: {system_info} {system_release} ({system_version})
**架构**: {machine_type}
**处理器**: {processor}
**主机名**: {hostname}
**用户**: {username}
**Shell**: {shell}
- 当前系统时间:{current_time}

## 当前环境
**工作目录**: {current_dir}
**用户主目录**: {home_dir}
**当前时间**: {current_time}

## 工作原则
- 始终考虑当前的系统环境和资源限制
- 在执行可能影响系统的操作前，先评估风险
- 优先使用适合当前操作系统的命令和工具
- 提供准确、实用的建议和解决方案
- 保持对用户数据和隐私的尊重

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
        f"[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]\n\n"
        f"[bold white]模型:[/bold white] [bold yellow]{model_name or 'Unknown'}[/bold yellow]\n"
        f"[bold white]状态:[/bold white] [bold green]✅ 启动成功![/bold green]\n"
        # f"[bold white]浏览器工具:[/bold white] [bold {browser_style}]{browser_status}[/bold {browser_style}]\n\n"
        f"[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]\n"
        f"[bold white]💡 使用提示:[/bold white]\n"
        f"[dim]  • 输入问题开始对话\n"
        f"  • 输入 [bold]'quit'[/bold] 或 [bold]'exit'[/bold] 退出\n"
        f"  • 支持多轮对话和上下文记忆\n",
        # f"  • 可以使用浏览器操作网页 (如果已启用)[/dim]",
        border_style="cyan",
        title="[bold green]启动完成[/bold green]",
        title_align="center",
        padding=(1, 2),
        expand=False
    )
    console.print(combined_panel)

    while True:
        try:
            # 获取用户输入，带有美化的提示符和占位符
            user_input = Prompt.ask(
                "[bold cyan]您[/bold cyan]",
                console=console,
                default="",
                show_default=False
            ).strip()

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
                command = user_input[1:].strip()
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

            # 显示AI思考状态并开始流式显示
            console.print()

            # 创建初始的AI面板
            response_text = ""
            ai_panel = Panel(
                Markdown("正在思考...", style="green"),
                title="[bold green]Qoze 回复[/bold green]",
                border_style="green",
                padding=(0, 2)
            )

            # 使用Live来实时更新显示
            with Live(ai_panel, console=console, refresh_per_second=4) as live:  # 降低刷新频率从10到4
                # 收集完整的响应消息
                response_messages = []
                last_update_time = 0
                update_interval = 0.25  # 最小更新间隔250ms，避免过于频繁的更新

                # 使用流式处理
                async for message_chunk, metadata in agent.astream(current_state, stream_mode="messages",
                                                                   config={"recursion_limit": 150}):  # 增加递归限制到100

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

                        # 累积响应文本
                        response_text += chunk_text

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
                            def create_scrollable_panel(text: str, title: str = "[bold green]Qoze 回复[/bold green]",
                                                        show_scroll_info: bool = True) -> Panel:
                                """创建可滚动的Panel，自动显示最新内容"""
                                try:
                                    if not text.strip():
                                        return Panel(
                                            Markdown("正在思考...", style="green"),
                                            title=title,
                                            border_style="green",
                                            padding=(0, 2)
                                        )

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

                                    return Panel(
                                        Markdown(display_text),
                                        title=title,
                                        border_style="green",
                                        padding=(0, 2)
                                    )
                                except Exception as e:
                                    # 如果创建Panel失败，返回简单的错误Panel
                                    return Panel(
                                        f"显示错误: {str(e)}",
                                        title="[bold red]错误[/bold red]",
                                        border_style="red",
                                        padding=(0, 2)
                                    )

                            # 在流式处理中使用新的Panel创建函数
                            # 实时更新显示
                            if response_text:
                                try:
                                    updated_panel = create_scrollable_panel(response_text)
                                    live.update(updated_panel)
                                    last_update_time = current_time
                                except Exception as e:
                                    # 如果更新失败，记录错误但继续处理
                                    console.print(f"更新显示时出错: {str(e)}", style="red")

                # 显示AI回复
                if response_text:
                    try:
                        # 创建完整回复的Panel，不显示滚动指示器
                        complete_panel = Panel(
                            Markdown(response_text),
                            title="",
                            subtitle="[bold blue]Qoze 完整回复[/bold blue]",
                            border_style="blue",
                            padding=(0, 2)
                        )
                        live.update(complete_panel)

                        # 短暂延迟确保最终显示稳定
                        await asyncio.sleep(0.1)

                    except Exception as e:
                        console.print(f"显示完整回复时出错: {str(e)}", style="red")

                    from langchain_core.messages import AIMessage
                    # 创建AI消息对象，只包含文本内容
                    ai_response = AIMessage(content=response_text)
                    # 更新对话状态，使用简化的响应消息
                    conversation_state["messages"].extend([user_message, ai_response])
                else:
                    # 如果没有文本内容，仍然保存原始响应
                    conversation_state["messages"].extend([user_message] + response_messages)

                conversation_state["llm_calls"] += 1

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

    # 先进行凭证交互式输入与保存，避免在加载状态下阻塞输入
    try:
        ensure_model_credentials(model_name)
    except KeyboardInterrupt:
        return
    except Exception as e:
        console.print(f"\n❌ {model_name} 凭证验证失败: {str(e)}", style="red")

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
        console.print(f"\n❌ 启动失败: {str(e)}", style="red")
