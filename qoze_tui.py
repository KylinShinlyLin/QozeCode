#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import platform
import uuid
import sys
import asyncio
import subprocess
import traceback
from datetime import datetime

from textual.app import App, ComposeResult, on
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, RichLog, Static, Label, Markdown as MarkdownWidget, TextArea, OptionList
from textual.widgets.option_list import Option
from textual.events import MouseScrollDown, MouseScrollUp
from textual.binding import Binding
from rich.text import Text
from rich.markup import escape
from rich.panel import Panel
from rich.console import Group
from rich.markdown import Markdown

# Skills TUI Integration
sys.path.append(".")
# Skills TUI Handler Import
sys.path.append(os.path.join(os.path.dirname(__file__), ".qoze"))
from skills.skills_tui_integration import SkillsTUIHandler

skills_tui_handler = SkillsTUIHandler()
# Dynamic Commands Import
sys.path.append(os.path.join(os.path.dirname(__file__), ".qoze"))
from dynamic_commands_patch import get_dynamic_commands, get_skills_commands

from utils.constants import init_prompt

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


class TopBar(Static):
    def on_mount(self):
        self.update_clock()
        self.set_interval(1, self.update_clock)

    def update_clock(self):
        time_str = datetime.now().strftime("%H:%M:%S")
        left = Text(" QozeCode ", style="bold white on #d75f00")
        left.append(" v0.3.2 ", style="bold white on #005faf")
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
        cwd = os.getcwd()
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
        self.view_mode = "Render"  # Render or Source

    def update_state(self, state):
        self.state_desc = state
        self.refresh()

    def update_view_mode(self, mode):
        self.view_mode = mode
        self.refresh()

    def render(self):
        # 构建快捷键提示
        shortcuts = []
        if self.view_mode == "Source":
            shortcuts.append("[bold yellow]Ctrl+R[/]: 切回渲染模式")
            shortcuts.append("[bold green]Ctrl+C[/]: 复制选中")
        else:
            shortcuts.append("[dim]Ctrl+R[/]: 切换选择模式")
            shortcuts.append("[dim]Ctrl+C[/]: 终止请求")

        shortcuts_text = " | ".join(shortcuts)

        # 如果状态是 Idle，只显示快捷键，不显示状态文本
        if self.state_desc == "Idle":
            return Text.from_markup(f" {shortcuts_text}")

        return Text.from_markup(f" {self.state_desc} | {shortcuts_text}")


