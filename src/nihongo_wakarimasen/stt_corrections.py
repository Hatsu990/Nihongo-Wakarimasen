from __future__ import annotations

import json
from pathlib import Path


class STTCorrections:
    def __init__(self, path: Path) -> None:
        self.replacements = self._load(path)

    def apply(self, text: str) -> tuple[str, list[dict[str, str]]]:
        corrected = text
        applied = []
        for source, target in self.replacements:
            if source in corrected:
                corrected = corrected.replace(source, target)
                applied.append({"source": source, "target": target})
        return corrected, applied

    def _load(self, path: Path) -> list[tuple[str, str]]:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            (item["source"], item["target"])
            for item in data.get("replacements", [])
            if item.get("source") and item.get("target")
        ]
