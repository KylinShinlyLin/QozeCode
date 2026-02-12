# !/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
import asyncio
import os
import sys
import uuid

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from textual.app import App, ComposeResult, on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, RichLog, Label, Markdown as MarkdownWidget, TextArea, OptionList
from textual.widgets.option_list import Option

# Import Enums
from enums import ModelProvider, ModelType
from tui_components import tui_constants

# Configure logging for debugging
log_file = os.path.join(os.path.dirname(__file__), '.qoze', 'debug.log')
# Ensure log directory exists
try:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
except Exception:
    pass

logging.basicConfig(
    filename=log_file,
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

sys.path.append(".")
# Skills TUI Handler Import
sys.path.append(os.path.join(os.path.dirname(__file__), ".qoze"))
try:
    from skills.skills_tui_integration import SkillsTUIHandler

    skills_tui_handler = SkillsTUIHandler()
except ImportError:
    skills_tui_handler = None

# Dynamic Commands Import
try:
    from dynamic_commands_patch import get_dynamic_commands, get_skills_commands
except ImportError:
    get_dynamic_commands = lambda: []
    get_skills_commands = lambda x: []

from utils.constants import init_prompt

# Add current directory to path
sys.path.append(os.getcwd())

# --- Theme Patch ---
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), '.qoze'))
    import qoze_theme

    qoze_theme.apply_theme()
except ImportError:
    pass
# -------------------

os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

# Import agent components
try:
    import launcher
    import model_initializer
    import qoze_code_agent
except ImportError as e:
    print(f"Critical Error: Could not import agent components: {e}")
    sys.exit(1)

# Import TUI Components
try:
    from tui_components.top_bar import TopBar
    from tui_components.sidebar import Sidebar
    from tui_components.request_indicator import RequestIndicator
    from tui_components.status_bar import StatusBar
    from tui_components.tui_stream_output import TUIStreamOutput
except ImportError as e:
    print(f"Critical Error: Could not import TUI components: {e}")
    sys.exit(1)


