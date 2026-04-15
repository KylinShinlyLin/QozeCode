#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
import asyncio
import os
import sys
import uuid

import queue
import time

from tui_components import tui_constants

try:
    from utils.audio_transcriber import AudioTranscriber
    AUDIO_TRANSCRIBER_IMPORT_ERROR = None
except ImportError as e:
    AudioTranscriber = None
    AUDIO_TRANSCRIBER_IMPORT_ERROR = str(e)

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from textual.app import App, ComposeResult, on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label, TextArea, OptionList, Markdown, Static
from textual.widgets.option_list import Option

# Import Enums
from enums import ModelProvider, ModelType

# Configure logging for debugging
log_file = os.path.join(os.path.dirname(__file__), '.qoze', 'debug.log')
try:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
except Exception:
    pass

logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

sys.path.append(".")
sys.path.append(os.path.join(os.path.dirname(__file__), ".qoze"))

try:
    from skills.skills_tui_integration import SkillsTUIHandler
    skills_tui_handler = SkillsTUIHandler()
except ImportError:
    skills_tui_handler = None

try:
    from dynamic_commands_patch import get_dynamic_commands, get_skills_commands
except ImportError:
    get_dynamic_commands = lambda: []
    get_skills_commands = lambda x: []

from utils.constants import init_prompt

sys.path.append(os.getcwd())

try:
    sys.path.append(os.path.join(os.path.dirname(__file__), '.qoze'))
    import qoze_theme
    qoze_theme.apply_theme()
except ImportError:
    pass

os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

try:
    import launcher
    import model_initializer
    import qoze_code_agent
except ImportError as e:
    print(f"Critical Error: Could not import agent components: {e}")
    sys.exit(1)

try:
    from tui_components.top_bar import TopBar
    from tui_components.sidebar import Sidebar
    from tui_components.request_indicator import RequestIndicator
    from tui_components.status_bar import StatusBar
    from tui_components.messages import MessageList
    from tui_components.messages.tool_status_panel import ToolStatusPanel
except ImportError as e:
    print(f"Critical Error: Could not import TUI components: {e}")
    sys.exit(1)


