# tui_components/messages/tool_widget.py
from textual.widgets import Static
from textual.reactive import reactive
from datetime import datetime

from .types import ToolMessage, ToolStatus


class ToolMessageWidget(Static):
    """工具消息组件 - 带 spinner 动画"""
    
    DEFAULT_CSS = """
    ToolMessageWidget {
        width: 100%;
        height: auto;
        color: #7aa2f7;
        margin: 0 0 1 0;
    }
    
    ToolMessageWidget.success {
        color: #9ece6a;
    }
    
    ToolMessageWidget.error {
        color: #f7768e;
    }
    """
    
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    
    # reactive 属性
    status: reactive[ToolStatus] = reactive(ToolStatus.PENDING)
    display_text: reactive[str] = reactive("")
    elapsed_time: reactive[float] = reactive(0.0)
    
    def __init__(self, message: ToolMessage, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self.status = message.status
        self._spinner_idx = 0
        self._timer = None
        self._start_time = datetime.now()
        
        # 初始显示文本
        self.display_text = message.display_name or message.tool_name
    
    def compose(self):
        yield Static(self._get_display_text())
    
    def _get_display_text(self) -> str:
        """根据状态生成显示文本"""
        if self.status == ToolStatus.RUNNING:
            # 执行中：显示 spinner + 工具名 + 计时
            frame = self.SPINNER_FRAMES[self._spinner_idx % len(self.SPINNER_FRAMES)]
            m, s = divmod(int(self.elapsed_time), 60)
            return f"{frame} {self.display_text} {m:02d}:{s:02d}"
        elif self.status == ToolStatus.SUCCESS:
            # 成功：显示 ✓ + 工具名
            return f"✓ {self.display_text}"
        elif self.status == ToolStatus.ERROR:
            # 失败：显示 ✗ + 工具名
            return f"✗ {self.display_text}"
        else:
            # 等待中
            return f"⏳ {self.display_text}"
    
    def watch_status(self, new_status: ToolStatus):
        """状态变化时更新显示"""
        # 更新样式类
        self.remove_class("running", "success", "error")
        
        if new_status == ToolStatus.RUNNING:
            self.add_class("running")
            self._start_spinner()
        elif new_status == ToolStatus.SUCCESS:
            self.add_class("success")
            self._stop_spinner()
        elif new_status == ToolStatus.ERROR:
            self.add_class("error")
            self._stop_spinner()
        
        # 立即更新显示
        self._update_display()
    
    def watch_elapsed_time(self, elapsed: float):
        """计时变化时更新（仅在 running 状态）"""
        if self.status == ToolStatus.RUNNING:
            self._update_display()
    
    def _start_spinner(self):
        """启动 spinner 动画定时器"""
        if self._timer is None:
            self._timer = self.set_interval(0.1, self._on_spinner_tick)
    
    def _stop_spinner(self):
        """停止 spinner 动画"""
        if self._timer:
            self._timer.stop()
            self._timer = None
    
    def _on_spinner_tick(self):
        """spinner 动画帧更新"""
        self._spinner_idx += 1
        # 更新计时
        self.elapsed_time = (datetime.now() - self._start_time).total_seconds()
        self._update_display()
    
    def _update_display(self):
        """更新显示内容"""
        try:
            static = self.query_one(Static)
            static.update(self._get_display_text())
        except Exception:
            pass
    
    def transition_to(self, new_status: ToolStatus, **kwargs):
        """状态转换接口"""
        if "display_name" in kwargs:
            self.display_text = kwargs["display_name"]
        if "elapsed_time" in kwargs:
            self.elapsed_time = kwargs["elapsed_time"]
        self.status = new_status
    
    def on_mount(self):
        """组件挂载时初始化"""
        if self.status == ToolStatus.RUNNING:
            self._start_spinner()
        self._update_display()
