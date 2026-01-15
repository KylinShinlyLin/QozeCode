#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import sys
import asyncio
import subprocess
import traceback
from datetime import datetime
import uuid

from textual import events
from textual.app import App, ComposeResult, on
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Static, Label, Markdown, TextArea, OptionList
from textual.widgets.option_list import Option
from textual.binding import Binding
from textual.geometry import Offset
from textual.message import Message
from rich.text import Text
from rich.markup import escape

# Skills TUI Integration
sys.path.append(".")
sys.path.append(os.path.join(os.path.dirname(__file__), ".qoze"))
try:
    from skills.skills_tui_integration import SkillsTUIHandler
except ImportError:
    # Fallback if module not found during init
    class SkillsTUIHandler:
        def handle_skills_command(self, *args): return False, "Skills module not found"

try:
    from dynamic_commands_patch import get_dynamic_commands, get_skills_commands
except ImportError:
    def get_dynamic_commands(): return []
    def get_skills_commands(s): return []

try:
    from utils.constants import init_prompt
except ImportError:
    init_prompt = "Hello"

# Add current directory to path
sys.path.append(os.getcwd())

os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

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


def get_git_info():
    try:
        repo_url = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], text=True,
                                           stderr=subprocess.DEVNULL).strip()
        return repo_url
    except:
        return "local"


def get_git_branch():
    try:
        branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], text=True,
                                         stderr=subprocess.DEVNULL).strip()
        return branch
    except:
        return None


def get_modified_files():
    try:
        status = subprocess.check_output(['git', 'status', '-s'], text=True, stderr=subprocess.DEVNULL).strip()
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


class SelectableMarkdownWidget(Markdown):
    """支持多行选择的 Markdown 组件"""

    DEFAULT_CSS = """
    SelectableMarkdownWidget {
        scrollbar-gutter: stable;
        background: #13131c;
        color: #c0caf5;
    }

    SelectableMarkdownWidget .selected {
        background: blue 50%;
        color: white;
    }
    
    SelectableMarkdownWidget > BlockQuote {
        border-left: solid #7aa2f7;
        color: #7aa2f7;
        background: #1f2335;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    """

    class SelectionChanged(Message):
        """选择改变时的消息"""

        def __init__(self, selected_text: str) -> None:
            self.selected_text = selected_text
            super().__init__()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selection_start = None
        self.selection_end = None
        self.is_selecting = False
        self.selected_text = ""

    def on_mount(self) -> None:
        """组件挂载时的初始化"""
        self.can_focus = True

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """鼠标按下事件"""
        if event.button == 1:  # 左键
            self.capture_mouse()
            self.is_selecting = True
            # 使用 Offset 来存储位置
            self.selection_start = Offset(event.x, event.y)
            self.selection_end = self.selection_start
            self.refresh()
            event.prevent_default()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """鼠标移动事件"""
        if self.is_selecting and event.button == 1:
            self.selection_end = Offset(event.x, event.y)
            self.refresh()
            event.prevent_default()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """鼠标释放事件"""
        if event.button == 1 and self.is_selecting:
            self.release_mouse()
            self.is_selecting = False
            self._update_selection()
            event.prevent_default()

    def _update_selection(self) -> None:
        """更新选择的文本"""
        if not self.selection_start or not self.selection_end:
            return

        # 获取选择区域内的文本
        selected_text = self._get_selected_text()
        self.selected_text = selected_text

        # 发送选择改变消息
        self.post_message(self.SelectionChanged(selected_text))

    def _get_selected_text(self) -> str:
        """获取选中的文本内容 (简易实现)"""
        if not self.selection_start or not self.selection_end:
            return ""
        
        try:
            start_row = min(self.selection_start.y, self.selection_end.y)
            end_row = max(self.selection_start.y, self.selection_end.y)
            start_col = min(self.selection_start.x, self.selection_end.x) if start_row == end_row else (
                self.selection_start.x if self.selection_start.y < self.selection_end.y else self.selection_end.x
            )
            end_col = max(self.selection_start.x, self.selection_end.x) if start_row == end_row else (
                self.selection_end.x if self.selection_start.y < self.selection_end.y else self.selection_start.x
            )
            return f"Selection: ({start_row},{start_col}) to ({end_row},{end_col})"
        except Exception:
            return ""

    def render(self):
        """渲染组件"""
        return super().render()

    def clear_selection(self) -> None:
        """清除选择"""
        self.selection_start = None
        self.selection_end = None
        self.selected_text = ""
        self.is_selecting = False
        self.refresh()

    def get_selected_text(self) -> str:
        """获取当前选中的文本"""
        return self.selected_text


