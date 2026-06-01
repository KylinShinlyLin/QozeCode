#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自定义 Textual Driver，解决 iTerm2 下中文输入法 (IME) 无法使用的问题。

策略: 仅重写 write() 拦截 Kitty Keyboard Protocol 的启用序列 (\x1b[>1u),
让 iTerm2 回退到基础按键模式, 从而恢复 IME 中文输入。
"""

import os
from textual.drivers.linux_driver import LinuxDriver


class ITermDriver(LinuxDriver):
    """iTerm2 优化 Driver: 拦截 Kitty Keyboard Protocol 启用序列。"""

    @staticmethod
    def is_iterm() -> bool:
        return (
            os.environ.get("LC_TERMINAL", "") == "iTerm2"
            or os.environ.get("TERM_PROGRAM", "") == "iTerm.app"
            or "ITERM_SESSION_ID" in os.environ
        )

    def start_application_mode(self) -> None:
        """启动后立即禁用 Kitty 协议（此时 write 已可用）。"""
        super().start_application_mode()
        if ITermDriver.is_iterm():
            # 父类已发送 \x1b[>1u（已被 write 拦截）
            # 再显式发送 \x1b[>0u 确保彻底禁用
            super().write("\x1b[>0u")
            super().write("\x1b[<u")

    def write(self, data: str) -> None:
        """拦截 Kitty 协议启用序列 (\x1b[>1u)。"""
        if ITermDriver.is_iterm() and data == "\x1b[>1u":
            return  # 静默丢弃
        super().write(data)
