from __future__ import annotations

import os
import sys
from pathlib import Path

from nihongo_wakarimasen.config import AppConfig
from nihongo_wakarimasen.overlay import run_overlay


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _set_default_env() -> None:
    defaults = {
        "NW_STT_PROVIDER": "local",
        "NW_WHISPER_MODEL": "kotoba-tech/kotoba-whisper-v2.0-faster",
        "NW_WHISPER_DEVICE": "cuda",
        "NW_WHISPER_COMPUTE_TYPE": "float16",
        "NW_STT_BEAM_SIZE": "5",
        "NW_CAPTURE_INTERVAL_SECONDS": "0.25",
        "NW_OVERLAP_STT": "1",
        "NW_OVERLAP_WINDOW_SECONDS": "5.5",
        "NW_OVERLAP_STEP_SECONDS": "1.5",
        "NW_PAPAGO_TIMEOUT_SECONDS": "4",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def main() -> int:
    os.chdir(_runtime_root())
    _set_default_env()
    return run_overlay(AppConfig.from_env())


if __name__ == "__main__":
    raise SystemExit(main())
