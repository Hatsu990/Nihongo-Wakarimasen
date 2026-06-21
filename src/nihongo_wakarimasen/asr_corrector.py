from __future__ import annotations

import json
import os
from pathlib import Path

from openai import OpenAI


class OpenAIASRCorrector:
    def __init__(
        self,
        model: str = "gpt-4.1-mini",
        hints_path: Path | None = None,
        use_hints: bool = False,
    ) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY environment variable is required.")
        self.client = OpenAI()
        self.model = model
        self.hints = self._load_hints(hints_path) if use_hints and hints_path else []

    def correct(self, japanese: str) -> str:
        text = japanese.strip()
        if not text:
            return ""
        hints_text = "\n".join(self.hints) if self.hints else "(none)"
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You conservatively clean Japanese ASR text for live subtitles. "
                        "Return only Japanese text. Do not translate. Do not summarize. "
                        "Do not add words, events, names, or intent that are not supported by the input. "
                        "Fix only obvious ASR confusions, punctuation, spacing, and repeated fragments. "
                        "If the input is already plausible, return it unchanged."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Generic correction hints:\n"
                        f"{hints_text}\n\n"
                        "ASR text:\n"
                        f"{text}"
                    ),
                },
            ],
        )
        return response.output_text.strip()

    def _load_hints(self, hints_path: Path) -> list[str]:
        if not hints_path.exists():
            return []
        data = json.loads(hints_path.read_text(encoding="utf-8"))
        hints = []
        for item in data.get("hints", []):
            asr = str(item.get("asr", "")).strip()
            intended = str(item.get("intended", "")).strip()
            note = str(item.get("note", "")).strip()
            if asr and intended:
                hints.append(f"- {asr} -> {intended}. {note}".strip())
        return hints
