#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import tempfile
import time

import constant
from utils.constants import init_prompt

os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

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
from skills_tui_integration import SkillsTUIHandler

skills_tui_handler = SkillsTUIHandler()
# Add current directory to path
sys.path.append(os.getcwd())

COMMANDS = [
    ("/clear", "清理会话上下文"),
    ("/line", "进入多行编辑模式"),
    ("/qoze init", "初始化项目指引"),
    ("/skills", "显示技能系统帮助"),
    ("/skills list", "列出所有可用技能"),
    ("/skills status", "显示技能系统状态"),
    ("/skills enable", "启用指定技能"),
    ("/skills disable", "禁用指定技能"),
    ("/quit", "退出程序"),
    # ("/help", "显示帮助信息"),
]

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
        repo_url = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], text=True,
                                           stderr=subprocess.DEVNULL).strip()
        return repo_url
    except:
        return "local"


def format_repo_path(repo):
    """格式化仓库路径显示"""
    if repo == "local":
        return repo

    # 尝试提取仓库名
    if repo.endswith('.git'):
        repo = repo[:-4]

    if 'github.com' in repo:
        parts = repo.split('/')
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"

    return repo


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
    """自定义顶部栏"""

    def on_mount(self):
        self.update_clock()
        self.set_interval(1, self.update_clock)

    def update_clock(self):
        time_str = datetime.now().strftime("%H:%M:%S")
        left = Text(" QozeCode ", style="bold white on #d75f00")
        left.append(" v0.3.1 ", style="bold white on #005faf")
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

        # Git Status
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
    """请求状态指示器 - 显示动画和持续时间"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_active = False
        self.start_time = None
        self.update_timer = None

    def start_request(self):
        """开始请求动画"""
        self.is_active = True
        self.start_time = time.time()
        self.remove_class("hidden")
        # 启动定时更新
        if self.update_timer:
            self.update_timer.stop()
        self.update_timer = self.set_timer(0.1, self._update_display)

    def stop_request(self):
        """停止请求动画"""
        self.is_active = False
        self.start_time = None
        self.add_class("hidden")
        if self.update_timer:
            self.update_timer.stop()
            self.update_timer = None

    def _update_display(self):
        """更新显示内容"""
        if not self.is_active or not self.start_time:
            return

        elapsed = time.time() - self.start_time
        frame = SPINNER_FRAMES[int(elapsed * 10) % len(SPINNER_FRAMES)]
        # 格式化持续时间 (HH:MM:SS)
        total_seconds = int(elapsed)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        content = f"[bold cyan]{frame} Processing request... {time_str}[/]"
        self.update(Text.from_markup(content))
        # 如果仍在活动状态，设置下一次更新
        if self.is_active:
            self.update_timer = self.set_timer(0.1, self._update_display)


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
        return Text(" ctrl+c 可以终止当前请求", style="dim")


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
        self.last_update_time = 0

    @staticmethod
    def _get_tool_display_name(tool_name: str, tool_args: dict) -> str:
        """根据工具名称和参数，生成用户友好的显示名称"""
        display_name = tool_name

        # 针对 execute_command 的特殊处理
        if tool_name == "execute_command":
            cmd = tool_args.get("command", "")
            if cmd:
                # 截取前 60 个字符，如果超长则添加 ...
                short_cmd = cmd[:50] + ("..." if len(cmd) > 50 else "")
                display_name = f"command: {short_cmd}"

        return display_name

    def _update_tool_spinner(self):
        if not self.tool_start_time or not self.current_display_tool:
            return

        elapsed = time.time() - self.tool_start_time
        frame = SPINNER_FRAMES[int(elapsed * 10) % len(SPINNER_FRAMES)]

        # 格式化时间
        m, s = divmod(int(elapsed), 60)
        time_str = f"{m:02d}:{s:02d}"

        content = f"[dim bold cyan] {frame} {escape(self.current_display_tool)} {time_str}[/]"
        self.tool_status.update(Text.from_markup(content))

    def flush_to_log(self, text: str, reasoning: str):
        """将当前流式缓冲区的内容固化到日志中，并清空流式显示"""
        if reasoning:
            self.main_log.write(Text(reasoning, style="italic dim #565f89"))
        if text:
            self.main_log.write(Markdown(text))

        # 确保滚动到底部
        self.main_log.scroll_end(animate=False)
        self.stream_display.update("")
        self.stream_display.styles.display = "none"

    async def stream_response(self, current_state, conversation_state, thread_id="default_session"):
        """核心流式处理逻辑"""
        # 用于显示的当前片段 buffer
        current_response_text = ""
        current_reasoning_content = ""

        # 用于 State 记录的完整累积
        total_response_text = ""
        total_reasoning_content = ""

        # 新增：用于累积 AI 消息以解析完整的 tool calls
        accumulated_ai_message = None

        # 激活流式显示区域
        self.stream_display.styles.display = "block"

        # 重置更新时间
        self.last_update_time = 0

        try:
            async for message_chunk, metadata in qoze_code_agent.agent.astream(
                    current_state,
                    stream_mode="messages",
                    config={"recursion_limit": 150, "configurable": {"thread_id": thread_id}}
            ):
                # 检查流式响应是否被用户取消
                try:
                    current_task = asyncio.current_task()
                    if current_task and current_task.cancelled():
                        raise asyncio.CancelledError("Stream cancelled by user")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass  # 忽略检查异常

                # 0. 累积 AI 消息 (用于获取完整的 tool_calls 参数)
                if isinstance(message_chunk, AIMessage):
                    if accumulated_ai_message is None:
                        accumulated_ai_message = message_chunk
                    else:
                        accumulated_ai_message += message_chunk

                # 1. 处理 ToolMessage (工具执行结果)
                if isinstance(message_chunk, ToolMessage):
                    # 遇到工具输出，先固化之前的 AI 文本
                    if current_response_text or current_reasoning_content:
                        self.flush_to_log(current_response_text, current_reasoning_content)
                        current_response_text = ""
                        current_reasoning_content = ""

                    # 尝试通过 tool_call_id 获取名称
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

                # 2. 处理 Tool Calls
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

                # 3. 处理 Reasoning/Thinking
                reasoning = ""
                if hasattr(message_chunk, "additional_kwargs") and message_chunk.additional_kwargs:
                    reasoning = message_chunk.additional_kwargs.get("reasoning_content", "")
                if isinstance(message_chunk.content, list):
                    for content_item in message_chunk.content:
                        if isinstance(content_item, dict) and content_item.get("type") == "reasoning_content":
                            reasoning_content = content_item.get("reasoning_content", {})
                            reasoning += reasoning_content.get("text", "") if isinstance(reasoning_content,
                                                                                         dict) else str(
                                reasoning_content)
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

                # 5. 更新流式显示
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

            # 循环结束后，固化最后的内容
            self.flush_to_log(current_response_text, current_reasoning_content)

            # 同步 Graph 内部状态到本地历史，确保包含完整的 Tool 调用链路
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

    /* 聊天区域布局调整 */
    #chat-area { width: 78%; height: 100%; }
    #main-output { width: 100%; height: 1fr; background: #13131c; border: none; padding: 0;  text-align: left; }
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
        scrollbar-visibility: hidden;   /* 隐藏滚动条渲染 */
    }

    /* 自定义 Markdown 样式以匹配主题 */
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

    /* 多行输入框样式 */
    TextArea {
        height: 10;
        width: 100%;
        background: #13131c;
        border: round #808080;
        color: #c0caf5;
        padding: 1;
    }

    .hidden {
        display: none;
    }


    /* 请求指示器样式 */
    #request-indicator {
        height: 1;
        width: 100%;
        background: #13131c;
        color: #7aa2f7;
        padding: 0 1;

    }
        StatusBar { height: 1; width: 100%; background: #13131c; dock: bottom; }
    LoadingIndicator { height: 100%; content-align: center middle; color: cyan; }

    .hidden {
        display: none;
    }

    #command-suggestions {
        display: none;
        background: #1e1e2e;
        border: solid #414868;
        max-height: 8;
        width: 60%;
        margin-left: 2;
        margin-bottom: 0;
    }"""

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Cancel/Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
        # 使用 priority=True 确保在组件之前处理
        Binding("ctrl+d", "submit_multiline", "Submit (Multi-line)", priority=True),
        Binding("escape", "cancel_multiline", "Cancel (Multi-line)", priority=True),
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
            # 使用 Vertical 容器包含历史记录和流式输出
            with Vertical(id="chat-area"):
                yield RichLog(id="main-output", markup=True, highlight=True, auto_scroll=True, wrap=True)
                yield Static(id="tool-status")
                # 使用 Textual Markdown Widget 替代 Static
                yield MarkdownWidget(id="stream-output")
            yield Sidebar(id="sidebar", model_name=self.model_name)
        with Vertical(id="bottom-container"):
            yield OptionList(id="command-suggestions")
            # todo 这里增加一个显示 状态的 运行
            with Horizontal(id="input-line"):
                yield Label("❯", classes="prompt-symbol")
                yield Input(placeholder="Initializing Agent...", id="input-box", disabled=True)
            # 添加多行输入组件，初始状态隐藏
            yield TextArea(id="multi-line-input", classes="hidden")
            yield RequestIndicator(id="request-indicator", classes="hidden")
            yield StatusBar(model_name=self.model_name)

    @on(Input.Changed, "#input-box")
    def on_input_changed(self, event: Input.Changed):
        value = event.value
        suggestions = self.query_one("#command-suggestions", OptionList)

        # 支持 / 命令和 skills 命令
        show_suggestions = False
        filtered = []

        if value.startswith("/"):
            search_term = value.lower()
            # 过滤匹配的命令
            filtered = [
                Option(f"{cmd} - {desc}", id=cmd[1:])  # 移除 / 前缀用于ID
                for cmd, desc in COMMANDS
                if cmd.lower().startswith(search_term)
            ]
            show_suggestions = len(filtered) > 0

        elif value.lower().startswith("skills"):
            # Skills 命令自动补全
            skills_commands = [
                ("skills", "显示技能系统帮助"),
                ("skills list", "列出所有可用技能"),
                ("skills list --active", "列出启用的技能"),
                ("skills status", "显示技能系统状态"),
                ("skills enable <name>", "启用指定技能"),
                ("skills disable <name>", "禁用指定技能"),
                ("skills refresh", "刷新技能缓存"),
                ("skills create", "创建新技能"),
                ("skills help", "显示技能命令帮助"),
            ]

            search_term = value.lower()
            filtered = [
                Option(f"{cmd} - {desc}", id=cmd)
                for cmd, desc in skills_commands
                if cmd.lower().startswith(search_term)
            ]
            show_suggestions = len(filtered) > 0

        if show_suggestions and filtered:
            suggestions.clear_options()
            suggestions.add_options(filtered)
            suggestions.styles.display = "block"
            suggestions.highlighted = 0
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

    def on_key(self, event) -> None:
        suggestions = self.query_one("#command-suggestions", OptionList)
        if suggestions.styles.display != "none":
            if event.key == "up":
                suggestions.action_cursor_up()
                event.prevent_default()
            elif event.key == "down":
                suggestions.action_cursor_down()
                event.prevent_default()
            elif event.key == "escape":
                suggestions.styles.display = "none"
                event.prevent_default()
                event.stop()
            elif event.key == "enter":
                if suggestions.highlighted is not None:
                    option = suggestions.get_option_at_index(suggestions.highlighted)
                    cmd = str(option.id)
                    suggestions.styles.display = "none"
                    self.input_box.value = ""
                    event.prevent_default()
                    event.stop()
                    # 直接执行命令
                    self.processing_worker = self.run_worker(self.process_user_input(cmd), exclusive=True)

    def on_mouse_scroll_down(self, event: MouseScrollDown) -> None:
        """处理鼠标向下滚动事件"""
        # 确保main_log获得焦点并进行滚动
        if hasattr(self, 'main_log') and self.main_log:
            self.main_log.scroll_relative(y=-3, animate=True, duration=0.1)
            event.prevent_default()

    def on_mouse_scroll_up(self, event: MouseScrollUp) -> None:
        """处理鼠标向上滚动事件"""
        if hasattr(self, 'main_log') and self.main_log:
            self.main_log.scroll_relative(y=3, animate=True, duration=0.1)
            event.prevent_default()

    def on_mount(self):
        self.main_log = self.query_one("#main-output", RichLog)
        self.tool_status = self.query_one("#tool-status", Static)
        self.stream_output = self.query_one("#stream-output", MarkdownWidget)
        self.input_box = self.query_one("#input-box", Input)
        self.multi_line_input = self.query_one("#multi-line-input", TextArea)
        self.request_indicator = self.query_one("#request-indicator", RequestIndicator)
        self.status_bar = self.query_one(StatusBar)

        # 为主输出区域启用滚动功能
        self.main_log.can_focus = False
        self.main_log.auto_scroll = True

        # 初始化流式输出适配器，传入 main_log 和 stream_output
        self.tui_stream = TUIStreamOutput(self.main_log, self.stream_output, self.tool_status)

        # 打印欢迎信息
        self.print_welcome()

        # 异步初始化 Agent
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

        # 创建信息网格

        from rich.align import Align

        # 使用提示面板
        tips_content = Group(
            Text(""),
            Text("模型: ", style="bold white").append(Text(f"{self.model_name or 'Unknown'}", style="bold cyan")),
            Text("当前目录: ", style="bold white").append(Text(f"{os.getcwd() or 'Unknown'}", style="bold cyan")),
            Text("使用提示: ", style="bold white"),
            Text("  • 输入 'q'、'quit' 或 'exit' 退出", style="dim bold white"),
            Text("  • 输入 'line' 进入多行编辑模式 (Ctrl+D 提交)", style="dim bold white"),
            Text("  • ! 开头的内容会直接按命令执行 例如：!ls", style="dim bold white"),
            Text("  • 输入 'clear' 清理整改会话上下文", style="dim bold white"),
            Text("  • Ctrl+D 可以强制终止正在运行的请求", style="dim bold white"),
            Text(""),
        )

        # 输出所有内容
        self.main_log.write(Align.center(Text(qoze_code_art, style="bold cyan")))
        self.main_log.write(Text(""))
        self.main_log.write(Align.center(Panel(
            tips_content,
            title="[dim white]Tips[/]",
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
            self.input_box.placeholder = "Type message...（输入 'line' 进入多行编辑）"
            self.input_box.focus()

        except Exception as e:
            self.main_log.write(Text(f"Initialization Failed: {e}", style="red"))
            self.main_log.write(Text(traceback.format_exc(), style="red"))

    async def process_user_input(self, user_input):
        """处理用户输入的核心逻辑"""
        if not user_input.strip():
            return

        if user_input.startswith("/"):
            user_input = user_input[1:]

        # 1. 优先处理退出命令
        if user_input.lower() in ["quit", "exit", "q"]:
            self.exit()
            return

        # 2. 处理特殊的本地命令 (不涉及 AI，不显示 "Thinking")
        if user_input.lower() == "line":
            self.main_log.write(Text("💡 进入多行编辑模式 (Ctrl+D 提交, Escape 退出)", style="dim"))
            self.multiline_mode = True
            self.query_one("#input-line").add_class("hidden")
            self.multi_line_input.remove_class("hidden")
            self.multi_line_input.focus()
            self.status_bar.update_state("Multi-line Mode (Ctrl+D to submit)")
            return

        if user_input.lower() == "clear":
            self.main_log.clear()
            import uuid
            self.thread_id = str(uuid.uuid4())
            qoze_code_agent.conversation_state["messages"] = []
            self.print_welcome()
            return

        # 处理 skills 命令
        if user_input.lower().startswith('skills'):
            try:
                command_parts = user_input.split()
                success, message = skills_tui_handler.handle_skills_command(command_parts)
                if success:
                    self.main_log.write(message)
                else:
                    self.main_log.write(Text(f"❌ {message}", style="red"))
                return
            except Exception as e:
                self.main_log.write(Text(f"❌ Error handling skills command: {str(e)}", style="red"))
                return

        # 处理项目初始化命令
        if user_input.lower() in ["qoze init", "init"]:
            user_input = init_prompt

        # 3. 启动请求指示器并隐藏输入框
        self.request_indicator.start_request()
        self.query_one("#input-line").add_class("hidden")
        self.main_log.focus()  # 确保主日志区域获得焦点以支持滚动
        self.status_bar.update_state("Thinking... (Ctrl+C to Cancel)")

        try:
            # 显示用户输入
            self.main_log.write(Text(f"\n❯ {user_input}", style="bold #bb9af7"))

            # 4. 准备消息与 AI 处理
            image_folder = ".qoze/image"
            human_msg = qoze_code_agent.create_message_with_images(user_input, image_folder)

            # 更新对话状态
            # 将新消息添加到本地历史记录
            qoze_code_agent.conversation_state["messages"].append(human_msg)

            # 构造传递给 Graph 的状态（只包含新消息，Graph 会根据 thread_id 自动合并历史）
            current_state = {
                "messages": [human_msg],
                "llm_calls": qoze_code_agent.conversation_state["llm_calls"]
            }
            # 先加入历史记录（如果取消需要移除）
            # Added to graph via stream_response

            # 流式获取回复
            await self.tui_stream.stream_response(
                current_state,
                qoze_code_agent.conversation_state,
                thread_id=self.thread_id
            )

        except KeyboardInterrupt:
            self.main_log.write(Text("⛔ 用户中断请求 (Ctrl+C)", style="bold red"))
            if qoze_code_agent.conversation_state["messages"]:
                qoze_code_agent.conversation_state["messages"].pop()
            self.input_box.value = user_input
            raise

        except asyncio.CancelledError:
            self.main_log.write(Text("⛔ 请求已被主动取消", style="bold red"))
            if qoze_code_agent.conversation_state["messages"]:
                qoze_code_agent.conversation_state["messages"].pop()
            self.input_box.value = user_input

        except Exception as e:
            self.main_log.write(Text(f"Error processing input: {e}", style="red"))
            self.main_log.write(Text(traceback.format_exc(), style="red"))

        finally:
            # 4. 停止请求指示器并恢复输入框显示
            self.request_indicator.stop_request()
            self.status_bar.update_state("Idle")
            self.query_one("#input-line").remove_class("hidden")
            self.input_box.focus()
            self.processing_worker = None

    def action_interrupt(self):
        """处理中断/退出逻辑"""
        # 如果有正在进行的 Worker，则取消它
        if self.processing_worker and self.processing_worker.is_running:
            self.processing_worker.cancel()
            # 强制停止并重置状态
            self.status_bar.update_state("Cancelled")
            self.query_one("#input-line").remove_class("hidden")
            self.input_box.focus()
            self.processing_worker = None
            return

        # 否则，执行正常的退出
        self.exit()

    @on(Input.Submitted)
    def handle_input(self, event: Input.Submitted):
        if not self.agent_ready:
            return

        user_input = event.value
        self.input_box.value = ""
        self.processing_worker = self.run_worker(self.process_user_input(user_input), exclusive=True)

    async def action_submit_multiline(self):
        """提交多行输入"""
        if not self.multiline_mode:
            return

        # 获取内容
        user_input = self.multi_line_input.text

        # 退出多行模式
        self.multiline_mode = False
        self.processing_worker = None
        self.multi_line_input.add_class("hidden")
        self.multi_line_input.text = ""  # 清空
        self.query_one("#input-line").remove_class("hidden")
        self.input_box.focus()

        # 处理输入
        if user_input.strip():
            self.processing_worker = self.run_worker(self.process_user_input(user_input), exclusive=True)
        else:
            self.status_bar.update_state("Idle")

    def action_cancel_multiline(self):
        """取消多行输入"""
        if not self.multiline_mode:
            return

        self.multiline_mode = False
        self.processing_worker = None
        self.multi_line_input.add_class("hidden")
        self.multi_line_input.text = ""  # 清空
        self.query_one("#input-line").remove_class("hidden")
        self.input_box.focus()

        self.status_bar.update_state("Idle")
        self.main_log.write(Text("💡 已退出多行编辑模式", style="dim"))


def main():
    # 1. 确保配置存在
    launcher.ensure_config()
    # 2. 获取模型选择
    model = launcher.get_model_choice()
    # 清理 console
    os.system('cls' if os.name == 'nt' else 'clear')
    if model is None:
        return
    # 3. 启动 TUI App
    app = Qoze(model_name=model)
    app.run()


if __name__ == "__main__":
    main()
