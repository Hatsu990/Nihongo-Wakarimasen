from __future__ import annotations

import argparse

from faster_whisper import WhisperModel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="kotoba-tech/kotoba-whisper-v2.0-faster")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--compute-type", default="float16")
    args = parser.parse_args()

    print(f"Loading model: {args.model}")
    print(f"device={args.device}, compute_type={args.compute_type}")
    WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    print("Model is ready.")


if __name__ == "__main__":
    main()
