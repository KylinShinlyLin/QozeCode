"""Behavior tests for the incremental raw/display text buffer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tui_components.messages.display_buffer import IncrementalDisplayBuffer
from tui_components.terminal_compat import sanitize_display_text


def test_append_sanitizes_each_nonempty_chunk_once_and_preserves_raw_text() -> None:
    calls: list[str] = []

    def sanitizer(chunk: str) -> str:
        calls.append(chunk)
        return sanitize_display_text(chunk, strip_emoji=True)

    chunks = [
        "中文\x1b[31m红色\x1b[0m 😀",
        "\n第二行",
        "\n",
        "末行\t完成",
    ]
    buffer = IncrementalDisplayBuffer(sanitizer, tail_chars=1024, tail_lines=20)

    for chunk in chunks:
        buffer.append(chunk)

    assert calls == chunks
    assert buffer.raw_text() == "".join(chunks)
    assert buffer.display_text(tail_only=False) == "".join(
        sanitize_display_text(chunk, strip_emoji=True) for chunk in chunks
    )
    assert "\x1b" in buffer.raw_text()
    assert "😀" in buffer.raw_text()
    assert "\x1b" not in buffer.display_text(tail_only=False)
    assert "😀" not in buffer.display_text(tail_only=False)


def test_tail_applies_character_budget_then_line_budget_without_rewriting_text() -> None:
    buffer = IncrementalDisplayBuffer(lambda text: text, tail_chars=12, tail_lines=2)
    buffer.append("zero\none\ntwo\nthree\nfour")

    # The 12-character suffix is "o\nthree\nfour"; its final two lines are retained.
    assert buffer.display_text() == "three\nfour"
    assert len(buffer.display_text()) <= 12
    assert len(buffer.display_text().splitlines()) <= 2

    no_newline = IncrementalDisplayBuffer(lambda text: text, tail_chars=5, tail_lines=2)
    no_newline.append("abc\ndef")
    assert no_newline.display_text() == "c\ndef"
    assert not no_newline.display_text().startswith("\n")
    assert not no_newline.display_text().endswith("\n")


def test_raw_and_full_display_joins_are_cached_for_the_current_version() -> None:
    buffer = IncrementalDisplayBuffer(str.upper, tail_chars=4096, tail_lines=100)
    buffer.append("first chunk " * 20)
    buffer.append("second chunk " * 20)

    raw_first = buffer.raw_text()
    raw_second = buffer.raw_text()
    display_first = buffer.display_text(tail_only=False)
    display_second = buffer.display_text(tail_only=False)

    assert raw_first is raw_second
    assert display_first is display_second

    previous_version = buffer.version
    buffer.append("new chunk " * 20)
    assert buffer.version == previous_version + 1
    assert buffer.raw_text() is not raw_first
    assert buffer.display_text(tail_only=False) is not display_first


def test_empty_append_is_a_noop_and_clear_invalidates_content() -> None:
    calls = 0

    def sanitizer(chunk: str) -> str:
        nonlocal calls
        calls += 1
        return chunk

    buffer = IncrementalDisplayBuffer(sanitizer, tail_chars=100, tail_lines=10)
    initial_version = buffer.version
    initial_raw = buffer.raw_text()
    initial_display = buffer.display_text(tail_only=False)

    buffer.append("")

    assert calls == 0
    assert buffer.version == initial_version
    assert buffer.raw_text() is initial_raw
    assert buffer.display_text(tail_only=False) is initial_display

    buffer.append("content")
    version_before_clear = buffer.version
    assert calls == 1

    buffer.clear()

    assert buffer.version == version_before_clear + 1
    assert buffer.raw_text() == ""
    assert buffer.display_text(tail_only=False) == ""
    assert buffer.display_text() == ""
    assert calls == 1

    buffer.clear()
    assert buffer.version == version_before_clear + 2


def test_tail_window_does_not_build_full_display_and_exposes_lengths(monkeypatch) -> None:
    buffer = IncrementalDisplayBuffer(lambda text: text, tail_chars=8, tail_lines=2)
    for chunk in ("prefix-", "one\ntwo\n", "three"):
        buffer.append(chunk)

    monkeypatch.setattr(
        buffer,
        "_full_display_text",
        lambda: (_ for _ in ()).throw(AssertionError("tail must not full-join")),
    )
    assert buffer.display_text() == "wo\nthree"
    assert buffer.raw_length == len("prefix-one\ntwo\nthree")
    assert buffer.display_length == len("prefix-one\ntwo\nthree")


def test_authoritative_display_repairs_cross_chunk_control_boundaries() -> None:
    chunks = [
        "A\x1b[", "31mRED\x1b[0", "mB\r", "\nC\x1b]0;ti", "tle\x07D",
        " family:\U0001f469", "\u200d\U0001f4bb",
    ]
    buffer = IncrementalDisplayBuffer(sanitize_display_text, tail_chars=1024, tail_lines=20)
    for chunk in chunks:
        buffer.append(chunk)

    raw = "".join(chunks)
    assert buffer.raw_text() == raw
    assert buffer.authoritative_display_text() == sanitize_display_text(raw)


def test_tail_cache_never_scans_empty_display_history_and_stays_bounded() -> None:
    class HistoryAccessForbidden(list[str]):
        def __iter__(self):
            raise AssertionError("tail lookup must not iterate display chunk history")

        def __reversed__(self):
            raise AssertionError("tail lookup must not reverse display chunk history")

    buffer = IncrementalDisplayBuffer(lambda _text: "", tail_chars=18, tail_lines=2)
    for _ in range(10_000):
        buffer.append("raw")

    assert buffer.raw_length == 30_000
    assert buffer.display_length == 0
    assert buffer.version == 10_000
    buffer._display_chunks = HistoryAccessForbidden(buffer._display_chunks)
    assert buffer.display_text(tail_only=True) == ""

    mixed = IncrementalDisplayBuffer(lambda text: text, tail_chars=18, tail_lines=2)
    mixed.append(("discarded line\n" * 1_000) + "alpha\nbeta")
    mixed.append("\ngamma\ndelta")
    assert mixed.display_text(tail_only=True) == "gamma\ndelta"
    assert len(mixed._tail_cache) <= 18
    assert len(mixed._tail_cache.splitlines()) <= 2

    mixed.clear()
    assert mixed.display_text(tail_only=True) == ""
    assert mixed.raw_length == 0
    assert mixed.display_length == 0
