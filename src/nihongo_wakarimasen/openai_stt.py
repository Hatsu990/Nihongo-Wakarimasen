from __future__ import annotations

import io
import os
import wave

import numpy as np
from openai import OpenAI


DEFAULT_TRANSCRIPTION_PROMPT = (
    "General Japanese conversation. Topics may change quickly and unpredictably. "
    "Transcribe only what is spoken in the current audio. "
    "Do not force continuity from previous topics. "
    "If the audio is not clearly Japanese speech, return an empty string. "
    "Do not translate Korean, English, music, noise, or silence into Japanese. "
    "Preserve uncertain words, names, game terms, item names, place names, "
    "and short casual utterances as accurately as possible. "
    "Preserve short backchannels like あーうん, そうですね, はい."
)


class OpenAIJapaneseTranscriber:
    def __init__(self, model: str, sample_rate: int, prompt: str | None = None) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY environment variable is required.")
        self.client = OpenAI()
        self.model = model
        self.sample_rate = sample_rate
        self.prompt = prompt or DEFAULT_TRANSCRIPTION_PROMPT

    def transcribe(self, audio: np.ndarray) -> str:
        result = self.client.audio.transcriptions.create(
            file=("audio.wav", self._to_wav(audio), "audio/wav"),
            model=self.model,
            language="ja",
            prompt=self.prompt,
            response_format="text",
            temperature=0,
            timeout=20,
        )
        return str(result).strip()

    def _to_wav(self, audio: np.ndarray) -> bytes:
        clipped = np.clip(audio, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype("<i2")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm16.tobytes())
        return buffer.getvalue()
