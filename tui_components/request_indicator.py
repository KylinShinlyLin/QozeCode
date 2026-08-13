# -*- coding: utf-8 -*-
import time
from rich.text import Text
from textual.widgets import Static
from .tui_constants import SPINNER_FRAMES


class RequestIndicator(Static):
    """Low-frequency request spinner with one explicitly owned interval timer."""

    UPDATE_INTERVAL = 0.25

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_active = False
        self.start_time = None
        self.update_timer = None

    def start_request(self):
        self.stop_request()
        self.is_active = True
        self.start_time = time.time()
        self.remove_class("hidden")
        self._update_display()
        self.update_timer = self.set_interval(self.UPDATE_INTERVAL, self._update_display)

    def stop_request(self):
        self.is_active = False
        self.start_time = None
        self.add_class("hidden")
        if self.update_timer is not None:
            self.update_timer.stop()
            self.update_timer = None

    def on_unmount(self):
        self.stop_request()

    def _update_display(self):
        if not self.is_active or self.start_time is None:
            return
        elapsed = time.time() - self.start_time
        frame = SPINNER_FRAMES[int(elapsed / self.UPDATE_INTERVAL) % len(SPINNER_FRAMES)]
        total_seconds = int(elapsed)
        time_str = f"{total_seconds // 3600:02d}:{(total_seconds % 3600) // 60:02d}:{total_seconds % 60:02d}"
        content = f"[bold cyan]{frame} Processing request... {time_str}[/]"
        self.update(Text.from_markup(content))
