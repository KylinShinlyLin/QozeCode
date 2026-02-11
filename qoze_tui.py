#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import logging
import asyncio
import os
import sys
import time
import traceback
import uuid
from datetime import datetime

from rich.console import Group
from rich.markdown import Markdown
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel
from rich.text import Text
from textual.app import App, ComposeResult, on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, RichLog, Static, Label, Markdown as MarkdownWidget, TextArea, OptionList
from textual.widgets.option_list import Option

# Skills TUI Integration

# Configure logging for debugging
log_file = os.path.join(os.path.dirname(__file__), '.qoze', 'debug.log')
# Ensure log directory exists
try:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
except Exception:
    pass  # Fail silently if permission issues, logging might fail later but better than crashing here

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


# --- Async Git Helpers ---
async def run_async_cmd(args, timeout=2.0):
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode('utf-8', errors='ignore').strip()
    except Exception:
        return ""


async def get_git_info():
    url = await run_async_cmd(['git', 'remote', 'get-url', 'origin'])
    return url if url else "local"


async def get_git_branch():
    branch = await run_async_cmd(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    return branch if branch else None


async def get_modified_files():
    status = await run_async_cmd(['git', 'status', '-s'])
    if not status:
        return []
    files = []
    for line in status.split('\n'):
        parts = line.split()
        if len(parts) >= 2:
            files.append((parts[0], parts[-1]))
    return files


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

    async def on_mount(self):
        # Initial update
        await self.update_info()
        # Scheduled update (Textual handles async callbacks correctly)
        self.set_interval(5, self.update_info)

    async def update_info(self):
        cwd = os.getcwd()
        repo_url = await get_git_info()
        modified = await get_modified_files()
        branch = await get_git_branch()

        text = Text()
        text.append("\n项目信息\n", style="bold #7aa2f7 underline")
        text.append(f"Repo: ", style="dim white")
        text.append(f"{repo_url.split('/')[-1].replace('.git', '')}\n", style="bold cyan")

        if branch:
            text.append(f"Branch: ", style="dim white")
            text.append(f"{branch}\n", style="bold cyan")

        text.append(f"模型: ", style="dim white")
        text.append(f"{self.model_name}\n", style="bold cyan")
        text.append(f"当前目录: ", style="dim white")
        text.append(f"{os.getcwd()}\n\n", style="bold cyan")

        # 实时检测图片数量
        image_folder = ".qoze/image"
        img_count = 0
        if os.path.exists(image_folder):
            try:
                img_files = qoze_code_agent.get_image_files(image_folder)
                img_count = len(img_files)
            except Exception:
                pass

        if img_count > 0:
            sent_imgs = qoze_code_agent.conversation_state.get("sent_images", {})
            new_count = 0
            if os.path.exists(image_folder):
                try:
                    for f in qoze_code_agent.get_image_files(image_folder):
                        mtime = os.path.getmtime(f)
                        if f not in sent_imgs or sent_imgs[f] != mtime:
                            new_count += 1
                except:
                    new_count = img_count
            text.append("图片上下文: ", style="dim white")
            if new_count > 0:
                text.append(f"{img_count} 张 ({new_count} 新)", style="bold yellow")
            else:
                text.append(f"{img_count} 张 (已发送)", style="dim green")

        if modified:
            text.append("\nGIT 变更记录\n", style="bold #7dcfff underline")
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
        shortcuts_text = " | ".join(shortcuts)

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
                short_cmd = cmd[:120] + ("..." if len(cmd) > 120 else "")
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
            reasoning_clean = reasoning.strip()
            content = Text(reasoning_clean, style="italic #565f89")
            self.main_log.write(Padding(content, (0, 0, 1, 0)))

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
                    config={"recursion_limit": 300, "configurable": {"thread_id": thread_id}}
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
                    # FIX: Ensure content is not None to prevent concatenation errors
                    if message_chunk.content is None:
                        message_chunk.content = ""
                    if accumulated_ai_message is None:
                        accumulated_ai_message = message_chunk
                    else:
                        accumulated_ai_message += message_chunk

                if isinstance(message_chunk, ToolMessage):
                    # Flush pending text before showing tool result
                    if current_response_text or current_reasoning_content:
                        self.flush_to_log(current_response_text, current_reasoning_content)
                        current_response_text = ""
                        current_reasoning_content = ""

                    tool_name = self.active_tools.pop(message_chunk.tool_call_id, None)
                    if not tool_name and self.active_tools:
                        # Fallback logic to find corresponding tool
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
                    is_error = content_str.startswith("[RUN_FAILED]") or "❌" in content_str
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

        # State is managed by MemorySaver

        except asyncio.CancelledError:
            self.stream_display.styles.display = "none"
            raise
        except Exception as e:
            traceback.print_exc()
            error_msg = str(e)
            if "429" in error_msg or "overloaded" in error_msg.lower():
                suggestion = "⚠️ 服务端负载过高，请稍后重试或切换其他模型。"
            else:
                suggestion = ""
            self.main_log.write(Text(f"Stream Error: {e}{suggestion}", style="red"))
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

    #main-output {
        width: 100%;
        height: 1fr;
        background: #13131c;
        border: none;
        padding: 1 2;
    }

    #source-output {
        width: 100%;
        height: 1fr;
        background: #13131c;
        border: none;
        color: #c0caf5;
        padding: 1;
        display: none;
    }

    #tool-status { width: 100%; height: auto; min-height: 1; background: #13131c; padding: 0 2; display: none; }

    #stream-output { color: #565f89;
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

    /* --- Markdown Styles --- */
    MarkdownH1 { color: #7aa2f7; text-style: bold; border-bottom: wide #7aa2f7; }
    MarkdownH2 { color: #7dcfff; text-style: bold; border-bottom: wide #7dcfff; }
    MarkdownH3 { color: #2ac3de; text-style: bold; }
    MarkdownH4 { color: #9ece6a; text-style: bold; }
    MarkdownH5 { color: #e0af68; text-style: bold; }
    MarkdownH6 { color: #ff9e64; text-style: bold; }
    MarkdownCode { color: #ff9e64; background: #24283b; }
    Markdown > BlockQuote { color: #565f89; border-left: solid #565f89; }
    /* ----------------------- */
        """

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Cancel", priority=True),
        Binding("ctrl+d", "submit_multiline", "Submit", priority=True),
        Binding("escape", "cancel_multiline", "Cancel", priority=True),
    ]

    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name
        self.agent_ready = False
        self.multiline_mode = False
        self.thread_id = "default_session"
        self.processing_worker = None

    def compose(self) -> ComposeResult:
        yield TopBar()
        with Horizontal(id="main-container"):
            with Vertical(id="chat-area"):
                yield RichLog(id="main-output", markup=True, highlight=True, auto_scroll=True, wrap=True)
                yield Static(id="tool-status")
                yield MarkdownWidget(id="stream-output")
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
        self.main_log = self.query_one("#main-output", RichLog)
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
            Text("  • 输入 'clean' 清空当前会话", style="dim bold white"),
            Text("  • 输入 'q'、'quit' 或 'exit' 退出", style="dim bold white"),
            Text("  • 输入 'line' 进入多行编辑模式 (Ctrl+D 提交)", style="dim bold white"),
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
            llm = model_initializer.initialize_llm(self.model_name)
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
            # Memory is automatically reset by changing thread_id
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

            # 只传递当前新消息，LangGraph 会根据 thread_id 自动从 MemorySaver 加载历史
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
    model = launcher.get_model_choice()

    if not model:
        return

    # 修复 TUI 错乱: 将共享 Console 的输出重定向到空设备
    # 这样可以防止工具直接使用 print/console.print 破坏界面
    # 保持对文件的引用，防止被 GC 关闭
    null_file = open(os.devnull, "w")
    shared_console.console.file = null_file

    # 清屏
    os.system("cls" if os.name == "nt" else "clear")

    Qoze(model_name=model).run()


if __name__ == "__main__":
    main()
