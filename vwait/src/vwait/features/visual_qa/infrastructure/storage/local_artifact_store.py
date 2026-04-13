from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from vwait.features.visual_qa.application.ports.artifact_store import ArtifactStore


class LocalArtifactStore(ArtifactStore):
    def __init__(self, runs_dir: str) -> None:
        self._runs_dir = Path(runs_dir).resolve()
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._runs_dir / "index.jsonl"
        self._history_path = self._runs_dir / "logs.jsonl"

    def create_run_dir(self, run_id: str) -> Path:
        run_dir = self._runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _resolve_run_dir(self, run_or_id: str | Path) -> Path:
        candidate = Path(run_or_id)
        if candidate.is_absolute() and candidate.exists() and candidate.is_dir():
            return candidate
        return self.create_run_dir(str(run_or_id))

    def _json_default(self, value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if is_dataclass(value):
            return asdict(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    def _to_jsonable(self, payload: Any) -> Any:
        if is_dataclass(payload):
            return asdict(payload)
        if isinstance(payload, Path):
            return str(payload)
        if isinstance(payload, datetime):
            return payload.isoformat()
        if isinstance(payload, Mapping):
            return dict(payload)
        return payload

    def _capture_diff_images(self, run_dir: Path, payload: Any) -> list[str]:
        copied: list[str] = []
        if not isinstance(payload, Mapping):
            return copied

        pixel = payload.get("pixel_result")
        if not isinstance(pixel, Mapping):
            return copied

        candidates: list[str] = []
        diff_image = pixel.get("diff_image_path")
        if isinstance(diff_image, str) and diff_image.strip():
            candidates.append(diff_image)

        raw = pixel.get("raw")
        if isinstance(raw, Mapping):
            artifacts = raw.get("artifact_paths")
            if isinstance(artifacts, Mapping):
                for value in artifacts.values():
                    if isinstance(value, str) and value.strip():
                        candidates.append(value)

        if not candidates:
            return copied

        out_dir = run_dir / "diff_images"
        out_dir.mkdir(parents=True, exist_ok=True)
        seen: set[str] = set()
        for src_str in candidates:
            src = Path(src_str).expanduser()
            key = str(src.resolve()) if src.exists() else str(src)
            if key in seen:
                continue
            seen.add(key)

            if src.exists() and src.is_file():
                target = out_dir / src.name
                if target.resolve() != src.resolve():
                    shutil.copy2(src, target)
                copied.append(str(target))
            else:
                copied.append(str(src))
        return copied

    def save_json(self, *args, **kwargs) -> Path:
        """Supports both call styles:
        - save_json(run_dir, filename, payload)   # legacy
        - save_json(run_id, payload, filename=...) # new
        """
        if len(args) == 3:
            run_or_id, filename, payload = args
        elif len(args) == 2:
            run_or_id, payload = args
            filename = kwargs.pop("filename", "run_result.json")
        else:
            raise TypeError("save_json expects (run_dir, filename, payload) or (run_id, payload, filename=...)")

        run_dir = self._resolve_run_dir(run_or_id)
        data = self._to_jsonable(payload)
        copied = self._capture_diff_images(run_dir, data if isinstance(data, Mapping) else {})
        if copied and isinstance(data, dict):
            data = dict(data)
            data["diff_image_artifacts"] = copied

        path = run_dir / str(filename)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=self._json_default)
        return path

    def save_markdown(self, *args, **kwargs) -> Path:
        """Supports both call styles:
        - save_markdown(run_dir, filename, markdown)   # legacy
        - save_markdown(run_id, content, filename=...) # new
        """
        if len(args) == 3:
            run_or_id, filename, markdown = args
        elif len(args) == 2:
            run_or_id, markdown = args
            filename = kwargs.pop("filename", "report.md")
        else:
            raise TypeError(
                "save_markdown expects (run_dir, filename, markdown) or (run_id, content, filename=...)"
            )

        run_dir = self._resolve_run_dir(run_or_id)
        path = run_dir / str(filename)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(markdown)
        return path

    def save_json_lines(self, run_dir: Path, filename: str, rows: Iterable[Dict[str, Any]]) -> Path:
        path = run_dir / filename
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    def append_history(self, summary_dict: Mapping[str, Any]) -> Path:
        row = dict(summary_dict)
        row.setdefault("timestamp", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        with self._history_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=self._json_default) + "\n")
        return self._history_path

    def append_runs_index(self, row: Dict[str, Any]) -> Path:
        with self._index_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        # Keep a unified history log with key summary fields as requested.
        summary = {
            "run_id": row.get("run_id"),
            "screen_type": row.get("predicted_screen_type") or row.get("screen_type"),
            "similarity": row.get("similarity"),
            "diff_percent": row.get("difference_percent") or row.get("diff_percent"),
            "ssim": row.get("ssim_score") or row.get("ssim"),
            "timestamp": row.get("timestamp"),
        }
        self.append_history(summary)
        return self._index_path

    def load_runs_index(self) -> list[Dict[str, Any]]:
        if not self._index_path.exists():
            return []
        rows: list[Dict[str, Any]] = []
        with self._index_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
        return rows

    def compute_historical_metrics(self, screen_type: str, last_n: int = 30) -> dict[str, Any]:
        if last_n <= 0:
            raise ValueError("last_n must be greater than 0")

        if not self._history_path.exists():
            return {
                "screen_type": screen_type,
                "runs_considered": 0,
                "average_similarity": None,
                "average_diff_percent": None,
                "average_ssim": None,
            }

        rows: list[dict[str, Any]] = []
        with self._history_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue
                if str(row.get("screen_type") or "") != str(screen_type):
                    continue
                rows.append(row)

        rows = rows[-last_n:]
        sims = [float(v) for v in (r.get("similarity") for r in rows) if isinstance(v, (int, float))]
        diffs = [float(v) for v in (r.get("diff_percent") for r in rows) if isinstance(v, (int, float))]
        ssims = [float(v) for v in (r.get("ssim") for r in rows) if isinstance(v, (int, float))]

        def _avg(values: list[float]) -> float | None:
            return (sum(values) / len(values)) if values else None

        return {
            "screen_type": screen_type,
            "runs_considered": len(rows),
            "average_similarity": _avg(sims),
            "average_diff_percent": _avg(diffs),
            "average_ssim": _avg(ssims),
        }
