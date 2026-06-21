from __future__ import annotations

import argparse
import time
from dataclasses import replace

import numpy as np

from .audio import ContinuousSystemAudioCapture, create_audio_capture, find_speaker, rms
from .config import AppConfig
from .diagnostics import print_diagnostics
from .pipeline import ListeningPipeline
from .translator import create_translator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overlay", action="store_true", help="Run the subtitle overlay.")
    parser.add_argument("--once", action="store_true", help="Capture once and print the result.")
    parser.add_argument("--diagnose", action="store_true", help="Print environment and audio device diagnostics.")
    parser.add_argument("--hotword-manager", action="store_true", help="Open the user-managed STT hotword dictionary.")
    parser.add_argument("--audio-meter", action="store_true", help="Print capture RMS/peak levels without STT.")
    parser.add_argument("--translate-text", default=None, help="Translate one Japanese text and exit.")
    parser.add_argument("--realtime-translate", action="store_true", help="Use OpenAI Realtime Translate instead of local STT plus text translation.")
    parser.add_argument("--realtime-target-language", default=None, help="Realtime Translate output language code.")
    parser.add_argument("--audio-device", default=None, help="Capture output device name fragment.")
    parser.add_argument("--capture-process", default=None, help="Capture audio from a Windows process name or PID.")
    parser.add_argument("--monitor-device", default=None, help="Playback output device name fragment for captured audio.")
    parser.add_argument("--seconds", type=float, default=None, help="Audio window length for one STT pass.")
    parser.add_argument("--capture-interval", type=float, default=None, help="Continuous capture interval for overlay mode.")
    parser.add_argument("--buffer-seconds", type=float, default=None, help="Recent audio buffer length.")
    parser.add_argument("--overlap-stt", action="store_true", help="Run recent-window STT repeatedly for faster provisional subtitles.")
    parser.add_argument("--overlap-window", type=float, default=None, help="Recent audio window length for overlap STT.")
    parser.add_argument("--overlap-step", type=float, default=None, help="Seconds between overlap STT requests.")
    parser.add_argument("--endpointing", action="store_true", help="Group audio by speech start/end before STT.")
    parser.add_argument("--endpoint-min", type=float, default=None, help="Minimum speech segment length before endpointing can close.")
    parser.add_argument("--endpoint-silence", type=float, default=None, help="Silence length that closes a speech segment.")
    parser.add_argument("--endpoint-max", type=float, default=None, help="Maximum speech segment length before forcing STT.")
    parser.add_argument("--endpoint-merge-short", type=float, default=None, help="Hold shorter speech segments and merge them into the next segment.")
    parser.add_argument("--beam-size", type=int, default=None, help="STT beam size.")
    parser.add_argument("--stt-provider", choices=["local", "openai"], default=None, help="STT provider.")
    parser.add_argument("--openai-stt-model", default=None, help="OpenAI transcription model.")
    parser.add_argument("--translator", choices=["openai", "papago"], default=None, help="Translation provider.")
    parser.add_argument("--papago-timeout", type=float, default=None, help="Papago request timeout in seconds.")
    parser.add_argument("--openai-model", default=None, help="OpenAI text translation model.")
    parser.add_argument("--queue-size", type=int, default=None, help="Continuous capture queue size.")
    parser.add_argument(
        "--translation-mode",
        choices=["conservative", "balanced"],
        default=None,
        help="Translation correction strength.",
    )
    parser.add_argument("--no-hints", action="store_true", help="Disable ASR hint file during translation.")
    args = parser.parse_args()

    config = AppConfig.from_env()
    if args.audio_device is not None:
        config = replace(config, audio_device=args.audio_device)
    if args.capture_process is not None:
        config = replace(config, capture_process=args.capture_process)
    if args.monitor_device is not None:
        config = replace(config, monitor_device=args.monitor_device)
    if args.realtime_translate:
        config = replace(config, realtime_translate=True)
    if args.realtime_target_language is not None:
        config = replace(config, realtime_target_language=args.realtime_target_language)
    if args.seconds is not None:
        config = replace(config, chunk_seconds=args.seconds)
    if args.capture_interval is not None:
        config = replace(config, capture_interval_seconds=args.capture_interval)
    if args.buffer_seconds is not None:
        config = replace(config, audio_buffer_seconds=args.buffer_seconds)
    if args.overlap_stt:
        config = replace(config, overlap_stt=True)
    if args.overlap_window is not None:
        config = replace(config, overlap_window_seconds=args.overlap_window)
    if args.overlap_step is not None:
        config = replace(config, overlap_step_seconds=args.overlap_step)
    if args.endpointing:
        config = replace(config, endpointing=True)
    if args.endpoint_min is not None:
        config = replace(config, endpoint_min_seconds=args.endpoint_min)
    if args.endpoint_silence is not None:
        config = replace(config, endpoint_silence_seconds=args.endpoint_silence)
    if args.endpoint_max is not None:
        config = replace(config, endpoint_max_seconds=args.endpoint_max)
    if args.endpoint_merge_short is not None:
        config = replace(config, endpoint_merge_short_seconds=args.endpoint_merge_short)
    if args.beam_size is not None:
        config = replace(config, stt_beam_size=args.beam_size)
    if args.stt_provider is not None:
        config = replace(config, stt_provider=args.stt_provider)
    if args.openai_stt_model is not None:
        config = replace(config, openai_stt_model=args.openai_stt_model)
    if args.translator is not None:
        config = replace(config, translator_provider=args.translator)
    if args.papago_timeout is not None:
        config = replace(config, papago_timeout_seconds=args.papago_timeout)
    if args.openai_model is not None:
        config = replace(config, openai_model=args.openai_model)
    if args.queue_size is not None:
        config = replace(config, audio_queue_size=args.queue_size)
    if args.translation_mode is not None:
        config = replace(config, translation_mode=args.translation_mode)
    if args.no_hints:
        config = replace(config, use_asr_hints=False)

    if args.translate_text is not None:
        translator = create_translator(
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
        try:
            print(translator.translate(args.translate_text), flush=True)
        except Exception as exc:
            print(f"translation failed: {exc}", flush=True)
        return

    if args.diagnose:
        print_diagnostics(config)
        return

    if args.hotword_manager:
        from .hotword_manager import run_hotword_manager

        raise SystemExit(run_hotword_manager(config))

    if args.audio_meter:
        total_seconds = config.chunk_seconds
        interval_seconds = min(config.capture_interval_seconds, total_seconds)
        monitor_speaker = find_speaker(config.monitor_device) if config.monitor_device else None
        started = time.monotonic()
        print(
            f"Audio meter: device={config.audio_device or '(default)'}, "
            f"process={config.capture_process or '(none)'}, "
            f"monitor={config.monitor_device or '(none)'}, "
            f"seconds={total_seconds:.1f}, interval={interval_seconds:.2f}",
            flush=True,
        )
        if config.capture_process:
            stream = ContinuousSystemAudioCapture(
                config.sample_rate,
                interval_seconds,
                max_chunks=4,
                process=config.capture_process,
            )
            stream.start()
            try:
                while time.monotonic() - started < total_seconds:
                    audio = stream.read()
                    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
                    print(f"rms={rms(audio):.6f} peak={peak:.6f}", flush=True)
            finally:
                stream.stop()
            return

        capture = create_audio_capture(config.sample_rate, config.audio_device)
        if monitor_speaker is None:
            while time.monotonic() - started < total_seconds:
                audio = capture.record(interval_seconds)
                peak = float(np.max(np.abs(audio))) if audio.size else 0.0
                print(f"rms={rms(audio):.6f} peak={peak:.6f}", flush=True)
        else:
            with monitor_speaker.player(samplerate=config.sample_rate, channels=1) as player:
                while time.monotonic() - started < total_seconds:
                    audio = capture.record(interval_seconds)
                    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
                    print(f"rms={rms(audio):.6f} peak={peak:.6f}", flush=True)
                    player.play(audio.reshape(-1, 1))
        return

    if args.overlay:
        from .overlay import run_overlay

        raise SystemExit(run_overlay(config))

    if args.once:
        pipeline = ListeningPipeline(config, status=lambda message: print(message, flush=True))
        utterance = pipeline.step()
        if utterance is None:
            print("No Japanese speech was recognized.")
            return
        print(f"JP: {utterance.japanese}")
        print(f"KO: {utterance.korean}")
        return

    parser.print_help()
