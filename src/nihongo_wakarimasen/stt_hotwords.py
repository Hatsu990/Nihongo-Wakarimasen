from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class STTHotwordEntry:
    name: str
    hiragana: str = ""
    katakana: str = ""
    korean: str = ""
    enabled: bool = True


class STTHotwords:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.entries = self._load(path)

    def prompt_text(self) -> str:
        words: list[str] = []
        seen = set()
        for entry in self.entries:
            if not entry.enabled:
                continue
            for value in (entry.name, entry.hiragana, entry.katakana):
                word = value.strip()
                if word and word not in seen:
                    seen.add(word)
                    words.append(word)
        return " ".join(words)

    def count_enabled_terms(self) -> int:
        return len([word for word in self.prompt_text().split(" ") if word])

    @staticmethod
    def _load(path: Path | None) -> list[STTHotwordEntry]:
        if path is None or not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = []
        for item in data.get("entries", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            hiragana = str(item.get("hiragana", "")).strip()
            katakana = str(item.get("katakana", "")).strip()
            korean = str(item.get("korean", "")).strip()
            if not any((name, hiragana, katakana, korean)):
                continue
            entries.append(
                STTHotwordEntry(
                    name=name,
                    hiragana=hiragana,
                    katakana=katakana,
                    korean=korean,
                    enabled=bool(item.get("enabled", True)),
                )
            )
        return entries
