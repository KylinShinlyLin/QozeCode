#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import subprocess
import traceback
from datetime import datetime

from textual.app import App, ComposeResult, on
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Input, RichLog, Static, Label
from textual.binding import Binding
from rich.text import Text
from rich.rule import Rule
from rich.panel import Panel
from rich.console import Group
from rich.align import Align
from rich.markdown import Markdown

# Add current directory to path
sys.path.append(os.getcwd())

# Import agent components
try:
    import launcher
    import model_initializer
    import qoze_code_agent
    from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
except ImportError as e:
    print(f"Critical Error: Could not import agent components: {e}")
    sys.exit(1)


# 获取 Git 信息
def get_git_info():
    try:
        repo_url = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], text=True).strip()
        return repo_url
    except:
        return "local/repository"


def get_modified_files():
    try:
        status = subprocess.check_output(['git', 'status', '-s'], text=True).strip()
        if not status:
            return []
        files = []
        for line in status.split('\n'):
            parts = line.split()
            if len(parts) >= 2:
                files.append((parts[0], parts[-1]))
        return files
    except:
        return []


class TopBar(Static):
    """自定义顶部栏"""

    def on_mount(self):
        self.update_clock()
        self.set_interval(1, self.update_clock)

    def update_clock(self):
        time_str = datetime.now().strftime("%H:%M:%S")
        left = Text(" Qoze Code ", style="bold white on #d75f00")
        left.append(" v0.2.3 ", style="bold white on #005faf")
        right = Text(f" {time_str} ", style="bold white on #333333")
        total_width = self.content_size.width or 80
        spacer_width = max(0, total_width - len(left) - len(right))
        content = left + Text(" " * spacer_width, style="on #1a1b26") + right
        self.update(content)


class Sidebar(Static):
    def on_mount(self):
        self.update_info()
        self.set_interval(5, self.update_info)

    def update_info(self):
        cwd = os.getcwd()
        repo_url = get_git_info()
        modified = get_modified_files()

        text = Text()
        text.append("\nPROJECT INFO\n", style="bold #7aa2f7 underline")
        text.append(f"Repo: ", style="dim white")
        text.append(f"{repo_url.split('/')[-1].replace('.git', '')}\n", style="bold cyan")

        path_parts = cwd.split('/')
        short_cwd = '/'.join(path_parts[-2:]) if len(path_parts) > 1 else cwd
        text.append("Path: ", style="dim white")
        text.append(f".../{short_cwd}\n\n", style="cyan")

        text.append("SESSION\n", style="bold #bb9af7 underline")
        text.append("Status: ", style="dim white")
        text.append("Active\n", style="green")

        # Git Status
        text.append("GIT STATUS\n", style="bold #f7768e underline")
        if modified:
            for status, filename in modified:
                if 'M' in status:
                    icon = "✹"
                    style = "yellow"
                elif 'A' in status or '?' in status:
                    icon = "+"
                    style = "green"
                elif 'D' in status:
                    icon = "x"
                    style = "red"
                else:
                    icon = "•"
                    style = "white"
                text.append(f"{icon} {filename[:20]}\n", style=style)
        else:
            text.append("Clean working tree\n", style="dim green")

        self.update(text)


class StatusBar(Static):
    def __init__(self, model_name="Unknown"):
        super().__init__()
        self.model_name = model_name
        self.context_tokens = 0
        self.state_desc = "Idle"

    def update_state(self, state):
        self.state_desc = state
        self.refresh()

    def render(self):
        left = Text(" Status: ", style="dim white on #1a1b26")

        status_style = "bold green" if self.state_desc == "Idle" else "bold yellow"
        left.append(f"{self.state_desc}", style=f"{status_style} on #1a1b26")

        right = Text(f"{self.model_name} ", style="bold white on #414868")

        total_width = self.content_size.width or 100
        spacer_width = max(0, total_width - len(left) - len(right))

        return left + Text(" " * spacer_width, style="on #1a1b26") + right