class TUIStreamOutput:
    """流式输出适配器"""

    def __init__(self, main_log: RichLog, stream_display: MarkdownWidget, tool_status: Static):
        self.main_log = main_log
        self.stream_display = stream_display
        self.tool_status = tool_status
        self.tool_start_time = None
        self.tool_timer = None
        self.active_tools = {}
        self.current_display_tool = None
        self.last_update_time = 0

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

    def flush_to_log(self, text: str, reasoning: str):
        if reasoning:
            self.main_log.write(Text(reasoning, style="italic dim #565f89"))
        if text:
            self.main_log.write(Markdown(text))
        self.main_log.scroll_end(animate=False)
        self.stream_display.update("")
        self.stream_display.styles.display = "none"

    async def stream_response(self, current_state, conversation_state, thread_id="default_session"):
        current_response_text = ""
        current_reasoning_content = ""
        total_response_text = ""
        total_reasoning_content = ""
        accumulated_ai_message = None

        self.stream_display.styles.display = "block"
        self.last_update_time = 0

        try:
            async for message_chunk, metadata in qoze_code_agent.agent.astream(
                    current_state,
                    stream_mode="messages",
                    config={"recursion_limit": 150, "configurable": {"thread_id": thread_id}}
            ):
                try:
                    current_task = asyncio.current_task()
                    if current_task and current_task.cancelled():
                        raise asyncio.CancelledError("Stream cancelled by user")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass

                if isinstance(message_chunk, AIMessage):
                    if accumulated_ai_message is None:
                        accumulated_ai_message = message_chunk
                    else:
                        accumulated_ai_message += message_chunk

                if isinstance(message_chunk, ToolMessage):
                    if current_response_text or current_reasoning_content:
                        self.flush_to_log(current_response_text, current_reasoning_content)
                        current_response_text = ""
                        current_reasoning_content = ""

                    tool_name = self.active_tools.pop(message_chunk.tool_call_id, None)
                    if not tool_name and self.active_tools:
                        if len(self.active_tools) == 1:
                            _id, _name = list(self.active_tools.items())[0]
                            tool_name = _name
                            self.active_tools.clear()
                        else:
                            _id, _name = list(self.active_tools.items())[-1]
                            tool_name = _name
                            del self.active_tools[_id]

                    if not tool_name:
                        tool_name = message_chunk.name if hasattr(message_chunk, "name") else None
                    if not tool_name:
                        tool_name = self.current_display_tool if self.current_display_tool else "Tool"

                    accumulated_ai_message = None

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
                    color = "red" if is_error else "cyan"
                    icon_color = "red" if is_error else "green"
                    final_msg = f"  [dim bold {icon_color}]{status_icon}[/][dim bold {color}] {escape(tool_name)} in {elapsed:.2f}s[/]"
                    self.main_log.write(Text.from_markup(final_msg))
                    continue

                if accumulated_ai_message and accumulated_ai_message.tool_calls:
                    if current_response_text or current_reasoning_content:
                        self.flush_to_log(current_response_text, current_reasoning_content)
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
                    self.stream_display.styles.display = "block"

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
                    total_reasoning_content += reasoning

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

                if current_reasoning_content or current_response_text:
                    now = time.time()
                    if now - self.last_update_time > 0.1:
                        md_content = ""
                        if current_reasoning_content:
                            md_content += current_reasoning_content + ""
                        if current_response_text:
                            md_content += current_response_text
                        try:
                            current_task = asyncio.current_task()
                            if current_task and current_task.cancelled():
                                break
                        except Exception:
                            pass
                        await self.stream_display.update(md_content)
                        self.main_log.scroll_end(animate=False)
                        self.stream_display.scroll_end(animate=False)
                        self.last_update_time = now

            self.flush_to_log(current_response_text, current_reasoning_content)

            graph_state = await qoze_code_agent.agent.aget_state(config={"configurable": {"thread_id": thread_id}})
            if graph_state and graph_state.values and "messages" in graph_state.values:
                conversation_state["messages"] = graph_state.values["messages"]

        except asyncio.CancelledError:
            self.stream_display.styles.display = "none"
            raise
        except Exception as e:
            traceback.print_exc()
            self.main_log.write(Text(f"Stream Error: {e}", style="red"))
            self.stream_display.styles.display = "none"
        finally:
            if total_response_text or total_reasoning_content:
                conversation_state["llm_calls"] += 1
            if self.tool_timer:
                self.tool_timer.stop()
                self.tool_timer = None
            self.tool_status.update("")
            self.tool_status.styles.display = "none"
            self.active_tools.clear()
            self.current_display_tool = None
            self.tool_start_time = None
            self.last_update_time = 0


