from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from faster_whisper import WhisperModel


MODEL = "kotoba-tech/kotoba-whisper-v2.0-faster"
DEVICE = "cuda"
COMPUTE_TYPE = "float16"


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def main() -> int:
    os.chdir(_runtime_root())
    print("Nihongo Wakarimasen local model downloader")
    print("")
    print(f"Model: {MODEL}")
    print(f"Device: {DEVICE}")
    print(f"Compute type: {COMPUTE_TYPE}")
    print("")
    print("The first run may take several minutes depending on your internet speed.")
    print("Please keep this window open until you see 'Model is ready'.")
    print("")
    try:
        WhisperModel(MODEL, device=DEVICE, compute_type=COMPUTE_TYPE)
    except Exception:
        print("")
        print("Model download or GPU initialization failed.")
        print("Check your internet connection, NVIDIA driver, and GPU support.")
        print("")
        traceback.print_exc()
        input("\nPress Enter to close...")
        return 1
    print("")
    print("Model is ready.")
    input("\nPress Enter to close...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
