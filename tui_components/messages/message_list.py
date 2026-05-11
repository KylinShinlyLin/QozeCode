# tui_components/messages/message_list.py
from textual.containers import ScrollableContainer
from textual.widgets import Static
import uuid
import time
import sys
import os
from datetime import datetime

from .types import UserMessage
from .user_widget import UserMessageWidget
from .bot_widget import BotMessageWidget
from .subagent_widget import SubagentWidget
from .stream_handler import MessageStreamHandler

# 日志文件路径
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".qoze", "stream_debug.log")

def _log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] [MSG_LIST] {msg}\n"
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        print(f"[LOG ERROR] {e}", file=sys.stderr)


class ErrorMessageWidget(Static):
    """流式异常展示组件 - 在 chat-area 中醒目显示错误信息"""

    DEFAULT_CSS = """
    ErrorMessageWidget {
        width: 100%;
        height: auto;
        margin: 1 0;
        padding: 1 2;
        color: #f7768e;
        background: #1a1a2e;
        border: solid #f7768e;
        content-align: left top;
    }
    """

    def __init__(self, error_summary: str, error_detail: str = "", **kwargs):
        # 关闭 Rich markup，避免 error_summary 中的 [...] 被误解析
        kwargs.setdefault("markup", False)
        super().__init__(**kwargs)
        lines = [
            "❌ 请求失败",
            error_summary,
        ]
        if error_detail:
            lines.append("")
            lines.append(error_detail)
        self.update("\n".join(lines))


class ToolResultWidget(Static):
    """工具执行结果组件 - 参考配色：成功图标green/文本cyan，失败图标red/文本red"""

    DEFAULT_CSS = """
    ToolResultWidget {
        width: 100%;
        height: auto;
        min-height: 1;
        margin: 0;
        padding: 0 1;
        content-align: left middle;
    }
    ToolResultWidget.success {
        color: #7aa2f7;
    }
    ToolResultWidget.success .icon {
        color: #9ece6a;
    }
    ToolResultWidget.error {
        color: #f7768e;
    }
    ToolResultWidget.error .icon {
        color: #f7768e;
    }
    """

    def __init__(self, display_text: str, is_error: bool = False, elapsed_time: float = 0.0, **kwargs):
        super().__init__(**kwargs)
        _log(f"[ToolResultWidget] init: display_text='{display_text}', is_error={is_error}, elapsed={elapsed_time}")

        # 替换 run: 为 command:
        display_text = display_text.replace("run:", "command:", 1)
        # 转义 Rich markup 特殊字符，避免用户内容中的方括号被误解析
        display_text = display_text.replace("[", "\[").replace("]", "\]")

        elapsed_str = f" in {elapsed_time:.2f}s" if elapsed_time > 0 else ""

        # 使用 Rich markup 实现图标和文本不同颜色，图标加粗
        if is_error:
            text = f"[red bold]✗[/] [#f8769e]{display_text}{elapsed_str}[/]"
        else:
            text = f"[green bold]✓[/] [#7aa2f7]{display_text}{elapsed_str}[/]"

        _log(f"[ToolResultWidget] final text: '{text}'")
        self.update(text)

        if is_error:
            self.add_class("error")
        else:
            self.add_class("success")


class ToolPlaceholderWidget(Static):
    """工具占位组件 - 最小化尺寸避免空白区域"""
    DEFAULT_CSS = """
    ToolPlaceholderWidget {
        width: 100%;
        height: 0;
        margin: 0;
        padding: 0;
        display: none;
    }
    """

    def __init__(self, tool_id: str, **kwargs):
        self.tool_id = tool_id
        super().__init__("", **kwargs)


