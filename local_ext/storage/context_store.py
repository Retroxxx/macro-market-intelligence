from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def data_dir() -> Path:
    path = Path(os.environ.get("LOCAL_MACRO_DATA_DIR", ".local-data/local-ext"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_latest() -> dict[str, Any] | None:
    path = data_dir() / "context.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def write_latest(value: dict[str, Any]) -> None:
    root = data_dir()
    temporary = root / "context.json.tmp"
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(root / "context.json")
