from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def default_user_config_dir() -> Path:
    root = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA") or str(Path.home())
    return Path(root) / "NihongoWakarimasen"


@dataclass(frozen=True)
class AppConfig:
    user_config_dir: Path = field(default_factory=default_user_config_dir)
    audio_device: str | None = None
    capture_process: str | None = None
    monitor_device: str | None = None
    realtime_translate: bool = False
    realtime_model: str = "gpt-realtime-translate"
    realtime_target_language: str = "ko"
    realtime_audio_chunk_seconds: float = 0.2
    realtime_log_path: Path = Path("logs/realtime_translate.jsonl")
    sample_rate: int = 16000
    chunk_seconds: float = 5.0
    capture_interval_seconds: float = 1.0
    audio_buffer_seconds: float = 10.0
    endpointing: bool = False
    overlap_stt: bool = False
    overlap_window_seconds: float = 5.5
    overlap_step_seconds: float = 1.5
    endpoint_min_seconds: float = 0.6
    endpoint_silence_seconds: float = 0.55
    endpoint_max_seconds: float = 4.0
    endpoint_merge_short_seconds: float = 1.2
    min_rms: float = 0.02
    process_min_rms: float = 0.006
    openai_min_rms: float = 0.005
    min_text_chars: int = 2
    max_no_speech_prob: float = 0.5
    min_avg_logprob: float = -0.7
    max_compression_ratio: float = 2.2
    stt_provider: str = "local"
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    stt_beam_size: int = 1
    audio_queue_size: int = 4
    translator_provider: str = "papago"
    papago_timeout_seconds: float = 4.0
    openai_model: str = "gpt-5-mini"
    translation_mode: str = "conservative"
    history_size: int = 4
    translation_context_size: int = 3
    pending_fragment_max_chars: int = 24
    pending_fragment_flush_chars: int = 48
    translation_dictionary_path: Path = Path("config/translation_dictionary_ja_ko.json")
    user_translation_dictionary_path: Path = field(
        default_factory=lambda: default_user_config_dir() / "translation_dictionary_user_ja_ko.json"
    )
    stt_corrections_path: Path = Path("config/stt_corrections_ja.json")
    stt_hotwords_path: Path = field(
        default_factory=lambda: default_user_config_dir() / "stt_hotwords_ja.json"
    )
    papago_credentials_path: Path = field(
        default_factory=lambda: default_user_config_dir() / "papago_credentials.json"
    )
    asr_hints_path: Path = Path("config/asr_hints_ja_ko.json")
    use_asr_hints: bool = False
    log_path: Path = Path("logs/conversation.jsonl")
    debug_log_path: Path = Path("logs/pipeline_debug.jsonl")

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            user_config_dir=Path(os.getenv("NW_USER_CONFIG_DIR", str(default_user_config_dir()))),
            audio_device=os.getenv("NW_AUDIO_DEVICE") or None,
            capture_process=os.getenv("NW_CAPTURE_PROCESS") or None,
            monitor_device=os.getenv("NW_MONITOR_DEVICE") or None,
            realtime_translate=os.getenv("NW_REALTIME_TRANSLATE", "0") != "0",
            realtime_model=os.getenv("NW_REALTIME_MODEL", "gpt-realtime-translate"),
            realtime_target_language=os.getenv("NW_REALTIME_TARGET_LANGUAGE", "ko"),
            realtime_audio_chunk_seconds=float(os.getenv("NW_REALTIME_AUDIO_CHUNK_SECONDS", "0.2")),
            realtime_log_path=Path(os.getenv("NW_REALTIME_LOG_PATH", "logs/realtime_translate.jsonl")),
            sample_rate=int(os.getenv("NW_SAMPLE_RATE", "16000")),
            chunk_seconds=float(os.getenv("NW_CHUNK_SECONDS", "5.0")),
            capture_interval_seconds=float(os.getenv("NW_CAPTURE_INTERVAL_SECONDS", "1.0")),
            audio_buffer_seconds=float(os.getenv("NW_AUDIO_BUFFER_SECONDS", "10.0")),
            endpointing=os.getenv("NW_ENDPOINTING", "0") != "0",
            overlap_stt=os.getenv("NW_OVERLAP_STT", "0") != "0",
            overlap_window_seconds=float(os.getenv("NW_OVERLAP_WINDOW_SECONDS", "5.5")),
            overlap_step_seconds=float(os.getenv("NW_OVERLAP_STEP_SECONDS", "1.5")),
            endpoint_min_seconds=float(os.getenv("NW_ENDPOINT_MIN_SECONDS", "0.6")),
            endpoint_silence_seconds=float(os.getenv("NW_ENDPOINT_SILENCE_SECONDS", "0.55")),
            endpoint_max_seconds=float(os.getenv("NW_ENDPOINT_MAX_SECONDS", "4.0")),
            endpoint_merge_short_seconds=float(os.getenv("NW_ENDPOINT_MERGE_SHORT_SECONDS", "1.2")),
            min_rms=float(os.getenv("NW_MIN_RMS", "0.02")),
            process_min_rms=float(os.getenv("NW_PROCESS_MIN_RMS", "0.006")),
            openai_min_rms=float(os.getenv("NW_OPENAI_MIN_RMS", "0.005")),
            min_text_chars=int(os.getenv("NW_MIN_TEXT_CHARS", "2")),
            max_no_speech_prob=float(os.getenv("NW_MAX_NO_SPEECH_PROB", "0.5")),
            min_avg_logprob=float(os.getenv("NW_MIN_AVG_LOGPROB", "-0.7")),
            max_compression_ratio=float(os.getenv("NW_MAX_COMPRESSION_RATIO", "2.2")),
            stt_provider=os.getenv("NW_STT_PROVIDER", "local"),
            openai_stt_model=os.getenv("NW_OPENAI_STT_MODEL", "gpt-4o-mini-transcribe"),
            whisper_model=os.getenv("NW_WHISPER_MODEL", "small"),
            whisper_device=os.getenv("NW_WHISPER_DEVICE", "cpu"),
            whisper_compute_type=os.getenv("NW_WHISPER_COMPUTE_TYPE", "int8"),
            stt_beam_size=int(os.getenv("NW_STT_BEAM_SIZE", "1")),
            audio_queue_size=int(os.getenv("NW_AUDIO_QUEUE_SIZE", "4")),
            translator_provider=os.getenv("NW_TRANSLATOR_PROVIDER", "papago"),
            papago_timeout_seconds=float(os.getenv("NW_PAPAGO_TIMEOUT_SECONDS", "4.0")),
            openai_model=os.getenv("NW_OPENAI_MODEL", "gpt-5-mini"),
            translation_mode=os.getenv("NW_TRANSLATION_MODE", "conservative"),
            history_size=int(os.getenv("NW_HISTORY_SIZE", "4")),
            translation_context_size=int(os.getenv("NW_TRANSLATION_CONTEXT_SIZE", "3")),
            pending_fragment_max_chars=int(os.getenv("NW_PENDING_FRAGMENT_MAX_CHARS", "24")),
            pending_fragment_flush_chars=int(os.getenv("NW_PENDING_FRAGMENT_FLUSH_CHARS", "48")),
            translation_dictionary_path=Path(os.getenv("NW_TRANSLATION_DICTIONARY_PATH", "config/translation_dictionary_ja_ko.json")),
            user_translation_dictionary_path=Path(os.getenv("NW_USER_TRANSLATION_DICTIONARY_PATH", str(default_user_config_dir() / "translation_dictionary_user_ja_ko.json"))),
            stt_corrections_path=Path(os.getenv("NW_STT_CORRECTIONS_PATH", "config/stt_corrections_ja.json")),
            stt_hotwords_path=Path(os.getenv("NW_STT_HOTWORDS_PATH", str(default_user_config_dir() / "stt_hotwords_ja.json"))),
            papago_credentials_path=Path(os.getenv("NW_PAPAGO_CREDENTIALS_PATH", str(default_user_config_dir() / "papago_credentials.json"))),
            asr_hints_path=Path(os.getenv("NW_ASR_HINTS_PATH", "config/asr_hints_ja_ko.json")),
            use_asr_hints=os.getenv("NW_USE_ASR_HINTS", "0") != "0",
            log_path=Path(os.getenv("NW_LOG_PATH", "logs/conversation.jsonl")),
            debug_log_path=Path(os.getenv("NW_DEBUG_LOG_PATH", "logs/pipeline_debug.jsonl")),
        )
