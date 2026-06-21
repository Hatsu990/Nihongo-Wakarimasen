from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Utterance:
    timestamp: datetime
    japanese: str
    korean: str
