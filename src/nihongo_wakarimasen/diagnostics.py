from __future__ import annotations

import os
import platform

import soundcard as sc

from .config import AppConfig
from .audio import find_capture_device, find_process_id, find_speaker, list_audio_processes
from .papago_credentials import load_papago_credentials
from .stt_hotwords import STTHotwords


def print_diagnostics(config: AppConfig) -> None:
    print(f"Python: {platform.python_version()}")
    print(f"Platform: {platform.platform()}")
    print(f"Realtime translate enabled: {config.realtime_translate}")
    if config.realtime_translate:
        print(f"Realtime model: {config.realtime_model}")
        print(f"Realtime target language: {config.realtime_target_language}")
        print(f"Realtime audio chunk seconds: {config.realtime_audio_chunk_seconds}")
        print(f"Realtime log path: {config.realtime_log_path}")
    print(f"STT provider: {config.stt_provider}")
    if config.stt_provider == "openai" or config.translator_provider == "openai":
        print(f"OpenAI API key: {'set' if os.getenv('OPENAI_API_KEY') else 'missing'}")
    if config.stt_provider == "openai":
        print(f"OpenAI STT model: {config.openai_stt_model}")
    print(f"Whisper model: {config.whisper_model}")
    print(f"Whisper device: {config.whisper_device}")
    print(f"Whisper compute type: {config.whisper_compute_type}")
    print(f"STT beam size: {config.stt_beam_size}")
    print(f"Audio queue size: {config.audio_queue_size}")
    print(f"Translator provider: {config.translator_provider}")
    print(f"Translation mode: {config.translation_mode}")
    print(f"Translation dictionary path: {config.translation_dictionary_path}")
    print(f"Translation dictionary file: {'found' if config.translation_dictionary_path.exists() else 'missing'}")
    print(f"User config dir: {config.user_config_dir}")
    print(f"User translation dictionary path: {config.user_translation_dictionary_path}")
    print(f"User translation dictionary file: {'found' if config.user_translation_dictionary_path.exists() else 'missing'}")
    print(f"STT corrections path: {config.stt_corrections_path}")
    print(f"STT corrections file: {'found' if config.stt_corrections_path.exists() else 'missing'}")
    stt_hotwords = STTHotwords(config.stt_hotwords_path)
    print(f"STT hotwords path: {config.stt_hotwords_path}")
    print(f"STT hotwords file: {'found' if config.stt_hotwords_path.exists() else 'missing'}")
    print(f"STT hotwords enabled terms: {stt_hotwords.count_enabled_terms()}")
    print(f"Papago endpoint: {os.getenv('PAPAGO_API_ENDPOINT', 'https://papago.apigw.ntruss.com/nmt/v1/translation')}")
    print(f"Papago timeout seconds: {config.papago_timeout_seconds}")
    papago_credentials = load_papago_credentials(config.papago_credentials_path)
    print(f"Papago credentials path: {config.papago_credentials_path}")
    print(f"Papago credentials file: {'found' if config.papago_credentials_path.exists() else 'missing'}")
    print(f"Papago client id: {'set' if os.getenv('NAVER_CLIENT_ID') or os.getenv('PAPAGO_CLIENT_ID') or papago_credentials.client_id else 'missing'}")
    print(f"Papago client secret: {'set' if os.getenv('NAVER_CLIENT_SECRET') or os.getenv('PAPAGO_CLIENT_SECRET') or papago_credentials.client_secret else 'missing'}")
    print(f"Translation context size: {config.translation_context_size}")
    print(f"Pending fragment max chars: {config.pending_fragment_max_chars}")
    print(f"Pending fragment flush chars: {config.pending_fragment_flush_chars}")
    print(f"ASR hints path: {config.asr_hints_path}")
    print(f"ASR hints enabled: {config.use_asr_hints}")
    print(f"ASR hints file: {'found' if config.asr_hints_path.exists() else 'missing'}")
    print(f"Debug log path: {config.debug_log_path}")
    print(f"Configured audio device: {config.audio_device or '(default)'}")
    print(f"Configured capture process: {config.capture_process or '(none)'}")
    print(f"Configured monitor device: {config.monitor_device or '(none)'}")
    if config.capture_process:
        try:
            print(f"Selected capture process PID: {find_process_id(config.capture_process)}")
        except Exception as exc:
            print(f"Selected capture process: error: {exc}")
    else:
        try:
            selected_device, use_loopback = find_capture_device(config.audio_device)
            device_type = "speaker loopback" if use_loopback else "microphone/input"
            print(f"Selected capture device: {selected_device.name} ({device_type})")
        except Exception as exc:
            print(f"Selected capture device: error: {exc}")
    if config.monitor_device:
        try:
            selected_monitor = find_speaker(config.monitor_device)
            print(f"Selected monitor speaker: {selected_monitor.name}")
        except Exception as exc:
            print(f"Selected monitor speaker: error: {exc}")
    print(f"Sample rate: {config.sample_rate}")
    print(f"Chunk seconds: {config.chunk_seconds}")
    print(f"Capture interval seconds: {config.capture_interval_seconds}")
    print(f"Audio buffer seconds: {config.audio_buffer_seconds}")
    print(f"Endpointing enabled: {config.endpointing}")
    print(f"Endpoint min seconds: {config.endpoint_min_seconds}")
    print(f"Endpoint silence seconds: {config.endpoint_silence_seconds}")
    print(f"Endpoint max seconds: {config.endpoint_max_seconds}")
    print(f"Endpoint merge short seconds: {config.endpoint_merge_short_seconds}")
    print(f"Min RMS: {config.min_rms}")
    print(f"Process Min RMS: {config.process_min_rms}")
    print(f"OpenAI Min RMS: {config.openai_min_rms}")
    print(f"Min text chars: {config.min_text_chars}")
    print(f"Max no speech prob: {config.max_no_speech_prob}")
    print(f"Min avg logprob: {config.min_avg_logprob}")
    print(f"Max compression ratio: {config.max_compression_ratio}")
    print("")

    default_speaker = sc.default_speaker()
    print(f"Default speaker: {default_speaker.name if default_speaker else 'none'}")
    print("")

    print("Speakers:")
    for speaker in sc.all_speakers():
        print(f"- {speaker.name}")

    print("")
    print("Microphones:")
    for microphone in sc.all_microphones(include_loopback=True):
        print(f"- {microphone.name}")

    print("")
    print("Active audio processes:")
    for process in list_audio_processes():
        print(f"- {process}")
