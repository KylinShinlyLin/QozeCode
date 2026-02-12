# -*- coding: utf-8 -*-
from rich.text import Text
from textual.widgets import Static

class StatusBar(Static):
    def __init__(self, model_name="Unknown"):
        super().__init__()
        self.model_name = model_name
        self.state_desc = "Idle"

    def update_state(self, state):
        self.state_desc = state
        self.refresh()

    def render(self):
        shortcuts = []
        shortcuts.append("[dim]输入 line 多行编辑[/]")
        shortcuts.append("[dim]Ctrl+C[/]: 终止")
        shortcuts.append("[dim]Ctrl+D[/]: 提交")
        shortcuts_text = " | ".join(shortcuts)

        if self.state_desc == "Idle":
            return Text.from_markup(f" {shortcuts_text}")

        return Text.from_markup(f" {self.state_desc} | {shortcuts_text}")
