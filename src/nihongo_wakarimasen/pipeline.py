from __future__ import annotations

from collections import deque
from datetime import datetime
from difflib import SequenceMatcher
from math import ceil
import queue
import re
import threading
import time
from typing import Callable

import numpy as np

from .audio import ContinuousSystemAudioCapture, create_audio_capture, rms
from .config import AppConfig
from .conversation_log import ConversationLog
from .debug_log import DebugLog
from .models import Utterance
from .openai_stt import OpenAIJapaneseTranscriber
from .stt import JapaneseTranscriber
from .stt_corrections import STTCorrections
from .stt_hotwords import STTHotwords
from .translator import TranslatorUnavailable, create_translator


_OVERLAP_MIN_WINDOW_SECONDS = 3.5
_OVERLAP_TAIL_SECONDS = 1.8
_OVERLAP_MIN_SPEECH_SECONDS = 0.35
_OVERLAP_TAIL_MIN_SPEECH_SECONDS = 0.15


class ListeningPipeline:
    def __init__(
        self,
        config: AppConfig,
        status: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config
        self.status = status or (lambda _message: None)
        self.status("audio capture ready")
        self.capture = create_audio_capture(
            config.sample_rate,
            config.audio_device,
            config.capture_process,
        )

        self.stt_hotwords = STTHotwords(config.stt_hotwords_path)
        hotwords_text = self.stt_hotwords.prompt_text()

        if config.stt_provider == "openai":
            self.status(f"OpenAI STT ready: model={config.openai_stt_model}")
            self.transcriber = OpenAIJapaneseTranscriber(
                config.openai_stt_model,
                config.sample_rate,
            )
        else:
            self.status(
                f"Whisper loading: model={config.whisper_model}, "
                f"device={config.whisper_device}, compute={config.whisper_compute_type}, "
                f"beam={config.stt_beam_size}"
            )
            self.transcriber = JapaneseTranscriber(
                config.whisper_model,
                config.whisper_device,
                config.whisper_compute_type,
                config.stt_beam_size,
                config.max_no_speech_prob,
                config.min_avg_logprob,
                config.max_compression_ratio,
                config.min_text_chars,
                hotwords_text,
            )

        self.status(
            f"translator ready: provider={config.translator_provider}, model={config.openai_model}"
        )
        self.translator = create_translator(
            config.translator_provider,
            config.openai_model,
            config.asr_hints_path,
            config.translation_mode,
            config.use_asr_hints,
            config.translation_dictionary_path,
            config.user_translation_dictionary_path,
            config.papago_credentials_path,
            config.papago_timeout_seconds,
        )
        self.log = ConversationLog(config.log_path)
        self.debug_log = DebugLog(config.debug_log_path)
        self.stt_corrections = STTCorrections(config.stt_corrections_path)
        self.history: deque[Utterance] = deque(maxlen=config.history_size)
        self.failed_japanese: deque[str] = deque(maxlen=3)
        self.pending_japanese_fragment = ""
        self.translation_unavailable = False
        self._stop_event = threading.Event()
        self._active_stream: ContinuousSystemAudioCapture | None = None
        self.debug_log.append(
            "pipeline_ready",
            stt_provider=config.stt_provider,
            translator_provider=config.translator_provider,
            whisper_model=config.whisper_model,
            whisper_device=config.whisper_device,
            whisper_compute_type=config.whisper_compute_type,
            stt_beam_size=config.stt_beam_size,
            stt_hotwords_path=str(config.stt_hotwords_path),
            stt_hotwords_count=self.stt_hotwords.count_enabled_terms(),
            user_translation_dictionary_path=str(config.user_translation_dictionary_path),
            capture_process=config.capture_process,
            audio_device=config.audio_device,
            endpointing=config.endpointing,
            overlap_stt=config.overlap_stt,
            overlap_window_seconds=config.overlap_window_seconds,
            overlap_step_seconds=config.overlap_step_seconds,
            endpoint_min_seconds=config.endpoint_min_seconds,
            endpoint_silence_seconds=config.endpoint_silence_seconds,
            endpoint_max_seconds=config.endpoint_max_seconds,
            endpoint_merge_short_seconds=config.endpoint_merge_short_seconds,
            overlap_vad_min_window_seconds=_OVERLAP_MIN_WINDOW_SECONDS,
            overlap_vad_min_speech_seconds=_OVERLAP_MIN_SPEECH_SECONDS,
        )
        self.status("pipeline ready")

    def stop(self) -> None:
        self._stop_event.set()
        if self._active_stream is not None:
            self._active_stream.stop()

    def step(self) -> Utterance | None:
        self.status(f"recording {self.config.chunk_seconds:.1f}s")
        audio = self.capture.record(self.config.chunk_seconds)
        return self._process_audio(audio)

    def _process_audio(self, audio) -> Utterance | None:
        return self._process_audio_with_update(audio, None)

    def _process_audio_with_update(
        self,
        audio,
        on_update: Callable[[list[Utterance]], None] | None,
    ) -> Utterance | None:
        audio_rms = rms(audio)
        min_rms = self._active_min_rms()
        self.status(
            f"audio captured: frames={audio.size}, rms={audio_rms:.6f}, min_rms={min_rms:.6f}"
        )
        self.debug_log.append(
            "audio_captured",
            frames=int(audio.size),
            seconds=audio.size / self.config.sample_rate,
            rms=audio_rms,
            min_rms=min_rms,
        )
        if audio_rms < min_rms:
            self.status("skipping quiet audio")
            self.debug_log.append("skip_quiet_audio", rms=audio_rms, min_rms=min_rms)
            return None

        self.status("Japanese STT processing")
        started = time.monotonic()
        japanese = self.transcriber.transcribe(audio)
        stt_seconds = time.monotonic() - started
        self.status(f"Japanese STT done: {stt_seconds:.1f}s")
        self.debug_log.append(
            "stt_done",
            seconds=stt_seconds,
            japanese=japanese,
            segment_debug=getattr(self.transcriber, "last_debug_segments", None),
        )
        if not japanese:
            self.status("STT returned empty text")
            self.debug_log.append("skip_empty_stt")
            return None
        if self.pending_japanese_fragment:
            previous = self.pending_japanese_fragment
            japanese = self._merge_japanese_fragments(previous, japanese)
            self.pending_japanese_fragment = ""
            self.debug_log.append(
                "merged_pending_japanese_fragment",
                previous=previous,
                merged=japanese,
            )
        corrected_japanese, corrections = self.stt_corrections.apply(japanese)
        if corrections:
            self.debug_log.append(
                "stt_corrected",
                original=japanese,
                corrected=corrected_japanese,
                corrections=corrections,
            )
            japanese = corrected_japanese
        deduped_japanese = self._remove_duplicate_sentences(japanese)
        if deduped_japanese != japanese.strip():
            self.debug_log.append(
                "stt_internal_repeat_cleaned",
                stage="before_filters",
                original=japanese,
                cleaned=deduped_japanese,
            )
        japanese = deduped_japanese

        if self.translation_unavailable:
            self.debug_log.append("skip_translation_unavailable", japanese=japanese)
            return None
        if self._is_known_stt_hallucination(japanese):
            self.status("skipping likely STT hallucination")
            self.debug_log.append("skip_known_stt_hallucination", japanese=japanese)
            return None
        if self._is_recent_failed_japanese(japanese):
            self.status("skipping recently failed STT")
            self.debug_log.append("skip_recent_failed_stt", japanese=japanese)
            return None
        if self._is_duplicate_japanese(japanese):
            self.status("skipping duplicate STT")
            self.debug_log.append("skip_duplicate_stt", japanese=japanese)
            return None
        if self._is_japanese_subset_of_recent(japanese):
            self.status("skipping overlapped STT tail")
            self.debug_log.append("skip_overlap_subset_stt", japanese=japanese)
            return None
        if self._is_low_value_backchannel(japanese):
            self.status("skipping short backchannel")
            self.debug_log.append("skip_backchannel", japanese=japanese)
            return None
        japanese = self._remove_backchannel_sentences(japanese)
        if not japanese:
            self.status("STT returned only backchannels")
            self.debug_log.append("skip_only_backchannels")
            return None
        deduped_japanese = self._remove_duplicate_sentences(japanese)
        if deduped_japanese != japanese.strip():
            self.debug_log.append(
                "stt_internal_repeat_cleaned",
                stage="after_backchannel_filter",
                original=japanese,
                cleaned=deduped_japanese,
            )
        japanese = deduped_japanese
        if self._is_low_value_short_fragment(japanese):
            self.status("skipping short fragment")
            self.debug_log.append("skip_short_fragment", japanese=japanese)
            return None
        if self._should_hold_japanese_fragment(japanese):
            self.pending_japanese_fragment = japanese
            self.status("holding incomplete STT fragment")
            self.debug_log.append("holding_japanese_fragment", japanese=japanese)
            return None

        self.status("Korean translation processing")

        context = [
            item.japanese
            for item in list(self.history)[-self.config.translation_context_size :]
        ]
        started = time.monotonic()
        try:
            korean = self.translator.translate(japanese, context)
        except TranslatorUnavailable as exc:
            self.translation_unavailable = True
            self.status(f"translation unavailable: {exc}")
            self.debug_log.append(
                "translation_unavailable",
                japanese=japanese,
                error=str(exc),
            )
            if on_update is not None:
                on_update(list(self.history))
            return None
        except Exception as exc:
            self.failed_japanese.append(japanese)
            self.status(f"Korean translation failed: {exc}")
            self.debug_log.append(
                "translation_failed",
                japanese=japanese,
                error=str(exc),
            )
            if on_update is not None:
                on_update(list(self.history))
            return None
        translation_seconds = time.monotonic() - started
        self.status(f"Korean translation done: {translation_seconds:.1f}s")
        self.debug_log.append(
            "translation_done",
            seconds=translation_seconds,
            japanese=japanese,
            korean=korean,
        )
        utterance = Utterance(datetime.now(), japanese, korean)
        if self._is_uncertain_translation(utterance.korean):
            self.status("skipping uncertain translation")
            return None
        if self._is_recent_utterance_revision(utterance):
            self.debug_log.append(
                "skip_overlap_revision_of_committed_result",
                japanese=utterance.japanese,
                korean=utterance.korean,
            )
            self.status("skipping overlap revision of committed result")
            return None
        if self._is_duplicate_utterance(utterance):
            self.status("skipping duplicate result")
            return None

        self.history.append(utterance)
        self.log.append(utterance)
        self.debug_log.append("result_saved", japanese=japanese, korean=korean)
        self.status("result saved")
        return utterance

    def _is_low_value_backchannel(self, japanese: str) -> bool:
        compact = "".join(japanese.split())
        if len(compact) > 18:
            return False
        return self._is_backchannel_sentence(compact)

    def _remove_backchannel_sentences(self, japanese: str) -> str:
        sentences = self._split_sentences(japanese)
        kept = [
            sentence
            for sentence in sentences
            if not self._is_backchannel_sentence("".join(sentence.split()))
        ]
        return " ".join(kept)

    def _remove_duplicate_sentences(self, japanese: str) -> str:
        sentences = self._split_sentences(japanese)
        if len(sentences) <= 1:
            return self._remove_internal_repeated_phrases(japanese.strip())
        kept: list[str] = []
        for sentence in sentences:
            sentence = self._remove_internal_repeated_phrases(sentence)
            compact = self._compact_for_overlap(sentence)
            if not compact:
                continue
            duplicate = False
            for previous in kept[-2:]:
                previous_compact = self._compact_for_overlap(previous)
                if compact == previous_compact:
                    duplicate = True
                    break
                if len(compact) <= len(previous_compact) and compact in previous_compact:
                    duplicate = True
                    break
                if self._similarity(compact, previous_compact) >= 0.9:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(sentence)
        return " ".join(kept)

    def _remove_internal_repeated_phrases(self, japanese: str) -> str:
        parts = japanese.split()
        if len(parts) <= 1:
            return japanese.strip()
        kept: list[str] = []
        for part in parts:
            if kept:
                merged = self._merge_repeated_phrase_variant(kept[-1], part)
                if merged is not None:
                    kept[-1] = merged
                    continue
            kept.append(part)
        return " ".join(kept)

    def _split_sentences(self, text: str) -> list[str]:
        split = re.sub(r"([.!?\u3002\uff01\uff1f])\s*", r"\1\n", text).splitlines()
        return [line.strip() for line in split if line.strip()]

    def _is_backchannel_sentence(self, compact: str) -> bool:
        phrases = (
            "\u3042",
            "\u3042\u30fc",
            "\u3048\u30fc",
            "\u3078\u3048",
            "\u3078\u30fc",
            "\u305d\u3046",
            "\u305d\u3046\u3067\u3059",
            "\u305d\u3046\u3067\u3059\u306d",
            "\u305d\u3046\u3067\u3059\u3088\u306d",
            "\u305d\u3046\u304b",
            "\u305d\u3046\u306a\u3093\u3060",
            "\u3042\u305d\u3046\u306a\u3093\u3060",
            "\u305d\u3046\u306a\u3093\u3067\u3059\u3088",
            "\u306a\u308b\u307b\u3069",
            "\u3046\u3093",
            "\u3048\u3048",
            "\u306f\u3044",
            "\u306f\u306f",
            "\u3042\u306f",
            "\u3042\u306f\u306f",
            "\u3075\u3075",
        )
        stripped = re.sub(r"[\u3002\uff01\uff1f.!?\u3001,]", "", compact)
        return any(stripped == phrase or stripped == phrase * 2 for phrase in phrases)

    def _is_low_value_short_fragment(self, japanese: str) -> bool:
        compact = "".join(japanese.split())
        stripped = re.sub(r"[\u3002\uff01\uff1f.!?\u3001,]", "", compact)
        return stripped in {"\u304b", "\u306d", "\u3088", "\u3044\u3084", "\u3042", "\u3046\u3093"}

    def _merge_japanese_fragments(self, previous: str, current: str) -> str:
        previous = previous.strip()
        current = current.strip()
        if not previous:
            return current
        if not current:
            return previous

        previous_compact = "".join(previous.split())
        current_compact = "".join(current.split())
        if len(previous_compact) <= 4 and previous_compact not in current_compact:
            return current
        if current_compact and current_compact in previous_compact:
            return previous
        if previous_compact and previous_compact in current_compact:
            return current
        repeated = self._merge_repeated_phrase_variant(previous, current)
        if repeated is not None:
            return repeated

        previous_parts = previous.split()
        if previous_parts and self._is_short_kana_word(previous_parts[-1]) and self._is_short_kana_word(current):
            if self._similarity(previous_parts[-1], current) >= 0.5:
                previous_parts[-1] = current
                return " ".join(previous_parts)

        max_overlap = min(len(previous_compact), len(current_compact))
        for size in range(max_overlap, 0, -1):
            if previous_compact[-size:] == current_compact[:size]:
                return f"{previous} {current_compact[size:]}".strip()
        return f"{previous} {current}"

    def _merge_repeated_phrase_variant(self, previous: str, current: str) -> str | None:
        previous_compact = self._compact_for_overlap(previous)
        current_compact = self._compact_for_overlap(current)
        if len(previous_compact) < 10 or len(current_compact) < 10:
            return None

        common = self._longest_common_substring_length(previous_compact, current_compact)
        if len(current_compact) >= len(previous_compact) + 4:
            prefix = self._common_prefix_length(previous_compact, current_compact)
            if (
                previous_compact in current_compact
                or common / len(previous_compact) >= 0.72
                or prefix / len(previous_compact) >= 0.58
            ):
                return current.strip()

        if len(previous_compact) >= len(current_compact) + 4:
            if current_compact in previous_compact or common / len(current_compact) >= 0.8:
                return previous.strip()
        return None

    def _is_short_kana_word(self, text: str) -> bool:
        stripped = re.sub(r"[\u3002\uff01\uff1f.!?\u3001,]", "", text.strip())
        return 2 <= len(stripped) <= 6 and bool(re.fullmatch(r"[\u3040-\u30ff\u30fc]+", stripped))

    def _is_duplicate_japanese(self, japanese: str) -> bool:
        return any(
            self._similarity(japanese, item.japanese) >= 0.92
            for item in list(self.history)[-2:]
        )

    def _is_japanese_subset_of_recent(self, japanese: str) -> bool:
        current = self._compact_for_overlap(japanese)
        if len(current) < 4:
            return False
        for item in list(self.history)[-3:]:
            previous = self._compact_for_overlap(item.japanese)
            if len(previous) >= len(current) and current in previous:
                return True
            previous_sentences = self._split_sentences(item.japanese)
            if (
                (len(previous_sentences) > 1 or len(previous) >= len(current) + 10)
                and len(current) >= 8
                and self._longest_common_substring_length(current, previous) / len(current) >= 0.6
            ):
                return True
        return False

    def _is_recent_utterance_revision(self, utterance: Utterance) -> bool:
        if not self.history:
            return False
        previous = self.history[-1]
        previous_compact = self._compact_for_overlap(previous.japanese)
        current_compact = self._compact_for_overlap(utterance.japanese)
        if len(previous_compact) < 6 or len(current_compact) < 6:
            return False
        if previous_compact in current_compact or current_compact in previous_compact:
            return True
        common = self._longest_common_substring_length(current_compact, previous_compact)
        return (
            self._similarity(current_compact, previous_compact) >= 0.72
            or common / min(len(current_compact), len(previous_compact)) >= 0.6
        )

    def _compact_for_overlap(self, text: str) -> str:
        return re.sub(r"[\s\u3002\uff01\uff1f.!?\u3001,]", "", text)

    def _common_prefix_length(self, left: str, right: str) -> int:
        size = min(len(left), len(right))
        for index in range(size):
            if left[index] != right[index]:
                return index
        return size

    def _is_recent_failed_japanese(self, japanese: str) -> bool:
        return any(
            self._similarity(japanese, failed) >= 0.96
            for failed in self.failed_japanese
        )

    def _is_duplicate_utterance(self, utterance: Utterance) -> bool:
        return any(
            self._similarity(utterance.korean, item.korean) >= 0.88
            or self._similarity(utterance.japanese, item.japanese) >= 0.92
            for item in list(self.history)[-3:]
        )

    def _is_uncertain_translation(self, korean: str) -> bool:
        normalized = korean.strip().lower()
        uncertain_prefixes = ("불확실", "不確実", "uncertain", "번역 불가")
        return any(normalized.startswith(prefix.lower()) for prefix in uncertain_prefixes)

    def _is_known_stt_hallucination(self, japanese: str) -> bool:
        compact = self._compact_for_overlap(japanese)
        if not compact:
            return True
        hallucinations = (
            "ご視聴ありがとうございました",
            "ご清聴ありがとうございました",
            "チャンネル登録お願いします",
            "字幕視聴ありがとうございました",
            "字幕をオンにしてください",
            "最後までご視聴",
        )
        if any(phrase in compact for phrase in hallucinations):
            return True
        if len(compact) >= 12 and len(set(compact)) <= 3:
            return True
        return False

    def _should_hold_japanese_fragment(self, japanese: str) -> bool:
        compact = self._compact_for_overlap(japanese)
        if len(compact) < 3:
            return False
        if self._ends_like_complete_sentence(japanese):
            return False
        if len(compact) > self.config.pending_fragment_max_chars:
            return False
        return compact.endswith(
            (
                "\u306e",
                "\u3092",
                "\u306b",
                "\u3078",
                "\u3068",
                "\u304c",
                "\u306f",
                "\u3082",
                "\u3067",
                "\u304b\u3089",
                "\u307e\u3067",
                "\u3063\u3066",
                "\u3057",
                "\u3066",
                "\u3068\u304b",
                "\u3068\u3044\u3046",
                "\u307f\u305f\u3044\u306a",
                "\u306a\u3093\u304b",
                "\u3042\u306e",
                "\u3048\u3063\u3068",
            )
        )

    def _ends_like_complete_sentence(self, japanese: str) -> bool:
        stripped = japanese.strip()
        if not stripped:
            return False
        if stripped[-1] in "\u3002\uff01\uff1f.!?":
            return True
        endings = (
            "\u3067\u3059",
            "\u307e\u3059",
            "\u3067\u3057\u305f",
            "\u307e\u3057\u305f",
            "\u3093\u3067\u3059",
            "\u306a\u3093\u3067\u3059",
            "\u3067\u3059\u306d",
            "\u3067\u3059\u3088",
            "\u307e\u3059\u306d",
            "\u307e\u3059\u3088",
            "\u3060",
            "\u3060\u3088",
            "\u3060\u306d",
            "\u3060\u3063\u305f",
            "\u3060\u3063\u305f\u3093\u3067\u3059",
            "\u305f",
            "\u3063\u305f",
            "\u306a\u3044",
            "\u306a\u304b\u3063\u305f",
            "\u308b",
            "\u3059\u308b",
            "\u3057\u305f",
            "\u3088",
            "\u306d",
            "\u304b\u306a",
            "\u304b\u3082",
            "\u3058\u3083\u3093",
            "\u3051\u3069",
            "\u3051\u3069\u306d",
        )
        return stripped.endswith(endings) or self._compact_for_overlap(stripped).endswith(endings)

    def _similarity(self, left: str, right: str) -> float:
        left = " ".join(left.split())
        right = " ".join(right.split())
        if not left or not right:
            return 0.0
        return SequenceMatcher(None, left, right).ratio()

    def _longest_common_substring_length(self, left: str, right: str) -> int:
        if not left or not right:
            return 0
        previous = [0] * (len(right) + 1)
        best = 0
        for left_char in left:
            current = [0] * (len(right) + 1)
            for index, right_char in enumerate(right, start=1):
                if left_char == right_char:
                    current[index] = previous[index - 1] + 1
                    best = max(best, current[index])
            previous = current
        return best

    def run_forever(self, on_update: Callable[[list[Utterance]], None]) -> None:
        recent_chunk_count = max(
            self.config.audio_queue_size,
            ceil(self.config.audio_buffer_seconds / self.config.capture_interval_seconds),
        )
        stream = ContinuousSystemAudioCapture(
            self.config.sample_rate,
            self.config.capture_interval_seconds,
            recent_chunk_count,
            recent_chunk_count,
            self.config.audio_device,
            self.config.monitor_device,
            self.config.capture_process,
        )
        self._active_stream = stream
        self.status(
            f"sliding capture started: interval={self.config.capture_interval_seconds:.1f}s, "
            f"window={self.config.chunk_seconds:.1f}s, "
            f"buffer={self.config.audio_buffer_seconds:.1f}s"
        )
        try:
            stream.start()
            if self.config.overlap_stt:
                self._run_overlap_forever(stream, on_update)
                return
            if self.config.endpointing:
                self._run_endpointing_forever(stream, on_update)
                return

            while not self._stop_event.is_set():
                max_frames = int(self.config.sample_rate * self.config.chunk_seconds)
                if self.config.stt_provider == "openai":
                    audio = self._read_preserved_window(stream, max_frames)
                    self.status(
                        f"processing preserved {audio.size / self.config.sample_rate:.1f}s"
                        f" queued={stream.queued_count()}"
                    )
                else:
                    audio, drained = stream.read_recent_window(max_frames)
                    drained_text = f", skipped={drained}" if drained else ""
                    self.status(
                        f"processing recent {audio.size / self.config.sample_rate:.1f}s"
                        f" queued={stream.queued_count()}{drained_text}"
                    )
                if self._stop_event.is_set():
                    break
                utterance = self._process_audio_with_update(audio, on_update)
                if utterance is not None:
                    on_update(list(self.history))
        finally:
            stream.stop()
            self._active_stream = None

    def _run_overlap_forever(
        self,
        stream: ContinuousSystemAudioCapture,
        on_update: Callable[[list[Utterance]], None],
    ) -> None:
        max_window_seconds = max(
            _OVERLAP_MIN_WINDOW_SECONDS,
            self.config.overlap_window_seconds,
        )
        step_seconds = max(self.config.capture_interval_seconds, self.config.overlap_step_seconds)
        threshold = self._active_min_rms()
        self.status(
            f"overlap STT started: window={_OVERLAP_MIN_WINDOW_SECONDS:.1f}-"
            f"{max_window_seconds:.1f}s, "
            f"step={step_seconds:.1f}s, threshold={threshold:.6f}"
        )
        work_queue = self._start_processing_worker(on_update)
        last_processed = time.monotonic()
        activity: deque[tuple[float, float, float, bool]] = deque()
        had_recent_speech = False
        final_confirm_sent = False

        while not self._stop_event.is_set():
            chunk = stream.read()
            if self._stop_event.is_set():
                break
            now = time.monotonic()
            chunk_seconds = chunk.size / self.config.sample_rate if chunk.size else 0.0
            chunk_rms = rms(chunk)
            activity.append((now, chunk_seconds, chunk_rms, chunk_rms >= threshold))
            self._trim_overlap_activity(activity, now, max_window_seconds + step_seconds)

            if now - last_processed < step_seconds:
                continue
            last_processed = now

            max_active_seconds = self._overlap_active_seconds(
                activity,
                now,
                max_window_seconds,
            )
            tail_active_seconds = self._overlap_active_seconds(
                activity,
                now,
                _OVERLAP_TAIL_SECONDS,
            )
            has_window_speech = max_active_seconds >= _OVERLAP_MIN_SPEECH_SECONDS
            has_tail_speech = tail_active_seconds >= _OVERLAP_TAIL_MIN_SPEECH_SECONDS
            if not has_window_speech:
                had_recent_speech = False
                final_confirm_sent = False
                self.status(f"overlap waiting for speech: rms={chunk_rms:.6f}")
                self.debug_log.append(
                    "skip_overlap_no_speech",
                    rms=chunk_rms,
                    threshold=threshold,
                    active_seconds=max_active_seconds,
                )
                continue

            if has_tail_speech:
                had_recent_speech = True
                final_confirm_sent = False
                window_seconds = max_window_seconds
            elif had_recent_speech and not final_confirm_sent:
                final_confirm_sent = True
                window_seconds = max_window_seconds
                self.debug_log.append(
                    "overlap_final_confirm",
                    active_seconds=max_active_seconds,
                    tail_active_seconds=tail_active_seconds,
                )
            else:
                self.status("overlap waiting: stale speech window")
                self.debug_log.append(
                    "skip_overlap_stale_speech",
                    active_seconds=max_active_seconds,
                    tail_active_seconds=tail_active_seconds,
                )
                continue

            window_frames = int(self.config.sample_rate * window_seconds)
            audio = stream.snapshot_recent_window(window_frames)
            audio_seconds = audio.size / self.config.sample_rate if audio.size else 0.0
            audio_rms = rms(audio)
            self.debug_log.append(
                "overlap_window_ready",
                seconds=audio_seconds,
                target_window_seconds=window_seconds,
                rms=audio_rms,
                active_seconds=max_active_seconds,
                tail_active_seconds=tail_active_seconds,
                queue_size=work_queue.qsize(),
            )
            if audio.size == 0 or audio_rms < threshold:
                self.status(f"overlap waiting: rms={audio_rms:.6f}")
                self.debug_log.append(
                    "skip_overlap_quiet_window",
                    rms=audio_rms,
                    threshold=threshold,
                    active_seconds=max_active_seconds,
                )
                continue
            self.status(
                f"overlap STT queued: {audio_seconds:.1f}s, "
                f"rms={audio_rms:.6f}, speech={max_active_seconds:.1f}s"
            )
            self._enqueue_audio(work_queue, audio)

    def _trim_overlap_activity(
        self,
        activity: deque[tuple[float, float, float, bool]],
        now: float,
        keep_seconds: float,
    ) -> None:
        cutoff = now - keep_seconds
        while activity and activity[0][0] < cutoff:
            activity.popleft()

    def _overlap_active_seconds(
        self,
        activity: deque[tuple[float, float, float, bool]],
        now: float,
        window_seconds: float,
    ) -> float:
        cutoff = now - window_seconds
        return sum(seconds for ts, seconds, _level, active in activity if active and ts >= cutoff)

    def _run_endpointing_forever(
        self,
        stream: ContinuousSystemAudioCapture,
        on_update: Callable[[list[Utterance]], None],
    ) -> None:
        threshold = self._active_min_rms()
        self.status(
            f"endpointing started: threshold={threshold:.6f}, "
            f"silence={self.config.endpoint_silence_seconds:.1f}s"
        )
        work_queue = self._start_processing_worker(on_update)

        chunks: list[np.ndarray] = []
        pending_audio: np.ndarray | None = None
        in_speech = False
        speech_seconds = 0.0
        silence_seconds = 0.0

        while not self._stop_event.is_set():
            chunk = stream.read()
            if self._stop_event.is_set():
                break
            chunk_seconds = chunk.size / self.config.sample_rate
            chunk_rms = rms(chunk)

            if chunk_rms >= threshold:
                if not in_speech:
                    self.status(f"speech started: rms={chunk_rms:.6f}")
                    self.debug_log.append("speech_started", rms=chunk_rms)
                    chunks = []
                    speech_seconds = 0.0
                    silence_seconds = 0.0
                    in_speech = True
                chunks.append(chunk)
                speech_seconds += chunk_seconds
                silence_seconds = 0.0
            elif in_speech:
                chunks.append(chunk)
                speech_seconds += chunk_seconds
                silence_seconds += chunk_seconds
            else:
                self.status(f"waiting for speech: rms={chunk_rms:.6f}")
                continue

            if not in_speech:
                continue

            reached_silence = (
                speech_seconds >= self.config.endpoint_min_seconds
                and silence_seconds >= self.config.endpoint_silence_seconds
            )
            reached_limit = speech_seconds >= self.config.endpoint_max_seconds
            if not reached_silence and not reached_limit:
                continue

            audio = np.concatenate(chunks)
            segment_seconds = audio.size / self.config.sample_rate
            reason = "max" if reached_limit else "silence"
            pending_seconds = (
                pending_audio.size / self.config.sample_rate
                if pending_audio is not None
                else 0.0
            )
            combined_seconds = pending_seconds + segment_seconds
            if (
                not reached_limit
                and combined_seconds < self.config.endpoint_merge_short_seconds
            ):
                pending_audio = (
                    audio
                    if pending_audio is None
                    else np.concatenate([pending_audio, audio])
                )
                self.status(
                    f"holding short speech segment: {segment_seconds:.1f}s"
                )
                self.debug_log.append(
                    "holding_short_speech",
                    segment_seconds=segment_seconds,
                    combined_seconds=combined_seconds,
                )
                chunks = []
                in_speech = False
                speech_seconds = 0.0
                silence_seconds = 0.0
                continue

            if pending_audio is not None:
                audio = np.concatenate([pending_audio, audio])
                pending_audio = None
                self.status(f"merged short speech prefix: {pending_seconds:.1f}s")
                self.debug_log.append("merged_short_speech", pending_seconds=pending_seconds)

            self.status(
                f"speech ended by {reason}: {audio.size / self.config.sample_rate:.1f}s"
            )
            self.debug_log.append(
                "speech_ended",
                reason=reason,
                seconds=audio.size / self.config.sample_rate,
                queue_size=work_queue.qsize(),
            )
            self._enqueue_audio(work_queue, audio)

            chunks = []
            in_speech = False
            speech_seconds = 0.0
            silence_seconds = 0.0

    def _start_processing_worker(
        self,
        on_update: Callable[[list[Utterance]], None],
    ) -> queue.Queue[np.ndarray]:
        work_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=2)

        def worker() -> None:
            while not self._stop_event.is_set():
                audio = work_queue.get()
                if self._stop_event.is_set():
                    work_queue.task_done()
                    break
                try:
                    utterance = self._process_audio_with_update(audio, on_update)
                    if utterance is not None:
                        on_update(list(self.history))
                except Exception as exc:
                    self.status(f"processing worker error: {exc}")
                    self.debug_log.append("processing_worker_error", error=str(exc))
                    on_update(list(self.history))
                finally:
                    work_queue.task_done()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return work_queue

    def _enqueue_audio(self, work_queue: queue.Queue[np.ndarray], audio: np.ndarray) -> None:
        if work_queue.full():
            try:
                work_queue.get_nowait()
                work_queue.task_done()
                self.status("dropped stale speech segment")
                self.debug_log.append("dropped_stale_speech_segment")
            except queue.Empty:
                pass
        work_queue.put(audio)

    def _active_min_rms(self) -> float:
        if self.config.stt_provider == "openai":
            return self.config.openai_min_rms
        if self.config.capture_process:
            return self.config.process_min_rms
        return self.config.min_rms

    def _read_preserved_window(
        self,
        stream: ContinuousSystemAudioCapture,
        max_frames: int,
    ):
        chunks = [stream.read()]
        total_frames = chunks[0].size
        while total_frames < max_frames:
            chunk = stream.read()
            chunks.append(chunk)
            total_frames += chunk.size
        audio = np.concatenate(chunks)
        if audio.size > max_frames:
            audio = audio[-max_frames:]
        return audio
