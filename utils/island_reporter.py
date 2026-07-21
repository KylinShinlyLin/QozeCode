# -*- coding: utf-8 -*-
"""
QozeIsland 状态上报客户端 (M1 + 自动重连)

职责:
- 连接 ~/.qoze/island.sock (QozeIsland.app 监听的 Unix Domain Socket)
- 后台 daemon 线程异步发送 NDJSON 状态消息, 绝不阻塞 Agent 主流程
- 自动重连: 初始连接失败或运行中断线后, 每 5s 静默重试;
  重连成功立即补发 session.register + 缓存的最新状态
- App 不存在 / 未启动时静默降级, 不影响任何终端交互

协议见 docs/qozeisland-tech-design.md §3
"""

import atexit
import json
import subprocess
import os
import queue
import socket
import sys
import threading
import time
import uuid

SOCKET_PATH = os.path.expanduser("~/.qoze/island.sock")
PROTOCOL_VERSION = 1
RECONNECT_INTERVAL = 5.0  # 秒
HEARTBEAT_INTERVAL = 5.0   # 秒: 空闲心跳, 用于探测死连接 (idle 会话不写消息, 只能靠心跳发现断线)
_MAX_DETAIL_LEN = 200     # detail 字符串字段截断长度


def _truncate(value, limit=_MAX_DETAIL_LEN):
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value


# ---------------- Island App 启动器 (macOS) ----------------

ISLAND_APP_PATH = os.path.expanduser("~/Applications/QozeCode.app")


def is_island_installed() -> bool:
    """QozeCode 菜单栏 App 是否已构建安装 (~/Applications/QozeCode.app)"""
    return sys.platform == "darwin" and os.path.isfile(
        os.path.join(ISLAND_APP_PATH, "Contents", "MacOS", "QozeCode"))


