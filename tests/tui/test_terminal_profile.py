import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tui_components import terminal_compat
from tui_components.terminal_compat import (
    TerminalRenderProfile,
    get_terminal_render_profile,
    sanitize_display_text,
)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (
            {},
            TerminalRenderProfile(
                name="default",
                frame_interval=0.05,
                busy_interval=0.10,
                tail_chars=32 * 1024,
                tail_lines=200,
            ),
        ),
        (
            {"TERMINAL_EMULATOR": "JetBrains-JediTerm"},
            TerminalRenderProfile(
                name="jediterm",
                frame_interval=0.10,
                busy_interval=0.166,
                tail_chars=16 * 1024,
                tail_lines=120,
            ),
        ),
        (
            {"TERMINAL_EMULATOR": "JEDITERM"},
            TerminalRenderProfile(
                name="jediterm",
                frame_interval=0.10,
                busy_interval=0.166,
                tail_chars=16 * 1024,
                tail_lines=120,
            ),
        ),
    ],
)
def test_terminal_render_profile(env, expected):
    assert get_terminal_render_profile(env) == expected


def test_terminal_render_profile_is_immutable():
    profile = get_terminal_render_profile({})

    with pytest.raises(FrozenInstanceError):
        profile.frame_interval = 1.0


@pytest.mark.parametrize("strip_emoji", [False, True])
def test_env_profile_does_not_change_existing_sanitize_or_emoji_semantics(
    monkeypatch, strip_emoji
):
    monkeypatch.setattr(terminal_compat, "STRIP_EMOJI", strip_emoji)
    text = "safe\x1b[31m red\x1b[0m\t😀 done"
    expected_default = sanitize_display_text(text)
    expected_keep = sanitize_display_text(text, strip_emoji=False)
    expected_strip = sanitize_display_text(text, strip_emoji=True)

    assert expected_keep == "safe red    😀 done"
    assert expected_strip == "safe red    done"

    get_terminal_render_profile(
        {
            "TERMINAL_EMULATOR": "JediTerm" if not strip_emoji else "other",
            "QOZE_STRIP_EMOJI": "1" if not strip_emoji else "0",
        }
    )

    assert terminal_compat.STRIP_EMOJI is strip_emoji
    assert sanitize_display_text(text) == expected_default
    assert sanitize_display_text(text, strip_emoji=False) == expected_keep
    assert sanitize_display_text(text, strip_emoji=True) == expected_strip


@pytest.mark.parametrize(
    "chunks",
    [
        ["safe\x1b[", "31mred\x1b[0", "m done"],
        ["before\x1b]8;;https://example.com", "\x07link\x1b]8;;\x07after"],
        ["line one\r", "\nline two"],
        ["coder \\U0001f469", "\u200d", "\\U0001f4bb done"],
    ],
)
def test_full_sanitize_is_authoritative_across_stream_boundaries(chunks):
    decoded = [chunk.encode().decode("unicode_escape") if "\\U" in chunk else chunk for chunk in chunks]
    raw = "".join(decoded)
    assert sanitize_display_text(raw) == sanitize_display_text("".join(decoded))