class TUIStreamOutput:
    """流式输出适配器 - 适配 Textual (真流式)"""

    def __init__(self, main_log: RichLog, stream_display: Static):
        self.main_log = main_log
        self.stream_display = stream_display

    def flush_to_log(self, text: str, reasoning: str):
        """将当前流式缓冲区的内容固化到日志中，并清空流式显示"""
        if reasoning:
            self.main_log.write(Text(reasoning, style="italic dim #565f89"))
        if text:
            self.main_log.write(Markdown(text))

        self.stream_display.update("")
        self.stream_display.styles.display = "none"

    async def stream_response(self, model_name, current_state, conversation_state):
        """核心流式处理逻辑"""
        # 用于显示的当前片段 buffer
        current_response_text = ""
        current_reasoning_content = ""

        # 用于 State 记录的完整累积
        total_response_text = ""
        total_reasoning_content = ""

        # # 标记 AI 回复开始
        # self.main_log.write(Rule(style="dim cyan"))

        # 激活流式显示区域
        self.stream_display.styles.display = "block"
        self.stream_display.update("")

        try:
            async for message_chunk, metadata in qoze_code_agent.agent.astream(
                    current_state, stream_mode="messages", config={"recursion_limit": 150}
            ):
                # 1. 处理 ToolMessage (工具执行结果)
                if isinstance(message_chunk, ToolMessage):
                    # 遇到工具输出，先固化之前的 AI 文本
                    if current_response_text or current_reasoning_content:
                        self.flush_to_log(current_response_text, current_reasoning_content)
                        current_response_text = ""
                        current_reasoning_content = ""

                    tool_name = message_chunk.name if hasattr(message_chunk, 'name') else "Tool"
                    content_preview = str(message_chunk.content)[:200] + "..." if len(
                        str(message_chunk.content)) > 200 else str(message_chunk.content)

                    panel = Panel(
                        Text(content_preview, style="dim white"),
                        title=f"🔧 Tool Output: {tool_name}",
                        border_style="dim yellow",
                        expand=False
                    )
                    self.main_log.write(panel)
                    continue

                # 2. 处理 Tool Calls (AI 决定调用工具)
                if isinstance(message_chunk, AIMessage) and message_chunk.tool_calls:
                    # 固化之前的 AI 文本
                    if current_response_text or current_reasoning_content:
                        self.flush_to_log(current_response_text, current_reasoning_content)
                        current_response_text = ""
                        current_reasoning_content = ""

                    for tool_call in message_chunk.tool_calls:
                        self.main_log.write(Text(f"⚙  Invoking tool: {tool_call['name']}...", style="bold yellow"))

                    # 继续显示后续可能的内容
                    self.stream_display.styles.display = "block"

                # 3. 处理 Reasoning
                reasoning = ""
                if hasattr(message_chunk, 'additional_kwargs') and message_chunk.additional_kwargs:
                    reasoning = message_chunk.additional_kwargs.get('reasoning_content', '')

                # Gemini thinking
                if isinstance(message_chunk.content, list):
                    for content_item in message_chunk.content:
                        if isinstance(content_item, dict) and content_item.get('type') == 'thinking':
                            reasoning += content_item.get('thinking', '')

                if reasoning:
                    current_reasoning_content += reasoning
                    total_reasoning_content += reasoning

                # 4. 处理 Content
                content = message_chunk.content
                chunk_text = ""
                if isinstance(content, str):
                    chunk_text = content
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            chunk_text += item.get('text', '')

                if chunk_text:
                    current_response_text += chunk_text
                    total_response_text += chunk_text

                # 5. 更新流式显示 (True Streaming)
                if current_reasoning_content or current_response_text:
                    renderables = []

                    if current_reasoning_content:
                        renderables.append(
                            Text(current_reasoning_content, style="italic dim #565f89")
                        )

                    if current_response_text:
                        if current_reasoning_content:
                            renderables.append(Text(" "))  # Spacer

                        # 尝试渲染 Markdown，如果失败退回文本，避免未闭合标签报错
                        try:
                            renderables.append(Markdown(current_response_text))
                        except:
                            renderables.append(Text(current_response_text))

                    self.stream_display.update(Group(*renderables))
                    self.stream_display.scroll_end(animate=False)

            # 循环结束后，固化最后的内容
            self.flush_to_log(current_response_text, current_reasoning_content)

            self.main_log.write(Text("✓ Completed", style="bold green"))
            self.main_log.write(Text(" ", style="dim"))  # Spacer

            # 保存到历史记录
            # 注意：这里只保存累积的文本和推理。如果是多轮工具调用，中间过程已被 LangChain 内部状态管理了吗？
            # 这里的 conversation_state 是手动管理的列表。为了简单起见，我们添加最终的 AI Message。
            if total_response_text or total_reasoning_content:
                additional_kwargs = {'reasoning_content': total_reasoning_content}
                ai_response = AIMessage(
                    content=total_response_text,
                    additional_kwargs=additional_kwargs)
                conversation_state["messages"].append(ai_response)
                conversation_state["llm_calls"] += 1

        except Exception as e:
            traceback.print_exc()
            self.main_log.write(f"[red]Stream Error: {e}[/]")
            self.stream_display.update("")
            self.stream_display.styles.display = "none"


