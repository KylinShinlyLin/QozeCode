# tui_components/messages/thinking_widget.py
"""A collapsible, scheduler-driven thinking display."""
from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from .auto_copy_widgets import AutoCopyStatic


class ThinkingWidget(Static):
    """Keep hidden content cold and fetch its latest tail only when expanded."""

    DEFAULT_CSS = """
    ThinkingWidget {
        width: 100%;
        height: auto;
        margin: 0 0 1 0;
    }

    ThinkingWidget > Vertical {
        width: 100%;
        height: auto;
        margin: 0;
        padding: 0;
    }

    ThinkingWidget .thinking-header {
        color: #808080;
        text-style: italic;
        height: auto;
        margin: 0;
        padding: 0;
    }

    ThinkingWidget .thinking-content {
        color: #808080;
        text-style: italic;
        margin: 0;
        padding: 0 0 0 2;
        height: auto;
    }

    ThinkingWidget .hidden {
        display: none;
    }
    """

    def __init__(
        self,
        snapshot_provider: Callable[[], str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._snapshot_provider = snapshot_provider
        self._char_count = 0
        self._display_tail = None
        self._collapsed = True
        self._mounted = False
        self._is_finalized = False
        self._header_widget = None
        self._content_widget = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield AutoCopyStatic(
                "已思考 0 字符 ▸",
                classes="thinking-header",
                id="thinking-header",
            )
            yield AutoCopyStatic(
                "",
                classes="thinking-content hidden",
                id="thinking-content",
            )

    def on_mount(self) -> None:
        self._mounted = True
        try:
            self._header_widget = self.query_one("#thinking-header", Static)
            self._content_widget = self.query_one("#thinking-content", Static)
        except Exception:
            return
        self._update_header()
        if not self._collapsed:
            self._content_widget.remove_class("hidden")
            self._update_expanded_content()

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def apply_snapshot(self, char_count: int, display_tail: str | None) -> None:
        """Apply one frame without touching hidden content while collapsed."""
        self._char_count = char_count
        if not self._mounted:
            if display_tail is not None:
                self._display_tail = display_tail
            return

        self._update_header()
        if self._collapsed or display_tail is None:
            return

        self._display_tail = display_tail
        self._content_widget.update(display_tail or " ")

    def finalize(self) -> None:
        if self._is_finalized:
            return
        self._is_finalized = True
        if self._mounted:
            self._update_header()

    def _update_header(self) -> None:
        if self._header_widget is None:
            return
        if self._is_finalized:
            marker = "✓"
        else:
            marker = "▸" if self._collapsed else "▾"
        self._header_widget.update(f"已思考 {self._char_count:,} 字符 {marker}")

    def _update_expanded_content(self) -> None:
        """Read the round snapshot lazily, including after scheduler shutdown."""
        if self._content_widget is None:
            return
        display_tail = self._display_tail
        if self._snapshot_provider is not None:
            try:
                display_tail = self._snapshot_provider()
            except Exception:
                pass
        if display_tail is not None:
            self._display_tail = display_tail
            self._content_widget.update(display_tail or " ")

    def on_click(self, event) -> None:
        event.stop()
        self._collapsed = not self._collapsed
        if self._mounted and self._content_widget is not None:
            if self._collapsed:
                self._content_widget.add_class("hidden")
            else:
                self._content_widget.remove_class("hidden")
                self._update_expanded_content()
            self._update_header()
