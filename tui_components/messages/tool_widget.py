# tui_components/messages/tool_widget.py
from textual.widgets import Static
from textual.reactive import reactive
from textual.app import ComposeResult
from datetime import datetime

from .types import ToolMessage, ToolStatus
from ..tui_constants import SPINNER_FRAMES


class ToolMessageWidget(Static):
    """工具消息组件 - 自定义 Spinner 实现，支持多工具并行"""
    
    DEFAULT_CSS = """
    ToolMessageWidget {
        width: 100%;
        height: auto;
        margin: 0 0 1 0;
    }
    
    ToolMessageWidget.success {
        color: #9ece6a;
    }
    
    ToolMessageWidget.error {
        color: #f7768e;
    }
    
    ToolMessageWidget Static {
        width: 100%;
        height: auto;
    }
    """
    
    # reactive 属性
    status: reactive[ToolStatus] = reactive(ToolStatus.PENDING)
    display_text: reactive[str] = reactive("")
    elapsed_str: reactive[str] = reactive("")
    spinner_frame: reactive[int] = reactive(0)
    
    def __init__(self, message: ToolMessage, **kwargs):
        # 初始化所有本地属性（在调用父类之前）
        self._start_time = datetime.now()
        self._elapsed_time = 0.0
        self.message = message
        self._timer = None
        self._mounted = False  # 标记是否已挂载
        
        # 调用父类 __init__
        super().__init__(**kwargs)
        
        # 初始化 reactive 属性
        self.display_text = message.display_name or message.tool_name
        self.elapsed_str = "00:00"
        self.spinner_frame = 0
        
        # 注意：不在 __init__ 中设置 status，避免触发 watch_status 启动 timer
        # 而是在 on_mount 中处理
        self._initial_status = message.status
    
    def compose(self) -> ComposeResult:
        """组件组成 - 只包含一个 Static"""
        yield Static(self._render_text())
    
    def _render_text(self) -> str:
        """渲染当前状态的文本"""
        if self.status == ToolStatus.RUNNING:
            frame = SPINNER_FRAMES[self.spinner_frame % len(SPINNER_FRAMES)]
            return f"{frame} {self.display_text} {self.elapsed_str}"
        elif self.status == ToolStatus.SUCCESS:
            elapsed = f" in {self._elapsed_time:.2f}s" if self._elapsed_time > 0 else ""
            return f"✓ {self.display_text}{elapsed}"
        elif self.status == ToolStatus.ERROR:
            elapsed = f" in {self._elapsed_time:.2f}s" if self._elapsed_time > 0 else ""
            return f"✗ {self.display_text}{elapsed}"
        else:
            return f"⏳ {self.display_text}"
    
    def _update_display(self):
        """更新显示"""
        try:
            static = self.query_one(Static)
            static.update(self._render_text())
        except Exception:
            pass
    
    def _on_tick(self):
        """定时更新 - 更新时间和 spinner 帧"""
        if self.status == ToolStatus.RUNNING:
            # 计算经过时间
            elapsed = (datetime.now() - self._start_time).total_seconds()
            m, s = divmod(int(elapsed), 60)
            self.elapsed_str = f"{m:02d}:{s:02d}"
            
            # 更新 spinner 帧（每 tick 前进一帧）
            self.spinner_frame = (self.spinner_frame + 1) % len(SPINNER_FRAMES)
    
    def _start_timer(self):
        """启动定时器 - 100ms 更新一次"""
        if self._timer is None and self.status == ToolStatus.RUNNING and self._mounted:
            self._timer = self.set_interval(0.1, self._on_tick)
    
    def _stop_timer(self):
        """停止定时器"""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
    
    def watch_status(self, new_status: ToolStatus):
        """状态变化时更新"""
        # 移除旧的状态类
        self.remove_class("running", "success", "error")
        
        if new_status == ToolStatus.RUNNING:
            self.add_class("running")
            self._start_timer()
        elif new_status == ToolStatus.SUCCESS:
            self.add_class("success")
            self._stop_timer()
            self._elapsed_time = (datetime.now() - self._start_time).total_seconds()
        elif new_status == ToolStatus.ERROR:
            self.add_class("error")
            self._stop_timer()
            self._elapsed_time = (datetime.now() - self._start_time).total_seconds()
        
        # 更新显示
        self._update_display()
    
    def watch_display_text(self, new_text: str):
        """显示文本变化时"""
        self._update_display()
    
    def watch_elapsed_str(self, new_str: str):
        """时间字符串变化时"""
        if self.status == ToolStatus.RUNNING:
            self._update_display()
    
    def watch_spinner_frame(self, new_frame: int):
        """spinner 帧变化时"""
        if self.status == ToolStatus.RUNNING:
            self._update_display()
    
    def transition_to(self, new_status: ToolStatus, **kwargs):
        """状态转换接口"""
        if "display_name" in kwargs:
            self.display_text = kwargs["display_name"]
        if "elapsed_time" in kwargs:
            self._elapsed_time = kwargs["elapsed_time"]
        
        self.status = new_status
    
    def on_mount(self):
        """组件挂载时"""
        self._mounted = True
        # 应用初始状态
        if self._initial_status != self.status:
            self.status = self._initial_status
        elif self._initial_status == ToolStatus.RUNNING:
            # 如果初始状态是 RUNNING，启动 timer
            self._start_timer()
        self._update_display()
    
    def on_unmount(self):
        """组件卸载时清理"""
        self._mounted = False
        self._stop_timer()
