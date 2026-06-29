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

from utils.audio_manager import AudioManager

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from tui_components.pixel_logo import render_pixel_text
from textual.app import App, ComposeResult, on
from textual.driver import Driver
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label, TextArea, OptionList, Markdown, Static
from textual._text_area_theme import TextAreaTheme
from rich.style import Style
from textual.widgets.option_list import Option

# Import Enums
from enums import ModelProvider, ModelType, supports_vision

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

# 移除 App 和 Screen 的默认背景色，让 TUI 跟随终端原生背景（透明）
from textual.app import App as _TextualApp
from textual.screen import Screen

# 按行过滤，移除 background: $background 行（保留 selection 等）
_TextualApp.DEFAULT_CSS = "\n".join(
    l for l in _TextualApp.DEFAULT_CSS.split("\n")
    if not (l.strip().startswith("background: $background;"))
)
Screen.DEFAULT_CSS = "\n".join(
    l for l in Screen.DEFAULT_CSS.split("\n")
    if not (l.strip().startswith("background: $background;"))
)

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


def fuzzy_match(query: str, target: str) -> bool:
    """模糊匹配：query 作为连续子串出现在 target 中。"""
    return query.lower() in target.lower()


class Qoze(App):
    CSS = tui_constants.CSS

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Cancel", priority=True),
        Binding("ctrl+d", "submit_multiline", "Submit", priority=True),
        Binding("escape", "cancel_action", "Cancel", priority=True),
        Binding("ctrl+q", "start_recording", "Record", priority=True),
        Binding("ctrl+e", "stop_recording", "Stop", priority=True),
        Binding("ctrl+n", "toggle_meeting_note", "Meeting Note", priority=True),
    ]

    def __init__(self, provider, model_type):
        super().__init__(ansi_color=True)
        self.model_type = model_type
        self.model_name = model_type.value
        self.provider = provider
        self.agent_ready = False
        self.multiline_mode = False
        self.thread_id = "default_session"
        self.processing_worker = None

        self.audio_manager = AudioManager()
        self.total_tokens = 0
        self._stream_base_tokens = 0
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
                    yield Static(render_pixel_text("QOZE CODE", start_color="#7aa2f7", end_color="#f093c6", gap=1),
                                 id="welcome-art")
                    yield Static(self._get_tips_text(), id="welcome-tips")

                yield MessageList(
                    id="message-list",
                    token_callback=self.add_tokens,
                    token_progress_callback=self.update_token_progress,
                    tool_status_panel=None  # 稍后设置
                )
                yield ToolStatusPanel(id="tool-status-panel")
            yield Sidebar(id="sidebar", model_name=self.model_name, provider=self.provider, model_type=self.model_type)
        with Vertical(id="bottom-container"):
            yield OptionList(id="command-suggestions")
            yield Label(id="audio-status", classes="hidden")
            yield Label(id="meeting-note-status", classes="hidden")
            with Horizontal(id="input-line"):
                yield Label("❯", classes="prompt-symbol")
                yield Input(placeholder="Initializing Agent...", id="input-box", disabled=True)
            yield TextArea(id="multi-line-input", classes="hidden")
            yield RequestIndicator(id="request-indicator", classes="hidden")
            yield StatusBar(model_name=self.model_name)

    def _get_tips_text(self) -> str:
        """获取 Tips 文本"""
        return f"""模型: {self.model_name or '未知'}  •  目录: {os.getcwd()}
💡 clear → 清空会话  •  quit/exit → 退出  •  line → 多行模式  •  Ctrl+Q → 语音输入  •  Ctrl+N → 录音笔记"""

    def on_mount(self):
        self.message_list = self.query_one("#message-list", MessageList)
        self.tool_status_panel = self.query_one("#tool-status-panel", ToolStatusPanel)
        self.welcome_panel = self.query_one("#welcome-panel", Vertical)
        self.welcome_tips = self.query_one("#welcome-tips", Static)
        self.input_box = self.query_one("#input-box", Input)
        self.multi_line_input = self.query_one("#multi-line-input", TextArea)
        # 修复 TextArea 光标颜色（TextArea 光标由语法主题 cursor_style 控制，不走普通 CSS）
        try:
            cursor_theme = TextAreaTheme(
                name="qoze-cursor",
                cursor_style=Style(color="#1a1b26", bgcolor="#c0c4cc"),
                syntax_styles={},
            )
            self.multi_line_input.register_theme(cursor_theme)
            self.multi_line_input.theme = "qoze-cursor"
        except Exception:
            pass
        self.request_indicator = self.query_one("#request-indicator", RequestIndicator)
        self.status_bar = self.query_one(StatusBar)
        self.sidebar = self.query_one("#sidebar", Sidebar)

        # 连接 tool_status_panel 到 message_list
        self.message_list._tool_status_panel = self.tool_status_panel

        self.run_worker(self.init_agent_worker(), exclusive=True)

        # ---- AudioManager callbacks ----
        am = self.audio_manager
        am.on_voice_wave = lambda w: self._on_audio_wave(w)
        am.on_voice_text = lambda t: self._on_audio_text(t)
        am.on_voice_error = lambda e: self.message_list.mount(Static(f"Audio Error: {e}"))
        am.on_meeting_wave = lambda w, t: self._on_meeting_wave(w, t)
        am.on_meeting_elapsed = lambda m, s: self._on_meeting_elapsed(m, s)
        am.on_meeting_error = lambda e: self.message_list.mount(Static(f"📝 Meeting Note Error: {e}"))
        am.on_meeting_started = lambda p: self.message_list.mount(Static(f"📝 Meeting note started → {p}"))
        am.on_meeting_stopped = lambda: self._on_meeting_stopped_ui()
        self._audio_poll_timer = self.set_interval(0.1, self._audio_poll)

    def add_tokens(self, new_tokens: int):
        """流结束时的回调——使用精确计算替代估算值"""
        self.update_token_count()

    def update_token_progress(self, progress_tokens: int):
        """流式输出期间实时更新 token 显示（进度值 + 基准值）"""
        display_tokens = self._stream_base_tokens + progress_tokens
        self.status_bar.update_token_count(display_tokens)

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

    # ------------------------------------------------------------------
    # Meeting Note Recorder (Ctrl+N toggle) - independent of AI agent
    # ------------------------------------------------------------------

    def action_toggle_meeting_note(self):
        """Toggle meeting note recording on / off."""
        was_active = self.audio_manager.meeting_active
        err = self.audio_manager.toggle_meeting()
        if err:
            self.message_list.mount(Static(err))
        elif not was_active:
            # 刚刚启动 — 显示声纹标签 + 状态栏
            mn_status = self.query_one("#meeting-note-status", Label)
            mn_status.remove_class("hidden")
            mn_status.update(Text("📝 Initializing Mic...", style="bold #FF8C00"))
            self.status_bar.update_state("📝 Recording Meeting Note...  Ctrl+N 停止", style="bold yellow")

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Audio helpers (delegated to AudioManager)
    # ------------------------------------------------------------------

    def _audio_poll(self):
        self.audio_manager.poll()

    def stop_audio(self):
        final_text = self.audio_manager.stop_voice()
        audio_status = self.query_one("#audio-status", Label)
        audio_status.add_class("hidden")
        audio_status.update("")
        self.status_bar.update_state("Idle")
        if final_text and self.multiline_mode:
            self.multi_line_input.text = final_text
            self.multi_line_input.cursor_location = (
                len(self.multi_line_input.document.lines) - 1,
                len(self.multi_line_input.document.lines[-1]),
            )
        elif final_text:
            self.input_box.value = final_text

    def _on_audio_wave(self, wave_str: str):
        audio_status = self.query_one("#audio-status", Label)
        audio_status.update(Text(f"🎤️ {wave_str}", style="cyan"))

    def _on_audio_text(self, text_str: str):
        if self.multiline_mode:
            self.multi_line_input.text = text_str
            self.multi_line_input.cursor_location = (
                len(self.multi_line_input.document.lines) - 1,
                len(self.multi_line_input.document.lines[-1]),
            )
        else:
            self.input_box.value = text_str

    def _on_meeting_wave(self, wave_str: str, latest_text):
        mn_status = self.query_one("#meeting-note-status", Label)
        if wave_str:
            display = f"📝 {wave_str}"
            if latest_text:
                display += f"  |  {latest_text[-60:]}"
        else:
            display = f"📝 {latest_text[-80:]}" if latest_text else "📝 ..."
        mn_status.update(Text(display, style="bold #FF8C00"))

    def _on_meeting_elapsed(self, mins: int, secs: int):
        self.status_bar.update_state(
            f"📝 Meeting Note | {mins:02d}:{secs:02d}  Ctrl+N 停止",
            style="bold yellow",
        )

    def _on_meeting_stopped_ui(self):
        mn_status = self.query_one("#meeting-note-status", Label)
        mn_status.add_class("hidden")
        mn_status.update("")
        self.status_bar.update_state("Idle")

    # Voice Input (Ctrl+Q / Ctrl+E) - feeds transcribed text into input
    # ------------------------------------------------------------------

    def action_start_recording(self):
        if self.audio_manager.meeting_active:
            return  # meeting note is active, block voice input
        if self.audio_manager.voice_active:
            return
        if self.multiline_mode:
            current_text = self.multi_line_input.text
        else:
            current_text = self.input_box.value
        err = self.audio_manager.start_voice(current_text)
        if err:
            self.message_list.mount(Static(err))
        else:
            audio_status = self.query_one("#audio-status", Label)
            audio_status.remove_class("hidden")
            audio_status.update(Text("🎤️ Initializing Mic...", style="cyan"))
            self.status_bar.update_state("Recording... Esc 停止语音输入")

    def action_stop_recording(self):
        if self.audio_manager.voice_active:
            self.stop_audio()

    def action_cancel_action(self):
        if self.audio_manager.meeting_active:
            self.audio_manager.stop_meeting()
            self._on_meeting_stopped_ui()
        elif self.audio_manager.voice_active:
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
            qoze_code_agent.current_model_type = self.model_type
            from tools.subagent_tool import reset_subagent_cache
            reset_subagent_cache()
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
            err = self.audio_manager.start_voice()
            if err:
                self.message_list.mount(Static(err))
                audio_status = self.query_one("#audio-status", Label)
                audio_status.remove_class("hidden")
                audio_status.update(Text("🎤️ Initializing Mic...", style="cyan"))
                self.status_bar.update_state("Recording... Esc 停止语音输入")
            return

        if user_input.lower() in ["quit", "exit", "q"]:
            self.exit()
            return

        # ---- checkpoint 命令 (独立 LLM 调用，不经过 Agent StateGraph) ----
        if user_input.lower() == "checkpoint":
            await self._handle_checkpoint(clear_after=False)
            return
        if user_input.lower() == "checkpoint --clear":
            await self._handle_checkpoint(clear_after=True)
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
            from tools.subagent_tool import reset_subagent_cache
            reset_subagent_cache()
            self.message_list.clear_messages()
            self.thread_id = str(uuid.uuid4())
            self.total_tokens = 0
            self.status_bar.update_token_count(0)
            self.show_welcome()
            self.print_welcome()
            return

        if skills_tui_handler and user_input.lower().startswith('skills'):
            success, message = skills_tui_handler.handle_skills_command(user_input.split())
            if not success:
                style = "bold red"
            elif "disable" in user_input.lower():
                style = "bold red"
            else:
                style = "bold green"
            icon = "✗" if "disable" in user_input.lower() else ("✓" if success else "✗")
            self.message_list.mount(Static(Text(f"Skills: {icon} {message}", style=style)))
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
            model_has_vision = supports_vision(self.model_type)
            human_msg = qoze_code_agent.create_message_with_images(
                actual_input, image_folder, supports_vision=model_has_vision
            )
            # 如果当前模型不支持视觉，但 .qoze/image 下有图片，给出提示
            if not model_has_vision:
                import os as _os
                from qoze_code_agent import get_image_files
                try:
                    img_files = get_image_files(image_folder)
                    if img_files:
                        await self.message_list.mount(Static(
                            Text(f"⚠️ 当前模型 ({self.model_name}) 不支持视觉模态，"
                                 f"{len(img_files)} 张图片不会被加载到上下文",
                                 style="dim yellow")
                        ))
                except Exception:
                    pass

            current_state = {"messages": [human_msg]}

            # 记录本次请求开始前的 token 基准值，用于流式期间实时显示
            self._stream_base_tokens = self.total_tokens

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
            await self.message_list.mount(Static(f"Error: {e}"))
        finally:
            self.request_indicator.stop_request()
            self.status_bar.update_state("Idle")
            # 请求结束后精确计算并校正 token 数
            self.update_token_count()
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

        if self.audio_manager.voice_active:
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
            filtered = [Option(f"{c} - {d}", id=c[1:]) for c, d in cmds if fuzzy_match(value[1:], c)]
            show_suggestions = bool(filtered)
        elif value.lower().startswith("skills"):
            try:
                cmds = get_skills_commands(value)
            except:
                cmds = []
            filtered = [Option(f"{c} - {d}", id=c) for c, d in cmds if fuzzy_match(value.lower(), c.lower())]
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
                err = self.audio_manager.start_voice()
                if err:
                    self.message_list.mount(Static(err))
                else:
                    audio_status = self.query_one("#audio-status", Label)
                    audio_status.remove_class("hidden")
                    audio_status.update(Text("🎤️ Initializing Mic...", style="cyan"))
                    self.status_bar.update_state("Recording... Esc 停止语音输入")
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
                        err = self.audio_manager.start_voice()
                        if err:
                            self.message_list.mount(Static(err))
                        else:
                            audio_status = self.query_one("#audio-status", Label)
                            audio_status.remove_class("hidden")
                            audio_status.update(Text("🎤️ Initializing Mic...", style="cyan"))
                            self.status_bar.update_state("Recording... Esc 停止语音输入")
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
            self.call_after_refresh(self.message_list.check_scroll_bottom_and_resume)
            event.stop()
            event.prevent_default()

    def on_mouse_scroll_up(self, event):
        if self.message_list.styles.display != "none":
            self.message_list.user_scrolled_up()
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

        if self.audio_manager.voice_active:
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
            err = self.audio_manager.start_voice(original_text)
            if err:
                self.message_list.mount(Static(err))
                audio_status = self.query_one("#audio-status", Label)
                audio_status.remove_class("hidden")
                audio_status.update(Text("🎤️ Initializing Mic...", style="cyan"))
                self.status_bar.update_state("Recording... Esc 停止语音输入")
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

    async def _handle_checkpoint(self, clear_after: bool = False):
        """处理 /checkpoint 命令 — 独立 LLM 调用，不经过 Agent StateGraph"""
        from utils.checkpoint_manager import CheckpointManager
        from textual.widgets import Static

        self.status_bar.update_state("Saving checkpoint...")
        self.query_one("#input-line").add_class("hidden")
        self.request_indicator.start_request()
        if self.tool_status_panel:
            self.tool_status_panel.add_tool("checkpoint", "提取会话摘要...")

        try:
            mgr = CheckpointManager()

            # 1. 读取主会话状态
            config = {"configurable": {"thread_id": self.thread_id}}
            state = qoze_code_agent.agent.get_state(config)

            messages = []
            if state and hasattr(state, 'values') and state.values:
                messages = state.values.get("messages", [])
            elif state and isinstance(state, dict):
                messages = state.get("values", {}).get("messages", [])

            if not messages:
                self.message_list.mount(Static(
                    Text("⚠️ 暂无会话内容可保存", style="bold yellow")
                ))
                return

            # 2. 过滤消息
            filtered = mgr.filter_messages(messages)
            if not filtered:
                self.message_list.mount(Static(
                    Text("⚠️ 过滤后无有效对话内容", style="bold yellow")
                ))
                return

            # 3. 收集元信息
            token_count = qoze_code_agent.estimate_token_count(messages)
            active_skills = []
            if skills_tui_handler and hasattr(skills_tui_handler, 'skill_manager'):
                sm = skills_tui_handler.skill_manager
                if hasattr(sm, 'active_skills'):
                    active_skills = list(sm.active_skills)


            rounds = sum(1 for m in filtered if m["role"] == "user")

            # 4. 构造 prompt + 独立 LLM 调用
            prompt = mgr.build_checkpoint_prompt(
                filtered_messages=filtered,
                model_name=str(self.model_type.value) if self.model_type else "未知",
                token_count=token_count,
                active_skills=active_skills,
                conversation_rounds=rounds,
            )
            summary = await mgr.summarize(qoze_code_agent.llm, prompt)

            # 5. 保存
            filepath = mgr.save(summary)

            # 6. 显示结果
            self.message_list.mount(Static(
                Text(f"✓ Checkpoint 已保存到 {filepath}", style="bold green")
            ))

            # 7. 可选清理
            if clear_after:
                qoze_code_agent.reset_conversation_state()
                from tools.subagent_tool import reset_subagent_cache
                reset_subagent_cache()
                self.message_list.clear_messages()
                self.thread_id = str(uuid.uuid4())
                self.total_tokens = 0
                self.status_bar.update_token_count(0)
                self.show_welcome()
                self.print_welcome()

        except Exception as e:
            import logging
            logging.exception("Checkpoint failed")
            self.message_list.mount(Static(
                Text(f"✗ Checkpoint 失败: {e}", style="bold red")
            ))
        finally:
            if self.tool_status_panel:
                self.tool_status_panel.remove_tool("checkpoint")
            self.request_indicator.stop_request()
            self.status_bar.update_state("Idle")
            self.query_one("#input-line").remove_class("hidden")
            self.input_box.focus()


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