def is_island_running() -> bool:
    """QozeCode 菜单栏 App 进程是否在运行"""
    if sys.platform != "darwin":
        return False
    try:
        return subprocess.run(
            ["pgrep", "-x", "QozeCode"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0
    except OSError:
        return False


def launch_island():
    """唤起 QozeCode.app (open 立即返回, 不等待 App 就绪)。

    Returns: (ok: bool, message: str)
    """
    if sys.platform != "darwin":
        return False, "Island 仅支持 macOS"
    if not is_island_installed():
        return False, "未安装 QozeCode 菜单栏 App, 请先执行: bash macos/build_island.sh"
    try:
        subprocess.Popen(["open", ISLAND_APP_PATH],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "已唤起 QozeCode"
    except OSError as e:
        return False, f"唤起失败: {e}"


def maybe_auto_launch_island() -> bool:
    """qoze 启动时按需自动唤起 Island (任一条件不满足即静默跳过)。

    条件链: macOS → [island] enabled → [island] auto_launch → 已安装 → 未运行
    唤起后由 Reporter 的周期重连自动接入, 无需在此等待 App 就绪。
    """
    if sys.platform != "darwin":
        return False
    try:
        from config_manager import get_island_enabled, get_island_auto_launch
        if not get_island_enabled() or not get_island_auto_launch():
            return False
    except Exception:
        return False
    if not is_island_installed() or is_island_running():
        return False
    ok, _ = launch_island()
    return ok


class IslandReporter:
    """QozeIsland 状态上报器 (单例使用, 全部方法线程安全、绝不抛异常)"""

    def __init__(self, model: str = ""):
        self.enabled = False
        self.session_id = uuid.uuid4().hex[:8]
        self._model = model
        self._sock = None
        self._queue = queue.Queue(maxsize=256)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._latest_state = None  # 最近一次 state 消息, 重连后补发
        self._last_activity = time.monotonic()  # 最近一次成功发送时间

        self._try_connect()
        threading.Thread(target=self._manager_loop, daemon=True,
                         name="island-reporter").start()
        atexit.register(self.shutdown)

    @staticmethod
    def _detect_host_app() -> dict:
        """沿进程树向上找最近的 GUI 应用 (.app/Contents/MacOS)。

        用于 Island 点击会话跳转窗口:
        - IDEA 终端: 祖先为 idea/pycharm 等进程 → 按 pid 激活应用窗口
        - Terminal/iTerm2: 祖先为终端 App → 结合 tty 做精确 tab 定位
        非 macOS 或探测失败返回 {} (跳转功能降级, 不影响其他能力)
        """
        try:
            pid = os.getppid()
            for _ in range(10):
                out = subprocess.check_output(
                    ["ps", "-o", "ppid=,comm=", "-p", str(pid)],
                    text=True, stderr=subprocess.DEVNULL,
                ).strip()
                parts = out.split(None, 1)
                if len(parts) != 2:
                    break
                ppid, comm = parts
                if ".app/Contents/MacOS" in comm:
                    return {
                        "host_app_pid": pid,
                        "host_app_name": comm.rsplit("/", 1)[-1],
                    }
                ppid = int(ppid)
                if ppid <= 1:
                    break
                pid = ppid
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        return {}

    @staticmethod
    def _safe_tty() -> str:
        try:
            return os.ttyname(sys.stdin.fileno())
        except (OSError, ValueError, AttributeError):
            return "unknown"

    # ---------------- 对外 API ----------------

    def report_state(self, state: str, **detail):
        """上报状态迁移 (thinking/executing/waiting_approval/done/error/idle)。

        始终缓存最新状态 (重连后补发); 已连接时异步入队发送,
        队列满时丢弃最旧消息 (状态类消息允许丢失, 新值覆盖旧值)。
        """
        msg = {
            "type": "state",
            "session_id": self.session_id,
            "state": state,
            "detail": {k: _truncate(v) for k, v in detail.items() if v is not None},
        }
        self._latest_state = msg
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(msg)
        except queue.Full:
            try:
                self._queue.get_nowait()  # 丢弃最旧
                self._queue.put_nowait(msg)
            except (queue.Empty, queue.Full):
                pass

    def shutdown(self):
        """进程退出时尽力发送 session.unregister 并关闭连接"""
        self._stop.set()
        if self.enabled:
            try:
                self._send_now({
                    "type": "session.unregister",
                    "session_id": self.session_id,
                })
            except OSError:
                pass
        self._cleanup()

    # ---------------- 连接管理 ----------------

    def _try_connect(self) -> bool:
        """尝试建立连接; 成功后补发 register + 最新状态"""
        try:
            if not os.path.exists(SOCKET_PATH):
                return False
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect(SOCKET_PATH)
            sock.settimeout(None)
            self._sock = sock
            self.enabled = True

            register_msg = {
                "type": "session.register",
                "version": PROTOCOL_VERSION,
                "session_id": self.session_id,
                "pid": os.getpid(),
                "cwd": os.getcwd(),
                "tty": self._safe_tty(),
                "term_program": os.environ.get("TERM_PROGRAM", "unknown"),
                "model": self._model,
                "started_at": int(time.time()),
            }
            register_msg.update(self._detect_host_app())
            self._send_now(register_msg)
            # 补发最新状态, 让 Island 立即呈现当前真实状态
            if self._latest_state:
                self._send_now(self._latest_state)
            return True
        except OSError:
            self._cleanup()
            return False

    def _manager_loop(self):
        """daemon 线程: 已连接时 drain 队列发送; 未连接时周期重连"""
        while not self._stop.is_set():
            if not self.enabled:
                self._stop.wait(RECONNECT_INTERVAL)
                if not self._stop.is_set():
                    self._try_connect()
                continue
            try:
                msg = self._queue.get(timeout=0.5)
            except queue.Empty:
                msg = None
            if msg is None:
                # 空闲心跳: idle 会话不写消息, 只有定期写才能发现对端已死
                if time.monotonic() - self._last_activity >= HEARTBEAT_INTERVAL:
                    msg = {"type": "ping", "session_id": self.session_id}
                else:
                    continue
            try:
                self._send_now(msg)
                self._last_activity = time.monotonic()
            except OSError:
                self._cleanup()  # 断线, 进入重连循环

    def _send_now(self, msg: dict):
        if not self._sock:
            return
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            self._sock.sendall(data)

    def _cleanup(self):
        self.enabled = False
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None


# ---------------- 全局单例 ----------------

_reporter: "IslandReporter | None" = None
_init_lock = threading.Lock()


def init_island_reporter(model: str = "") -> IslandReporter:
    """初始化全局 Reporter (幂等)。配置禁用时返回 enabled=False 的空实例。"""
    global _reporter
    with _init_lock:
        if _reporter is None:
            try:
                from config_manager import get_island_enabled
                if not get_island_enabled():
                    _reporter = IslandReporter.__new__(IslandReporter)
                    _reporter.enabled = False
                    _reporter.session_id = "disabled"
                    _reporter._latest_state = None
                    return _reporter
            except Exception:
                pass  # 配置读取失败不影响主流程, 默认尝试连接
            _reporter = IslandReporter(model=model)
    return _reporter


def get_island_reporter() -> "IslandReporter | None":
    return _reporter


def report_state(state: str, **detail):
    """便捷入口: 未初始化或配置禁用时静默忽略"""
    if _reporter is not None:
        _reporter.report_state(state, **detail)
