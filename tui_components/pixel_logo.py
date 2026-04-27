# -*- coding: utf-8 -*-
"""
像素块艺术字渲染器（10×7 精修版）
参考经典 8-bit 像素字体设计原则：圆角、等粗笔画、统一字怀
"""
from rich.text import Text

# 10×7 逻辑位图（0=空白, 1=主体）
PIXEL_FONT = {
    "Q": [
        [0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0],
        [0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0],
        [1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0],
        [1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0],
        [1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0],
        [0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0],
    ],
    "O": [
        [0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0],
        [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
        [1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 1],
        [1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1],
        [1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 1],
        [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
        [0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0],
    ],
    "Z": [
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
        [0, 0, 0, 0, 0, 0, 1, 1, 1, 0],
        [0, 0, 0, 0, 1, 1, 1, 0, 0, 0],
        [0, 0, 0, 1, 1, 1, 0, 0, 0, 0],
        [0, 0, 1, 1, 1, 0, 0, 0, 0, 0],
        [0, 1, 1, 1, 0, 0, 0, 0, 0, 0],
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
    ],
    "E": [
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
        [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
        [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
        [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
        [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
    ],
    "C": [
        [0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0],
        [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
        [1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
        [1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
        [0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0],
    ],
    "D": [
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0],
        [1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 0],
        [1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 1, 0],
        [1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 1, 0],
        [1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 1, 0],
        [1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 0],
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0],
    ],
    " ": [
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
    ],
}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _lerp_color(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def render_pixel_text(
        text: str,
        start_color: str,
        end_color: str,
        gap: int = 1,
) -> Text:
    """
    将字符串渲染为像素块艺术字（水平渐变）
    """
    text = text.upper()
    n = len(text)
    result_lines = [Text() for _ in range(7)]

    letter_colors = [
        _lerp_color(start_color, end_color, i / max(1, n - 1))
        for i in range(n)
    ]

    for idx, char in enumerate(text):
        matrix = PIXEL_FONT.get(char, PIXEL_FONT[" "])
        color = letter_colors[idx]
        width = len(matrix[0]) if matrix else 3
        for row in range(7):
            row_text = result_lines[row]
            for c in range(width):
                cell = matrix[row][c] if row < len(matrix) and c < width else 0
                if cell == 1:
                    row_text.append("█", style=color)
                else:
                    row_text.append(" ")
            if idx < n - 1:
                row_text.append(" " * gap)

    final = Text()
    for i, line in enumerate(result_lines):
        final.append(line)
        if i < len(result_lines) - 1:
            final.append("\n")
    return final