class Qoze(App):
    CSS = tui_constants.CSS

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Cancel", priority=True),
        Binding("ctrl+d", "submit_multiline", "Submit", priority=True),
        Binding("escape", "cancel_action", "Cancel", priority=True),
        Binding("ctrl+q", "start_recording", "Record", priority=True),
        Binding("ctrl+e", "stop_recording", "Stop", priority=True),
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

        self.audio_transcriber = None
        self.audio_queue = queue.Queue()
        self.audio_mode = False
        self.audio_original_text = ""
        self.audio_check_timer = None
        self.total_tokens = 0
        self._processing_suggestion = False

        self._last_scroll_time = 0
        self._scroll_throttle_ms = 50
        self._scroll_accumulator = 0

    def compose(self) -> ComposeResult:
        yield TopBar()
        with Horizontal(id="main-container"):
            with Vertical(id="chat-area"):
                # 欢迎区域 - 包含 ASCII Art 和 Tips
                with Vertical(id="welcome-panel"):
                    yield Static(tui_constants.QOZE_CODE_ART, id="welcome-art")
                    yield Static(self._get_tips_text(), id="welcome-tips")
                
                yield MessageList(
                    id="message-list",
                    token_callback=self.add_tokens,
                    tool_status_panel=None  # 稍后设置
                )
                yield ToolStatusPanel(id="tool-status-panel")
            yield Sidebar(id="sidebar", model_name=self.model_name, provider=self.provider)
        with Vertical(id="bottom-container"):
            yield OptionList(id="command-suggestions")
            yield Label(id="audio-status", classes="hidden")
            with Horizontal(id="input-line"):
                yield Label("❯", classes="prompt-symbol")
                yield Input(placeholder="Initializing Agent...", id="input-box", disabled=True)
            yield TextArea(id="multi-line-input", classes="hidden")
            yield RequestIndicator(id="request-indicator", classes="hidden")
            yield StatusBar(model_name=self.model_name)

    def _get_tips_text(self) -> str:
        """获取 Tips 文本"""
        return f"""模型: {self.model_name or '未知'}  •  目录: {os.getcwd()}
💡 clear → 清空会话  •  quit/exit → 退出  •  line → 多行模式  •  Ctrl+Q → 语音输入"""

    def on_mount(self):
        self.message_list = self.query_one("#message-list", MessageList)
        self.tool_status_panel = self.query_one("#tool-status-panel", ToolStatusPanel)
        self.welcome_panel = self.query_one("#welcome-panel", Vertical)
        self.welcome_tips = self.query_one("#welcome-tips", Static)
        self.input_box = self.query_one("#input-box", Input)
        self.multi_line_input = self.query_one("#multi-line-input", TextArea)
        self.request_indicator = self.query_one("#request-indicator", RequestIndicator)
        self.status_bar = self.query_one(StatusBar)
        
        # 连接 tool_status_panel 到 message_list
        self.message_list._tool_status_panel = self.tool_status_panel

        self.run_worker(self.init_agent_worker(), exclusive=True)

    def add_tokens(self, new_tokens: int):
        """累加本次对话新增的 token 数"""
        self.total_tokens += new_tokens
        self.status_bar.update_token_count(self.total_tokens)

    def update_token_count(self):
        """更新状态栏中的 token 数量"""
        try:
            config = {"configurable": {"thread_id": self.thread_id}}
            state = qoze_code_agent.agent.get_state(config)

            messages = None
            if state:
                if hasattr(state, 'values') and state.values:
                    messages = state.values.get('messages')
                elif isinstance(state, dict):
                    messages = state.get('values', {}).get('messages')
                elif hasattr(state, 'messages'):
                    messages = state.messages

            if messages:
                token_count = qoze_code_agent.estimate_token_count(messages)
                self.total_tokens = token_count
                self.status_bar.update_token_count(token_count)
            else:
                self.total_tokens = 0
                self.status_bar.update_token_count(0)
        except Exception as e:
            import logging
            logging.error(f"Token count update failed: {e}")
            pass

    def print_welcome(self):
        """更新欢迎区域的 tips（在 clear 后调用）"""
        if self.welcome_tips:
            self.welcome_tips.update(self._get_tips_text())

    def hide_welcome(self):
        """隐藏欢迎区域（当有新消息时）"""
        if self.welcome_panel:
            self.welcome_panel.add_class("hidden")

    def show_welcome(self):
        """显示欢迎区域"""
        if self.welcome_panel:
            self.welcome_panel.remove_class("hidden")

    def check_audio_queue(self):
        if not self.audio_mode:
            return
        updates = False
        text_content = None
        wave_content = None
        while not self.audio_queue.empty():
            msg = self.audio_queue.get()
            if msg["type"] == "text":
                text_content = msg["data"]
                updates = True
            elif msg["type"] == "wave":
                wave_content = msg["data"]
                updates = True
            elif msg["type"] == "error":
                self.message_list.mount(Static(f"Audio Error: {msg['data']}"))

        if text_content is not None:
            combined_text = self.audio_original_text
            if combined_text:
                combined_text += " " + text_content
            else:
                combined_text = text_content

            if self.multiline_mode:
                self.multi_line_input.text = combined_text
                self.multi_line_input.cursor_location = (len(self.multi_line_input.document.lines) - 1,
                                                         len(self.multi_line_input.document.lines[-1]))
            else:
                self.input_box.value = combined_text

        if wave_content is not None:
            audio_status = self.query_one("#audio-status", Label)
            audio_status.update(Text(f"🎙️ {wave_content}", style="cyan"))

    def start_audio(self, original_text=""):
        if AudioTranscriber is None:
            self.message_list.mount(Static("Audio Transcriber not available. Dependencies may be missing."))
            return

        import config_manager
        soniox_key = config_manager.get_soniox_key()
        if not soniox_key:
            self.message_list.mount(Static("🔴 未检测到 Soniox API Key。请在 qoze.conf 的 [soniox] 节点下添加 api_key"))
            return

        self.audio_mode = True
        self.audio_original_text = original_text
        self.audio_transcriber = AudioTranscriber(api_key=soniox_key, event_queue=self.audio_queue)
        self.audio_transcriber.start()

        audio_status = self.query_one("#audio-status", Label)
        audio_status.remove_class("hidden")
        audio_status.update(Text("🎙️ Initializing Mic...", style="cyan"))

        self.status_bar.update_state("Recording... Esc 停止语音输入")

        if self.audio_check_timer:
            self.audio_check_timer.stop()
        self.audio_check_timer = self.set_interval(0.1, self.check_audio_queue)

    def stop_audio(self):
        if not self.audio_mode:
            return
        self.audio_mode = False
        if self.audio_transcriber:
            self.audio_transcriber.stop()
            self.audio_transcriber = None

        audio_status = self.query_one("#audio-status", Label)
        audio_status.add_class("hidden")
        audio_status.update("")

        if self.audio_check_timer:
            self.audio_check_timer.stop()
            self.audio_check_timer = None

        self.status_bar.update_state("Idle")
        self.check_audio_queue()

    def action_start_recording(self):
        if self.audio_mode:
            return
        if self.multiline_mode:
            current_text = self.multi_line_input.text
        else:
            current_text = self.input_box.value
        self.start_audio(current_text)

    def action_stop_recording(self):
        if self.audio_mode:
            self.stop_audio()

    def action_cancel_action(self):
        if self.audio_mode:
            self.stop_audio()
        elif self.multiline_mode:
            self.action_cancel_multiline()

    def action_interrupt(self):
        if self.processing_worker and self.processing_worker.is_running:
            self.processing_worker.cancel()
            self.status_bar.update_state("Cancelled")
            self.query_one("#input-line").remove_class("hidden")
            self.input_box.focus()
            self.processing_worker = None
            if self.tool_status_panel:
                self.tool_status_panel.clear_all()
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
            self.status_bar.update_token_count(0)
        except Exception as e:
            logging.exception("Initialization Failed")
            self.message_list.mount(Static(f"Initialization Failed: {e}"))

    async def process_user_input(self, user_input):
        if not user_input.strip(): 
            return
        if user_input.startswith("/"): 
            user_input = user_input[1:]

        if user_input.lower() == "audio":
            self.start_audio()
            return

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
            self.message_list.clear_messages()
            self.thread_id = str(uuid.uuid4())
            self.total_tokens = 0
            self.status_bar.update_token_count(0)
            self.show_welcome()
            self.print_welcome()
            return

        if skills_tui_handler and user_input.lower().startswith('skills'):
            success, message = skills_tui_handler.handle_skills_command(user_input.split())
            self.message_list.mount(Markdown(f"**Skills:** {'✓' if success else '✗'} {message}"))
            return

        is_init_command = user_input.lower() in ["init"]
        display_input = user_input
        actual_input = init_prompt if is_init_command else user_input

        # 隐藏欢迎区域，当有用户输入时
        self.hide_welcome()

        self.request_indicator.start_request()
        self.query_one("#input-line").add_class("hidden")

        try:
            # 显示用户消息
            is_cmd = user_input.startswith("/") or user_input.lower() in ["init", "clear"]
            if is_init_command:
                self.message_list.add_user_message("/init", is_command=True)
            else:
                self.message_list.add_user_message(display_input, is_command=is_cmd)

            image_folder = ".qoze/image"
            human_msg = qoze_code_agent.create_message_with_images(actual_input, image_folder)

            current_state = {"messages": [human_msg]}

            # 新消息系统流式处理
            stream = qoze_code_agent.agent.astream(
                current_state,
                stream_mode="messages",
                config={"recursion_limit": 300, "configurable": {"thread_id": self.thread_id}}
            )
            await self.message_list.stream_agent_response(stream)

        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        except Exception as e:
            self.message_list.mount(Static(f"Error: {e}"))
        finally:
            self.request_indicator.stop_request()
            self.status_bar.update_state("Idle")
            self.query_one("#input-line").remove_class("hidden")
            self.input_box.focus()
            self.processing_worker = None
            if self.tool_status_panel:
                self.tool_status_panel.clear_all()

    @on(Input.Submitted)
    def handle_input(self, event: Input.Submitted):
        if not self.agent_ready: 
            return

        suggestions = self.query_one("#command-suggestions", OptionList)
        if suggestions.styles.display != "none":
            return

        if self._processing_suggestion:
            self._processing_suggestion = False
            return

        if self.audio_mode:
            self.stop_audio()
            user_input = event.value
            self.input_box.value = ""
            self.processing_worker = self.run_worker(self.process_user_input(user_input), exclusive=True)
            return

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
            if cmd == "audio":
                self.start_audio()
            else:
                self.processing_worker = self.run_worker(self.process_user_input(cmd), exclusive=True)

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
                    self._processing_suggestion = True
                    opt = suggestions.get_option_at_index(suggestions.highlighted)
                    cmd = str(opt.id)
                    suggestions.styles.display = "none"
                    self.input_box.value = ""
                    self.input_box.focus()
                    if cmd == "audio":
                        self.start_audio()
                    else:
                        self.processing_worker = self.run_worker(self.process_user_input(cmd), exclusive=True)
                event.stop()
            elif event.key == "escape":
                suggestions.styles.display = "none"
                event.stop()

    def _should_process_scroll(self) -> bool:
        """检查是否应该处理滚动事件（节流控制）"""
        current_time = int(time.time() * 1000)
        elapsed = current_time - self._last_scroll_time
        if elapsed >= self._scroll_throttle_ms:
            self._last_scroll_time = current_time
            return True
        return False

    def _get_scroll_lines(self, direction: int) -> int:
        """获取应该滚动的行数"""
        self._scroll_accumulator += direction
        if abs(self._scroll_accumulator) >= 1:
            lines = self._scroll_accumulator
            self._scroll_accumulator = 0
            return lines
        return 0

    def on_mouse_scroll_down(self, event):
        if self.message_list.styles.display != "none":
            if not self._should_process_scroll():
                event.stop()
                event.prevent_default()
                return
            lines = self._get_scroll_lines(5)
            if lines != 0:
                self.message_list.scroll_relative(y=lines, animate=False)
            event.stop()
            event.prevent_default()

    def on_mouse_scroll_up(self, event):
        if self.message_list.styles.display != "none":
            if not self._should_process_scroll():
                event.stop()
                event.prevent_default()
                return
            lines = self._get_scroll_lines(-5)
            if lines != 0:
                self.message_list.scroll_relative(y=lines, animate=False)
            event.stop()
            event.prevent_default()

    async def action_submit_multiline(self):
        if not self.multiline_mode: 
            return

        if self.audio_mode:
            self.stop_audio()
            return

        user_input = self.multi_line_input.text
        lines = user_input.split('\n')
        if lines and lines[-1].strip().endswith("/audio") or lines and lines[-1].strip().endswith("audio"):
            original_text = user_input
            if original_text.endswith("/audio"):
                original_text = original_text[:-6]
            elif original_text.endswith("audio"):
                original_text = original_text[:-5]

            self.multi_line_input.text = original_text
            self.start_audio(original_text)
            return

        self.multiline_mode = False
        self.multi_line_input.add_class("hidden")
        self.multi_line_input.text = ""
        self.query_one("#input-line").remove_class("hidden")
        self.input_box.focus()
        if user_input.strip():
            self.processing_worker = self.run_worker(self.process_user_input(user_input), exclusive=True)

    def action_cancel_multiline(self):
        if not self.multiline_mode: 
            return
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

    # 修复 TUI 错乱: 将共享 Console 的输出重定向到空设备
    null_file = open(os.devnull, "w")
    shared_console.console.file = null_file

    # 清屏
    os.system("cls" if os.name == "nt" else "clear")

    Qoze(provider=provider, model_type=model_type).run()


if __name__ == "__main__":
    main()