class TopBar(Static):
    def on_mount(self):
        self.update_clock()
        self.set_interval(1, self.update_clock)

    def update_clock(self):
        time_str = datetime.now().strftime("%H:%M:%S")
        left = Text(" QozeCode ", style="bold white on #d75f00")
        left.append(" v0.3.3 ", style="bold white on #005faf")
        right = Text(f" {time_str} ", style="bold white on #333333")
        total_width = self.content_size.width or 80
        spacer_width = max(0, total_width - len(left) - len(right))
        content = left + Text(" " * spacer_width, style="on #1a1b26") + right
        self.update(content)


class Sidebar(Static):
    def __init__(self, *args, model_name="Unknown", **kwargs):
        self.model_name = model_name
        super().__init__(*args, **kwargs)

    def on_mount(self):
        self.update_info()
        self.set_interval(5, self.update_info)

    def update_info(self):
        repo_url = get_git_info()
        modified = get_modified_files()
        branch = get_git_branch()

        text = Text()
        text.append("\n项目信息\n", style="bold #7aa2f7 underline")
        text.append(f"Repo: ", style="dim white")
        text.append(f"{repo_url.split('/')[-1].replace('.git', '')}\n", style="bold cyan")

        if branch:
            text.append(f"Branch: ", style="dim white")
            text.append(f"{branch}\n", style="bold cyan")

        text.append(f"模型: ", style="dim white")
        text.append(f"{self.model_name}\n\n", style="bold cyan")

        if modified:
            text.append("GIT 变更记录\n", style="bold #7dcfff underline")
            for status, filename in modified:
                if 'M' in status:
                    icon = "✹"
                    style = "yellow"
                elif 'A' in status or '?' in status:
                    icon = "+"
                    style = "green"
                elif 'D' in status:
                    icon = "-"
                    style = "dim white"
                else:
                    icon = "•"
                    style = "white"
                text.append(f"{icon} {filename[:20]}\n", style=style)
        else:
            text.append("", style="dim green")

        self.update(text)


class RequestIndicator(Static):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_active = False
        self.start_time = None
        self.update_timer = None

    def start_request(self):
        self.is_active = True
        self.start_time = time.time()
        self.remove_class("hidden")
        if self.update_timer:
            self.update_timer.stop()
        self.update_timer = self.set_timer(0.1, self._update_display)

    def stop_request(self):
        self.is_active = False
        self.start_time = None
        self.add_class("hidden")
        if self.update_timer:
            self.update_timer.stop()
            self.update_timer = None

    def _update_display(self):
        if not self.is_active or not self.start_time:
            return
        elapsed = time.time() - self.start_time
        frame = SPINNER_FRAMES[int(elapsed * 10) % len(SPINNER_FRAMES)]
        total_seconds = int(elapsed)
        time_str = f"{total_seconds // 3600:02d}:{(total_seconds % 3600) // 60:02d}:{total_seconds % 60:02d}"
        content = f"[bold cyan]{frame} Processing request... {time_str}[/]"
        self.update(Text.from_markup(content))
        if self.is_active:
            self.update_timer = self.set_timer(0.1, self._update_display)


