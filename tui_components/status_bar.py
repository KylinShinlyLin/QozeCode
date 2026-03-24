# -*- coding: utf-8 -*-
from rich.text import Text
from textual.widgets import Static


class StatusBar(Static):
    def __init__(self, model_name="Unknown"):
        super().__init__("")
        self.model_name = model_name
        self.state_desc = "Idle"
        self.token_count = 0

    def update_state(self, state):
        self.state_desc = state
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

        # 构建左侧文本
        shortcuts = "输入 line | Ctrl+Q:语音输入 | Ctrl+C:终止 | Ctrl+D:提交"
        if self.state_desc == "Idle":
            left = f" {shortcuts}"
        else:
            left = f" {self.state_desc} | {shortcuts}"
        
        # 右侧 token 计数 - 使用固定的标签
        right = f"Context: {token_str} tokens"
        
        # 获取终端宽度
        try:
            width = self.size.width if self.size else 120
        except:
            width = 120
        
        # 计算填充空格
        total_len = len(left) + len(right) + 1
        padding = width - total_len
        if padding < 1:
            padding = 1
        
        # 组合完整行
        full_line = f"{left}{' ' * padding}{right}"
        
        # 返回 Text 对象，使用 dim 样式
        return Text(full_line, style="dim")
