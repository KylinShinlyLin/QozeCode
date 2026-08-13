# tui_components/terminal_compat.py
# -*- coding: utf-8 -*-
"""
终端兼容层：展示边界净化，规避特殊 Unicode 字符导致的 UI 错乱。

背景：
Rich/Textual 依据 wcwidth 计算字符宽度，但部分终端（如 JetBrains 终端
JediTerm）对 emoji 宽度渲染不稳定；而复制粘贴进 TUI 的文本常携带
控制字符 / ANSI 转义 / 零宽字符 / 双向控制符等，会在任意终端引发错位、
残影甚至指令注入。本模块在「显示边界」统一净化，原始内容
（message.content / buffer）完全不受影响，仅净化展示文本。

净化分层：
1. 通用净化（总是执行，任何终端都有益）：
   - C0/C1 控制字符、ANSI/终端转义序列（防错位与注入）
   - 零宽字符、双向文本控制符、BOM、软连字符（复制粘贴常见）
   - 未配对代理、非字符、私用区（PUA）码点
   - tab 归一为 4 空格
2. emoji 剥离（可选，由参数/环境决定）：
   - strip_emoji=None -> 按 QOZE_STRIP_EMOJI 环境变量或终端检测（JediTerm）
   - strip_emoji=True  -> 强制剥离（如用户输入展示）
   - strip_emoji=False -> 保留 emoji（仅通用净化）

环境变量 QOZE_STRIP_EMOJI=1 / 0 可强制开启/关闭 emoji 剥离（调试用）。
"""
import os
import re
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class TerminalRenderProfile:
    """Terminal-specific refresh and retained-tail budgets."""

    name: str
    frame_interval: float
    busy_interval: float
    tail_chars: int
    tail_lines: int


def get_terminal_render_profile(
    env: Mapping[str, str] | None = None,
) -> TerminalRenderProfile:
    """Return render budgets for the supplied environment without side effects."""
    source = os.environ if env is None else env
    is_jediterm = "jediterm" in source.get("TERMINAL_EMULATOR", "").lower()
    if is_jediterm:
        return TerminalRenderProfile(
            name="jediterm",
            frame_interval=0.10,
            busy_interval=0.166,
            tail_chars=16 * 1024,
            tail_lines=120,
        )
    return TerminalRenderProfile(
        name="default",
        frame_interval=0.05,
        busy_interval=0.10,
        tail_chars=32 * 1024,
        tail_lines=200,
    )


def _detect_jediterm() -> bool:
    return "jediterm" in os.environ.get("TERMINAL_EMULATOR", "").lower()


_override = os.environ.get("QOZE_STRIP_EMOJI", "").strip().lower()
if _override in ("1", "true", "yes", "on"):
    STRIP_EMOJI = True
elif _override in ("0", "false", "no", "off"):
    STRIP_EMOJI = False
else:
    STRIP_EMOJI = _detect_jediterm()

# 2600–26FF 中 Emoji_Presentation=Yes 的码点（⚠(26A0) 为 text 默认，保留）
_MISC_EMOJI = (
    "\u2600-\u2604\u260e\u2611\u2614-\u2615\u2618\u261d\u2620\u2622-\u2623"
    "\u2626\u262a\u262e-\u262f\u2638-\u263a\u2640\u2642\u2648-\u2653"
    "\u265f-\u2660\u2663\u2665-\u2666\u2668\u267b\u267e-\u267f"
    "\u2692-\u2697\u2699\u269b-\u269c\u26a1\u26aa-\u26ab\u26b0-\u26b1"
    "\u26bd-\u26be\u26c4-\u26c5\u26c8\u26ce-\u26cf\u26d1\u26d3-\u26d4"
    "\u26e9-\u26ea\u26f0-\u26f5\u26f7-\u26fa\u26fd"
)
# 2700–27BF 中 Emoji_Presentation=Yes 的码点（✓(2713) ✗(2717) 等保留）
_DINGBAT_EMOJI = (
    "\u2705\u2708-\u270d\u270f\u2712\u2714\u2716\u271d\u2721\u2728"
    "\u2733-\u2734\u2744\u2747\u274c\u274e\u2753-\u2755\u2757"
    "\u2763-\u2764\u2795-\u2797\u27a1\u27b0\u27bf"
)

# ── 通用净化正则（任何终端都执行）──────────────────────────────