class Qoze(App):
    CSS = tui_constants.CSS

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Cancel", priority=True),
        Binding("ctrl+d", "submit_multiline", "Submit", priority=True),
        Binding("escape", "cancel_multiline", "Cancel", priority=True),
    ]

    def __init__(self, provider, model_type):
        super().__init__()
        self.model_type = model_type
        self.model_name = model_type.value
        self.provider = provider
        self.agent_ready = False
        self.multiline_mode = False
        self.thread_id = "default_session"
        self.processing_worker = None

    def compose(self) -> ComposeResult:
        yield TopBar()
        with Horizontal(id="main-container"):
            with Vertical(id="chat-area"):
                yield RichLog(id="main-output", markup=True, highlight=True, auto_scroll=True, wrap=True)
                from textual.widgets import Static
                yield Static(id="tool-status")
                yield MarkdownWidget(id="stream-output")
            yield Sidebar(id="sidebar", model_name=self.model_name, provider=self.provider)
        with Vertical(id="bottom-container"):
            yield OptionList(id="command-suggestions")
            with Horizontal(id="input-line"):
                yield Label("❯", classes="prompt-symbol")
                yield Input(placeholder="Initializing Agent...", id="input-box", disabled=True)
            yield TextArea(id="multi-line-input", classes="hidden")
            yield RequestIndicator(id="request-indicator", classes="hidden")
            yield StatusBar(model_name=self.model_name)

    def on_mount(self):
        self.main_log = self.query_one("#main-output", RichLog)
        from textual.widgets import Static
        self.tool_status = self.query_one("#tool-status", Static)
        self.stream_output = self.query_one("#stream-output", MarkdownWidget)
        self.input_box = self.query_one("#input-box", Input)
        self.multi_line_input = self.query_one("#multi-line-input", TextArea)
        self.request_indicator = self.query_one("#request-indicator", RequestIndicator)
        self.status_bar = self.query_one(StatusBar)

        self.main_log.can_focus = False
        self.main_log.auto_scroll = True
        self.tui_stream = TUIStreamOutput(self.main_log, self.stream_output, self.tool_status)

        self.print_welcome()
        self.run_worker(self.init_agent_worker(), exclusive=True)

    def print_welcome(self):

        tips_content = Group(
            Text(""),
            Text("模型: ", style="bold white").append(Text(f"{self.model_name or 'Unknown'}", style="bold cyan")),
            Text("当前目录: ", style="bold white").append(Text(f"{os.getcwd() or 'Unknown'}", style="bold cyan")),
            Text("使用提示: ", style="bold white"),
            Text("  • 输入 'clean' 清空当前会话", style="dim bold white"),
            Text("  • 输入 'q'、'quit' 或 'exit' 退出", style="dim bold white"),
            Text("  • 输入 'line' 进入多行编辑模式 (Ctrl+D 提交)", style="dim bold white"),
            Text(""),
        )
        self.main_log.write(Align.center(Text(tui_constants.QOZE_CODE_ART, style="bold cyan")))
        self.main_log.write(Text(""))
        self.main_log.write(Align.center(Panel(
            tips_content,
            title="[dim white]Tips[/]",
            border_style="bold #414868",
            padding=(0, 1)
        )))

    def action_interrupt(self):
        if self.processing_worker and self.processing_worker.is_running:
            self.processing_worker.cancel()
            self.status_bar.update_state("Cancelled")
            self.query_one("#input-line").remove_class("hidden")
            self.input_box.focus()
            self.processing_worker = None
            return
        self.exit()

    async def init_agent_worker(self):
        try:
            llm = model_initializer.initialize_llm(self.provider, self.model_type)
            qoze_code_agent.llm = llm
            qoze_code_agent.llm_with_tools = llm.bind_tools(qoze_code_agent.tools)
            self.agent_ready = True
            self.input_box.disabled = False
            self.input_box.placeholder = "Type message..."
            self.input_box.focus()
        except Exception as e:
            logging.exception("Initialization Failed")
            self.main_log.write(Text(f"Initialization Failed: {e}", style="red"))

    async def process_user_input(self, user_input):
        if not user_input.strip(): return
        if user_input.startswith("/"): user_input = user_input[1:]

        if user_input.lower() in ["quit", "exit", "q"]:
            self.exit()
            return

        if user_input.lower() == "line":
            self.multiline_mode = True
            self.query_one("#input-line").add_class("hidden")
            self.multi_line_input.remove_class("hidden")
            self.multi_line_input.focus()
            self.status_bar.update_state("Multi-line Mode")
            return

        if user_input.lower() == "clear":
            qoze_code_agent.reset_conversation_state()
            self.main_log.clear()
            self.thread_id = str(uuid.uuid4())
            self.print_welcome()
            return

        if skills_tui_handler and user_input.lower().startswith('skills'):
            success, message = skills_tui_handler.handle_skills_command(user_input.split())
            self.main_log.write(message if success else Text(f"❌ {message}", style="red"))
            return

        if user_input.lower() in ["qoze init", "init"]:
            user_input = init_prompt

        self.request_indicator.start_request()
        self.query_one("#input-line").add_class("hidden")
        self.main_log.focus()

        try:
            self.main_log.write(Text(f"\n❯ {user_input}", style="bold #bb9af7"))

            image_folder = ".qoze/image"
            human_msg = qoze_code_agent.create_message_with_images(user_input, image_folder)

            current_state = {
                "messages": [human_msg]
            }

            await self.tui_stream.stream_response(current_state, qoze_code_agent.conversation_state,
                                                  thread_id=self.thread_id)

        except (KeyboardInterrupt, asyncio.CancelledError):
            self.main_log.write(Text("⛔ Interrupted", style="bold red"))
        except Exception as e:
            self.main_log.write(Text(f"Error: {e}", style="red"))
        finally:
            self.request_indicator.stop_request()
            self.status_bar.update_state("Idle")
            self.query_one("#input-line").remove_class("hidden")
            self.input_box.focus()
            self.processing_worker = None

    @on(Input.Submitted)
    def handle_input(self, event: Input.Submitted):
        if not self.agent_ready: return
        user_input = event.value
        self.input_box.value = ""
        self.processing_worker = self.run_worker(self.process_user_input(user_input), exclusive=True)

    @on(Input.Changed, "#input-box")
    def on_input_changed(self, event: Input.Changed):
        value = event.value
        suggestions = self.query_one("#command-suggestions", OptionList)

        show_suggestions = False
        filtered = []
        if value.startswith("/"):
            try:
                cmds = get_dynamic_commands()
            except:
                cmds = [("/quit", "Quit"), ("/clear", "Clear"), ("/skills", "Skills")]
            filtered = [Option(f"{c} - {d}", id=c[1:]) for c, d in cmds if c.startswith(value)]
            show_suggestions = bool(filtered)
        elif value.lower().startswith("skills"):
            try:
                cmds = get_skills_commands(value)
            except:
                cmds = []
            filtered = [Option(f"{c} - {d}", id=c) for c, d in cmds if c.startswith(value.lower())]
            show_suggestions = bool(filtered)

        if show_suggestions:
            suggestions.clear_options()
            suggestions.add_options(filtered)
            suggestions.styles.display = "block"
        else:
            suggestions.styles.display = "none"

    @on(OptionList.OptionSelected, "#command-suggestions")
    def on_command_selected(self, event: OptionList.OptionSelected):
        cmd = event.option_id
        if cmd:
            self.query_one("#command-suggestions").styles.display = "none"
            self.input_box.value = ""
            self.input_box.focus()
            self.processing_worker = self.run_worker(self.process_user_input(str(cmd)), exclusive=True)

    def on_key(self, event):
        suggestions = self.query_one("#command-suggestions", OptionList)
        if suggestions.styles.display != "none":
            if event.key in ["up", "down"]:
                if event.key == "up":
                    suggestions.action_cursor_up()
                else:
                    suggestions.action_cursor_down()
                event.stop()
            elif event.key == "enter":
                if suggestions.highlighted is not None:
                    opt = suggestions.get_option_at_index(suggestions.highlighted)
                    cmd = str(opt.id)
                    suggestions.styles.display = "none"
                    self.input_box.value = ""
                    self.input_box.focus()
                    self.processing_worker = self.run_worker(self.process_user_input(cmd), exclusive=True)
                event.stop()
            elif event.key == "escape":
                suggestions.styles.display = "none"
                event.stop()

    def on_mouse_scroll_down(self, event):
        if self.main_log.styles.display != "none":
            self.main_log.scroll_relative(y=1, animate=False)

    def on_mouse_scroll_up(self, event):
        if self.main_log.styles.display != "none":
            self.main_log.scroll_relative(y=-1, animate=False)

    async def action_submit_multiline(self):
        if not self.multiline_mode: return
        user_input = self.multi_line_input.text
        self.multiline_mode = False
        self.multi_line_input.add_class("hidden")
        self.multi_line_input.text = ""
        self.query_one("#input-line").remove_class("hidden")
        self.input_box.focus()
        if user_input.strip():
            self.processing_worker = self.run_worker(self.process_user_input(user_input), exclusive=True)

    def action_cancel_multiline(self):
        if not self.multiline_mode: return
        self.multiline_mode = False
        self.multi_line_input.add_class("hidden")
        self.multi_line_input.text = ""
        self.query_one("#input-line").remove_class("hidden")
        self.input_box.focus()
        self.status_bar.update_state("Idle")


def main():
    import shared_console

    launcher.ensure_config()
    selection = launcher.get_model_choice()
    if not selection:
        return
    provider, model_type = selection
    # model 变量为了兼容旧逻辑，赋值为 model_type.value
    model = model_type.value

    # 修复 TUI 错乱: 将共享 Console 的输出重定向到空设备
    null_file = open(os.devnull, "w")
    shared_console.console.file = null_file

    # 清屏
    os.system("cls" if os.name == "nt" else "clear")

    Qoze(provider=provider, model_type=model_type).run()


if __name__ == "__main__":
    main()
