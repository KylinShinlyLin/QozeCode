import asyncio
import os
import sys
import subprocess
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

# Add current directory to path
sys.path.append(os.getcwd())

# Import agent components
try:
    from qoze_code_agent import agent, conversation_state, create_message_with_images
    from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
except ImportError as e:
    # Fallback for development/testing without full agent setup
    print(f"Warning: Could not import agent components: {e}")
    agent = None
    conversation_state = {"messages": [], "llm_calls": 0}


    def create_message_with_images(text):
        return HumanMessage(content=text)


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
    """自定义顶部栏，替代默认 Header"""

    def on_mount(self):
        self.update_clock()
        self.set_interval(1, self.update_clock)

    def update_clock(self):
        time_str = datetime.now().strftime("%H:%M:%S")
        # 左侧标题，右侧时间
        left = Text(" Qoze Code ", style="bold white on #d75f00")
        left.append(" v0.2.3 ", style="bold white on #005faf")

        right = Text(f" {time_str} ", style="bold white on #333333")

        # 计算中间空格
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

        # Project Info
        text.append("\nPROJECT INFO\n", style="bold #7aa2f7 underline")
        text.append(f"Repo: ", style="dim white")
        text.append(f"{repo_url.split('/')[-1].replace('.git', '')}\n", style="bold cyan")

        # CWD (Shortened)
        path_parts = cwd.split('/')
        short_cwd = '/'.join(path_parts[-2:]) if len(path_parts) > 1 else cwd
        text.append("Path: ", style="dim white")
        text.append(f".../{short_cwd}\n\n", style="cyan")

        # Session
        text.append("SESSION\n", style="bold #bb9af7 underline")
        text.append("Status: ", style="dim white")
        text.append("Active\n", style="green")
        text.append("Mode:   ", style="dim white")
        text.append("Interactive\n\n", style="yellow")

        # Modified Files
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
    def __init__(self, model_name="deepseek-r1"):
        super().__init__()
        self.model_name = model_name
        self.context_tokens = 0
        self.cost = 0.0

    def update_stats(self, tokens=0, cost=0.0):
        self.context_tokens = tokens
        self.cost = cost
        self.refresh()

    def render(self):
        left = Text(" Context: ", style="dim white on #1a1b26")
        left.append(f"{self.context_tokens / 1000:.1f} tokens", style="bold cyan on #1a1b26")
        # left.append(" | Cost: ", style="dim white on #1a1b26")
        # left.append(f"${self.cost:.4f}", style="bold green on #1a1b26")
        right = Text(f"{self.model_name} ", style="bold white on #414868")

        total_width = self.content_size.width or 100
        spacer_width = max(0, total_width - len(left) - len(right))

        return left + Text(" " * spacer_width, style="on #1a1b26") + right


class TUIStreamOutput:
    def __init__(self, main_log: RichLog):
        self.main_log = main_log
        self.buffer = ""

    def log_event(self, message, style="dim"):
        pass

    def write_main(self, text: str, style=None):
        self.buffer += text
        if '\n' in self.buffer:
            lines = self.buffer.split('\n')
            for line in lines[:-1]:
                self.main_log.write(Text(line, style=style))
            self.buffer = lines[-1]

    def flush_main(self, style=None):
        if self.buffer:
            self.main_log.write(Text(self.buffer, style=style))
            self.buffer = ""

    async def stream_response(self, model_name, current_state, conversation_state):
        current_response_text = ""
        current_reasoning_content = ""

        self.write_main(f"\n", style="")

        try:
            if not agent:
                self.write_main("Agent not initialized. Mocking response...", "red")
                return

            async for message_chunk, metadata in agent.astream(
                    current_state, stream_mode="messages", config={"recursion_limit": 150}
            ):
                if isinstance(message_chunk, ToolMessage):
                    tool_name = message_chunk.name if hasattr(message_chunk, 'name') else "Tool"
                    self.main_log.write(Text(f"✓ {tool_name} completed", style="green"))
                    continue

                if isinstance(message_chunk, AIMessage) and message_chunk.tool_calls:
                    for tool_call in message_chunk.tool_calls:
                        self.main_log.write(Text(f"⚙ Executing {tool_call['name']}...", style="bold yellow"))

                if hasattr(message_chunk, 'additional_kwargs') and message_chunk.additional_kwargs:
                    reasoning = message_chunk.additional_kwargs.get('reasoning_content', '')
                    if reasoning:
                        current_reasoning_content += reasoning
                        self.write_main(reasoning, style="italic dim #565f89")
                        continue

                content = message_chunk.content
                chunk_text = ""
                if isinstance(content, str):
                    chunk_text = content
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            chunk_text += item.get('text', '')

                if chunk_text:
                    self.write_main(chunk_text)
                    current_response_text += chunk_text

            self.flush_main()

            additional_kwargs = {'reasoning_content': current_reasoning_content}
            ai_response = AIMessage(
                content=current_response_text,
                additional_kwargs=additional_kwargs)
            conversation_state["messages"].extend([ai_response])
            conversation_state["llm_calls"] += 1

        except Exception as e:
            self.main_log.write(f"[red]Error: {e}[/]")


