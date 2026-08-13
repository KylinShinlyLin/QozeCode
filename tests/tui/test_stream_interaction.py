"""Disaster-recovery interaction coverage for the scheduled TUI stream path.

The tests deliberately use small Python spies instead of starting a Textual App.  They
exercise production handlers and bind MessageList/widget methods to deterministic
harnesses so frame ownership and lifecycle rules remain observable.
"""
from __future__ import annotations

import asyncio
import sys
import weakref
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tui_components.messages import stream_handler as stream_handler_module
from tui_components.messages.bot_widget import BotMessageWidget
from tui_components.messages.message_list import MessageList
from tui_components.messages.subagent_widget import SubagentWidget
from tui_components.messages.thinking_widget import ThinkingWidget
from tui_components.request_indicator import RequestIndicator
from tui_components.terminal_compat import TerminalRenderProfile, sanitize_display_text


class AIMessageChunk:
    """Minimal LangChain-like chunk accepted by the handler's name fallback."""

    def __init__(
        self,
        content: str = "",
        *,
        thinking: str = "",
        finish_reason: str = "",
        tool_calls: list[dict[str, object]] | None = None,
    ) -> None:
        self.content = content
        self.additional_kwargs = {"reasoning_content": thinking} if thinking else {}
        self.response_metadata = {"finish_reason": finish_reason} if finish_reason else {}
        self.usage_metadata = None
        self.id = None
        self.tool_calls = tool_calls or []

    def __add__(self, other: "AIMessageChunk") -> "AIMessageChunk":
        return AIMessageChunk(
            self.content + other.content,
            thinking=(self.additional_kwargs.get("reasoning_content", "")
                      + other.additional_kwargs.get("reasoning_content", "")),
            tool_calls=other.tool_calls or self.tool_calls,
        )


class ToolMessage:
    def __init__(self, tool_call_id: str, content: str = "ok") -> None:
        self.tool_call_id = tool_call_id
        self.content = content


class StreamFailure(RuntimeError):
    pass


class FakeBotWidget:
    instances: list["FakeBotWidget"] = []

    def __init__(self, message: object) -> None:
        self.message = message
        self.snapshots: list[tuple[str, str | None]] = []
        self.finalized_with: list[str] = []
        self.final_raw: list[str | None] = []
        type(self).instances.append(self)

    def apply_stream_snapshot(self, display_text: str, raw_text: str | None = None) -> None:
        self.snapshots.append((display_text, raw_text))

    def finalize(self, final_text: str, raw_text: str | None = None) -> None:
        self.finalized_with.append(final_text)
        self.final_raw.append(raw_text)


class FakeThinkingWidget:
    instances: list["FakeThinkingWidget"] = []
    collapsed_on_create = True

    def __init__(self, snapshot_provider=None) -> None:
        self._collapsed = type(self).collapsed_on_create
        self._snapshot_provider = snapshot_provider
        self._is_finalized = False
        self.snapshots: list[tuple[int, str | None]] = []
        self.finalize_calls = 0
        self.displayed_tail = ""
        self.content_update_calls = 0
        type(self).instances.append(self)

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def apply_snapshot(self, char_count: int, display_tail: str | None) -> None:
        self.snapshots.append((char_count, display_tail))
        if not self._collapsed and display_tail is not None:
            self.displayed_tail = display_tail
            self.content_update_calls += 1

    def finalize(self) -> None:
        if self._is_finalized:
            return
        self._is_finalized = True
        self.finalize_calls += 1

    def expand(self) -> None:
        self._collapsed = False
        if self._snapshot_provider is not None:
            self.displayed_tail = self._snapshot_provider()
            self.content_update_calls += 1

    def collapse(self) -> None:
        self._collapsed = True


def _profile() -> TerminalRenderProfile:
    return TerminalRenderProfile(
        name="interaction-test",
        frame_interval=10.0,
        busy_interval=10.0,
        tail_chars=64 * 1024,
        tail_lines=2000,
    )


def _install_stream_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    thinking_collapsed: bool = True,
) -> None:
    FakeBotWidget.instances.clear()
    FakeThinkingWidget.instances.clear()
    FakeThinkingWidget.collapsed_on_create = thinking_collapsed
    monkeypatch.setattr(stream_handler_module, "BotMessageWidget", FakeBotWidget)
    monkeypatch.setattr(stream_handler_module, "ThinkingWidget", FakeThinkingWidget)
    monkeypatch.setattr(stream_handler_module, "get_terminal_render_profile", _profile)


def _handler(**callbacks):
    return stream_handler_module.MessageStreamHandler(
        on_bot_created=callbacks.pop("on_bot_created", lambda widget: None),
        on_bot_updated=callbacks.pop("on_bot_updated", lambda widget: None),
        **callbacks,
    )


def _run_chunks(chunks: list[object], handler=None):
    handler = handler or _handler()

    async def stream():
        for chunk in chunks:
            yield chunk, {}

    asyncio.run(handler.process_stream(stream()))
    return handler


