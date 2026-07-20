# tui_components/terminal_compat.py
# -*- coding: utf-8 -*-
"""
终端兼容层：规避 JetBrains 终端（JediTerm）emoji 宽度渲染不稳定导致的像素错乱。

背景：
Rich/Textual 依据 wcwidth 计算字符宽度（emoji 默认呈现码点计为 1 格），
但 JediTerm（尤其新版 Reworked Terminal）将它们渲染为 2 格宽的 emoji 图形，
宽度不一致导致差分重绘后在屏幕上残留像素块。

策略：
仅在检测到 JetBrains 终端时，于「显示边界」剥离问题字符——
原始内容（buffer / 消息对象）完全不受影响，仅净化显示文本。
其他终端（iTerm2、系统终端等）不做任何处理。

剥离范围（精确清单，不误伤正常字符）：
- U+1F000–U+1FAFF 全部 pictograph 区块（📂🌿🐛👋 等，终端必渲染为宽 emoji）
- 2600–26FF / 2700–27BF / 2B00–2BFF 中 Emoji_Presentation=Yes 的码点
  （✅❌⭐❤ 等；✓(2713) ⚠(26A0) 等 text 默认呈现的符号刻意保留）
- VS16(FE0F) / ZWJ(200D) / 键帽符(20E3) / 标签字符（emoji 组合序列成分）

环境变量 QOZE_STRIP_EMOJI=1 / 0 可强制开启/关闭该行为（调试用）。
"""
import os
import re


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


def sanitize_display_text(text: str) -> str:
    """JetBrains 终端下去除 emoji，其他终端原样返回。"""
    if not STRIP_EMOJI or not text:
        return text
    text = _COMBINING_RE.sub("", text)
    return _EMOJI_RUN_RE.sub("", text)
