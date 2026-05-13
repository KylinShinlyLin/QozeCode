# -*- coding: utf-8 -*-
from rich.text import Text
from textual.widgets import Static


class StatusBar(Static):
    def __init__(self, model_name="Unknown"):
        super().__init__("")
        self.model_name = model_name
        self.state_desc = "Idle"
        self.state_style = None
        self.token_count = 0
        self.plan_mode = False

    def update_state(self, state, style=None):
        self.state_desc = state
        self.state_style = style
        self.refresh()

    def update_plan_mode(self, enabled: bool):
        self.plan_mode = enabled
        self.refresh()

    def update_token_count(self, count):
        """更新 token 数量显示"""
        try:
            self.token_count = int(count) if count is not None else 0
        except (ValueError, TypeError):
            self.token_count = 0
        self.refresh()

    def render(self):
        # 获取并格式化 token 数量
        try:
            count = int(self.token_count) if self.token_count is not None else 0
        except (ValueError, TypeError):
            count = 0

        if count >= 1000:
            token_str = f"{count / 1000:.1f}k"
        else:
            token_str = str(count)

        # 构建状态栏，逐段精确控制样式
        shortcuts = "输入 line | Ctrl+Q:语音输入 | Ctrl+C:终止 | Ctrl+D:提交"
        mode_tag = "[PLAN] " if self.plan_mode else ""

        if self.state_desc == "Idle":
            left = f" {mode_tag}{shortcuts}"
            result = Text(left, style="dim")

        elif self.state_style:
            result = Text(f" {mode_tag}", style="dim")
            result.append(f"{self.state_desc} | ", style=self.state_style)
            result.append(shortcuts, style="dim")

        else:
            left = f" {mode_tag}{self.state_desc} | {shortcuts}"
            result = Text(left, style="dim")

        result.append(" " * 5)
        result.append(f"Context: {token_str} tokens", style="dim")
        return result