# C0 控制符（保留 \n；\t 单独归一；\r 已在换行归一阶段删除）
_C0_CONTROL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
# C1 控制符（0x80-0x9F）
_C1_CONTROL_RE = re.compile("[\x80-\x9f]")
# ANSI/终端转义序列（ESC 开头：CSI / OSC / 单字符）
_ANSI_ESCAPE_RE = re.compile(
    "\x1b(?:\\[[0-?]*[ -/]*[@-~]|\\][^\\x07]*(?:\\x07|\\x1b\\\\)|[@-Z\\-_]|.)"
)
# 零宽与格式控制（保留 ZWJ \u200d 以维持组合 emoji 序列完整）
_ZERO_WIDTH_RE = re.compile(
    "[\u200b-\u200c\u200e-\u200f\u202a-\u202e\u2060-\u206f\ufeff\u180e\u00ad]"
)
# 未配对代理（独立出现的 surrogate）
_SURROGATE_RE = re.compile("[\ud800-\udfff]")
# 非字符（U+FDD0-FDEF、各 plane 末两位）
_NONCHAR_RE = re.compile(
    "[\ufdd0-\ufdef\ufffe\uffff"
    "\U0001fffe-\U0001ffff\U0002fffe-\U0002ffff\U0003fffe-\U0003ffff"
    "\U0004fffe-\U0004ffff\U0005fffe-\U0005ffff\U0006fffe-\U0006ffff"
    "\U0007fffe-\U0007ffff\U0008fffe-\U0008ffff\U0009fffe-\U0009ffff"
    "\U000afffe-\U000affff\U000bfffe-\U000bffff\U000cfffe-\U000cffff"
    "\U000dfffe-\U000dffff\U000efffe-\U000effff\U000ffffe-\U000fffff]"
)
# 私用区（PUA，多终端渲染为乱码方块）
_PUA_RE = re.compile("[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]")

# ── emoji 剥离正则（按 STRIP_EMOJI 决定）────────────────────────

# 组合符单独先行移除（不吞空格）：⚠️ -> ⚠（text 呈现，宽度一致）
_COMBINING_RE = re.compile("[\uFE0F\u200D\u20E3\U000E0020-\U000E007F]")
# emoji 本体移除，连同尾随的一个空格，保持排版整洁
_EMOJI_RUN_RE = re.compile(
    "(?:["
    "\U0001F000-\U0001FAFF"  # 表情/符号/交通/动植物等全部 pictograph 区块
    "\u2B00-\u2BFF"          # 补充符号（⭐⬛ 等）
    + _MISC_EMOJI + _DINGBAT_EMOJI +
    "])+ ?"
)


def sanitize_display_text(text: str, strip_emoji: Optional[bool] = None) -> str:
    """展示层净化：剥离会导致终端 UI 错乱的特殊 Unicode 字符。

    仅在展示边界调用；AI 上下文（message.content / buffer）保持原始内容。

    Args:
        text: 待净化的展示文本
        strip_emoji: emoji 剥离开关
            None  -> 按环境变量 QOZE_STRIP_EMOJI 或终端检测（默认）
            True  -> 强制剥离 emoji（如用户输入展示）
            False -> 保留 emoji（仅通用净化）

    Returns:
        净化后的展示文本
    """
    if not text:
        return text

    # 1) 换行归一 + 删除 \r（复制粘贴内容常见 \r\n）
    text = text.replace("\r\n", "\n").replace("\r", "")

    # 2) 通用净化（总是执行）
    # 注意顺序：ANSI 转义须先于 C0 控制符处理，否则 ESC 被替换为空格后无法识别序列
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\x1b", "")  # 兜底：清除残留 ESC
    text = _C0_CONTROL_RE.sub(" ", text)
    text = _C1_CONTROL_RE.sub("", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _SURROGATE_RE.sub("", text)
    text = _NONCHAR_RE.sub("", text)
    text = _PUA_RE.sub(" ", text)

    # 3) tab → 4 空格（避免终端 tab 宽度不一致错位）
    text = text.replace("\t", "    ")

    # 4) emoji 剥离（可选）
    if strip_emoji is None:
        strip_emoji = STRIP_EMOJI
    if strip_emoji:
        text = _COMBINING_RE.sub("", text)
        text = _EMOJI_RUN_RE.sub("", text)

    return text
