from __future__ import annotations

import os
import re
import site

import numpy as np


_DLL_DIRECTORY_HANDLES = []


def _add_nvidia_dll_directories() -> None:
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return
    for site_dir in site.getsitepackages():
        nvidia_dir = os.path.join(site_dir, "nvidia")
        if not os.path.isdir(nvidia_dir):
            continue
        for package_name in os.listdir(nvidia_dir):
            bin_dir = os.path.join(nvidia_dir, package_name, "bin")
            if os.path.isdir(bin_dir):
                _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(bin_dir))
                current_path = os.environ.get("PATH", "")
                if bin_dir not in current_path.split(os.pathsep):
                    os.environ["PATH"] = bin_dir + os.pathsep + current_path


_add_nvidia_dll_directories()

from faster_whisper import WhisperModel


HALLUCINATION_PATTERNS = (
    "ご視聴ありがとうございました",
    "ご清聴ありがとうございました",
    "ありがとうございました",
    "エンディング",
    "字幕",
    "チャンネル登録",
    "高評価",
)


class JapaneseTranscriber:
    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        beam_size: int,
        max_no_speech_prob: float,
        min_avg_logprob: float,
        max_compression_ratio: float,
        min_text_chars: int,
        hotwords: str = "",
    ) -> None:
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
        self.beam_size = beam_size
        self.max_no_speech_prob = max_no_speech_prob
        self.min_avg_logprob = min_avg_logprob
        self.max_compression_ratio = max_compression_ratio
        self.min_text_chars = min_text_chars
        self.hotwords = hotwords.strip()
        self.last_debug_segments = []

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _info = self.model.transcribe(
            audio,
            language="ja",
            beam_size=self.beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
            hotwords=self.hotwords or None,
        )
        kept = []
        debug_segments = []
        for segment in segments:
            text = segment.text.strip()
            keep, reason = self._segment_filter_result(text, segment)
            debug_segments.append(
                {
                    "text": text,
                    "start": segment.start,
                    "end": segment.end,
                    "avg_logprob": segment.avg_logprob,
                    "no_speech_prob": segment.no_speech_prob,
                    "compression_ratio": segment.compression_ratio,
                    "keep": keep,
                    "reason": reason,
                }
            )
            if keep:
                kept.append(text)
        self.last_debug_segments = debug_segments
        return "".join(kept).strip()

    def _should_keep_segment(self, text: str, segment) -> bool:
        keep, _reason = self._segment_filter_result(text, segment)
        return keep

    def _segment_filter_result(self, text: str, segment) -> tuple[bool, str]:
        compact = re.sub(r"\s+", "", text)
        if len(compact) < self.min_text_chars:
            return False, "too_short"
        if any(pattern in compact for pattern in HALLUCINATION_PATTERNS):
            return False, "hallucination_pattern"
        if self._is_repetitive(compact):
            return False, "repetitive"
        if segment.no_speech_prob > self.max_no_speech_prob:
            return False, "no_speech_prob"
        if segment.avg_logprob < self.min_avg_logprob:
            return False, "avg_logprob"
        if segment.compression_ratio > self.max_compression_ratio:
            return False, "compression_ratio"
        return True, "kept"

    def _is_repetitive(self, text: str) -> bool:
        if len(text) >= 6 and len(set(text)) <= 2:
            return True
        for size in range(1, 5):
            if len(text) >= size * 4:
                unit = text[:size]
                if unit and unit * (len(text) // size) == text[: size * (len(text) // size)]:
                    return True
        return False