class Qoze(App):
    CSS = """
    Screen { background: #1a1b26; color: #a9b1d6; }
    TopBar { dock: top; height: 1; background: #13131c; color: #c0caf5; }

    #main-container { height: 1fr; width: 100%; layout: horizontal; }
    #chat-area { width: 78%; height: 100%; }
    
    /* 核心显示组件 */
    #main-output { 
        width: 100%; 
        height: 1fr; 
        background: #13131c; 
        border: none; 
        padding: 0; 
    }
    
    #source-output {
        width: 100%;
        height: 1fr;
        background: #13131c;
        border: none;
        color: #c0caf5;
        padding: 1;
        display: none; /* 默认隐藏 */
    }
    
    #source-output:focus {
        border: solid #7aa2f7; /* 聚焦时显示蓝色边框 */
    }

    #tool-status { width: 100%; height: auto; min-height: 1; background: #13131c; padding: 0 2; display: none; }
    
    #stream-output {
        width: 100%;
        height: auto;
        max-height: 60%;
        background: #13131c;
        padding: 0 2;
        border-top: solid #414868;
        display: none;
        overflow-y: auto;
        scrollbar-visibility: hidden;
    }
    
    #stream-output > BlockQuote {
        border-left: none;
        color: #565f89;
        background: #13131c;
        text-style: italic;
        margin: 0 0 1 0;
        padding: 0 1;
    }

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
        Binding("ctrl+c", "interrupt_or_copy", "Cancel/Copy", priority=True),
        Binding("ctrl+l", "clear_screen", "Clear"),
        Binding("ctrl+d", "submit_multiline", "Submit", priority=True),
        Binding("escape", "cancel_multiline", "Cancel", priority=True),
        Binding("ctrl+r", "toggle_view_mode", "Toggle View", priority=True),
    ]

    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name
        self.agent_ready = False
        self.multiline_mode = False
        self.view_mode = "Render"  # Render | Source
        self.thread_id = "default_session"
        self.processing_worker = None

    def compose(self) -> ComposeResult:
        yield TopBar()
        with Horizontal(id="main-container"):
            with Vertical(id="chat-area"):
                # Render View (默认)
                yield RichLog(id="main-output", markup=True, highlight=True, auto_scroll=True, wrap=True)
                # Source View (用于选择复制，默认隐藏)
                yield TextArea(id="source-output", read_only=True, show_line_numbers=False, language="markdown")

                yield Static(id="tool-status")
                yield MarkdownWidget(id="stream-output")
            yield Sidebar(id="sidebar", model_name=self.model_name)
        with Vertical(id="bottom-container"):
            yield OptionList(id="command-suggestions")
            with Horizontal(id="input-line"):
                yield Label("❯", classes="prompt-symbol")
                yield Input(placeholder="Initializing Agent... (Ctrl+R 切换选择模式)", id="input-box", disabled=True)
            yield TextArea(id="multi-line-input", classes="hidden")
            yield RequestIndicator(id="request-indicator", classes="hidden")
            yield StatusBar(model_name=self.model_name)

    def on_mount(self):
        self.main_log = self.query_one("#main-output", RichLog)
        self.source_output = self.query_one("#source-output", TextArea)
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
        qoze_code_art = """
        ╭────────────────────────────────────────────────────────────────────────────╮
        │   ██████╗  ██████╗ ███████╗███████╗     ██████╗ ██████╗ ██████╗ ███████╗   │
        │   ██╔═══██╗██╔═══██╗╚══███╔╝██╔════╝    ██╔════╝██╔═══██╗██╔══██╗██╔════╝  │
        │   ██║   ██║██║   ██║  ███╔╝ █████╗      ██║     ██║   ██║██║  ██║█████╗    │
        │   ██║▄▄ ██║██║   ██║ ███╔╝  ██╔══╝      ██║     ██║   ██║██║  ██║██╔══╝    │
        │   ╚██████╔╝╚██████╔╝███████╗███████╗    ╚██████╗╚██████╔╝██████╔╝███████╗  │
        │    ╚══▀▀═╝  ╚═════╝ ╚═════╝ ╚══════╝     ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝  │
        ╰────────────────────────────────────────────────────────────────────────────╯
        """
        from rich.align import Align
        tips_content = Group(
            Text(""),
            Text("模型: ", style="bold white").append(Text(f"{self.model_name or 'Unknown'}", style="bold cyan")),
            Text("当前目录: ", style="bold white").append(Text(f"{os.getcwd() or 'Unknown'}", style="bold cyan")),
            Text("使用提示: ", style="bold white"),
            Text("  • 输入 'q'、'quit' 或 'exit' 退出", style="dim bold white"),
            Text("  • 输入 'line' 进入多行编辑模式 (Ctrl+D 提交)", style="dim bold white"),
            Text("  • Ctrl+R 切换选择模式 (支持鼠标选择复制)", style="dim bold white"),
            Text(""),
        )
        self.main_log.write(Align.center(Text(qoze_code_art, style="bold cyan")))
        self.main_log.write(Text(""))
        self.main_log.write(Align.center(Panel(
            tips_content,
            title="[dim white]Tips[/]",
            border_style="bold #414868",
            padding=(0, 1)
        )))

    def action_toggle_view_mode(self):
        """在 Render(RichLog) 和 Source(TextArea) 模式间切换"""
        if self.view_mode == "Render":
            # 切换到 Source Mode
            self.view_mode = "Source"

            # 生成 Source 文本
            full_text = self._generate_source_text()
            self.source_output.text = full_text
            self.source_output.move_cursor(self.source_output.document.end)  # 滚动到底部

            self.main_log.styles.display = "none"
            self.source_output.styles.display = "block"
            self.source_output.focus()

            self.status_bar.update_view_mode("Source")
            self.notify("进入选择模式: 支持鼠标选择，Ctrl+C 复制")

        else:
            # 切换回 Render Mode
            self.view_mode = "Render"

            self.source_output.styles.display = "none"
            self.main_log.styles.display = "block"

            # 恢复焦点到输入框 (除非在多行模式)
            if not self.multiline_mode:
                self.input_box.focus()

            self.status_bar.update_view_mode("Render")

    def _generate_source_text(self):
        """从 conversation_state 重建 Markdown 源码文本"""
        messages = qoze_code_agent.conversation_state.get("messages", [])
        text_parts = []

        # 添加 Header
        text_parts.append("# QozeCode Session History\n")

        for msg in messages:
            if isinstance(msg, HumanMessage):
                content = str(msg.content)
                text_parts.append(f"\n## 🧑 User\n{content}\n")
            elif isinstance(msg, AIMessage):
                content = ""
                # 处理内容 (List or String)
                if isinstance(msg.content, str):
                    content = msg.content
                elif isinstance(msg.content, list):
                    for item in msg.content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            content += item.get("text", "")

                if content:
                    text_parts.append(f"\n## 🤖 Assistant\n{content}\n")

                # 处理 Tool Calls (虽然通常不需要显示细节，但为了完整性)
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        text_parts.append(f"\n> 🛠️ Call Tool: `{tc.get('name')}`\n")

            elif isinstance(msg, ToolMessage):
                content = str(msg.content)
                # 简化 Tool 输出显示，避免太长
                if len(content) > 500:
                    preview = content[:200] + "\n... (content truncated) ...\n" + content[-200:]
                    text_parts.append(f"\n> 📦 Tool Output:\n```\n{preview}\n```\n")
                else:
                    text_parts.append(f"\n> 📦 Tool Output:\n```\n{content}\n```\n")

        return "".join(text_parts)

    def action_interrupt_or_copy(self):
        """Ctrl+C 处理逻辑：在 Source 模式且有选中时复制，否则中断"""
        # 1. 如果在 Source 模式且有选中内容 -> 复制
        if self.view_mode == "Source" and self.focused == self.source_output:
            selected_text = self.source_output.selected_text
            if selected_text:
                if self.copy_to_clipboard(selected_text):
                    self.notify(f"✅ 已复制 {len(selected_text)} 字符")
                else:
                    self.notify("❌ 复制失败")
                return

        # 2. 否则 -> 中断/取消
        self.action_interrupt()

    def action_interrupt(self):
        if self.processing_worker and self.processing_worker.is_running:
            self.processing_worker.cancel()
            self.status_bar.update_state("Cancelled")
            self.query_one("#input-line").remove_class("hidden")
            self.input_box.focus()
            self.processing_worker = None
            return
        self.exit()

    def copy_to_clipboard(self, text: str) -> bool:
        """跨平台复制实现"""
        try:
            if platform.system() == "Darwin":
                process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
                process.communicate(text.encode('utf-8'))
                return process.returncode == 0
            elif platform.system() == "Linux":
                try:
                    process = subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE)
                    process.communicate(text.encode('utf-8'))
                    return process.returncode == 0
                except FileNotFoundError:
                    process = subprocess.Popen(['xsel', '-ib'], stdin=subprocess.PIPE)
                    process.communicate(text.encode('utf-8'))
                    return process.returncode == 0
            else:  # Windows
                import pyperclip
                pyperclip.copy(text)
                return True
        except Exception as e:
            self.notify(f"Copy Error: {e}")
            return False

    async def init_agent_worker(self):
        try:
            llm = model_initializer.initialize_llm(self.model_name)
            qoze_code_agent.llm = llm
            qoze_code_agent.llm_with_tools = llm.bind_tools(qoze_code_agent.tools)
            self.agent_ready = True
            self.input_box.disabled = False
            self.input_box.placeholder = "Type message... (Ctrl+R 切换选择模式)"
            self.input_box.focus()
        except Exception as e:
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
            self.main_log.clear()
            self.thread_id = str(uuid.uuid4())
            qoze_code_agent.conversation_state["messages"] = []
            self.print_welcome()
            return

        if user_input.lower().startswith('skills'):
            success, message = skills_tui_handler.handle_skills_command(user_input.split())
            self.main_log.write(message if success else Text(f"❌ {message}", style="red"))
            return

        if user_input.lower() in ["qoze init", "init"]:
            user_input = init_prompt

        self.request_indicator.start_request()
        self.query_one("#input-line").add_class("hidden")
        self.main_log.focus()
        self.status_bar.update_state("Thinking...")

        try:
            self.main_log.write(Text(f"\n❯ {user_input}", style="bold #bb9af7"))

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

        # 简单补全逻辑
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
                    # 修复：直接执行逻辑，避免模拟 Event 对象参数不匹配
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
        if self.view_mode == "Render" and self.main_log.styles.display != "none":
            self.main_log.scroll_relative(y=1, animate=False)

    def on_mouse_scroll_up(self, event):
        if self.view_mode == "Render" and self.main_log.styles.display != "none":
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
    launcher.ensure_config()
    model = launcher.get_model_choice()
    os.system('cls' if os.name == 'nt' else 'clear')
    if model:
        Qoze(model_name=model).run()


if __name__ == "__main__":
    main()
