#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义 Textual Driver，解决 iTerm2 下中文输入法 (IME) 无法使用的问题。

问题根因: Textual 默认启用 Kitty Keyboard Protocol (`\x1b[>1u`),
但 iTerm2 对该协议的支持存在 bug, 会打断 macOS IME 的组合输入过程，
导致中文等 CJK 输入法无法正常工作。

解决方案: 在 iTerm2 环境中跳过 Kitty Keyboard Protocol 的启用，
但保留退出时的禁用 (清理可能遗留的协议状态)。
"""

import os
from textual.drivers.linux_driver import LinuxDriver


class ITermDriver(LinuxDriver):
    """针对 iTerm2 优化的 LinuxDriver, 禁用 Kitty Keyboard Protocol。

    仅拦截 Kitty 协议的 **启用** 序列 (`\x1b[>1u`),
    保留 **禁用** 序列 (`\x1b[<u`) 透传, 确保退出时能清理
    终端状态, 避免整个 iTerm2 被污染。
    """

    @staticmethod
    def is_iterm() -> bool:
        """检测当前是否运行在 iTerm2 中。"""
        return (
            os.environ.get("LC_TERMINAL", "") == "iTerm2"
            or os.environ.get("TERM_PROGRAM", "") == "iTerm.app"
        )

    def write(self, data: str) -> None:
        """写入数据到终端, 仅过滤 Kitty Keyboard Protocol 的启用序列。

        重要: 不禁用序列 `\x1b[<u` 必须透传, 否则退出应用后
        iTerm2 会残留 Kitty 协议状态, 导致整个终端输出乱码。
        """
        if ITermDriver.is_iterm() and data == "\x1b[>1u":
            return  # 静默丢弃 Kitty 协议启用, IME 恢复正常
        super().write(data)
