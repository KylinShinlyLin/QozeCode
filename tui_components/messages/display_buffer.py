"""Incremental storage for raw stream text and sanitized display text."""

from __future__ import annotations

from collections.abc import Callable


class IncrementalDisplayBuffer:
    """Keep raw/display chunks with an O(tail budget) streaming window."""

    def __init__(
        self,
        sanitizer: Callable[[str], str],
        tail_chars: int,
        tail_lines: int,
    ) -> None:
        self._sanitizer = sanitizer
        self._tail_chars = tail_chars
        self._tail_lines = tail_lines
        self._raw_chunks: list[str] = []
        self._display_chunks: list[str] = []
        self.raw_length = 0
        self.display_length = 0
        self.version = 0
        self._raw_cache_version = self.version
        self._raw_cache = ""
        self._display_cache_version = self.version
        self._display_cache = ""
        self._tail_cache = ""

    def append(self, raw_chunk: str) -> None:
        """Append one chunk, preserving per-chunk streaming sanitization."""
        if not raw_chunk:
            return
        display_chunk = self._sanitizer(raw_chunk)
        self._raw_chunks.append(raw_chunk)
        self._display_chunks.append(display_chunk)
        self.raw_length += len(raw_chunk)
        self.display_length += len(display_chunk)
        self._tail_cache = self._make_tail(self._tail_cache + display_chunk)
        self.version += 1

    def raw_text(self) -> str:
        """Join complete raw text only for terminal/explicit consumers."""
        if self._raw_cache_version != self.version:
            self._raw_cache = "".join(self._raw_chunks)
            self._raw_cache_version = self.version
        return self._raw_cache

    def display_text(self, tail_only: bool = True) -> str:
        """Return a bounded streaming tail, or explicitly join all display chunks."""
        if not tail_only:
            return self._full_display_text()
        return self._tail_cache

    def authoritative_display_text(self, tail_only: bool = False) -> str:
        """Sanitize complete raw text at terminal boundaries to repair split sequences."""
        display = self._sanitizer(self.raw_text())
        return self._make_tail(display) if tail_only else display

    def clear(self) -> None:
        self._raw_chunks.clear()
        self._display_chunks.clear()
        self.raw_length = 0
        self.display_length = 0
        self._tail_cache = ""
        self.version += 1

    def _full_display_text(self) -> str:
        if self._display_cache_version != self.version:
            self._display_cache = "".join(self._display_chunks)
            self._display_cache_version = self.version
        return self._display_cache

    def _make_tail(self, display: str) -> str:
        if self._tail_chars <= 0 or self._tail_lines <= 0:
            return ""
        character_tail = display[-self._tail_chars :]
        lines = character_tail.splitlines(keepends=True)
        return "".join(lines[-self._tail_lines :])
