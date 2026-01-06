import asyncio
import os
import sys
from datetime import datetime
from textual.app import App, ComposeResult, on
from textual.containers import Container
from textual.widgets import Header, Footer, Input, RichLog
from textual.binding import Binding
from rich.text import Text
from rich.panel import Panel

# Add current directory to path
sys.path.append(os.getcwd())

# Import agent components
try:
    from qoze_code_agent import agent, conversation_state, create_message_with_images
    from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
except ImportError as e:
    print(f"Error importing qoze_code_agent: {e}")
    sys.exit(1)


class TUIStreamOutput:
    def __init__(self, main_log: RichLog, event_log: RichLog):
        self.main_log = main_log
        self.event_log = event_log
        self.buffer = ""

    def log_event(self, message, style="dim"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.event_log.write(Text(f"[{timestamp}] {message}", style=style))

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

        self.log_event(f"Start generating with {model_name}", "bold blue")
        self.write_main(f"\n--- Response ({model_name}) ---\n", "bold magenta")

        try:
            async for message_chunk, metadata in agent.astream(
                    current_state, stream_mode="messages", config={"recursion_limit": 150}
            ):
                if isinstance(message_chunk, ToolMessage):
                    tool_name = message_chunk.name if hasattr(message_chunk, 'name') else "Tool"
                    self.log_event(f"Tool Done: {tool_name}", "green")
                    continue

                if isinstance(message_chunk, AIMessage) and message_chunk.tool_calls:
                    for tool_call in message_chunk.tool_calls:
                        self.log_event(f"Tool Call: {tool_call['name']}", "bold yellow")

                # DeepSeek Reasoning
                if hasattr(message_chunk, 'additional_kwargs') and message_chunk.additional_kwargs:
                    reasoning = message_chunk.additional_kwargs.get('reasoning_content', '')
                    if reasoning:
                        current_reasoning_content += reasoning
                        # Display reasoning in main log? Or maybe side log?
                        # Let's put it in main log but dim
                        self.write_main(reasoning, style="dim italic")
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
            self.main_log.write(Text("\n[Completed]", style="bold green"))
            self.log_event("Generation Completed", "bold green")

            # Update State
            additional_kwargs = {'reasoning_content': current_reasoning_content}
            ai_response = AIMessage(
                content=current_response_text,
                additional_kwargs=additional_kwargs)
            conversation_state["messages"].extend([ai_response])
            conversation_state["llm_calls"] += 1

        except Exception as e:
            self.main_log.write(f"[red]Error: {e}[/]")
            self.log_event(f"Error: {e}", "bold red")


class QozeTui(App):
    CSS = """
    #grid-container {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 70% 30%;
        height: 1fr;
    }

    #left-panel {
        height: 100%;
    }

    #main-output {
        height: 100%;
    }

    #input-area {
        dock: bottom;
        height: 3;
        border: round #5EF9FF;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="grid-container"):
            # Swapped: Main Output is now first (left, 70%), Events/Left-Panel is second (right, 30%)
            yield RichLog(id="main-output", markup=True, highlight=True, auto_scroll=True, wrap=True)
            yield RichLog(id="left-panel", markup=True, highlight=True, auto_scroll=True)
        yield Input(placeholder="回车执行请求（输入 'line' 进入多行编辑）", id="input-area")

    def on_mount(self):
        self.left_log = self.query_one("#left-panel", RichLog)
        self.main_log = self.query_one("#main-output", RichLog)

        self.left_log.write(Panel("System Events\nWaiting for input...", style="bold green"))
        self.main_log.write(Panel("Qoze Agent Output Area", style="bold blue"))

        self.tui_stream = TUIStreamOutput(self.main_log, self.left_log)
        self.current_model = "deepseek-r1:14b"  # Hardcoded default for now

    @on(Input.Submitted)
    async def handle_input(self, event: Input.Submitted):
        user_input = event.value
        if not user_input.strip():
            return

        self.query_one("#input-area", Input).value = ""

        self.main_log.write(Text(f"\n> User: {user_input}", style="bold white on black"))
        self.tui_stream.log_event("Input Received", "bold white")

        if user_input.lower() in ['quit', 'exit', 'q']:
            self.exit()
            return

        if user_input.lower() == 'clear':
            self.main_log.clear()
            self.left_log.clear()
            return

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