def _tool_call(tool_id: str = "call-1") -> dict[str, object]:
    return {"id": tool_id, "name": "read_file", "args": {"path": "README.md"}}


def test_body_100_chunks_are_coalesced_and_preserve_complete_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stream_fakes(monkeypatch)
    chunks = [f"段{i}\t\x1b[31m红\x1b[0m\n" for i in range(100)]
    updated: list[FakeBotWidget] = []
    handler = _run_chunks([AIMessageChunk(text) for text in chunks], _handler(on_bot_updated=updated.append))
    widget = FakeBotWidget.instances[0]
    raw = "".join(chunks)
    display = "".join(sanitize_display_text(text) for text in chunks)

    assert 0 < len(widget.snapshots) < 100
    assert updated == [widget] * len(widget.snapshots)
    assert widget.snapshots[-1] == (display, None)
    assert widget.finalized_with == [display]
    assert handler._content_buffer.raw_text() == raw


def test_cancel_flushes_latest_body_then_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stream_fakes(monkeypatch)
    chunks = ["取消前", "\t正文", "\x1b[32m完整\x1b[0m"]
    handler = _handler()

    async def scenario() -> None:
        delivered = asyncio.Event()
        hold = asyncio.Event()

        async def stream():
            for text in chunks:
                yield AIMessageChunk(text), {}
            delivered.set()
            await hold.wait()

        task = asyncio.create_task(handler.process_stream(stream()))
        await asyncio.wait_for(delivered.wait(), timeout=0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    widget = FakeBotWidget.instances[0]
    raw = "".join(chunks)
    display = "".join(sanitize_display_text(text) for text in chunks)
    assert widget.snapshots[-1] == (display, None)
    assert widget.finalized_with == [display]
    assert handler._render_scheduler._closed is True


def test_iterator_error_finalizes_body_and_notifies_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stream_fakes(monkeypatch)
    errors: list[tuple[str, str]] = []
    handler = _handler(on_error=lambda summary, detail: errors.append((summary, detail)))

    async def stream():
        yield AIMessageChunk("异常前"), {}
        yield AIMessageChunk("完整"), {}
        raise StreamFailure("iterator exploded")

    asyncio.run(handler.process_stream(stream()))
    widget = FakeBotWidget.instances[0]
    assert widget.snapshots[-1] == ("异常前完整", None)
    assert widget.finalized_with == ["异常前完整"]
    assert errors[0][0] == "StreamFailure: iterator exploded"
    assert handler._render_scheduler._closed is True
    assert handler._render_scheduler.pending is False


@pytest.mark.parametrize("failure_point", ["finalize", "on_stream_complete"])
def test_callback_exception_still_closes_scheduler(
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    _install_stream_fakes(monkeypatch)

    def fail(message: str) -> None:
        raise RuntimeError(message)

    handler = _handler(
        on_stream_complete=(lambda tokens: fail("complete failed"))
        if failure_point == "on_stream_complete" else None,
    )
    if failure_point == "finalize":
        original = FakeBotWidget.finalize

        def failing_finalize(self, final_text):
            original(self, final_text)
            fail("finalize failed")

        monkeypatch.setattr(FakeBotWidget, "finalize", failing_finalize)

    async def stream():
        yield AIMessageChunk("正文"), {}

    expected = "complete failed" if failure_point == "on_stream_complete" else "finalize failed"
    with pytest.raises(RuntimeError, match=expected):
        asyncio.run(handler.process_stream(stream()))
    assert handler._render_scheduler._closed is True
    assert handler._render_scheduler.pending is False


def test_tool_rounds_do_not_share_body_buffer(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_stream_fakes(monkeypatch)
    chunks = [
        AIMessageChunk("第一轮"),
        AIMessageChunk(finish_reason="tool_calls", tool_calls=[_tool_call()]),
        ToolMessage("call-1"),
        AIMessageChunk("第二轮"),
    ]
    handler = _run_chunks(chunks)
    first, second = FakeBotWidget.instances
    assert first.snapshots[-1] == ("第一轮", None)
    assert first.finalized_with == ["第一轮"]
    assert second.snapshots[-1] == ("第二轮", None)
    assert second.finalized_with == ["第二轮"]
    assert handler._content_buffer.raw_text() == "第二轮"


def test_thinking_1000_chunks_are_coalesced_while_collapsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stream_fakes(monkeypatch, thinking_collapsed=True)
    chunks = [f"思考{i}\t\x1b[31m片段\x1b[0m\n" for i in range(1000)]
    updated: list[FakeThinkingWidget] = []
    finalized: list[FakeThinkingWidget] = []
    handler = _run_chunks(
        [AIMessageChunk(thinking=text) for text in chunks],
        _handler(on_thinking_updated=updated.append, on_thinking_finalized=finalized.append),
    )
    widget = FakeThinkingWidget.instances[0]
    raw = "".join(chunks)
    assert 0 < len(widget.snapshots) < 1000
    assert all(tail is None for _, tail in widget.snapshots)
    assert widget.snapshots[-1] == (len(raw), None)
    assert updated == [widget] * len(widget.snapshots)
    assert finalized == [widget]
    assert handler._thinking_buffer.raw_text() == raw


def test_expanded_thinking_gets_sanitized_final_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stream_fakes(monkeypatch, thinking_collapsed=False)
    texts = ["展开", "\t思考", "\x1b[32m完整\x1b[0m"]
    _run_chunks([AIMessageChunk(thinking=text) for text in texts])
    widget = FakeThinkingWidget.instances[0]
    raw = "".join(texts)
    expected = "".join(sanitize_display_text(text) for text in texts)
    assert widget.snapshots[-1] == (len(raw), expected)
    assert widget.finalize_calls == 1


def test_thinking_only_tool_boundary_drains_before_finalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stream_fakes(monkeypatch, thinking_collapsed=True)
    finalized: list[FakeThinkingWidget] = []
    _run_chunks(
        [
            AIMessageChunk(thinking="仅思考尚未刷新"),
            AIMessageChunk(finish_reason="tool_calls", tool_calls=[_tool_call("think-call")]),
        ],
        _handler(on_thinking_finalized=finalized.append),
    )
    widget = FakeThinkingWidget.instances[0]
    assert widget.snapshots[-1] == (len("仅思考尚未刷新"), None)
    assert widget.finalize_calls == 1
    assert finalized == [widget]


def test_gemini_tool_result_rotates_mixed_body_and_thinking_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stream_fakes(monkeypatch, thinking_collapsed=False)
    first = AIMessageChunk("第一轮正文", thinking="第一轮思考", tool_calls=[_tool_call("gemini")])
    _run_chunks([first, ToolMessage("gemini"), AIMessageChunk("第二轮正文", thinking="第二轮思考")])
    assert len(FakeBotWidget.instances) == 2
    assert len(FakeThinkingWidget.instances) == 2
    first_thinking, second_thinking = FakeThinkingWidget.instances
    assert first_thinking.snapshots[-1][1] == "第一轮思考"
    assert second_thinking.snapshots[-1][1] == "第二轮思考"
    assert first_thinking.finalize_calls == second_thinking.finalize_calls == 1


def test_thinking_iterator_error_finalizes_callback_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stream_fakes(monkeypatch)
    finalized: list[FakeThinkingWidget] = []
    errors: list[str] = []
    handler = _handler(
        on_thinking_finalized=finalized.append,
        on_error=lambda summary, detail: errors.append(summary),
    )

    async def stream():
        yield AIMessageChunk(thinking="异常前思考"), {}
        raise StreamFailure("thinking failed")

    asyncio.run(handler.process_stream(stream()))
    widget = FakeThinkingWidget.instances[0]
    assert widget.snapshots[-1] == (len("异常前思考"), None)
    assert widget.finalize_calls == 1
    assert finalized == [widget]
    assert errors == ["StreamFailure: thinking failed"]


def test_body_and_thinking_share_complete_final_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_stream_fakes(monkeypatch, thinking_collapsed=False)
    _run_chunks([AIMessageChunk("正文", thinking="思考")])
    assert FakeBotWidget.instances[0].snapshots[-1] == ("正文", None)
    assert FakeThinkingWidget.instances[0].snapshots[-1] == (len("思考"), "思考")


class _DisplaySpy:
    def __init__(self) -> None:
        self.updates: list[object] = []
        self.classes = {"hidden"}

    def update(self, value) -> None:
        self.updates.append(value)

    def add_class(self, name: str) -> None:
        self.classes.add(name)

    def remove_class(self, name: str) -> None:
        self.classes.discard(name)


class _Click:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _mounted_thinking(provider=lambda: "latest"):
    widget = ThinkingWidget(snapshot_provider=provider)
    widget._mounted = True
    widget._header_widget = _DisplaySpy()
    widget._content_widget = _DisplaySpy()
    return widget


def test_real_thinking_collapsed_content_stays_cold_and_finalize_is_idempotent() -> None:
    widget = _mounted_thinking()
    widget.apply_snapshot(99, None)
    widget.finalize()
    widget.finalize()
    assert widget._content_widget.updates == []
    assert widget._is_finalized is True
    assert len(widget._header_widget.updates) == 2


def test_real_thinking_expansion_lazily_reads_provider_after_finalize() -> None:
    latest = ["first"]
    widget = _mounted_thinking(lambda: latest[0])
    widget.apply_snapshot(5, None)
    latest[0] = "final latest"
    widget.finalize()
    event = _Click()
    widget.on_click(event)
    assert event.stopped is True
    assert widget.is_collapsed is False
    assert widget._content_widget.updates[-1] == "final latest"


class MessageListHarness:
    is_stream_render_paused = MessageList.is_stream_render_paused
    _install_stream_snapshot_gate = MessageList._install_stream_snapshot_gate
    _gate_stream_widget_call = MessageList._gate_stream_widget_call
    _restore_stream_snapshot_gates = MessageList._restore_stream_snapshot_gates
    apply_stream_snapshot = MessageList.apply_stream_snapshot
    pause_stream_render = MessageList.pause_stream_render
    resume_stream_render = MessageList.resume_stream_render
    request_structure_layout = MessageList.request_structure_layout
    _flush_structure_layout = MessageList._flush_structure_layout
    _deferred_scroll_end = MessageList._deferred_scroll_end
    _safe_scroll_to_bottom = MessageList._safe_scroll_to_bottom
    user_scrolled_up = MessageList.user_scrolled_up
    check_scroll_bottom_and_resume = MessageList.check_scroll_bottom_and_resume
    on_key = MessageList.on_key

    def __init__(self) -> None:
        self._auto_scroll = True
        self._stream_render_paused = False
        self._pending_stream_snapshots = {}
        self._stream_snapshot_gates = {}
        self._structure_layout_pending = False
        self._scroll_pending = False
        self.after_refresh: list[tuple[object, tuple, dict]] = []
        self.refresh_calls: list[dict] = []
        self.scroll_end_calls = 0
        self.scroll_y = 0
        self.max_scroll_y = 100

    def call_after_refresh(self, callback, *args, **kwargs) -> None:
        self.after_refresh.append((callback, args, kwargs))

    def refresh(self, **kwargs) -> None:
        self.refresh_calls.append(kwargs)

    def scroll_end(self, *, animate: bool) -> None:
        self.scroll_end_calls += 1


class GateBot:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def apply_stream_snapshot(self, display: str, raw: str | None = None) -> None:
        self.calls.append(("snapshot", display, raw))

    def finalize(self, final: str) -> None:
        self.calls.append(("finalize", final))


class GateThinking:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def apply_snapshot(self, count: int, tail: str | None) -> None:
        self.calls.append(("snapshot", count, tail))

    def finalize(self) -> None:
        self.calls.append(("finalize",))


class _Key:
    def __init__(self, key: str) -> None:
        self.key = key


def test_bot_snapshot_and_finalize_are_gated_in_order() -> None:
    owner = MessageListHarness()
    widget = GateBot()
    owner._install_stream_snapshot_gate(widget)
    owner.pause_stream_render()
    widget.apply_stream_snapshot("old", "old")
    widget.apply_stream_snapshot("latest", "latest")
    widget.finalize("final")
    widget.apply_stream_snapshot("stale", "stale")
    assert widget.calls == []
    owner.resume_stream_render()
    assert widget.calls == [("snapshot", "latest", "latest"), ("finalize", "final")]


def test_thinking_snapshot_and_finalize_are_gated_in_order() -> None:
    owner = MessageListHarness()
    widget = GateThinking()
    owner._install_stream_snapshot_gate(widget)
    owner.pause_stream_render()
    widget.apply_snapshot(1, None)
    widget.apply_snapshot(9, "latest")
    widget.finalize()
    owner.resume_stream_render()
    assert widget.calls == [("snapshot", 9, "latest"), ("finalize",)]


@pytest.mark.parametrize("terminal", ["normal", "cancel", "error", "tool"])
def test_terminal_paths_replay_latest_then_finalize_once(terminal: str) -> None:
    owner = MessageListHarness()
    bot = GateBot()
    thinking = GateThinking()
    owner._install_stream_snapshot_gate(bot)
    owner._install_stream_snapshot_gate(thinking)
    owner.pause_stream_render()
    bot.apply_stream_snapshot(f"{terminal}-latest", terminal)
    thinking.apply_snapshot(len(terminal), terminal)
    bot.finalize(f"{terminal}-final")
    thinking.finalize()
    bot.finalize("duplicate")
    thinking.finalize()
    owner.resume_stream_render()
    assert bot.calls == [
        ("snapshot", f"{terminal}-latest", terminal),
        ("finalize", f"{terminal}-final"),
    ]
    assert thinking.calls == [("snapshot", len(terminal), terminal), ("finalize",)]


def test_structure_layout_uses_one_deferred_slot() -> None:
    owner = MessageListHarness()
    for _ in range(5):
        owner.request_structure_layout()
    assert len(owner.after_refresh) == 1
    callback, args, kwargs = owner.after_refresh.pop()
    callback(*args, **kwargs)
    assert owner.refresh_calls == [{"layout": True}]
    assert owner._structure_layout_pending is False


def test_structure_layout_queue_failure_rolls_back_pending_flag() -> None:
    owner = MessageListHarness()
    owner.call_after_refresh = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("closed"))
    with pytest.raises(RuntimeError, match="closed"):
        owner.request_structure_layout()
    assert owner._structure_layout_pending is False


def test_clear_style_gate_restore_releases_pending_and_original_methods() -> None:
    owner = MessageListHarness()
    widget = GateBot()
    original_function = widget.apply_stream_snapshot.__func__
    owner._install_stream_snapshot_gate(widget)
    owner.pause_stream_render()
    widget.apply_stream_snapshot("pending", "pending")
    owner._restore_stream_snapshot_gates()
    assert widget.apply_stream_snapshot.__func__ is original_function
    assert owner._stream_snapshot_gates == {}
    assert owner._pending_stream_snapshots == {}


def test_unmount_style_restore_uses_weak_wrappers_without_owner_retention() -> None:
    owner = MessageListHarness()
    widget = GateThinking()
    owner._install_stream_snapshot_gate(widget)
    owner_ref = weakref.ref(owner)
    owner._restore_stream_snapshot_gates()
    del owner
    assert owner_ref() is None
    widget.apply_snapshot(1, "still callable")
    assert widget.calls == [("snapshot", 1, "still callable")]


def test_scroll_callbacks_recheck_pause_state_when_interleaved() -> None:
    owner = MessageListHarness()
    owner._safe_scroll_to_bottom()
    assert len(owner.after_refresh) == 1
    callback, args, kwargs = owner.after_refresh.pop()
    owner.user_scrolled_up()
    callback(*args, **kwargs)
    assert owner.scroll_end_calls == 0
    owner.on_key(_Key("end"))
    assert owner.is_stream_render_paused is False
    assert len(owner.after_refresh) == 1
    owner.user_scrolled_up()
    callback, args, kwargs = owner.after_refresh.pop()
    callback(*args, **kwargs)
    assert owner.scroll_end_calls == 0


def test_bot_widget_snapshot_and_finalize_work_before_mount() -> None:
    message = SimpleNamespace(content="")
    widget = BotMessageWidget(message)
    widget.apply_stream_snapshot("display", "raw")
    widget.finalize("final")
    assert widget._display_text == "final"
    assert widget._raw_text == "raw"


class TimerSpy:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1

    cancel = stop


class SubagentEventWidget:
    def __init__(self) -> None:
        self._collapsed = False
        self.content = ""
        self.display_updates = 0
        self.finalize_calls = 0

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def append_content(self, text: str) -> None:
        self.content += text

    def append_tool(self, name: str, args: str, status: str) -> None:
        if status == "start":
            self.content += name

    def _update_content_display(self) -> None:
        self.display_updates += 1

    def finalize(self) -> None:
        self.finalize_calls += 1


class SubagentHarness:
    _cancel_subagent_trailing = MessageList._cancel_subagent_trailing
    _clear_subagent_render_state = MessageList._clear_subagent_render_state
    _clear_all_subagent_state = MessageList._clear_all_subagent_state
    _paint_subagent = MessageList._paint_subagent
    _flush_subagent_trailing = MessageList._flush_subagent_trailing
    _on_subagent_collapsed_change = MessageList._on_subagent_collapsed_change
    _maybe_render_subagent = MessageList._maybe_render_subagent
    _on_subagent_event = MessageList._on_subagent_event

    def __init__(self, widget: SubagentEventWidget | None = None) -> None:
        self._stream_render_paused = False
        self._pending_subagent_paints = set()
        self._pending_subagent_finalizes = set()
        self._subagent_widgets = {"agent": widget} if widget else {}
        self._subagent_labels = {}
        self._subagent_last_ui_update = {}
        self._subagent_trailing_handles = {}
        self._subagent_profile = _profile()
        self._subagent_profile = SimpleNamespace(frame_interval=0.1)
        self.now = 1.0
        self._subagent_clock = lambda: self.now
        self.scheduled: list[tuple[float, TimerSpy, object]] = []
        self.update_callbacks = 0

    def _schedule_subagent_trailing(self, delay, callback):
        handle = TimerSpy()
        self.scheduled.append((delay, handle, callback))
        return handle

    def _update_widget(self, widget) -> None:
        self.update_callbacks += 1

    def _add_widget(self, widget) -> None:
        return None


def _subagent_content_widget() -> tuple[SubagentWidget, _DisplaySpy, _DisplaySpy]:
    widget = SubagentWidget("agent", "label")
    static = _DisplaySpy()
    markdown = _DisplaySpy()
    header = _DisplaySpy()
    widget._mounted = True
    widget.query_one = lambda selector, cls=None: {
        "#subagent-content-static": static,
        "#subagent-content-md": markdown,
        "#subagent-header": header,
    }[selector]
    widget.refresh = lambda **kwargs: None
    widget._stop_timer = lambda: None
    return widget, static, markdown


def test_collapsed_subagent_keeps_hidden_static_cold_and_finalizes_once() -> None:
    widget, static, markdown = _subagent_content_widget()
    widget.append_content("折叠期间")
    widget._update_content_display()
    widget.finalize()
    widget.finalize()
    assert static.updates == []
    assert markdown.updates == ["折叠期间"]
    assert widget._done_received is True
    assert widget._final_view_applied is True


def test_subagent_burst_schedules_one_trailing_latest_wins_flush() -> None:
    widget = SubagentEventWidget()
    owner = SubagentHarness(widget)

    async def scenario() -> None:
        await owner._on_subagent_event({"type": "subagent_stream", "agent_id": "agent", "content": "a"})
        owner.now = 1.04
        await owner._on_subagent_event({"type": "subagent_stream", "agent_id": "agent", "content": "b"})
        owner.now = 1.09
        await owner._on_subagent_event({
            "type": "subagent_tool", "agent_id": "agent", "tool_name": "c",
            "tool_args": "", "status": "start",
        })

    asyncio.run(scenario())
    assert widget.content == "abc"
    assert widget.display_updates == 1
    assert len(owner.scheduled) == 1
    _, handle, callback = owner.scheduled[0]
    callback()
    assert handle.stop_calls == 0
    assert widget.display_updates == 2
    assert owner._subagent_trailing_handles == {}


def test_subagent_done_and_collapse_cancel_pending_handle() -> None:
    for cleanup in ("done", "collapse"):
        widget = SubagentEventWidget()
        owner = SubagentHarness(widget)
        handle = TimerSpy()
        owner._subagent_trailing_handles["agent"] = handle
        owner._subagent_last_ui_update["agent"] = 1.0
        if cleanup == "done":
            asyncio.run(owner._on_subagent_event({"type": "subagent_done", "agent_id": "agent"}))
            assert widget.finalize_calls == 1
        else:
            owner._on_subagent_collapsed_change("agent", True)
        assert handle.stop_calls == 1
        assert "agent" not in owner._subagent_trailing_handles
        assert "agent" not in owner._subagent_last_ui_update


def test_subagent_finalize_before_mount_applies_final_view_once_on_mount() -> None:
    widget, static, markdown = _subagent_content_widget()
    widget._mounted = False
    widget.append_content("mount 前完成")
    widget.finalize()
    assert widget._done_received is True
    assert widget._final_view_applied is False
    assert markdown.updates == []
    widget.on_mount()
    widget.finalize()
    assert markdown.updates == ["mount 前完成"]
    assert widget._final_view_applied is True


class RunningToolItemStub:
    def __init__(self, tool_id: str, display_text: str) -> None:
        self.tool_id = tool_id
        self.display_text = display_text
        self.removed = 0
        self.updated = 0

    def remove(self) -> None:
        self.removed += 1

    def _update(self) -> None:
        self.updated += 1

    def get_elapsed_time(self) -> float:
        return 1.25


from tui_components.messages import tool_status_panel as tool_status_panel_module

ToolStatusPanel = tool_status_panel_module.ToolStatusPanel
RunningToolItem = tool_status_panel_module.RunningToolItem


@pytest.fixture
def running_tool_item_stub(monkeypatch: pytest.MonkeyPatch) -> type[RunningToolItemStub]:
    monkeypatch.setattr(tool_status_panel_module, "RunningToolItem", RunningToolItemStub)
    return RunningToolItemStub

class ToolPanelHarness:
    MAX_VISIBLE_TOOLS = ToolStatusPanel.MAX_VISIBLE_TOOLS
    _start_timer_if_needed = ToolStatusPanel._start_timer_if_needed
    _stop_timer = ToolStatusPanel._stop_timer
    _update_running_tools = ToolStatusPanel._update_running_tools
    _extract_tool_name = staticmethod(ToolStatusPanel._extract_tool_name)
    def __init__(self) -> None:
        self._running_tools = {}
        self._timer = None
        self._mounted = False
        self.timers: list[TimerSpy] = []
        self.classes = set()
        self.styles = SimpleNamespace(display="none")
        self.mounted_items = []

    def set_interval(self, interval, callback):
        assert interval == 0.25
        timer = TimerSpy()
        self.timers.append(timer)
        return timer

    def mount(self, item) -> None:
        self.mounted_items.append(item)

    def refresh(self) -> None:
        return None

    def add_class(self, name) -> None:
        self.classes.add(name)

    def remove_class(self, name) -> None:
        self.classes.discard(name)


def test_tool_panel_timer_follows_zero_one_zero_restart_lifecycle(
    running_tool_item_stub: type[RunningToolItemStub],
) -> None:
    panel = ToolPanelHarness()
    ToolStatusPanel.on_mount(panel)
    assert panel.timers == []
    ToolStatusPanel.add_tool(panel, "one", "read_file: one")
    first = panel._timer
    assert first is panel.timers[0]
    ToolStatusPanel.add_tool(panel, "two", "execute_command: two")
    assert len(panel.timers) == 1
    assert ToolStatusPanel.remove_tool(panel, "one") == 1.25
    assert first.stop_calls == 0
    ToolStatusPanel.remove_tool(panel, "two")
    assert first.stop_calls == 1
    assert panel._timer is None
    ToolStatusPanel.add_tool(panel, "three", "search: three")
    assert len(panel.timers) == 2
    ToolStatusPanel.clear_all(panel)
    assert panel.timers[1].stop_calls == 1
    assert panel._running_tools == {}


def test_tool_panel_unmount_stops_shared_timer(
    running_tool_item_stub: type[RunningToolItemStub],
) -> None:
    panel = ToolPanelHarness()
    ToolStatusPanel.on_mount(panel)
    ToolStatusPanel.add_tool(panel, "one", "read_file: one")
    timer = panel._timer
    ToolStatusPanel.on_unmount(panel)
    assert timer.stop_calls == 1
    assert panel._timer is None
    assert panel._mounted is False


def test_real_running_tool_item_has_no_independent_timer_and_updates_child() -> None:
    item = RunningToolItem("one", "read_file: README.md")
    child = _DisplaySpy()
    item.query_one = lambda cls: child

    assert "on_mount" not in RunningToolItem.__dict__
    assert "set_interval" not in RunningToolItem.__dict__
    assert "_timer" not in RunningToolItem.__dict__
    assert "_timer" not in item.__dict__

    item._update()

    assert len(child.updates) == 1
    assert "read_file: README.md" in str(child.updates[0])


def test_request_indicator_repeated_start_stop_and_unmount_own_one_timer() -> None:
    indicator = RequestIndicator()
    timers: list[TimerSpy] = []
    intervals: list[float] = []
    indicator.set_interval = lambda interval, callback: (
        intervals.append(interval), timers.append(TimerSpy()), timers[-1]
    )[-1]
    indicator.remove_class = lambda name: None
    indicator.add_class = lambda name: None
    indicator.update = lambda value: None
    indicator.start_request()
    first = indicator.update_timer
    indicator.start_request()
    second = indicator.update_timer
    assert first.stop_calls == 1
    assert second is not first
    assert intervals == [0.25, 0.25]
    indicator.stop_request()
    indicator.stop_request()
    indicator.on_unmount()
    assert second.stop_calls == 1
    assert indicator.update_timer is None
    assert indicator.is_active is False


def test_clear_all_subagent_state_cancels_handles_and_clears_registries() -> None:
    owner = SubagentHarness(SubagentEventWidget())
    first = TimerSpy()
    second = TimerSpy()
    owner._subagent_trailing_handles = {"agent": first, "other": second}
    owner._subagent_last_ui_update = {"agent": 1.0, "other": 2.0}
    owner._subagent_widgets["other"] = SubagentEventWidget()
    owner._subagent_labels = {"agent": "one", "other": "two"}
    owner._clear_all_subagent_state()
    assert first.stop_calls == second.stop_calls == 1
    assert owner._subagent_trailing_handles == {}
    assert owner._subagent_last_ui_update == {}
    assert owner._subagent_widgets == {}
    assert owner._subagent_labels == {}


def test_handler_frame_uses_tail_and_lengths_without_raw_join(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_stream_fakes(monkeypatch)
    handler = _handler()
    handler.reset()
    widget = FakeBotWidget(SimpleNamespace(content=""))
    thinking = FakeThinkingWidget(snapshot_provider=None)
    thinking._collapsed = False
    handler.current_bot_message = widget
    handler._thinking_widget = thinking
    handler._content_buffer.append("body")
    handler._thinking_buffer.append("thought")
    handler._content_buffer.raw_text = lambda: (_ for _ in ()).throw(AssertionError("frame raw join"))
    handler._thinking_buffer.raw_text = lambda: (_ for _ in ()).throw(AssertionError("frame raw join"))

    asyncio.run(handler._flush_stream_snapshots())
    assert widget.snapshots == [("body", None)]
    assert thinking.snapshots == [(len("thought"), "thought")]


def test_cross_chunk_boundaries_are_repaired_for_final_bot_and_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stream_fakes(monkeypatch, thinking_collapsed=False)
    body = ["A\x1b[", "31mRED\x1b[0", "mB\r", "\nC\x1b]0;x", "\x07D"]
    thought = ["T\x1b[", "32mGREEN\x1b[0", "m ", "\U0001f469", "\u200d\U0001f4bb"]
    _run_chunks([
        AIMessageChunk(body_part, thinking=thought_part)
        for body_part, thought_part in zip(body, thought)
    ])
    assert FakeBotWidget.instances[0].finalized_with == [sanitize_display_text("".join(body))]
    assert FakeThinkingWidget.instances[0].snapshots[-1][1] == sanitize_display_text("".join(thought))


def test_update_widget_requests_single_slot_auto_follow_per_effective_frame() -> None:
    owner = MessageListHarness()
    widget = object()
    owner._update_widget = MessageList._update_widget.__get__(owner, MessageListHarness)
    owner._update_widget(widget)
    owner._update_widget(widget)
    assert len(owner.after_refresh) == 1


def test_new_user_message_resumes_paused_stream_and_replays_once() -> None:
    owner = MessageListHarness()
    owner._create_user_message_widget = MessageList._create_user_message_widget.__get__(owner, MessageListHarness)
    bot = GateBot()
    owner._install_stream_snapshot_gate(bot)
    owner.pause_stream_render()
    bot.apply_stream_snapshot("latest", None)
    owner._create_user_message_widget("next")
    assert owner.is_stream_render_paused is False
    assert bot.calls == [("snapshot", "latest", None)]


def test_subagent_paint_is_held_while_paused_and_replayed_once_on_resume() -> None:
    widget = SubagentEventWidget()
    owner = SubagentHarness(widget)
    owner._stream_render_paused = True
    owner._auto_scroll = False
    owner._pending_stream_snapshots = {}
    owner._safe_scroll_to_bottom = lambda: None
    owner.resume_stream_render = MessageList.resume_stream_render.__get__(owner, SubagentHarness)
    owner._paint_subagent("agent", widget)
    assert widget.display_updates == 0
    owner.resume_stream_render()
    assert widget.display_updates == 1


def test_subagent_callback_mount_replaces_and_unmount_compare_clears() -> None:
    from tools.subagent_tool import get_subagent_stream_callback, set_subagent_stream_callback

    first = MessageListHarness()
    first._on_subagent_event = lambda event: None
    first._register_subagent_callback = MessageList._register_subagent_callback.__get__(first, MessageListHarness)
    first._unregister_subagent_callback = MessageList._unregister_subagent_callback.__get__(first, MessageListHarness)
    first._register_subagent_callback()
    first_callback = get_subagent_stream_callback()

    second = MessageListHarness()
    second._on_subagent_event = lambda event: None
    second._register_subagent_callback = MessageList._register_subagent_callback.__get__(second, MessageListHarness)
    second._unregister_subagent_callback = MessageList._unregister_subagent_callback.__get__(second, MessageListHarness)
    second._register_subagent_callback()
    second_callback = get_subagent_stream_callback()
    assert second_callback == second._on_subagent_event
    first._unregister_subagent_callback()
    assert get_subagent_stream_callback() is second_callback
    second._unregister_subagent_callback()
    assert get_subagent_stream_callback() is None
    set_subagent_stream_callback(None)


def test_real_textual_mount_applies_bot_finalize_before_mount_once() -> None:
    from textual.app import App, ComposeResult

    class LifecycleApp(App):
        def __init__(self) -> None:
            super().__init__()
            self.bot = BotMessageWidget(SimpleNamespace(content=""))
            self.bot.apply_stream_snapshot("stream", None)
            self.bot.finalize("**final**")
        def compose(self) -> ComposeResult:
            yield self.bot

    async def scenario() -> None:
        app = LifecycleApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            static = app.bot.query_one("#content-static")
            markdown = app.bot.query_one("#content-md")
            assert app.bot._terminal_received is True
            assert app.bot._final_view_applied is True
            assert static.has_class("hidden")
            assert not markdown.has_class("hidden")

    asyncio.run(scenario())


def test_handler_wires_process_metrics_and_records_character_volumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Metrics:
        def __init__(self) -> None:
            self.increments: list[tuple[str, int]] = []
            self.observations: list[tuple[str, float]] = []
        def increment(self, name: str, value: int = 1) -> None:
            self.increments.append((name, value))
        def observe(self, name: str, value: float) -> None:
            self.observations.append((name, value))

    metrics = Metrics()
    monkeypatch.setattr(stream_handler_module, "get_perf_metrics", lambda: metrics)
    _install_stream_fakes(monkeypatch)
    handler = _run_chunks([AIMessageChunk("abc", thinking="xy")])
    assert handler._render_scheduler._metrics is metrics
    names = {name for name, _ in metrics.increments}
    assert {"stream.chunks", "stream.raw_chars", "stream.display_chars"} <= names
    assert any(name == "stream.sanitize" for name, _ in metrics.observations)


def test_tool_args_split_across_chunks_accumulate_complete_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """args 分片跨 chunk 到达时，最终 display 必须是完整命令而非 (empty)。

    用真实 langchain AIMessageChunk 而非测试 fake，因为真实 __add__ 对
    tool_calls 做结构化拼接，能反映生产环境的累积语义。
    """
    from langchain_core.messages import AIMessageChunk as RealAIMessageChunk

    _install_stream_fakes(monkeypatch)
    started: list[str] = []
    handler = _handler(on_tool_started=lambda tid, name: started.append(name))
    chunks = [
        RealAIMessageChunk(
            content="",
            tool_calls=[{"id": "call-1", "name": "execute_command", "args": {}}],
        ),
        RealAIMessageChunk(
            content="",
            tool_calls=[{"id": "call-1", "name": "execute_command", "args": {"command": "ls -la"}}],
        ),
        ToolMessage("call-1"),
    ]
    _run_chunks(chunks, handler)
    assert any("ls -la" in name for name in started), started
    assert not any("(empty)" in name for name in started), started
