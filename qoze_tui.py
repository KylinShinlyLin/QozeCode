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
from rich.panel import Panel
from rich.console import Group

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
                # status is first part, filename is last part
                files.append((parts[0], parts[-1]))
        return files
    except:
        return []


class Sidebar(Static):
    def on_mount(self):
        self.update_info()
        self.set_interval(5, self.update_info)

    def update_info(self):
        cwd = os.getcwd()
        repo_url = get_git_info()
        modified = get_modified_files()

        # Build Sidebar Content
        text = Text()

        # Header
        text.append("○ QozeCode v0.2.3\n", style="bold dim white")
        text.append(f"{repo_url}\n\n", style="dim white")

        # CWD
        text.append("cwd: ", style="dim")
        text.append(f"{cwd}\n\n", style="dim white")

        # Session
        text.append("Session: ", style="bold #d75f00")  # Orange
        text.append("Interactive Development\n\n", style="dim white")

        # Configuration
        text.append("LSP Configuration\n\n", style="bold #d75f00")

        # Modified Files
        text.append("Modified Files:\n", style="bold #d75f00")
        if modified:
            for status, filename in modified:
                # Color logic based on git status
                if 'M' in status:
                    color = "#d75f00"  # Orange for modified
                elif 'A' in status or '?' in status:
                    color = "green"
                elif 'D' in status:
                    color = "red"
                else:
                    color = "yellow"

                text.append(f"{filename} ", style="white")
                text.append(f"{status}\n", style=f"bold {color}")
        else:
            text.append("No changes\n", style="dim")

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
        # Left side
        left = Text(" ctrl+? help ", style="bold black on white")
        left.append(f" Context: {self.context_tokens / 1000:.1f}K, Cost: ${self.cost:.2f}",
                    style="dim white on #1e1e1e")

        # Right side
        right = Text(" No diagnostics ", style="dim white on #1e1e1e")
        right.append(f" {self.model_name} ", style="bold white on #005faf")  # Blue background

        # Calculate spacing
        total_width = self.content_size.width or 100
        left_len = len(left)
        right_len = len(right)

        spacer_width = max(0, total_width - left_len - right_len)

        final_text = left + Text(" " * spacer_width, style="on #1e1e1e") + right
        return final_text


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
                        self.main_log.write(Text(f"⚙ Executing {tool_call['name']}...", style="yellow"))

                # DeepSeek Reasoning
                if hasattr(message_chunk, 'additional_kwargs') and message_chunk.additional_kwargs:
                    reasoning = message_chunk.additional_kwargs.get('reasoning_content', '')
                    if reasoning:
                        current_reasoning_content += reasoning
                        # Display reasoning in italic dim
                        self.write_main(reasoning, style="italic dim bright_black")
                        continue

                # Content
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

            # Update State
            additional_kwargs = {'reasoning_content': current_reasoning_content}
            ai_response = AIMessage(
                content=current_response_text,
                additional_kwargs=additional_kwargs)
            conversation_state["messages"].extend([ai_response])
            conversation_state["llm_calls"] += 1

        except Exception as e:
            self.main_log.write(f"[red]Error: {e}[/]")


class QozeTui(App):
    CSS = """
    Screen {
        background: #111111;
        color: #e0e0e0;
    }

    #main-container {
        height: 1fr;
        width: 100%;
    }

    #main-output {
        height: 100%;
        width: 70%;
        background: #111111;
        border: none;
        padding: 1 2;
        scrollbar-gutter: stable;
    }

    #sidebar {
        width: 30%;
        height: 100%;
        background: #111111;
        padding: 2;
        color: #888888;
        border-left: vkey #333333; /* Optional subtle border */
    }

    #bottom-container {
        height: auto;
        dock: bottom;
        background: #111111;
    }

    #input-line {
        height: 3;
        width: 100%;
        align-vertical: middle;
        padding: 0 1;
        border-top: solid #333333;
    }

    .prompt-symbol {
        color: #d75f00;
        text-style: bold;
        width: 2;
        content-align: center middle;
    }

    Input {
        width: 1fr;
        background: #111111;
        border: none;
        color: white;
        padding: 0;
    }
    
    Input:focus {
        border: none;
    }
    
    /* Remove default Input styles */
    Input > .input--placeholder {
        color: #555555;
    }
    
    Input > .input--cursor {
        background: #d75f00;
        color: black;
    }

    StatusBar {
        height: 1;
        width: 100%;
        background: #1e1e1e;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-container"):
            yield RichLog(id="main-output", markup=True, highlight=True, auto_scroll=True, wrap=True)
            yield Sidebar(id="sidebar")

        with Vertical(id="bottom-container"):
            with Horizontal(id="input-line"):
                yield Label(">", classes="prompt-symbol")
                yield Input(placeholder="Type a message...", id="input-box")
            yield StatusBar(model_name="Claude 3.7 Sonnet")

    def on_mount(self):
        self.main_log = self.query_one("#main-output", RichLog)
        self.input_box = self.query_one("#input-box", Input)
        self.status_bar = self.query_one(StatusBar)

        self.main_log.write(Text("* gofumpt: 1", style="dim"))
        self.main_log.write(Text("task: [lint] golangci-lint run", style="dim"))
        self.main_log.write(Text("\nReady.", style="bold green"))

        self.tui_stream = TUIStreamOutput(self.main_log)
        self.current_model = "deepseek-r1:14b"
        self.input_box.focus()

    @on(Input.Submitted)
    async def handle_input(self, event: Input.Submitted):
        user_input = event.value
        if not user_input.strip():
            return

        self.input_box.value = ""

        self.main_log.write(Text(f"\n> {user_input}", style="bold white"))

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
    app = QozeTui()
    app.run()
