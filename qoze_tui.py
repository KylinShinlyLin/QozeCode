#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import time
import os
import sys
import subprocess
import traceback
from datetime import datetime

from textual.app import App, ComposeResult, on
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Input, RichLog, Static, Label, Markdown as MarkdownWidget
from textual.binding import Binding
from rich.text import Text
from rich.rule import Rule
from rich.panel import Panel
from rich.console import Group
from rich.align import Align
from rich.markdown import Markdown

# Add current directory to path
sys.path.append(os.getcwd())

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

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

    def __init__(self, main_log: RichLog, stream_display: MarkdownWidget, tool_status: Static):
        self.main_log = main_log
        self.stream_display = stream_display
        self.tool_status = tool_status
        self.tool_start_time = None
        self.tool_timer = None
        # Track active tools: {tool_call_id: tool_name}
        self.active_tools = {}
        # Track display name for spinner (latest active tool)
        self.current_display_tool = None

    def _update_tool_spinner(self):
        if not self.tool_start_time or not self.current_display_tool:
            return

        elapsed = time.time() - self.tool_start_time
        frame = SPINNER_FRAMES[int(elapsed * 10) % len(SPINNER_FRAMES)]

        # 格式化时间
        m, s = divmod(int(elapsed), 60)
        time_str = f"{m:02d}:{s:02d}"

        content = f"{frame} [bold blue]{self.current_display_tool}[/] [rgb(65,170,65)]{time_str}[/]"
        self.tool_status.update(Text.from_markup(content))

    def flush_to_log(self, text: str, reasoning: str):
        """将当前流式缓冲区的内容固化到日志中，并清空流式显示"""
        if reasoning:
            self.main_log.write(Text(reasoning, style="italic dim #565f89"))
        if text:
            self.main_log.write(Text(text))

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

                    # 尝试通过 tool_call_id 获取名称
                    tool_name = self.active_tools.pop(message_chunk.tool_call_id, None)

                    # 如果没找到，尝试从 message_chunk 属性获取
                    if not tool_name:
                        tool_name = message_chunk.name if hasattr(message_chunk, "name") else None

                    # 如果还是没找到，使用 fallback
                    if not tool_name:
                        tool_name = self.current_display_tool if self.current_display_tool else "Tool"

                    # 只有当活跃工具列表为空时，才停止 Spinner
                    # (这对于并行调用可能不完美，但对于串行足够)
                    if not self.active_tools:
                        if self.tool_timer:
                            self.tool_timer.stop()
                            self.tool_timer = None

                        self.tool_status.update("")
                        self.tool_status.styles.display = "none"
                        self.current_display_tool = None

                    elapsed = time.time() - (self.tool_start_time or time.time())
                    # 如果还有活跃工具，不重置 start_time，继续计时
                    if not self.active_tools:
                        self.tool_start_time = None

                    content_str = str(message_chunk.content)

                    # Simple error detection
                    is_error = "error" in content_str.lower() and len(content_str) < 500

                    status_icon = "✗" if is_error else "✓"
                    status_color = "red" if is_error else "green"
                    status_text = "Failed" if is_error else "Success"

                    # Log simple status line
                    final_msg = f"{status_icon} [bold blue]{tool_name}[/] [{status_color}]{status_text}[/] [rgb(65,170,65)]in {elapsed:.2f}s[/]"
                    self.main_log.write(Text.from_markup(final_msg))

                    continue

                # 2. 处理 Tool Calls (AI 决定调用工具)
                if isinstance(message_chunk, AIMessage) and message_chunk.tool_calls:
                    # 固化之前的 AI 文本
                    if current_response_text or current_reasoning_content:
                        self.flush_to_log(current_response_text, current_reasoning_content)
                        current_response_text = ""
                        current_reasoning_content = ""

                    for tool_call in message_chunk.tool_calls:
                        t_name = tool_call.get("name", "Unknown Tool")
                        t_id = tool_call.get("id", "unknown_id")

                        self.active_tools[t_id] = t_name
                        self.current_display_tool = t_name

                        # Start Spinner if not running
                        if not self.tool_timer:
                            self.tool_start_time = time.time()
                            self.tool_status.styles.display = "block"
                            self.tool_timer = self.tool_status.set_interval(0.1, self._update_tool_spinner)

                    # 继续显示后续可能的内容
                    self.stream_display.styles.display = "block"

                # 3. 处理 Reasoning
                reasoning = ""
                if hasattr(message_chunk, "additional_kwargs") and message_chunk.additional_kwargs:
                    reasoning = message_chunk.additional_kwargs.get("reasoning_content", "")

                # Gemini thinking
                if isinstance(message_chunk.content, list):
                    for content_item in message_chunk.content:
                        if isinstance(content_item, dict) and content_item.get("type") == "thinking":
                            reasoning += content_item.get("thinking", "")

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
                        if isinstance(item, dict) and item.get("type") == "text":
                            chunk_text += item.get("text", "")

                if chunk_text:
                    current_response_text += chunk_text
                    total_response_text += chunk_text

                # 5. 更新流式显示 (True Streaming with Markdown Widget)
                if current_reasoning_content or current_response_text:
                    md_content = ""

                    if current_reasoning_content:
                        # 格式化推理内容为引用块，模拟 dim 效果
                        lines = current_reasoning_content.split("\n")
                        quoted_lines = [f"> {line}" for line in lines]
                        md_content += "\n".join(quoted_lines) + "\n\n"

                    if current_response_text:
                        md_content += current_response_text

                    self.stream_display.update(md_content)
                    self.stream_display.scroll_end(animate=False)

            # 循环结束后，固化最后的内容
            self.flush_to_log(current_response_text, current_reasoning_content)

            # 保存到历史记录
            if total_response_text or total_reasoning_content:
                additional_kwargs = {"reasoning_content": total_reasoning_content}
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
    TopBar { dock: top; height: 1; background: #13131c; color: #c0caf5; }

    #main-container { height: 1fr; width: 100%; layout: horizontal; }

    /* 聊天区域布局调整 */
    #chat-area { width: 77%; height: 100%; }
    #main-output { width: 100%; height: 1fr; background: #13131c; border: none; padding: 1 2; }
    /* 工具状态栏 */
    #tool-status {
        width: 100%;
        height: auto;
        min-height: 1;
        background: #13131c;
        padding: 0 2;
        display: none;
    }


    /* 流式输出区域 - 使用 Markdown Widget */
    #stream-output {
        width: 100%;
        height: auto;
        max-height: 60%;
        background: #13131c;
        padding: 0 2;
        border-top: solid #414868;
        display: none;
        overflow-y: auto; /* 确保可滚动 */
    }

    /* 自定义 Markdown 样式以匹配主题 */
    #stream-output > BlockQuote {
        border-left: solid #565f89;
        color: #787c99;
        background: #13131c;
        text-style: italic;
        margin: 0 0 1 0;
        padding: 0 1;
    }

    #sidebar { width: 23%; height: 100%; background: #16161e; padding: 1 2; color: #787c99; border-left: solid #2f334d; }
    #bottom-container { height: auto; dock: bottom; background: #13131c; }
    #input-line { height: 4; width: 100%; align-vertical: middle; padding: 0 1; border-top: solid #414868; background: #13131c; }
    .prompt-symbol { color: #bb9af7; text-style: bold; width: 2; content-align: center middle; }
    Input { width: 1fr; background: #13131c; border: none; color: #c0caf5; padding: 0; }
    Input:focus { border: none; }
    StatusBar { height: 1; width: 100%; background: #13131c; dock: bottom; }
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
                yield Static(id="tool-status")
                # 使用 Textual Markdown Widget 替代 Static
                yield MarkdownWidget(id="stream-output")
            yield Sidebar(id="sidebar")
        with Vertical(id="bottom-container"):
            with Horizontal(id="input-line"):
                yield Label("❯", classes="prompt-symbol")
                yield Input(placeholder="Initializing Agent...", id="input-box", disabled=True)
            yield StatusBar(model_name=self.model_name)

    def on_mount(self):
        self.main_log = self.query_one("#main-output", RichLog)
        self.tool_status = self.query_one("#tool-status", Static)
        self.stream_output = self.query_one("#stream-output", MarkdownWidget)
        self.input_box = self.query_one("#input-box", Input)
        self.status_bar = self.query_one(StatusBar)

        # 初始化流式输出适配器，传入 main_log 和 stream_output
        self.tui_stream = TUIStreamOutput(self.main_log, self.stream_output, self.tool_status)

        # 打印欢迎信息
        self.print_welcome()

        # 异步初始化 Agent
        self.run_worker(self.init_agent_worker(), exclusive=True)

    def print_welcome(self):

        qoze_code_art = """
        ╭────────────────────────────────────────────────────────────────────────────╮
        │  ██████╗  ██████╗ ███████╗███████╗     ██████╗ ██████╗ ██████╗ ███████╗    │
        │ ██╔═══██╗██╔═══██╗╚══███╔╝██╔════╝    ██╔════╝██╔═══██╗██╔══██╗██╔════╝    │
        │ ██║   ██║██║   ██║  ███╔╝ █████╗      ██║     ██║   ██║██║  ██║█████╗      │
        │ ██║▄▄ ██║██║   ██║ ███╔╝  ██╔══╝      ██║     ██║   ██║██║  ██║██╔══╝      │
        │ ╚██████╔╝╚██████╔╝███████╗███████╗    ╚██████╗╚██████╔╝██████╔╝███████╗    │
        │  ╚══▀▀═╝  ╚═════╝ ╚══════╝╚══════╝     ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝    │
        ╰────────────────────────────────────────────────────────────────────────────╯
        """

        # 创建信息网格

        from rich.align import Align

        # 使用提示面板
        tips_content = Group(
            Text("✦ Welcome to QozeCode 0.2.3", style="bold dim cyan"),
            Text(""),
            Text("模型: ", style="bold white").append(Text(f"{self.model_name or 'Unknown'}", style="bold cyan")),
            Text("当前目录: ", style="bold white").append(Text(f"{os.getcwd() or 'Unknown'}", style="bold cyan")),
            Text("使用提示: ", style="bold white"),
            Text("  • 输入 'q'、'quit' 或 'exit' 退出", style="dim bold white"),
            Text("  • ! 开头的内容会直接按命令执行 例如：!ls", style="dim bold white"),
            Text("  • 输入 'clear' 清理整改会话上下文", style="dim bold white"),
            Text(""),
            Text("✓ Agent Ready ",
                 style="italic bold green", justify="center")
        )

        # 输出所有内容
        self.main_log.write(Align.center(Text(qoze_code_art, style="bold #7aa2f7")))
        self.main_log.write(Text(""))
        self.main_log.write(Align.center(Panel(
            tips_content,
            title="[bold #bb9af7]Tips[/]",
            border_style="bold #414868",
            padding=(0, 1)
        )))

    async def init_agent_worker(self):
        """后台初始化 Agent"""
        try:
            llm = model_initializer.initialize_llm(self.model_name)

            # 设置 qoze_code_agent 的全局变量，注入 LLM
            qoze_code_agent.llm = llm
            qoze_code_agent.llm_with_tools = llm.bind_tools(qoze_code_agent.tools)

            self.agent_ready = True
            self.input_box.disabled = False
            self.input_box.placeholder = "Ask Qoze anything..."
            self.input_box.focus()

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
    # 0. 设置 TUI 模式环境变量 (关键!)
    os.environ["QOZE_TUI_MODE"] = "true"

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
