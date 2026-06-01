#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义 Textual Driver，解决 iTerm2 下中文输入法 (IME) 无法使用的问题。

问题根因: Textual 默认启用 Kitty Keyboard Protocol (`\x1b[>1u`),
但 iTerm2 对该协议的支持存在 bug, 会打断 macOS IME 的组合输入过程，
导致中文等 CJK 输入法无法正常工作。

解决方案: 在 iTerm2 环境中跳过 Kitty Keyboard Protocol 的启用/禁用，
让终端回退到基础按键处理模式，与 macOS Terminal.app 行为一致。

参考:
- https://github.com/anthropics/claude-code/issues/38694
- https://github.com/anthropics/claude-code/issues/51175
"""

import os
from textual.drivers.linux_driver import LinuxDriver


class ITermDriver(LinuxDriver):
    """针对 iTerm2 优化的 LinuxDriver, 禁用 Kitty Keyboard Protocol。

    通过重写 write 方法拦截并静默丢弃 Kitty Keyboard Protocol 的
    启用 (`\x1b[>1u`) 和禁用 (`\x1b[<u`) 序列, 使终端回退到基础
    按键处理模式, 恢复 IME 的正常工作。

    仅影响 iTerm2 环境, 其他终端仍使用标准 LinuxDriver 行为。
    """

    @staticmethod
    def is_iterm() -> bool:
        """检测当前是否运行在 iTerm2 中。"""
        return (
            os.environ.get("LC_TERMINAL", "") == "iTerm2"
            or os.environ.get("TERM_PROGRAM", "") == "iTerm.app"
        )

    def write(self, data: str) -> None:
        """写入数据到终端, 过滤 Kitty Keyboard Protocol 序列。

        在 iTerm2 环境下, 拦截并静默丢弃 Kitty Keyboard Protocol
        的启用/禁用序列, 其余数据正常透传。
        """
        # 仅在 iTerm2 环境下过滤, 其他终端不干预
        if ITermDriver.is_iterm():
            # 拦截 Kitty Keyboard Protocol 的启用 (\x1b[>1u) 和禁用 (\x1b[<u)
            if data in ("\x1b[>1u", "\x1b[<u"):
                return
        super().write(data)
