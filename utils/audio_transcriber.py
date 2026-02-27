import threading
import queue
import time
import pyaudio
import numpy as np
from typing import Iterator
from collections import deque
from soniox import SonioxClient
from soniox.types import (
    RealtimeSTTConfig,
    Token,
    StructuredContext,
    StructuredContextGeneralItem,
)
from soniox.utils import render_tokens, start_audio_thread
from config_manager import get_soniox_key

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024


class AudioTranscriber:
    def __init__(self, api_key: str, event_queue: queue.Queue):
        self.api_key = api_key
        self.event_queue = event_queue
        self.client = SonioxClient(api_key=self.api_key)
        self.is_running = False
        self.thread = None
        self.wave_history = deque([0] * 60, maxlen=60)

    def get_wave_bar(self, rms):
        self.wave_history.append(rms)
        bars = [" ", " ", "▂", "▃", "▃", "▄", "▄", "▅", "▅", "▆", "▇", "█"]
        wave_str = ""
        for r in self.wave_history:
            normalized = min(max(r / 2000.0, 0), 1)
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
        try:
            while self.is_running:
                data = stream.read(CHUNK, exception_on_overflow=False)

                audio_data = np.frombuffer(data, dtype=np.int16)
                rms = np.sqrt(np.mean(np.square(audio_data.astype(np.float32))))
                wave_str = self.get_wave_bar(rms)

                self.event_queue.put({"type": "wave", "data": f"{wave_str}  [RMS: {int(rms):04d}]"})
                yield data
        except Exception as e:
            self.event_queue.put({"type": "error", "data": str(e)})
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    def start(self):
        self.is_running = True
        self.thread = threading.Thread(target=self._run_stt, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2)

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
                    StructuredContextGeneralItem(key="domain", value="live microphone dictation"),
                    StructuredContextGeneralItem(key="topic", value="programming and software development")
                ],
                text="Live dictation from microphone. The user is a developer working on the project, discussing programming, AI agents, and terminal commands.",
                terms=[
                    "QozeCode", "Soniox", "Pydantic", "diarization", "Reddit", "github",
                    "ReAct", "Tavily"
                ],
            ),
        )
        final_tokens: list[Token] = []
        non_final_tokens: list[Token] = []

        try:
            with self.client.realtime.stt.connect(config=config) as session:
                start_audio_thread(session, self.stream_audio_from_microphone())

                for event in session.receive_events():
                    if getattr(event, 'error_message', None):
                        self.event_queue.put({"type": "error", "data": f"Soniox API Error: {event.error_message}"})
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
                    non_final_tokens.clear()
        except Exception as e:
            if self.is_running:
                self.event_queue.put({"type": "error", "data": str(e)})
        finally:
            self.is_running = False
