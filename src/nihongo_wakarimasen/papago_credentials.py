from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PapagoCredentials:
    client_id: str = ""
    client_secret: str = ""


def load_papago_credentials(path: Path | None) -> PapagoCredentials:
    if path is None or not path.exists():
        return PapagoCredentials()
    data = json.loads(path.read_text(encoding="utf-8"))
    return PapagoCredentials(
        client_id=str(data.get("client_id", "")).strip(),
        client_secret=str(data.get("client_secret", "")).strip(),
    )


def save_papago_credentials(path: Path, client_id: str, client_secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "client_id": client_id.strip(),
                "client_secret": client_secret.strip(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