class Qoze(App):
    CSS = """
    /* Tokyo Night Theme Inspired */
    Screen {
        background: #1a1b26;
        color: #a9b1d6;
    }

    /* Top Bar */
    TopBar {
        dock: top;
        height: 1;
        background: #1a1b26;
        color: #c0caf5;
    }

    /* Main Layout */
    #main-container {
        height: 1fr;
        width: 100%;
        layout: horizontal;
    }

    #main-output {
        height: 100%;
        width: 75%;
        background: #1a1b26;
        border: none;
        padding: 1 2;
        scrollbar-size: 1 1;
        scrollbar-color: #565f89;
    }

    #sidebar {
        width: 25%;
        height: 100%;
        background: #16161e; /* Slightly darker */
        padding: 1 2;
        color: #787c99;
        border-left: solid #2f334d;
    }

    /* Bottom Area */
    #bottom-container {
        height: auto;
        dock: bottom;
        background: #1a1b26;
    }

    #input-line {
        height: 3;
        width: 100%;
        align-vertical: middle;
        padding: 0 1;
        border-top: solid #414868;
        background: #1a1b26;
    }

    .prompt-symbol {
        color: #bb9af7;
        text-style: bold;
        width: 2;
        content-align: center middle;
    }

    Input {
        width: 1fr;
        background: #1a1b26;
        border: none;
        color: #c0caf5;
        padding: 0;
    }

    Input:focus {
        border: none;
    }

    Input > .input--placeholder {
        color: #565f89;
    }

    Input > .input--cursor {
        background: #bb9af7;
        color: #1a1b26;
    }

    StatusBar {
        height: 1;
        width: 100%;
        background: #1a1b26;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
    ]

    def compose(self) -> ComposeResult:
        # 1. Top Bar
        yield TopBar()

        # 2. Main Content (Log + Sidebar)
        with Horizontal(id="main-container"):
            yield RichLog(id="main-output", markup=True, highlight=True, auto_scroll=True, wrap=True)
            yield Sidebar(id="sidebar")

        # 3. Bottom Controls
        with Vertical(id="bottom-container"):
            with Horizontal(id="input-line"):
                yield Label("❯", classes="prompt-symbol")
                yield Input(placeholder="Ask Qoze anything...", id="input-box", select_on_focus=False)
            yield StatusBar(model_name="Claude 3.7 Sonnet")

    def on_mount(self):
        self.main_log = self.query_one("#main-output", RichLog)
        self.input_box = self.query_one("#input-box", Input)
        self.status_bar = self.query_one(StatusBar)

        # Welcome Message
        welcome = Text()
        welcome.append("╭──────────────────────────────────────────────╮\n", style="bold #7aa2f7")
        welcome.append("│           Welcome to QozeCode v0.2.3         │\n", style="bold #7aa2f7")
        welcome.append("╰──────────────────────────────────────────────╯\n", style="bold #7aa2f7")

        self.main_log.write(welcome)
        self.main_log.write(Text("Current Agent: ", style="bold white").append("DeepSeek-R1", style="bold cyan"))
        self.main_log.write(Text("Environment:   ", style="bold white").append(f"{os.getcwd()}", style="cyan"))
        self.main_log.write(Text("\nTips:", style="bold white"))
        self.main_log.write(Text(" • Type 'exit' to quit", style="dim white"))
        self.main_log.write(Text(" • Start with '!' to execute commands (e.g., !ls)", style="dim white"))
        self.main_log.write(Text(" • Type 'clear' to reset view", style="dim white"))
        self.main_log.write(Rule(style="#414868"))
        self.tui_stream = TUIStreamOutput(self.main_log)
        self.current_model = "deepseek-r1:14b"
        self.input_box.focus()

    @on(Input.Submitted)
    async def handle_input(self, event: Input.Submitted):
        user_input = event.value
        if not user_input.strip():
            return

        self.input_box.value = ""

        # User message style
        self.main_log.write(Text(f"\n❯ {user_input}", style="bold #bb9af7"))

        if user_input.lower() in ['quit', 'exit', 'q']:
            self.exit()
            return

        if user_input.lower() == 'clear':
            self.main_log.clear()
            return

        current_tokens = self.status_bar.context_tokens + len(user_input) * 1.5
        current_cost = self.status_bar.cost + 0.0001
        self.status_bar.update_stats(tokens=current_tokens, cost=current_cost)

        human_msg = create_message_with_images(user_input)
        conversation_state["messages"].append(human_msg)

        # Run agent
        await self.tui_stream.stream_response(
            self.current_model,
            conversation_state,
            conversation_state
        )


if __name__ == "__main__":
    app = Qoze()
    app.run()
