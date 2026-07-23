# -*- coding: utf-8 -*-
"""
Token 用量统计与持久化

- 按天 × 按模型累计 input/output tokens 与请求次数
- 持久化到 ~/.qoze/token_usage.json (用户级, 跨项目全局累计)
- 写入安全: 进程内锁 + 跨进程文件锁 (fcntl.flock) + tmp 原子替换, 多 qoze 会话并发写不丢数据
- 仅保留最近 90 天数据, 每次写入时自动清理更早记录
- Island App 双通道消费: 直接读该文件 + 接收 token.usage 推送快照

所有公开方法绝不抛异常 —— 统计失败不得影响 Agent 主流程
"""

import json
import os
import threading
from datetime import datetime, timedelta

try:
    import fcntl
except ImportError:  # Windows 降级: 无跨进程文件锁 (单进程内仍有线程锁)
    fcntl = None

DATA_DIR = os.path.expanduser("~/.qoze")
DATA_FILE = os.path.join(DATA_DIR, "token_usage.json")
LOCK_FILE = os.path.join(DATA_DIR, "token_usage.lock")
RETENTION_DAYS = 90

_EMPTY = {"version": 1, "days": {}}


class TokenUsageTracker:
    """token 用量统计器 (全局单例, 线程安全)"""

    def __init__(self):
        self._lock = threading.Lock()
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
        except OSError:
            pass

    # ---------------- 内部: 文件读写 ----------------

    @staticmethod
    def _today() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _read_file() -> dict:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("days"), dict):
                return data
        except (OSError, ValueError):
            pass
        return {"version": 1, "days": {}}

    @staticmethod
    def _write_file(data: dict):
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, DATA_FILE)  # 原子替换, 避免半写状态

    @staticmethod
    def _prune(data: dict):
        cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        days = data.get("days", {})
        for key in [k for k in days if isinstance(k, str) and k < cutoff]:
            days.pop(key, None)

    # ---------------- 对外 API ----------------

    def record(self, model: str, input_tokens: int, output_tokens: int):
        """记录一次请求的 token 消耗 (进程内锁 + 跨进程文件锁)"""
        if not model:
            model = "未知"
        try:
            input_tokens = max(0, int(input_tokens or 0))
            output_tokens = max(0, int(output_tokens or 0))
        except (TypeError, ValueError):
            return
        if input_tokens == 0 and output_tokens == 0:
            return
        try:
            with self._lock:
                with open(LOCK_FILE, "a") as lock_f:
                    if fcntl is not None:
                        fcntl.flock(lock_f, fcntl.LOCK_EX)
                    try:
                        data = self._read_file()
                        days = data.setdefault("days", {})
                        day = days.setdefault(self._today(), {"models": {}})
                        models = day.setdefault("models", {})
                        entry = models.setdefault(
                            model, {"input": 0, "output": 0, "requests": 0})
                        entry["input"] = int(entry.get("input", 0)) + input_tokens
                        entry["output"] = int(entry.get("output", 0)) + output_tokens
                        entry["requests"] = int(entry.get("requests", 0)) + 1
                        self._prune(data)
                        self._write_file(data)
                    finally:
                        if fcntl is not None:
                            fcntl.flock(lock_f, fcntl.LOCK_UN)
        except Exception:
            pass  # 统计失败静默降级

    def snapshot(self) -> dict:
        """返回当前持久化数据快照 (用于 Island 推送与调试)"""
        try:
            with self._lock:
                return self._read_file()
        except Exception:
            return dict(_EMPTY)


# ---------------- 全局单例 ----------------

_tracker = None
_tracker_lock = threading.Lock()


def get_token_usage_tracker() -> TokenUsageTracker:
    global _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = TokenUsageTracker()
    return _tracker
