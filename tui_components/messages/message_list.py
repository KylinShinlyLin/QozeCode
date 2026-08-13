# tui_components/messages/message_list.py
from textual.containers import ScrollableContainer
from textual.widgets import Static
import asyncio
import uuid
import weakref
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
from ..terminal_compat import get_terminal_render_profile

# 日志文件路径
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".qoze", "stream_debug.log")

_LOG_ENABLED = os.environ.get("QOZE_DEBUG", "") != ""


def _log(msg):
    if not _LOG_ENABLED:
        return
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


class HistoryBannerWidget(Static):
    """历史记录恢复提示组件 - 启动时显示已加载的会话历史"""

    DEFAULT_CSS = """
    HistoryBannerWidget {
        width: 100%;
        height: auto;
        margin: 1 0;
        padding: 1 2;
        border-left: thick #7aa2f7;
        background: #1a1d2e;
        color: #a9b1d6;
        content-align: left top;
    }
    """

    def __init__(self, stats: dict, **kwargs):
        kwargs.setdefault("markup", False)
        super().__init__(**kwargs)

        count = stats['message_count']
        chars = stats['total_chars']
        rounds = stats['user_msgs']
        last_time = stats.get('last_time', '')
        ckpt_count = stats.get('checkpoint_count', 0)

        if chars >= 1000:
            token_str = f'{chars / 1000:.1f}K'
        else:
            token_str = str(chars)

        lines = [
            f'📋 已恢复 {count} 条历史消息',
            f'约 {token_str} chars · {rounds} 轮对话 · {ckpt_count} 个 checkpoint',
        ]
        if last_time:
            lines.append(f'上次会话: {last_time}')

        self.update('\n'.join(lines))


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
        display_text = display_text.replace("[", "\\[").replace("]", "\\]")

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
        padding: 1 2;
        border: none;
        overflow-y: auto;
        overflow-x: hidden;
    }
    """

    def __init__(self, token_callback=None, token_progress_callback=None, tool_status_panel=None, **kwargs):
        super().__init__(**kwargs)
        self._token_callback = token_callback
        self._token_progress_callback = token_progress_callback
        self._tool_status_panel = tool_status_panel
        self._pending_tools: dict = {}
        self._tool_placeholders: dict = {}
        self._auto_scroll = True  # 是否自动跟随流式滚动
        self._stream_render_paused = False
        self._pending_stream_snapshots: dict = {}
        self._stream_snapshot_gates: dict = {}
        self._structure_layout_pending = False
        self._scroll_pending = False
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
        self._subagent_labels: dict = {}  # agent_id -> str (显示标签)
        self._subagent_last_ui_update: dict = {}
        self._subagent_trailing_handles: dict = {}
        self._pending_subagent_paints: set[str] = set()
        self._pending_subagent_finalizes: set[str] = set()
        self._registered_subagent_callback = None
        self._subagent_profile = get_terminal_render_profile()
        self._subagent_clock = time.monotonic

    def on_mount(self):
        """Register global routing only while this MessageList is mounted."""
        self._register_subagent_callback()

    def _register_subagent_callback(self):
        """注册 subagent 流式回调到 subagent_tool 模块"""
        try:
            from tools.subagent_tool import set_subagent_stream_callback
            callback = self._on_subagent_event
            set_subagent_stream_callback(callback)
            self._registered_subagent_callback = callback
            _log("subagent stream callback registered")
        except Exception as e:
            _log(f"Failed to register subagent callback: {e}")

    def _unregister_subagent_callback(self):
        """Compare-and-clear so an older unmount cannot detach a newer list."""
        callback = getattr(self, "_registered_subagent_callback", None)
        if callback is None:
            return
        try:
            from tools.subagent_tool import compare_and_clear_subagent_stream_callback
            compare_and_clear_subagent_stream_callback(callback)
        except Exception as e:
            _log(f"Failed to unregister subagent callback: {e}")
        finally:
            self._registered_subagent_callback = None

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

    def _cancel_subagent_trailing(self, agent_id: str):
        """Cancel the one trailing repaint owned by an agent, if any."""
        handle = self._subagent_trailing_handles.pop(agent_id, None)
        if handle is not None:
            cancel = getattr(handle, "cancel", None) or getattr(handle, "stop", None)
            if cancel is not None:
                cancel()

    def _clear_subagent_render_state(self, agent_id: str):
        self._cancel_subagent_trailing(agent_id)
        self._subagent_last_ui_update.pop(agent_id, None)

    def _clear_all_subagent_state(self):
        for agent_id in tuple(self._subagent_trailing_handles):
            self._cancel_subagent_trailing(agent_id)
        self._subagent_last_ui_update.clear()
        self._subagent_widgets.clear()
        self._subagent_labels.clear()
        getattr(self, "_pending_subagent_paints", set()).clear()
        getattr(self, "_pending_subagent_finalizes", set()).clear()

    def _schedule_subagent_trailing(self, delay: float, callback):
        """Scheduling seam kept injectable for deterministic interaction tests."""
        return asyncio.get_running_loop().call_later(delay, callback)

    def _paint_subagent(self, agent_id: str, widget):
        if self._stream_render_paused:
            pending = getattr(self, "_pending_subagent_paints", None)
            if pending is None:
                pending = self._pending_subagent_paints = set()
            pending.add(agent_id)
            return
        self._subagent_last_ui_update[agent_id] = self._subagent_clock()
        widget._update_content_display()
        self._update_widget(widget)

    def _flush_subagent_trailing(self, agent_id: str):
        self._subagent_trailing_handles.pop(agent_id, None)
        widget = self._subagent_widgets.get(agent_id)
        if self._stream_render_paused:
            if widget is not None and not widget.is_collapsed:
                self._pending_subagent_paints.add(agent_id)
            return
        if widget is None or widget.is_collapsed:
            self._subagent_last_ui_update.pop(agent_id, None)
            return
        self._paint_subagent(agent_id, widget)

    def _on_subagent_collapsed_change(self, agent_id: str, collapsed: bool):
        """Keep click-driven visibility changes under the same frame ownership."""
        if collapsed:
            self._clear_subagent_render_state(agent_id)
        else:
            self._clear_subagent_render_state(agent_id)
            self._maybe_render_subagent(agent_id)

    def _maybe_render_subagent(self, agent_id: str):
        """Paint a leading frame and guarantee one latest-wins trailing frame."""
        widget = self._subagent_widgets.get(agent_id)
        if widget is None or widget.is_collapsed:
            self._clear_subagent_render_state(agent_id)
            return
        now = self._subagent_clock()
        last = self._subagent_last_ui_update.get(agent_id)
        interval = self._subagent_profile.frame_interval
        if last is not None and now - last < interval:
            if agent_id not in self._subagent_trailing_handles:
                delay = interval - (now - last)
                self._subagent_trailing_handles[agent_id] = self._schedule_subagent_trailing(
                    delay, lambda: self._flush_subagent_trailing(agent_id)
                )
            return
        self._cancel_subagent_trailing(agent_id)
        self._paint_subagent(agent_id, widget)

    async def _on_subagent_event(self, event: dict):
        """Handle subagent events while keeping collapsed bodies completely cold."""
        try:
            etype = event["type"]
            agent_id = event["agent_id"]

            if etype == "subagent_start":
                self._clear_subagent_render_state(agent_id)
                label = event.get("label", "Subagent")
                self._subagent_labels[agent_id] = label
                widget = SubagentWidget(
                    agent_id=agent_id,
                    label=label,
                    on_collapsed_change=lambda collapsed, aid=agent_id: (
                        self._on_subagent_collapsed_change(aid, collapsed)
                    ),
                )
                self._subagent_widgets[agent_id] = widget
                self._add_widget(widget)
                _log(f"subagent_start: {agent_id} {label!r}")

            elif etype == "subagent_stream":
                widget = self._subagent_widgets.get(agent_id)
                if widget is not None:
                    widget.append_content(event.get("content", ""))
                    self._maybe_render_subagent(agent_id)

            elif etype == "subagent_tool":
                widget = self._subagent_widgets.get(agent_id)
                if widget is not None:
                    widget.append_tool(
                        event.get("tool_name", ""),
                        event.get("tool_args", ""),
                        event.get("status", ""),
                    )
                    self._maybe_render_subagent(agent_id)

            elif etype == "subagent_done":
                widget = self._subagent_widgets.get(agent_id)
                if widget is not None:
                    self._clear_subagent_render_state(agent_id)
                    if self._stream_render_paused:
                        self._pending_subagent_finalizes.add(agent_id)
                    else:
                        widget.finalize()
                        self._update_widget(widget)
                    _log(f"subagent_done: {agent_id}")

        except Exception as e:
            _log(f"_on_subagent_event error: {e}")

    async def stream_agent_response(self, stream):
        """处理流式输出"""
        _log("process_stream called")
        await self._stream_handler.process_stream(stream)

    def consume_stream_usage(self):
        """取出本次请求流中模型返回的精确 token 用量 (无则返回 None)。

        必须在下一次 stream_agent_response 之前调用 (process_stream 会重置)。
        """
        handler = getattr(self, "_stream_handler", None)
        if handler is None:
            return None
        return handler.consume_stream_usage()

    def _create_user_message_widget(self, user_message, is_command: bool = False):
        """标准化用户消息并创建其展示组件。"""
        if isinstance(user_message, str):
            user_message = UserMessage(
                id=str(uuid.uuid4())[:8],
                content=user_message,
                is_command=is_command
            )
        # A new request is an explicit intent to follow current output again.
        self.resume_stream_render()
        return UserMessageWidget(user_message)

    def add_user_message(self, user_message, is_command: bool = False):
        """通过兼容的异步队列路径添加用户消息。"""
        widget = self._create_user_message_widget(user_message, is_command)
        self._add_widget(widget)
        return widget

    async def add_user_message_and_wait_for_render(self, user_message, is_command: bool = False):
        """挂载用户消息，并等待其布局刷新和自动滚动完成。"""
        widget = self._create_user_message_widget(user_message, is_command)

        try:
            await self.mount(widget)

            render_complete = asyncio.get_running_loop().create_future()

            def finish_render():
                try:
                    if self._auto_scroll and not self._stream_render_paused:
                        self.scroll_end(animate=False)
                finally:
                    if not render_complete.done():
                        render_complete.set_result(None)

            # 用户消息挂载属于结构变化；通过单槽请求合并 layout。
            self.request_structure_layout()
            self.call_after_refresh(finish_render)
            await render_complete
        except Exception as exc:
            # UI 展示异常不应阻塞 Agent 请求，保留当前容错语义。
            _log(f"user message render barrier failed: {exc}")

        return widget

    def add_static_text(self, text: str):
        """添加纯文本消息（如系统提示）"""
        widget = Static(text)
        self._add_widget(widget)

    @property
    def is_stream_render_paused(self) -> bool:
        """Whether stream snapshots are being held while the user reads history."""
        return self._stream_render_paused

    def _install_stream_snapshot_gate(self, widget):
        """Gate Bot/Thinking snapshots and terminal transitions before widget apply."""
        gates = getattr(self, "_stream_snapshot_gates", None)
        if gates is None:
            gates = self._stream_snapshot_gates = {}
        if widget in gates:
            return

        snapshot_method = None
        for candidate in ("apply_stream_snapshot", "apply_snapshot"):
            if callable(getattr(widget, candidate, None)):
                snapshot_method = candidate
                break
        if snapshot_method is None:
            return

        method_names = [snapshot_method]
        if callable(getattr(widget, "finalize", None)):
            method_names.append("finalize")
        gate = {
            "methods": {name: getattr(widget, name) for name in method_names},
            "snapshot_method": snapshot_method,
            "terminal_received": False,
        }
        gates[widget] = gate

        owner_ref = weakref.ref(self)
        widget_ref = weakref.ref(widget)

        def make_wrapper(method_name):
            def gated_method(*args, **kwargs):
                owner = owner_ref()
                target = widget_ref()
                if owner is None or target is None:
                    return None
                return owner._gate_stream_widget_call(
                    target, method_name, args, kwargs
                )
            return gated_method

        for method_name in method_names:
            setattr(widget, method_name, make_wrapper(method_name))

    def _gate_stream_widget_call(self, widget, method_name, args, kwargs):
        """Retain latest snapshot plus optional finalize while rendering is paused."""
        gate = self._stream_snapshot_gates.get(widget)
        if gate is None:
            return None
        original = gate["methods"][method_name]
        is_finalize = method_name == "finalize"

        if is_finalize:
            if gate["terminal_received"]:
                return None
            gate["terminal_received"] = True
            if not self._stream_render_paused:
                return original(*args, **kwargs)
        elif gate["terminal_received"]:
            # A terminal state owns the widget from the moment it arrives.
            return None
        elif not self._stream_render_paused:
            return original(*args, **kwargs)

        pending = self._pending_stream_snapshots.setdefault(
            widget, {"snapshot": None, "finalize": None}
        )
        action = (original, args, kwargs)
        if is_finalize:
            pending["finalize"] = action
        else:
            pending["snapshot"] = action
        return None

    def _restore_stream_snapshot_gates(self):
        """Restore original bound methods and release all gate/pending references."""
        gates = getattr(self, "_stream_snapshot_gates", {})
        for widget, gate in list(gates.items()):
            for method_name, original in gate["methods"].items():
                try:
                    setattr(widget, method_name, original)
                except Exception:
                    pass
        gates.clear()
        self._pending_stream_snapshots.clear()

    def apply_stream_snapshot(self, widget):
        """Compatibility callback; widget mutation already passed through its gate."""
        return None

    def pause_stream_render(self):
        """Pause body snapshot painting and automatic following."""
        self._stream_render_paused = True
        self._auto_scroll = False

    def resume_stream_render(self):
        """Replay each widget latest snapshot, then its finalize, at most once each."""
        pending = list(self._pending_stream_snapshots.values())
        self._pending_stream_snapshots.clear()
        self._stream_render_paused = False
        self._auto_scroll = True

        for state in pending:
            for action_name in ("snapshot", "finalize"):
                action = state[action_name]
                if action is None:
                    continue
                original, args, kwargs = action
                try:
                    original(*args, **kwargs)
                except Exception:
                    pass

        pending_finalizes = tuple(getattr(self, "_pending_subagent_finalizes", set()))
        getattr(self, "_pending_subagent_finalizes", set()).clear()
        for agent_id in pending_finalizes:
            widget = getattr(self, "_subagent_widgets", {}).get(agent_id)
            if widget is not None:
                widget.finalize()
                self._update_widget(widget)

        pending_paints = tuple(getattr(self, "_pending_subagent_paints", set()))
        getattr(self, "_pending_subagent_paints", set()).clear()
        for agent_id in pending_paints:
            widget = getattr(self, "_subagent_widgets", {}).get(agent_id)
            if widget is not None and not widget.is_collapsed and agent_id not in pending_finalizes:
                self._paint_subagent(agent_id, widget)

        self._safe_scroll_to_bottom()

    def request_structure_layout(self):
        """Coalesce structural changes into a single deferred layout refresh."""
        if self._structure_layout_pending:
            return
        self._structure_layout_pending = True
        try:
            self.call_after_refresh(self._flush_structure_layout)
        except Exception:
            self._structure_layout_pending = False
            raise

    def _flush_structure_layout(self):
        """Run the one pending structural layout request."""
        self._structure_layout_pending = False
        try:
            self.refresh(layout=True)
        except Exception:
            pass

    def _add_widget(self, widget):
        """Mount a structural child and coalesce layout and auto-follow requests."""
        self._install_stream_snapshot_gate(widget)
        self.mount(widget)
        self.request_structure_layout()
        if (
            self._auto_scroll
            and not self._stream_render_paused
            and not self._scroll_pending
        ):
            self._scroll_pending = True
            try:
                self.call_after_refresh(self._deferred_scroll_end)
            except Exception:
                self._scroll_pending = False
                raise

    def _update_widget(self, widget):
        """Accept one effective frame and request single-slot auto-follow."""
        self.apply_stream_snapshot(widget)
        self._safe_scroll_to_bottom()

    def _deferred_scroll_end(self):
        """Scroll once after refresh unless reading history has paused following."""
        self._scroll_pending = False
        if self._stream_render_paused or not self._auto_scroll:
            return
        try:
            self.scroll_end(animate=False)
        except Exception:
            pass

    def _safe_scroll_to_bottom(self):
        """Schedule stream auto-follow only while rendering and following are active."""
        if self._stream_render_paused or not self._auto_scroll:
            return
        try:
            if not self._scroll_pending:
                self._scroll_pending = True
                self.call_after_refresh(self._deferred_scroll_end)
        except Exception:
            self._scroll_pending = False

    def user_scrolled_up(self):
        """Pause stream painting and auto-follow while the user reads history."""
        self.pause_stream_render()

    def check_scroll_bottom_and_resume(self):
        """Resume stream painting once the viewport returns to the bottom."""
        try:
            if self.scroll_y >= self.max_scroll_y - 3:
                self.resume_stream_render()
        except Exception:
            pass

    def on_key(self, event):
        """Keyboard scrolling shares the same pause/resume state transitions."""
        if event.key in ("up", "pageup"):
            self.user_scrolled_up()
        elif event.key in ("down", "pagedown"):
            self.call_after_refresh(self.check_scroll_bottom_and_resume)
        elif event.key == "end":
            self.resume_stream_render()

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
            panel_elapsed = self._tool_status_panel.remove_tool(tool_id, display_name)
            if panel_elapsed > 0:
                elapsed = panel_elapsed

        # 移除占位组件
        placeholder = self._tool_placeholders.pop(tool_id, None)
        if placeholder:
            try:
                placeholder.remove()
                self.request_structure_layout()
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

    def on_unmount(self):
        """Detach instance gates before Textual releases this message list."""
        self._unregister_subagent_callback()
        self._restore_stream_snapshot_gates()
        self._clear_all_subagent_state()
        self._structure_layout_pending = False
        self._scroll_pending = False

    def clear_messages(self):
        """清除所有消息"""
        self._restore_stream_snapshot_gates()
        self._clear_all_subagent_state()
        self._structure_layout_pending = False
        self._scroll_pending = False
        for child in self.children[:]:
            child.remove()
        self._pending_tools.clear()
        self._tool_placeholders.clear()
        self.request_structure_layout()
