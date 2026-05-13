#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Meeting Note Recorder — standalone async meeting recording with real-time STT.
Audio is saved to .wav, transcription is appended to .txt.
Completely independent of the AI agent loop.
"""

import threading
import queue
import wave
import numpy as np
from typing import Iterator
from collections import deque

import pyaudio
from soniox import SonioxClient
from soniox.types import (
    RealtimeSTTConfig,
    Token,
    StructuredContext,
    StructuredContextGeneralItem,
)
from soniox.utils import render_tokens, start_audio_thread

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024


class MeetingNoteRecorder:
    """Records microphone audio to .wav while simultaneously transcribing via
    Soniox real-time STT.  Audio chunks are written to disk as they arrive;
    finalised transcription tokens are appended to a text file."""

    def __init__(self, api_key: str, event_queue: queue.Queue,
                 audio_path: str, text_path: str):
        self.api_key = api_key
        self.event_queue = event_queue
        self.audio_path = audio_path
        self.text_path = text_path

        self.is_running = False
        self.thread = None
        self.client = SonioxClient(api_key=self.api_key)
        self._wave_file = None
        self._wave_history = deque([0] * 60, maxlen=60)

        # Track how many final tokens have been persisted to disk
        self._saved_final_count = 0

    # ------------------------------------------------------------------
    # Audio capture + disk writing
    # ------------------------------------------------------------------

    def _get_wave_bar(self, rms: float) -> str:
        self._wave_history.append(rms)
        # 10-level bar with log scale for better quiet/loud differentiation
        bars = [" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█", "█"]
        import math
        max_log = math.log(4000)  # reference: RMS 4000 ≈ max expected speech
        wave_str = ""
        for r in self._wave_history:
            # log scale: quiet sounds spread across lower bars
            r_clamped = max(r, 1)
            normalized = min(math.log(r_clamped) / max_log, 1.0)
            index = int(normalized * (len(bars) - 1))
            wave_str += bars[index]
        return wave_str

    def stream_audio_from_microphone(self) -> Iterator[bytes]:
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        # Open WAV file for writing
        self._wave_file = wave.open(self.audio_path, 'wb')
        self._wave_file.setnchannels(CHANNELS)
        self._wave_file.setsampwidth(p.get_sample_size(FORMAT))
        self._wave_file.setframerate(RATE)

        try:
            while self.is_running:
                data = stream.read(CHUNK, exception_on_overflow=False)

                # Calculate RMS for visual wave bar
                audio_data = np.frombuffer(data, dtype=np.int16)
                rms = np.sqrt(np.mean(np.square(audio_data.astype(np.float32))))
                wave_str = self._get_wave_bar(rms)

                self.event_queue.put({
                    "type": "wave",
                    "data": f"{wave_str}  [RMS: {int(rms):04d}]"
                })

                # Write raw PCM frames to WAV
                if self._wave_file:
                    self._wave_file.writeframes(data)

                yield data
        except Exception as e:
            self.event_queue.put({"type": "error", "data": str(e)})
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()
            if self._wave_file:
                self._wave_file.close()
                self._wave_file = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Spawn background thread for STT + audio capture."""
        self.is_running = True
        self._saved_final_count = 0

        # Seed empty text file
        try:
            with open(self.text_path, 'w', encoding='utf-8') as f:
                f.write("")
        except Exception as e:
            self.event_queue.put({"type": "error",
                                  "data": f"Cannot create transcript file: {e}"})

        self.thread = threading.Thread(target=self._run_stt, daemon=True)
        self.thread.start()

    def stop(self):
        """Signal the background thread to finish and join."""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None

    # ------------------------------------------------------------------
    # Transcription persistence
    # ------------------------------------------------------------------

    def _append_transcript(self, text: str):
        """Append one line of finalised transcription to the text file."""
        if not text.strip():
            return
        try:
            with open(self.text_path, 'a', encoding='utf-8') as f:
                f.write(text.strip() + "\n")
        except Exception as e:
            self.event_queue.put({
                "type": "error",
                "data": f"Failed to write transcript: {e}"
            })

    # ------------------------------------------------------------------
    # Soniox real-time STT loop
    # ------------------------------------------------------------------

    def _run_stt(self):
        config = RealtimeSTTConfig(
            model="stt-rt-v4",
            audio_format="pcm_s16le",
            sample_rate=RATE,
            num_channels=CHANNELS,
            enable_endpoint_detection=False,
            enable_speaker_diarization=False,
            language_hints=["en", "zh"],
            context=StructuredContext(
                general=[
                    StructuredContextGeneralItem(
                        key="domain", value="meeting note dictation"),
                    StructuredContextGeneralItem(
                        key="topic", value="general meeting and conversation")
                ],
                text="Live meeting dictation from microphone. The user is recording "
                     "a meeting for note-taking purposes. Speech may include multiple "
                     "topics, discussions, and varied speakers.",
                terms=["QozeCode", "meeting", "note"],
            ),
        )

        final_tokens: list[Token] = []
        non_final_tokens: list[Token] = []

        try:
            with self.client.realtime.stt.connect(config=config) as session:
                start_audio_thread(
                    session, self.stream_audio_from_microphone())

                for event in session.receive_events():
                    if getattr(event, 'error_message', None):
                        self.event_queue.put({
                            "type": "error",
                            "data": f"Soniox API Error: {event.error_message}"
                        })
                        break

                    if not self.is_running:
                        break

                    for token in event.tokens:
                        if token.is_final:
                            final_tokens.append(token)
                        else:
                            non_final_tokens.append(token)

                    text_content = render_tokens(final_tokens, non_final_tokens)
                    self.event_queue.put({"type": "text", "data": text_content})

                    # Persist newly-finalised tokens to the text file
                    if len(final_tokens) > self._saved_final_count:
                        new_tokens = final_tokens[self._saved_final_count:]
                        new_text = "".join(t.text for t in new_tokens)
                        self._saved_final_count = len(final_tokens)
                        self._append_transcript(new_text)

                    non_final_tokens.clear()

        except Exception as e:
            if self.is_running:
                self.event_queue.put({"type": "error", "data": str(e)})
        finally:
            self.is_running = False
