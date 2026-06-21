from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class DebugLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, **fields: Any) -> None:
        record = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
