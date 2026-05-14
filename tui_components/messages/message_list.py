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
from .thinking_widget import ThinkingWidget
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
            on_thinking_created=self._on_thinking_created,
            on_thinking_updated=self._on_thinking_updated,
            on_thinking_finalized=self._on_thinking_finalized,
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

    # ---------- Thinking Widget 回调 ----------

    def _on_thinking_created(self, widget: ThinkingWidget):
        """thinking 开始，将 ThinkingWidget 挂载到消息列表"""
        self._add_widget(widget)

    def _on_thinking_updated(self, widget: ThinkingWidget):
        """thinking 内容更新，刷新 widget"""
        self._update_widget(widget)

    def _on_thinking_finalized(self, widget: ThinkingWidget):
        """thinking 结束，刷新 widget 以显示完成状态"""
        self._update_widget(widget)

    # ---------- Subagent 回调 ----------

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
                    self._subagent_widgets[agent_id].finalize()
                    self._update_widget(self._subagent_widgets[agent_id])
                    _log(f"subagent_done: {agent_id}")

        except Exception as e:
            _log(f"_on_subagent_event error: {e}")

    async def stream_agent_response(self, stream):
        """处理流式输出"""
        _log("process_stream called")
        await self._stream_handler.process_stream(stream)

    def add_user_message(self, user_message, is_command: bool = False):
        """添加用户消息到列表

        Args:
            user_message: UserMessage 对象或纯文本字符串
            is_command: 是否为命令消息（仅当 user_message 为字符串时使用）
        """
        if isinstance(user_message, str):
            user_message = UserMessage(
                id=str(uuid.uuid4())[:8],
                content=user_message,
                is_command=is_command
            )
        widget = UserMessageWidget(user_message)
        self._add_widget(widget)

    def add_static_text(self, text: str):
        """添加纯文本消息（如系统提示）"""
        widget = Static(text)
        self._add_widget(widget)

    def _add_widget(self, widget):
        """挂载组件并滚动到底部"""
        self.mount(widget)
        # 滚动到底部
        self._safe_scroll_to_bottom()

    def _update_widget(self, widget):
        """刷新组件（已挂载时无需额外操作，内容更新会自动反映）"""
        try:
            widget.refresh(layout=True)
        except Exception:
            pass
        self._safe_scroll_to_bottom()

    def _safe_scroll_to_bottom(self):
        """节流滚动到底部"""
        now = time.time()
        if now - self._last_scroll_time < self._scroll_interval:
            return
        self._last_scroll_time = now
        try:
            if hasattr(self, 'scroll_end'):
                self.call_after_refresh(self.scroll_end, animate=False)
        except Exception:
            pass

    def _on_tool_started(self, tool_id: str, display_name: str):
        """工具开始执行回调"""
        _log(f"_on_tool_started: {tool_id} - {display_name}")
        self._pending_tools[tool_id] = {
            "display_name": display_name,
            "start_time": time.time(),
        }

        # 在消息列表中插入占位（最小化布局空间）
        placeholder = ToolPlaceholderWidget(tool_id)
        self._tool_placeholders[tool_id] = placeholder
        self._add_widget(placeholder)

        # 在工具状态面板中显示运行中状态
        if self._tool_status_panel:
            self._tool_status_panel.add_tool(tool_id, display_name)

    def _on_tool_completed(self, tool_id: str, display_name: str, is_error: bool):
        """工具执行完成回调"""
        _log(f"_on_tool_completed: {tool_id} - {display_name}, is_error={is_error}")
        elapsed = 0.0
        if tool_id in self._pending_tools:
            elapsed = time.time() - self._pending_tools[tool_id]["start_time"]
            del self._pending_tools[tool_id]

        # 移除工具状态面板中的条目
        if self._tool_status_panel:
            panel_elapsed = self._tool_status_panel.remove_tool(tool_id)
            if panel_elapsed > 0:
                elapsed = panel_elapsed

        # 移除占位组件
        placeholder = self._tool_placeholders.pop(tool_id, None)
        if placeholder:
            try:
                placeholder.remove()
            except Exception:
                pass

        # 在消息列表中插入工具结果
        result_widget = ToolResultWidget(
            display_name,
            is_error=is_error,
            elapsed_time=elapsed,
        )
        self._add_widget(result_widget)

    def _on_stream_complete(self, estimated_tokens: int):
        """流式完成回调"""
        _log(f"_on_stream_complete: estimated_tokens={estimated_tokens}")
        if self._token_callback:
            self._token_callback(estimated_tokens)

    def _on_stream_progress(self, estimated_tokens: int):
        """流式进度回调（实时 token 计数）"""
        if self._token_progress_callback:
            self._token_progress_callback(estimated_tokens)

    def _on_stream_error(self, error_summary: str, error_detail: str):
        """流式异常回调 - 创建 ErrorMessageWidget 并挂载"""
        _log(f"_on_stream_error: {error_summary}")
        try:
            error_widget = ErrorMessageWidget(error_summary, error_detail)
            self._add_widget(error_widget)
        except Exception as e:
            _log(f"Failed to mount error widget: {e}")

    def clear_messages(self):
        """清除所有消息"""
        for child in self.children[:]:
            child.remove()
        self._pending_tools.clear()
        self._tool_placeholders.clear()
