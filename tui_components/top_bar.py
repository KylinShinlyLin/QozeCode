# -*- coding: utf-8 -*-
from datetime import datetime
from rich.text import Text
from textual.widgets import Static

class TopBar(Static):
    def on_mount(self):
        self.set_interval(1, self.update_clock)
        self.call_after_refresh(self.update_clock)

    def update_clock(self):
        time_str = datetime.now().strftime("%H:%M:%S")
        total_width = self.content_size.width or 80
        right_label = f" {time_str} "
        spacer_width = max(0, total_width - len(" QozeCode  v0.3.8 ") - len(right_label))

        content = Text()
        content.append(" QozeCode ", style="bold white on #d75f00")
        content.append(" v0.3.8 ", style="bold white on #005faf")
        content.append(" " * spacer_width)
        content.append(right_label, style="bold white on #333333")
        self.update(content)