class Qoze(App):
    CSS = """
    Screen { background: #1a1b26; color: #a9b1d6; }
    TopBar { dock: top; height: 1; background: #1a1b26; color: #c0caf5; }
    
    #main-container { height: 1fr; width: 100%; layout: horizontal; }
    
    /* 聊天区域布局调整 */
    #chat-area { width: 75%; height: 100%; }
    #main-output { width: 100%; height: 1fr; background: #1a1b26; border: none; padding: 1 2; }
    
    /* 流式输出区域 - 初始隐藏 */
    #stream-output { 
        width: 100%; 
        height: auto; 
        max-height: 60%; 
        background: #1a1b26; 
        padding: 0 2; 
        border-top: solid #414868;
        display: none;
        overflow-y: auto;
    }
    
    #sidebar { width: 25%; height: 100%; background: #16161e; padding: 1 2; color: #787c99; border-left: solid #2f334d; }
    #bottom-container { height: auto; dock: bottom; background: #1a1b26; }
    #input-line { height: 4; width: 100%; align-vertical: middle; padding: 0 1; border-top: solid #414868; background: #1a1b26; }
    .prompt-symbol { color: #bb9af7; text-style: bold; width: 2; content-align: center middle; }
    Input { width: 1fr; background: #1a1b26; border: none; color: #c0caf5; padding: 0; }
    Input:focus { border: none; }
    StatusBar { height: 1; width: 100%; background: #1a1b26; dock: bottom; }
    LoadingIndicator { height: 100%; content-align: center middle; color: cyan; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
    ]

    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name
        self.agent_ready = False

    def compose(self) -> ComposeResult:
        yield TopBar()
        with Horizontal(id="main-container"):
            # 使用 Vertical 容器包含历史记录和流式输出
            with Vertical(id="chat-area"):
                yield RichLog(id="main-output", markup=True, highlight=True, auto_scroll=True, wrap=True)
                yield Static(id="stream-output")
            yield Sidebar(id="sidebar")
        with Vertical(id="bottom-container"):
            with Horizontal(id="input-line"):
                yield Label("❯", classes="prompt-symbol")
                yield Input(placeholder="Initializing Agent...", id="input-box", disabled=True)
            yield StatusBar(model_name=self.model_name)

    def on_mount(self):
        self.main_log = self.query_one("#main-output", RichLog)
        self.stream_output = self.query_one("#stream-output", Static)
        self.input_box = self.query_one("#input-box", Input)
        self.status_bar = self.query_one(StatusBar)

        # 初始化流式输出适配器，传入 main_log 和 stream_output
        self.tui_stream = TUIStreamOutput(self.main_log, self.stream_output)

        # 打印欢迎信息
        self.print_welcome()

        # 异步初始化 Agent
        self.run_worker(self.init_agent_worker(), exclusive=True)

    def print_welcome(self):
        ascii_art = """
   ██████╗  ██████╗ ███████╗███████╗
  ██╔═══██╗██╔═══██╗╚══███╔╝██╔════╝
  ██║   ██║██║   ██║  ███╔╝ █████╗
  ██║▄▄ ██║██║   ██║ ███╔╝  ██╔══╝
  ╚██████╔╝╚██████╔╝███████╗███████╗
   ╚══▀▀═╝  ╚═════╝ ╚══════╝╚══════╝
        """
        self.main_log.write(Text(ascii_art, style="bold cyan"))
        self.main_log.write(Text(f"Model: {self.model_name}", style="bold white"))
        self.main_log.write(Rule(style="#414868"))

    async def init_agent_worker(self):
        """后台初始化 Agent"""
        self.main_log.write(Text("⚡ Initializing LLM and Tools...", style="yellow"))
        try:
            llm = model_initializer.initialize_llm(self.model_name)

            # 设置 qoze_code_agent 的全局变量，注入 LLM
            qoze_code_agent.llm = llm
            qoze_code_agent.llm_with_tools = llm.bind_tools(qoze_code_agent.tools)

            self.agent_ready = True
            self.input_box.disabled = False
            self.input_box.placeholder = "Ask Qoze anything..."
            self.input_box.focus()
            self.main_log.write(Text("✓ Agent Ready!", style="bold green"))

        except Exception as e:
            self.main_log.write(f"[red]Initialization Failed: {e}[/]")
            self.main_log.write(f"[red]{traceback.format_exc()}[/]")

    @on(Input.Submitted)
    async def handle_input(self, event: Input.Submitted):
        if not self.agent_ready:
            return

        user_input = event.value
        if not user_input.strip():
            return

        self.input_box.value = ""
        self.status_bar.update_state("Thinking...")

        # Display User Input
        self.main_log.write(Text(f"\n❯ {user_input}", style="bold #bb9af7"))

        if user_input.lower() in ['quit', 'exit', 'q']:
            self.exit()
            return

        if user_input.lower() == 'clear':
            self.main_log.clear()
            self.print_welcome()
            self.status_bar.update_state("Idle")
            return

        # Prepare Message
        image_folder = ".qoze/image"
        human_msg = qoze_code_agent.create_message_with_images(user_input, image_folder)

        # Update State
        current_state = {
            "messages": qoze_code_agent.conversation_state["messages"] + [human_msg],
            "llm_calls": qoze_code_agent.conversation_state["llm_calls"]
        }
        qoze_code_agent.conversation_state["messages"].append(human_msg)

        # Stream Response
        await self.tui_stream.stream_response(
            self.model_name,
            current_state,
            qoze_code_agent.conversation_state
        )

        self.status_bar.update_state("Idle")


def main():
    # 1. 确保配置存在
    launcher.ensure_config()

    # 2. 获取模型选择
    try:
        model = launcher.get_model_choice()
    except Exception as e:
        print(f"Model selection failed: {e}")
        model = "gpt-5.2"

    if model is None:
        return

    # 3. 启动 TUI App
    app = Qoze(model_name=model)
    app.run()


if __name__ == "__main__":
    main()