class StatusBar(Static):
    def __init__(self, model_name="Unknown"):
        super().__init__()
        self.model_name = model_name
        self.state_desc = "Idle"

    def update_state(self, state):
        self.state_desc = state
        self.refresh()

    def render(self):
        shortcuts = []
        shortcuts.append("[dim]Ctrl+C[/]: 终止请求")
        shortcuts.append("[dim]Ctrl+D[/]: 提交多行")
        shortcuts_text = " | ".join(shortcuts)

        if self.state_desc == "Idle":
            return Text.from_markup(f" {shortcuts_text}")

        return Text.from_markup(f" {self.state_desc} | {shortcuts_text}")


class TUIStreamOutput:
    """流式输出适配器 - 直接输出到 Markdown 组件"""

    def __init__(self, main_display: SelectableMarkdownWidget, tool_status: Static, app_instance):
        self.main_display = main_display
        self.tool_status = tool_status
        self.app = app_instance
        self.tool_start_time = None
        self.tool_timer = None
        self.active_tools = {}
        self.current_display_tool = None
        self.last_update_time = 0
        
    @property
    def full_content(self):
        return self.app.conversation_markdown

    @full_content.setter
    def full_content(self, value):
        self.app.conversation_markdown = value

    @staticmethod
    def _get_tool_display_name(tool_name: str, tool_args: dict) -> str:
        display_name = tool_name
        if tool_name == "execute_command":
            cmd = tool_args.get("command", "")
            if cmd:
                short_cmd = cmd[:50] + ("..." if len(cmd) > 50 else "")
                display_name = f"command: {short_cmd}"
        return display_name

    def _update_tool_spinner(self):
        if not self.tool_start_time or not self.current_display_tool:
            return
        elapsed = time.time() - self.tool_start_time
        frame = SPINNER_FRAMES[int(elapsed * 10) % len(SPINNER_FRAMES)]
        m, s = divmod(int(elapsed), 60)
        content = f"[dim bold cyan] {frame} {escape(self.current_display_tool)} {m:02d}:{s:02d}[/]"
        self.tool_status.update(Text.from_markup(content))

    def append_content(self, text: str):
        """追加内容到历史记录并更新显示"""
        self.full_content += text
        self.main_display.update(self.full_content)

    async def stream_response(self, current_state, conversation_state, thread_id="default_session"):
        current_response_text = ""
        current_reasoning_content = ""
        accumulated_ai_message = None
        
        # 记录开始时的内容长度，用于流式更新
        base_content = self.full_content
        
        # 添加 AI 回复头
        base_content += "\n\n**🤖 AI:**\n\n"
        self.full_content = base_content
        self.main_display.update(self.full_content)

        self.last_update_time = 0

        try:
            async for message_chunk, metadata in qoze_code_agent.agent.astream(
                    current_state,
                    stream_mode="messages",
                    config={"recursion_limit": 300, "configurable": {"thread_id": thread_id}}
            ):
                if isinstance(message_chunk, AIMessage):
                    if accumulated_ai_message is None:
                        accumulated_ai_message = message_chunk
                    else:
                        accumulated_ai_message += message_chunk

                if isinstance(message_chunk, ToolMessage):
                    # 工具执行结果
                    if current_response_text or current_reasoning_content:
                        # 先把之前的文本固化
                        formatted_reasoning = f"> {current_reasoning_content}\n" if current_reasoning_content else ""
                        base_content += formatted_reasoning + current_response_text
                        current_response_text = ""
                        current_reasoning_content = ""

                    tool_name = self.active_tools.pop(message_chunk.tool_call_id, None)
                    if not tool_name:
                         tool_name = message_chunk.name if hasattr(message_chunk, "name") else "Tool"
                    
                    if not self.active_tools:
                        if self.tool_timer:
                            self.tool_timer.stop()
                            self.tool_timer = None
                        self.tool_status.update("")
                        self.tool_status.styles.display = "none"
                        self.current_display_tool = None

                    elapsed = time.time() - (self.tool_start_time or time.time())
                    if not self.active_tools:
                        self.tool_start_time = None
                    
                    content_str = str(message_chunk.content)
                    is_error = content_str.startswith("[RUN_FAILED]")
                    status_icon = "✗" if is_error else "✓"
                    
                    # 将工具结果追加到 Markdown
                    tool_md = f"\n\n> 🔨 **{tool_name}** ({elapsed:.2f}s) {status_icon}\n"
                    base_content += tool_md
                    self.full_content = base_content
                    await self.main_display.update(self.full_content)
                    continue

                if accumulated_ai_message and accumulated_ai_message.tool_calls:
                    # 工具调用请求
                    if current_response_text or current_reasoning_content:
                        formatted_reasoning = f"> *{current_reasoning_content}*\n\n" if current_reasoning_content else ""
                        base_content += formatted_reasoning + current_response_text
                        current_response_text = ""
                        current_reasoning_content = ""

                    for tool_call in accumulated_ai_message.tool_calls:
                        t_name = tool_call.get("name", "Unknown Tool")
                        t_id = tool_call.get("id", "unknown_id")
                        t_args = tool_call.get("args", {})
                        display_name = self._get_tool_display_name(t_name, t_args)
                        self.active_tools[t_id] = display_name
                        self.current_display_tool = display_name

                        if not self.tool_timer:
                            self.tool_start_time = time.time()
                            self.tool_status.styles.display = "block"
                            self.tool_timer = self.tool_status.set_interval(0.1, self._update_tool_spinner)
                    
                    # 更新 base_content
                    self.full_content = base_content
                    await self.main_display.update(self.full_content)

                # 处理文本和思考内容
                reasoning = ""
                if hasattr(message_chunk, "additional_kwargs") and message_chunk.additional_kwargs:
                    reasoning = message_chunk.additional_kwargs.get("reasoning_content", "")
                if isinstance(message_chunk.content, list):
                    for content_item in message_chunk.content:
                        if isinstance(content_item, dict) and content_item.get("type") == "reasoning_content":
                            rc = content_item.get("reasoning_content", {})
                            reasoning += rc.get("text", "") if isinstance(rc, dict) else str(rc)
                        if isinstance(content_item, dict) and content_item.get("type") == "thinking":
                            reasoning += content_item.get("thinking", "")

                if reasoning:
                    current_reasoning_content += reasoning

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

                # 实时更新显示
                if current_reasoning_content or current_response_text:
                    now = time.time()
                    if now - self.last_update_time > 0.1:
                        # 构造临时 Markdown
                        temp_md = base_content
                        if current_reasoning_content:
                            temp_md += f"> *{current_reasoning_content}*\n\n"
                        if current_response_text:
                            temp_md += current_response_text
                        
                        self.full_content = temp_md
                        await self.main_display.update(self.full_content)
                        self.last_update_time = now

            # 循环结束，固化最后的内容
            formatted_reasoning = f"> *{current_reasoning_content}*\n\n" if current_reasoning_content else ""
            base_content += formatted_reasoning + current_response_text
            self.full_content = base_content
            await self.main_display.update(self.full_content)

            graph_state = await qoze_code_agent.agent.aget_state(config={"configurable": {"thread_id": thread_id}})
            if graph_state and graph_state.values and "messages" in graph_state.values:
                conversation_state["messages"] = graph_state.values["messages"]

        except asyncio.CancelledError:
            raise
        except Exception as e:
            traceback.print_exc()
            self.full_content += f"\n\n**Error**: {e}\n"
            await self.main_display.update(self.full_content)
        finally:
            if self.tool_timer:
                self.tool_timer.stop()
                self.tool_timer = None
            self.tool_status.update("")
            self.tool_status.styles.display = "none"
            self.active_tools.clear()