class MessageList(ScrollableContainer):
    DEFAULT_CSS = """
    MessageList {
        width: 100%;
        height: 1fr;
        background: #13131c;
        padding: 1 2;
        border: none;
        overflow-y: auto;
    }
    """

    def __init__(self, token_callback=None, token_progress_callback=None, tool_status_panel=None, **kwargs):
        super().__init__(**kwargs)
        self._token_callback = token_callback
        self._token_progress_callback = token_progress_callback
        self._tool_status_panel = tool_status_panel
        self._pending_tools: dict = {}
        self._tool_placeholders: dict = {}
        self._last_scroll_time = 0
        self._scroll_interval = 0.2
        _log(f"init: tool_status_panel={tool_status_panel is not None}")

        self._stream_handler = MessageStreamHandler(
            on_bot_created=self._add_widget,
            on_bot_updated=self._update_widget,
            on_tool_started=self._on_tool_started,
            on_tool_completed=self._on_tool_completed,
            on_stream_complete=self._on_stream_complete,
            on_stream_progress=self._on_stream_progress,
            on_error=self._on_stream_error,
        )

        # --- Subagent 流式回调 ---
        self._subagent_widgets: dict = {}  # agent_id -> SubagentWidget
        self._subagent_labels: dict = {}   # agent_id -> str (显示标签)
        self._register_subagent_callback()

    def _register_subagent_callback(self):
        """注册 subagent 流式回调到 subagent_tool 模块"""
        try:
            from tools.subagent_tool import set_subagent_stream_callback
            set_subagent_stream_callback(self._on_subagent_event)
            _log("subagent stream callback registered")
        except Exception as e:
            _log(f"Failed to register subagent callback: {e}")

    async def _on_subagent_event(self, event: dict):
        """处理 subagent 事件，使用 SubagentWidget 流式展示"""
        try:
            etype = event["type"]
            agent_id = event["agent_id"]

            if etype == "subagent_start":
                label = event.get("label", "Subagent")
                self._subagent_labels[agent_id] = label
                widget = SubagentWidget(agent_id=agent_id, label=label)
                self._subagent_widgets[agent_id] = widget
                self._add_widget(widget)
                _log(f"subagent_start: {agent_id} '{label}'")

            elif etype == "subagent_stream":
                text = event.get("content", "")
                if agent_id in self._subagent_widgets:
                    self._subagent_widgets[agent_id].append_content(text)
                    self._update_widget(self._subagent_widgets[agent_id])

            elif etype == "subagent_tool":
                tool_name = event.get("tool_name", "")
                tool_args = event.get("tool_args", "")
                status = event.get("status", "")
                if agent_id in self._subagent_widgets:
                    self._subagent_widgets[agent_id].append_tool(tool_name, tool_args, status)
                    self._update_widget(self._subagent_widgets[agent_id])

            elif etype == "subagent_done":
                if agent_id in self._subagent_widgets:
                    widget = self._subagent_widgets[agent_id]
                    widget.finalize()
                    self._update_widget(widget)
                    self._subagent_widgets.pop(agent_id, None)
                    self._subagent_labels.pop(agent_id, None)
                stats = event.get("stats", {})
                _log(f"subagent_done: {agent_id} llm={stats.get('llm_calls','?')} tools={stats.get('tool_calls','?')}")
        except Exception as e:
            _log(f"_on_subagent_event error: {type(e).__name__}: {e}")

    def add_user_message(self, content: str, is_command: bool = False):
        _log(f"add_user_message: content='{content[:50]}...'")
        try:
            msg = UserMessage(id=str(uuid.uuid4()), content=content, is_command=is_command)
            widget = UserMessageWidget(msg)
            self.mount(widget)
            self.refresh(layout=True)
            return widget
        except Exception as e:
            _log(f"add_user_message ERROR: {type(e).__name__}: {e}")
            import traceback
            _log(traceback.format_exc())
            raise

    async def stream_agent_response(self, agent_stream):
        _log("stream_agent_response called")
        try:
            await self._stream_handler.process_stream(agent_stream)
        except Exception as e:
            # 最后防线：process_stream 内部已通过 on_error 处理异常，
            # 但如果仍有异常泄漏到这里，提供双重保险
            import traceback
            tb = traceback.format_exc()
            _log(f"Uncaught error in stream_agent_response: {e}")
            _log(tb)
            exc_type = type(e).__name__
            exc_msg = str(e)
            tb_lines = tb.strip().split("\n")
            concise_tb = "\n".join(tb_lines[-6:]) if len(tb_lines) > 6 else "\n".join(tb_lines)
            self._mount_error_widget(
                f"{exc_type}: {exc_msg}" if exc_msg else exc_type,
                f"发生时间: {datetime.now().strftime('%H:%M:%S')}\n堆栈跟踪 (最后几行):\n{concise_tb}"
            )

    def _on_stream_error(self, error_summary: str, error_detail: str):
        """流错误回调 - 在 chat-area 中显示错误信息"""
        _log(f"_on_stream_error: summary='{error_summary}'")
        self._mount_error_widget(error_summary, error_detail)

    def _mount_error_widget(self, error_summary: str, error_detail: str):
        """挂载错误展示组件到聊天区域"""
        try:
            widget = ErrorMessageWidget(error_summary, error_detail)
            self.mount(widget)
            self.refresh(layout=True)
        except Exception as e:
            # 如果 UI 操作也失败了，至少保证日志可见
            _log(f"CRITICAL: Failed to mount error widget: {e}")
            import traceback
            _log(traceback.format_exc())

            # 兜底：尝试用最简单的 Static 展示
            try:
                fallback = Static(f"❌ 错误: {error_summary}")
                self.mount(fallback)
                self.refresh(layout=True)
            except Exception:
                _log("CRITICAL: Even fallback error display failed")

    def _add_widget(self, widget):
        _log(f"_add_widget: {type(widget).__name__}")
        self.mount(widget)
        self.refresh(layout=True)

    def _update_widget(self, widget):
        widget.refresh(layout=True)
        self.refresh(layout=True)

    def _is_at_bottom(self) -> bool:
        """用户是否在列表底部（允许 2 行误差）"""
        try:
            return self.scroll_offset.y >= max(0, self.max_scroll_offset.y - 2)
        except Exception:
            return True  # 异常时默认滚动

    def _scroll_to_end(self):
        """仅当用户在底部时才自动滚动"""
        if not self._is_at_bottom():
            return
        current_time = time.time()
        if current_time - self._last_scroll_time > self._scroll_interval:
            self.scroll_end(animate=False)
            self._last_scroll_time = current_time

    def _on_tool_started(self, tool_id: str, display_text: str):
        _log(f"[_on_tool_started] tool_id={tool_id[:30]}..., display_text='{display_text}'")
        self._pending_tools[tool_id] = display_text
        if self._tool_status_panel:
            self._tool_status_panel.add_tool(tool_id, display_text)
        # 不再创建 placeholder，避免空白区域
        # placeholder 仅用于标识工具是否已在进行中
        self._tool_placeholders[tool_id] = None

    def _on_tool_completed(self, tool_id: str, display_text: str, is_error: bool):
        _log(f"[_on_tool_completed] tool_id={tool_id[:30]}...")
        _log(f"[_on_tool_completed] display_text='{display_text}', is_error={is_error}")
        
        elapsed_time = 0.0
        if self._tool_status_panel:
            elapsed_time = self._tool_status_panel.remove_tool(tool_id)
            _log(f"[_on_tool_completed] elapsed_time={elapsed_time}")
        self._pending_tools.pop(tool_id, None)

        widget = ToolResultWidget(
            display_text=display_text,
            is_error=is_error,
            elapsed_time=elapsed_time
        )

        # 直接挂载 ToolResultWidget，不处理 placeholder
        self._tool_placeholders.pop(tool_id, None)
        self.mount(widget)
        self.refresh(layout=True)
        _log(f"[_on_tool_completed] mounted ToolResultWidget")

    def _on_stream_progress(self, progress_tokens: int):
        """流式输出期间的实时 token 进度回调"""
        if self._token_progress_callback:
            self._token_progress_callback(progress_tokens)

    def _on_stream_complete(self, total_tokens: int):
        _log(f"stream_complete: tokens={total_tokens}")
        # 最终刷新确保所有内容都显示
        if hasattr(self._stream_handler, 'current_bot_message') and self._stream_handler.current_bot_message:
            self._stream_handler.current_bot_message.refresh(layout=True)
        self.refresh(layout=True)
        if self._token_callback:
            self._token_callback(total_tokens)
        for placeholder in self._tool_placeholders.values():
            if placeholder is None:
                continue
            placeholder.remove()
        self._tool_placeholders.clear()

    def clear_messages(self):
        self.remove_children()
        self._pending_tools.clear()
        self._tool_placeholders.clear()
        if self._tool_status_panel:
            self._tool_status_panel.clear_all()
