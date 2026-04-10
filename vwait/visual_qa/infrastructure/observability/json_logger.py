from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class JsonRunLogger:
    """Simple in-memory event collector that can be flushed to JSONL."""

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._events: List[Dict[str, Any]] = []

    def log(self, event: str, **kwargs: Any) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self._run_id,
            "event": event,
            **kwargs,
        }
        self._events.append(row)

    @property
    def events(self) -> List[Dict[str, Any]]:
        return list(self._events)

    def flush(self, path: Path) -> Path:
        with path.open("w", encoding="utf-8") as fh:
            for row in self._events:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path