class Qoze(App):
    CSS = """
    Screen { background: #1a1b26; color: #a9b1d6; }
    TopBar { dock: top; height: 1; background: #13131c; color: #c0caf5; }

    #main-container { height: 1fr; width: 100%; layout: horizontal; }
    #chat-area { width: 78%; height: 100%; }

    /* 核心显示组件 - Markdown */
    #main-output {
        width: 100%;
        height: 1fr;
        background: #13131c;
        border: none;
        padding: 0 2;
        overflow-y: scroll;
    }
    
    /* 调整 Markdown 内的段落间距 */
    Markdown > P {
        margin: 0 0 1 0;
    }

    #tool-status { width: 100%; height: auto; min-height: 1; background: #13131c; padding: 0 2; display: none; }

    #sidebar { width: 22%; height: 100%; background: #16161e; padding: 1 2; color: #565f89; border-left: solid #2f334d; }
    #bottom-container { height: auto; dock: bottom; background: #13131c; }
    #input-line { height: 3; width: 100%; align-vertical: middle; padding: 0 1; border-top: solid #414868; background: #13131c; }
    .prompt-symbol { color: #bb9af7; text-style: bold; width: 2; content-align: center middle; }

    Input { width: 1fr; background: #13131c; border: none; color: #c0caf5; padding: 0; }
    Input:focus { border: none; }

    TextArea { height: 10; width: 100%; background: #13131c; border: round #808080; color: #c0caf5; padding: 1; }

    .hidden { display: none; }

    #request-indicator { height: 1; width: 100%; background: #13131c; color: #7aa2f7; padding: 0 1; }
    StatusBar { height: 1; width: 100%; background: #13131c; dock: bottom; }

    #command-suggestions {
        display: none;
        background: #1e1e2e;
        border: round #414868;
        max-height: 12;
        width: 70%;
        margin-left: 2;
        margin-bottom: 0;
        padding: 1;
        overflow-y: auto;
    }
    #command-suggestions > .option-list--option { padding: 0 1; }
    #command-suggestions > .option-list--option:hover { background: #414868; }
    """

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Cancel", priority=True),
        Binding("ctrl+d", "submit_multiline", "Submit", priority=True),
        Binding("escape", "cancel_multiline", "Cancel", priority=True),
        Binding("c", "copy_selection", "Copy Selection"),
    ]

    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name
        self.agent_ready = False
        self.multiline_mode = False
        self.thread_id = "default_session"
        self.processing_worker = None
        self.conversation_markdown = "" # 全局对话历史 (Markdown 格式)
        self.skills_tui_handler = SkillsTUIHandler()

    def compose(self) -> ComposeResult:
        yield TopBar()
        with Horizontal(id="main-container"):
            with Vertical(id="chat-area"):
                # 替换为支持选择的 Markdown 组件
                yield SelectableMarkdownWidget(id="main-output")
                yield Static(id="tool-status")
            yield Sidebar(id="sidebar", model_name=self.model_name)
        with Vertical(id="bottom-container"):
            yield OptionList(id="command-suggestions")
            with Horizontal(id="input-line"):
                yield Label("❯", classes="prompt-symbol")
                yield Input(placeholder="Initializing Agent...", id="input-box", disabled=True)
            yield TextArea(id="multi-line-input", classes="hidden")
            yield RequestIndicator(id="request-indicator", classes="hidden")
            yield StatusBar(model_name=self.model_name)

    def on_mount(self):
        self.main_display = self.query_one("#main-output", SelectableMarkdownWidget)
        self.tool_status = self.query_one("#tool-status", Static)
        self.input_box = self.query_one("#input-box", Input)
        self.multi_line_input = self.query_one("#multi-line-input", TextArea)
        self.request_indicator = self.query_one("#request-indicator", RequestIndicator)
        self.status_bar = self.query_one(StatusBar)

        self.tui_stream = TUIStreamOutput(self.main_display, self.tool_status, self)

        self.print_welcome()
        self.run_worker(self.init_agent_worker(), exclusive=True)

    def print_welcome(self):
        # 简化版 Welcome，避免复杂转义字符
        welcome_md = """
**Tips:**
- 输入 `q`, `quit`, `exit` 退出
- 输入 `line` 进入多行编辑模式 (Ctrl+D 提交)
- 使用鼠标选择文本，按 `C` 复制选中文本
- 滚动查看历史记录

---
"""
        self.conversation_markdown = welcome_md
        self.main_display.update(self.conversation_markdown)

    def action_interrupt(self):
        if self.processing_worker and self.processing_worker.is_running:
            self.processing_worker.cancel()
            self.status_bar.update_state("Cancelled")
            self.query_one("#input-line").remove_class("hidden")
            self.input_box.focus()
            self.processing_worker = None
            return
        self.exit()
    
    def action_copy_selection(self):
        """复制选中文本"""
        text = self.main_display.get_selected_text()
        if text:
            try:
                # 尝试使用 clipboard 工具
                import pyperclip
                pyperclip.copy(text)
                self.notify("Copied to clipboard!", title="Success")
            except ImportError:
                self.notify("Install 'pyperclip' to enable copying.", severity="warning", title="Copy Failed")
            except Exception as e:
                self.notify(str(e), severity="error")
        else:
            self.notify("No text selected.", severity="warning")

    async def init_agent_worker(self):
        try:
            llm = model_initializer.initialize_llm(self.model_name)
            qoze_code_agent.llm = llm
            qoze_code_agent.llm_with_tools = llm.bind_tools(qoze_code_agent.tools)
            self.agent_ready = True
            self.input_box.disabled = False
            self.input_box.placeholder = "Type message..."
            self.input_box.focus()
        except Exception as e:
            self.conversation_markdown += f"\n\n**Initialization Failed**: {e}\n"
            await self.main_display.update(self.conversation_markdown)

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
            self.conversation_markdown = ""
            self.thread_id = str(uuid.uuid4())
            qoze_code_agent.conversation_state["messages"] = []
            self.print_welcome()
            return

        if user_input.lower().startswith('skills'):
            success, message = self.skills_tui_handler.handle_skills_command(user_input.split())
            if isinstance(message, Text): message = str(message)
            self.conversation_markdown += f"\n\n**System**: {message}\n"
            await self.main_display.update(self.conversation_markdown)
            return

        if user_input.lower() in ["qoze init", "init"]:
            user_input = init_prompt

        self.request_indicator.start_request()
        self.query_one("#input-line").add_class("hidden")
        self.main_display.focus()

        try:
            # 更新 Markdown 显示用户输入
            self.conversation_markdown += f"\n\n**👤 User**: {user_input}\n"
            await self.main_display.update(self.conversation_markdown)

            image_folder = ".qoze/image"
            human_msg = qoze_code_agent.create_message_with_images(user_input, image_folder)
            qoze_code_agent.conversation_state["messages"].append(human_msg)

            current_state = {
                "messages": [human_msg],
                "llm_calls": qoze_code_agent.conversation_state["llm_calls"]
            }

            await self.tui_stream.stream_response(current_state, qoze_code_agent.conversation_state,
                                                  thread_id=self.thread_id)

        except (KeyboardInterrupt, asyncio.CancelledError):
             self.conversation_markdown += "\n\n**⛔ Interrupted**\n"
             await self.main_display.update(self.conversation_markdown)
        except Exception as e:
            self.conversation_markdown += f"\n\n**Error**: {e}\n"
            await self.main_display.update(self.conversation_markdown)
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
    launcher.ensure_config()
    model = launcher.get_model_choice()
    os.system('cls' if os.name == 'nt' else 'clear')
    if model:
        Qoze(model_name=model).run()


if __name__ == "__main__":
    main()
