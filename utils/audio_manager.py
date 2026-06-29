#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AudioManager — 独立的语音输入与会议录音管理器。

将 qoze_tui.py 中的录音相关逻辑抽离，通过回调机制与 TUI 层解耦：
- 不依赖任何 Textual/Rich 组件
- 管理 AudioTranscriber / MeetingNoteRecorder 的生命周期
- 通过 poll() 方法轮询事件队列并触发回调
- 可独立测试

快捷键映射（在 qoze_tui.py 的 BINDINGS 中定义）：
- Ctrl+Q / Ctrl+E → 语音输入 开始/停止
- Ctrl+N → 会议笔记 开关
"""

import os
import queue
import time
from typing import Optional, Callable

# ------------------------------------------------------------------
# 延迟导入 — 避免 pyaudio / soniox 缺失时整个 TUI 无法启动
# ------------------------------------------------------------------
_AudioTranscriber = None
_MeetingNoteRecorder = None
_IMPORT_ERROR: Optional[str] = None

try:
    from utils.audio_transcriber import AudioTranscriber as _AT
    from utils.meeting_note_recorder import MeetingNoteRecorder as _MNR

    _AudioTranscriber = _AT
    _MeetingNoteRecorder = _MNR
except ImportError as e:
    _IMPORT_ERROR = str(e)


# ==================================================================
class AudioManager:
    """语音输入 & 会议录音 管理器。

    通过回调将 UI 展示所需数据传递给 TUI 层，自身不持有任何 UI 引用。

    使用示例::

        am = AudioManager()

        # 注册回调
        am.on_voice_wave = lambda w: status_label.update(f"🎙️ {w}")
        am.on_voice_text = lambda t: input_box.value = t
        am.on_voice_error = lambda e: mount_error(e)

        # 启动语音输入
        err = am.start_voice("已有的文本")
        if err:
            print(err)

        # 在 TUI 定时器中轮询
        am.poll()

        # 停止
        am.stop_voice()
    """

    def __init__(self):
        # ---- 语音输入 ----
        self.voice_active: bool = False
        self._voice_original_text: str = ""
        self._voice_transcriber = None
        self._voice_queue: queue.Queue = queue.Queue()

        # ---- 会议笔记 ----
        self.meeting_active: bool = False
        self._meeting_recorder = None
        self._meeting_queue: queue.Queue = queue.Queue()
        self._meeting_start_time: Optional[float] = None
        self._last_meeting_text: str = ""

        # ---- 回调注册 ----
        # 语音输入
        self.on_voice_wave: Optional[Callable[[str], None]] = None       # (wave_bar: str)
        self.on_voice_text: Optional[Callable[[str], None]] = None       # (combined_text: str)
        self.on_voice_error: Optional[Callable[[str], None]] = None      # (error_msg: str)

        # 会议笔记
        self.on_meeting_wave: Optional[Callable[[str, Optional[str]], None]] = None   # (wave_bar, latest_text)
        self.on_meeting_elapsed: Optional[Callable[[int, int], None]] = None          # (mins, secs)
        self.on_meeting_error: Optional[Callable[[str], None]] = None                 # (error_msg)
        self.on_meeting_started: Optional[Callable[[str], None]] = None               # (note_path_relative)
        self.on_meeting_stopped: Optional[Callable[[], None]] = None

    # ------------------------------------------------------------------
    # 能力检测
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        """依赖库是否已安装。"""
        return _AudioTranscriber is not None and _MeetingNoteRecorder is not None

    @property
    def import_error(self) -> Optional[str]:
        """导入失败时的错误信息。"""
        return _IMPORT_ERROR

    # ------------------------------------------------------------------
    # 语音输入 (Ctrl+Q / Ctrl+E)
    # ------------------------------------------------------------------

    def start_voice(self, original_text: str = "") -> Optional[str]:
        """启动语音输入。成功返回 None，失败返回错误描述。"""
        if not self.is_available:
            return f"Audio dependencies missing: {_IMPORT_ERROR}"

        # 互斥：停止正在进行的会议笔记
        if self.meeting_active:
            self.stop_meeting()

        import config_manager
        soniox_key = config_manager.get_soniox_key()
        if not soniox_key:
            return (
                "🔴 未检测到 Soniox API Key。"
                "请在 qoze.conf 的 [soniox] 节点下添加 api_key"
            )

        self.voice_active = True
        self._voice_original_text = original_text
        self._voice_transcriber = _AudioTranscriber(
            api_key=soniox_key, event_queue=self._voice_queue
        )
        self._voice_transcriber.start()
        return None

    def stop_voice(self) -> Optional[str]:
        """停止语音输入，返回最终拼接文本（可能为 None）。"""
        if not self.voice_active:
            return None

        self.voice_active = False
        if self._voice_transcriber:
            self._voice_transcriber.stop()
            self._voice_transcriber = None

        # 清空残留事件，拼出最终文本
        final = self._voice_original_text
        while not self._voice_queue.empty():
            msg = self._voice_queue.get_nowait()
            if msg["type"] == "text":
                final = (final + " " + msg["data"]) if final else msg["data"]
        return final if final else None

    # ------------------------------------------------------------------
    # 会议笔记 (Ctrl+N)
    # ------------------------------------------------------------------

    def start_meeting(self) -> Optional[str]:
        """启动会议录音。成功返回 None，失败返回错误描述。"""
        if not self.is_available:
            return f"Meeting Note dependencies missing: {_IMPORT_ERROR}"

        # 互斥
        if self.voice_active:
            self.stop_voice()

        import config_manager
        soniox_key = config_manager.get_soniox_key()
        if not soniox_key:
            return (
                "🔴 未检测到 Soniox API Key。"
                "请在 qoze.conf 的 [soniox] 节点下添加 api_key"
            )

        from datetime import datetime

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H-%M-%S")
        note_dir = os.path.join(".qoze", "note", date_str)
        os.makedirs(note_dir, exist_ok=True)

        audio_path = os.path.join(note_dir, f"{time_str}.wav")
        text_path = os.path.join(note_dir, f"{time_str}.txt")

        self.meeting_active = True
        self._meeting_start_time = time.time()
        self._last_meeting_text = ""
        self._meeting_recorder = _MeetingNoteRecorder(
            api_key=soniox_key,
            event_queue=self._meeting_queue,
            audio_path=audio_path,
            text_path=text_path,
        )
        self._meeting_recorder.start()

        if self.on_meeting_started:
            self.on_meeting_started(f"{note_dir}/{time_str}")
        return None

    def stop_meeting(self):
        """停止会议录音。"""
        if not self.meeting_active:
            return

        self.meeting_active = False
        if self._meeting_recorder:
            self._meeting_recorder.stop()
            self._meeting_recorder = None

        self._meeting_start_time = None
        self._last_meeting_text = ""

        if self.on_meeting_stopped:
            self.on_meeting_stopped()

    def toggle_meeting(self) -> Optional[str]:
        """切换会议笔记状态。成功返回 None，失败返回错误描述。"""
        if self.meeting_active:
            self.stop_meeting()
            return None
        return self.start_meeting()

    # ------------------------------------------------------------------
    # Poll — 由外部定时器驱动，每次调用排空事件队列并触发回调
    # ------------------------------------------------------------------

    def poll(self):
        """轮询语音输入和会议笔记的事件队列。"""
        if self.voice_active:
            self._poll_voice()
        if self.meeting_active:
            self._poll_meeting()

    def _poll_voice(self):
        wave_content = None
        text_content = None

        while not self._voice_queue.empty():
            msg = self._voice_queue.get_nowait()
            if msg["type"] == "text":
                text_content = msg["data"]
            elif msg["type"] == "wave":
                wave_content = msg["data"]
            elif msg["type"] == "error":
                if self.on_voice_error:
                    self.on_voice_error(msg["data"])

        if text_content is not None:
            combined = self._voice_original_text
            combined = (combined + " " + text_content) if combined else text_content
            if self.on_voice_text:
                self.on_voice_text(combined)

        if wave_content is not None and self.on_voice_wave:
            self.on_voice_wave(wave_content)

    def _poll_meeting(self):
        wave_content = None
        text_content = None
        has_error = None

        while not self._meeting_queue.empty():
            msg = self._meeting_queue.get_nowait()
            if msg["type"] == "error":
                has_error = msg["data"]
                break
            elif msg["type"] == "wave":
                wave_content = msg["data"]
            elif msg["type"] == "text":
                text_content = msg["data"]

        if has_error is not None:
            self.stop_meeting()
            if self.on_meeting_error:
                self.on_meeting_error(has_error)
            return

        if text_content is not None:
            self._last_meeting_text = text_content

        if (wave_content is not None or text_content is not None) and self.on_meeting_wave:
            self.on_meeting_wave(
                wave_content or "",
                self._last_meeting_text if self._last_meeting_text else None,
            )

        if self._meeting_start_time and self.on_meeting_elapsed:
            elapsed = int(time.time() - self._meeting_start_time)
            self.on_meeting_elapsed(elapsed // 60, elapsed % 60)

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def cleanup(self):
        """停止所有录音并释放资源。"""
        if self.voice_active:
            self.stop_voice()
        if self.meeting_active:
            self.stop_meeting()
