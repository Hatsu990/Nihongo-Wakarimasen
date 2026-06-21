from __future__ import annotations

import base64
from collections import deque
from datetime import datetime
import json
import os
from pathlib import Path
import threading
from typing import Callable

import numpy as np
import websocket

from .audio import ContinuousSystemAudioCapture
from .config import AppConfig
from .models import Utterance


REALTIME_SAMPLE_RATE = 24000


class RealtimeTranslatePipeline:
    def __init__(
        self,
        config: AppConfig,
        status: Callable[[str], None] | None = None,
    ) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY environment variable is required.")
        self.config = config
        self.status = status or (lambda _message: None)
        self.history: deque[Utterance] = deque(maxlen=config.history_size)
        self.current_source = ""
        self.current_translation = ""
        self._stop = threading.Event()
        self._ws = None
        self._sender_error: Exception | None = None
        self.log_path = config.realtime_log_path

    def run_forever(self, on_update: Callable[[list[Utterance]], None]) -> None:
        self.status(f"Realtime Translate connecting: model={self.config.realtime_model}")
        ws = websocket.WebSocket()
        ws.connect(
            f"wss://api.openai.com/v1/realtime/translations?model={self.config.realtime_model}",
            header=[
                f"Authorization: Bearer {os.environ['OPENAI_API_KEY']}",
                "OpenAI-Safety-Identifier: nihongo-wakarimasen-local",
            ],
        )
        self._ws = ws
        self._send_session_update(ws)
        self._wait_until_session_ready(ws)
        sender = threading.Thread(target=self._send_audio_loop, args=(ws,), daemon=True)
        sender.start()
        self.status("Realtime Translate connected")

        while not self._stop.is_set():
            if self._sender_error is not None:
                raise RuntimeError(f"Realtime audio sender failed: {self._sender_error}")
            event = json.loads(ws.recv())
            event_type = event.get("type", "")
            self._log_event(event)
            if event_type == "error":
                error = event.get("error", {})
                raise RuntimeError(error.get("message") or str(error))
            if event_type == "session.input_transcript.delta" or (
                "input_transcript" in event_type and event_type.endswith(".delta")
            ):
                self.current_source += event.get("delta", "")
                self._render_current(on_update)
            elif event_type == "session.output_transcript.delta" or (
                "output_transcript" in event_type and event_type.endswith(".delta")
            ):
                self.current_translation += event.get("delta", "")
                self._render_current(on_update)
            elif event_type == "session.output_transcript.done" or (
                "output_transcript" in event_type and event_type.endswith(".done")
            ):
                self._finalize_current(on_update)
            elif event_type == "session.closed":
                return

    def _wait_until_session_ready(self, ws) -> None:
        while True:
            event = json.loads(ws.recv())
            event_type = event.get("type", "")
            self._log_event(event)
            if event_type == "error":
                error = event.get("error", {})
                raise RuntimeError(error.get("message") or str(error))
            if event_type == "session.updated":
                return

    def _send_session_update(self, ws) -> None:
        ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "audio": {
                            "output": {
                                "language": self.config.realtime_target_language,
                            },
                        },
                    },
                }
            )
        )

    def _send_audio_loop(self, ws) -> None:
        stream = ContinuousSystemAudioCapture(
            REALTIME_SAMPLE_RATE,
            self.config.realtime_audio_chunk_seconds,
            max_chunks=8,
            recent_chunks=8,
            speaker_name=self.config.audio_device,
            monitor_speaker_name=None,
        )
        stream.start()
        try:
            while not self._stop.is_set():
                audio = stream.read()
                ws.send(
                    json.dumps(
                        {
                            "type": "session.input_audio_buffer.append",
                            "audio": self._to_base64_pcm16(audio),
                        }
                    )
                )
        except Exception as exc:
            self._sender_error = exc
        finally:
            stream.stop()

    def _render_current(self, on_update: Callable[[list[Utterance]], None]) -> None:
        if not self.current_source and not self.current_translation:
            return
        current = Utterance(
            datetime.now(),
            self.current_source.strip(),
            self.current_translation.strip() or "translating...",
        )
        on_update(list(self.history) + [current])

    def _finalize_current(self, on_update: Callable[[list[Utterance]], None]) -> None:
        translation = self.current_translation.strip()
        source = self.current_source.strip()
        if translation:
            self.history.append(Utterance(datetime.now(), source, translation))
            on_update(list(self.history))
        self.current_source = ""
        self.current_translation = ""

    def _to_base64_pcm16(self, audio: np.ndarray) -> str:
        clipped = np.clip(audio, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype("<i2")
        return base64.b64encode(pcm16.tobytes()).decode("ascii")

    def _log_event(self, event: dict) -> None:
        event_type = event.get("type", "")
        keep = {"type": event_type, "timestamp": datetime.now().isoformat()}
        if event_type == "error":
            keep["error"] = event.get("error", {})
        if "delta" in event:
            keep["delta"] = event.get("delta", "")
        if event_type.endswith(".done"):
            keep["text"] = event.get("text") or event.get("transcript") or ""
        self._append_jsonl(self.log_path, keep)

    def _append_jsonl(self, path: Path, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
