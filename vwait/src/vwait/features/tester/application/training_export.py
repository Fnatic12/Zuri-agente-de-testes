from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vwait.core.paths import (
    ensure_data_roots,
    normalize_segment,
    tester_actions_path,
    tester_catalog_dir,
    tester_expected_final_path,
    tester_recorded_dir,
    tester_recorded_frames_dir,
    tester_test_metadata_path,
    training_episode_dir,
    training_manifest_all_episodes_path,
    training_taxonomy_categories_path,
    training_taxonomy_flows_path,
)
from vwait.platform.adb import resolve_adb_path


SCHEMA_VERSION = "1.0"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_utc(moment: datetime | None = None) -> str:
    return (moment or _utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _episode_id(moment: datetime | None = None) -> str:
    dt = moment or _utc_now()
    return f"ep_{dt.strftime('%Y%m%d')}_{dt.strftime('%H%M%S')}_{secrets.token_hex(3)}"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _copy_image(src: Path | None, dst: Path) -> bool:
    if not src or not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _split_lines(raw_text: str | None) -> list[str]:
    return [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]


def _parse_iso_timestamp(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _duration_ms(actions: list[dict[str, Any]]) -> int | None:
    starts = [_parse_iso_timestamp(item.get("action_timestamp") or item.get("timestamp")) for item in actions if isinstance(item, dict)]
    ends = [_parse_iso_timestamp(item.get("screenshot_timestamp") or item.get("timestamp")) for item in actions if isinstance(item, dict)]
    starts = [item for item in starts if item is not None]
    ends = [item for item in ends if item is not None]
    if not starts or not ends:
        return None
    return max(0, int((max(ends) - min(starts)) * 1000))


def _adb_shell_text(serial: str | None, *shell_args: str) -> str | None:
    adb_path = resolve_adb_path()
    if not adb_path:
        return None
    cmd = [adb_path]
    if serial:
        cmd += ["-s", serial]
    cmd += ["shell", *shell_args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    text = (result.stdout or "").strip()
    return text or None


def _wm_resolution(serial: str | None, fallback: dict[str, Any]) -> dict[str, int | None]:
    raw = _adb_shell_text(serial, "wm", "size") or ""
    width = height = None
    for token in raw.split():
        if "x" not in token:
            continue
        try:
            maybe_w, maybe_h = token.split("x", 1)
            width = int(maybe_w)
            height = int(maybe_h)
            break
        except Exception:
            continue
    return {
        "width": width or fallback.get("width"),
        "height": height or fallback.get("height"),
    }


def _fallback_resolution(actions: list[dict[str, Any]]) -> dict[str, int | None]:
    for item in actions:
        if not isinstance(item, dict):
            continue
        action = item.get("acao") if isinstance(item.get("acao"), dict) else {}
        resolution = action.get("resolucao") if isinstance(action, dict) else {}
        if not isinstance(resolution, dict):
            continue
        width = resolution.get("largura")
        height = resolution.get("altura")
        if width or height:
            return {
                "width": int(width) if width else None,
                "height": int(height) if height else None,
            }
    return {"width": None, "height": None}


def _update_taxonomy(path: Path, key: str, raw_name: str, extra: dict[str, Any] | None = None) -> None:
    name = str(raw_name or "").strip()
    if not name:
        return
    slug = normalize_segment(name)
    payload = _load_json(path)
    entries = payload.get(key)
    if not isinstance(entries, list):
        entries = []
    by_slug = {str(item.get("slug")): item for item in entries if isinstance(item, dict)}
    item = {
        "slug": slug,
        "name": name,
        "updated_at": _iso_utc(),
    }
    if extra:
        item.update(extra)
    if slug in by_slug:
        by_slug[slug].update(item)
    else:
        by_slug[slug] = item
    ordered = [by_slug[item] for item in sorted(by_slug)]
    _write_json(path, {"schema_version": SCHEMA_VERSION, key: ordered})


def _update_manifest(entry: dict[str, Any]) -> None:
    path = training_manifest_all_episodes_path()
    entries: dict[str, dict[str, Any]] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict) and item.get("episode_id"):
                entries[str(item["episode_id"])] = item
    entries[str(entry["episode_id"])] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(entries[key], ensure_ascii=False, sort_keys=True)
        for key in sorted(entries, key=lambda value: str(entries[value].get("created_at", "")))
    ]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    os.replace(tmp, path)


def _action_metadata(action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {}
    return {
        "type": action.get("tipo"),
        "gesture": action.get("gesture"),
        "coordinates": {
            key: action.get(key)
            for key in ("x", "y", "x1", "y1", "x2", "y2")
            if key in action
        },
        "duration_s": action.get("duracao_s"),
        "duration_ms": action.get("duracao_ms"),
    }


def _validated_training_metadata(
    *,
    training_category: str,
    flow: str,
    objective: str,
    success_criteria_final: str,
) -> tuple[bool, str, dict[str, str]]:
    category_name = str(training_category or "").strip()
    flow_name = str(flow or "").strip()
    objective_text = str(objective or "").strip()
    success_text = str(success_criteria_final or "").strip()
    missing = [
        label
        for label, value in (
            ("Categoria/DOMINIO", category_name),
            ("Fluxo/Caso de teste", flow_name),
            ("Objetivo do episodio", objective_text),
            ("Criterio de sucesso final", success_text),
        )
        if not value
    ]
    if missing:
        return False, "Campos obrigatorios ausentes: " + ", ".join(missing), {}
    return True, "", {
        "category_name": category_name,
        "flow_name": flow_name,
        "objective_text": objective_text,
        "success_text": success_text,
        "category_slug": normalize_segment(category_name),
        "flow_slug": normalize_segment(flow_name),
    }


def create_training_episode_draft(
    *,
    category: str,
    test_name: str,
    training_category: str,
    flow: str,
    objective: str,
    success_criteria_final: str,
    tester_id: str | None = None,
    notes: str | None = None,
    serial: str | None = None,
    input_source: str | None = None,
    step_intents_text: str | None = None,
    step_expected_text: str | None = None,
) -> tuple[bool, str, str | None]:
    ensure_data_roots()

    ok, error, meta = _validated_training_metadata(
        training_category=training_category,
        flow=flow,
        objective=objective,
        success_criteria_final=success_criteria_final,
    )
    if not ok:
        return False, error, None

    created_at = _iso_utc()
    episode_id = _episode_id()
    episode_dir = training_episode_dir(meta["category_slug"], meta["flow_slug"], episode_id)
    steps_root = episode_dir / "steps"
    data_source_path = tester_catalog_dir(category, test_name)
    initial_state_path = tester_recorded_dir(category, test_name) / "initial_state.png"
    final_expected_src = tester_expected_final_path(category, test_name)
    resolution = _wm_resolution(serial, {"width": None, "height": None})

    steps_root.mkdir(parents=True, exist_ok=True)
    _write_json(
        episode_dir / "episode.json",
        {
            "schema_version": SCHEMA_VERSION,
            "episode_id": episode_id,
            "category": meta["category_slug"],
            "category_name": meta["category_name"],
            "flow": meta["flow_slug"],
            "flow_name": meta["flow_name"],
            "objective": meta["objective_text"],
            "success_criteria_final": meta["success_text"],
            "tester_id": tester_id or None,
            "created_at": created_at,
            "step_count": 0,
            "notes": str(notes or "").strip(),
            "status": "recording",
        },
    )
    _write_json(
        episode_dir / "environment.json",
        {
            "schema_version": SCHEMA_VERSION,
            "device_id": serial or None,
            "source": input_source or None,
            "os_version": _adb_shell_text(serial, "getprop", "ro.build.version.release"),
            "build_version": _adb_shell_text(serial, "getprop", "ro.build.display.id"),
            "resolution": {"width": resolution.get("width"), "height": resolution.get("height")},
            "device_model": _adb_shell_text(serial, "getprop", "ro.product.model"),
            "manufacturer": _adb_shell_text(serial, "getprop", "ro.product.manufacturer"),
        },
    )
    _write_json(
        episode_dir / "summary.json",
        {
            "schema_version": SCHEMA_VERSION,
            "status": "recording",
            "duration_ms": None,
            "steps_recorded": 0,
            "manual_step_annotations": bool(_split_lines(step_intents_text) or _split_lines(step_expected_text)),
            "missing_artifacts": [],
        },
    )
    _write_json(
        episode_dir / "manual_annotations.json",
        {
            "schema_version": SCHEMA_VERSION,
            "step_intents": _split_lines(step_intents_text),
            "step_expected_results": _split_lines(step_expected_text),
            "raw_step_intents_text": str(step_intents_text or ""),
            "raw_step_expected_text": str(step_expected_text or ""),
        },
    )
    _write_json(
        episode_dir / "source_refs.json",
        {
            "schema_version": SCHEMA_VERSION,
            "data_source_path": str(data_source_path),
            "recorded_initial_state": str(initial_state_path) if initial_state_path.is_file() else None,
            "source_session_id": None,
            "actions_path": str(tester_actions_path(category, test_name)),
            "expected_final_path": str(final_expected_src) if final_expected_src.is_file() else None,
            "final_expected_exported": None,
        },
    )

    _update_taxonomy(training_taxonomy_categories_path(), "categories", meta["category_name"])
    _update_taxonomy(
        training_taxonomy_flows_path(),
        "flows",
        meta["flow_name"],
        {"category": meta["category_slug"], "category_name": meta["category_name"]},
    )
    _update_manifest(
        {
            "episode_id": episode_id,
            "category": meta["category_slug"],
            "flow": meta["flow_slug"],
            "objective": meta["objective_text"],
            "success_criteria_final": meta["success_text"],
            "path": str(episode_dir),
            "created_at": created_at,
            "step_count": 0,
            "status": "recording",
        }
    )
    return True, str(episode_dir), episode_id


def export_training_episode(
    *,
    category: str,
    test_name: str,
    training_category: str,
    flow: str,
    objective: str,
    success_criteria_final: str,
    tester_id: str | None = None,
    notes: str | None = None,
    serial: str | None = None,
    input_source: str | None = None,
    step_intents_text: str | None = None,
    step_expected_text: str | None = None,
    episode_id: str | None = None,
) -> tuple[bool, str]:
    ensure_data_roots()

    operational_category = normalize_segment(category)
    operational_test = normalize_segment(test_name)
    ok, error, meta = _validated_training_metadata(
        training_category=training_category,
        flow=flow,
        objective=objective,
        success_criteria_final=success_criteria_final,
    )
    if not ok:
        return False, error

    category_name = meta["category_name"]
    flow_name = meta["flow_name"]
    objective_text = meta["objective_text"]
    success_text = meta["success_text"]
    category_slug = meta["category_slug"]
    flow_slug = meta["flow_slug"]
    created_at = _iso_utc()
    final_episode_id = normalize_segment(episode_id) if episode_id else _episode_id()
    episode_dir = training_episode_dir(category_slug, flow_slug, final_episode_id)
    steps_root = episode_dir / "steps"

    actions_path = tester_actions_path(operational_category, operational_test)
    actions_payload = _load_json(actions_path)
    actions = actions_payload.get("acoes")
    if not isinstance(actions, list) or not actions:
        return False, "Nenhuma acao encontrada para exportar."

    test_meta = _load_json(tester_test_metadata_path(operational_category, operational_test))
    data_source_path = tester_catalog_dir(operational_category, operational_test)
    recorded_dir = tester_recorded_dir(operational_category, operational_test)
    frames_dir = tester_recorded_frames_dir(operational_category, operational_test)
    initial_state_path = recorded_dir / "initial_state.png"
    final_expected_src = tester_expected_final_path(operational_category, operational_test)

    episode_dir.mkdir(parents=True, exist_ok=True)
    steps_root.mkdir(parents=True, exist_ok=True)

    intents = _split_lines(step_intents_text)
    expected_results = _split_lines(step_expected_text)
    manual_step_annotations = bool(intents or expected_results)

    previous_after = initial_state_path if initial_state_path.is_file() else None
    steps_written = 0
    missing_artifacts: list[dict[str, Any]] = []

    for index, item in enumerate(actions, start=1):
        if not isinstance(item, dict):
            continue
        action = item.get("acao") if isinstance(item.get("acao"), dict) else {}
        image_name = str(item.get("imagem") or f"frame_{index:02d}.png").strip()
        after_src = frames_dir / image_name
        before_src = previous_after if previous_after and previous_after.is_file() else None

        step_dir = steps_root / f"{index:04d}"
        before_copied = _copy_image(before_src, step_dir / "before.png")
        after_copied = _copy_image(after_src, step_dir / "after.png")
        if not before_copied:
            missing_artifacts.append({"step_index": index, "artifact": "before.png", "source": str(before_src or "")})
        if not after_copied:
            missing_artifacts.append({"step_index": index, "artifact": "after.png", "source": str(after_src)})

        intent = intents[index - 1] if index - 1 < len(intents) else f"fallback_step_{index}"
        expected_result = (
            expected_results[index - 1]
            if index - 1 < len(expected_results)
            else f"state_changed_after_step_{index}"
        )
        step_payload = {
            "schema_version": SCHEMA_VERSION,
            "step_index": index,
            "intent": intent,
            "expected_result": expected_result,
            "action_source": "recorded_touch",
            "timestamp_start": item.get("action_timestamp") or item.get("timestamp"),
            "timestamp_end": item.get("screenshot_timestamp") or item.get("timestamp"),
            "artifacts": {
                "before": "before.png" if before_copied else None,
                "after": "after.png" if after_copied else None,
            },
            "recorded_action": _action_metadata(action),
            "source_refs": {
                "recorded_frame": str(after_src),
                "action_id": item.get("id", index),
            },
        }
        _write_json(step_dir / "step.json", step_payload)
        previous_after = after_src if after_src.is_file() else previous_after
        steps_written += 1

    final_expected_copied = _copy_image(final_expected_src, episode_dir / "final_expected.png")
    resolution = _wm_resolution(serial, _fallback_resolution(actions))
    source_value = input_source or actions_payload.get("fonte") or test_meta.get("input_source") or None

    episode_payload = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": final_episode_id,
        "category": category_slug,
        "category_name": category_name,
        "flow": flow_slug,
        "flow_name": flow_name,
        "objective": objective_text,
        "success_criteria_final": success_text,
        "tester_id": tester_id or None,
        "created_at": created_at,
        "step_count": steps_written,
        "notes": str(notes or "").strip(),
        "status": "completed",
    }
    environment_payload = {
        "schema_version": SCHEMA_VERSION,
        "device_id": serial or None,
        "source": source_value,
        "os_version": _adb_shell_text(serial, "getprop", "ro.build.version.release"),
        "build_version": _adb_shell_text(serial, "getprop", "ro.build.display.id"),
        "resolution": {
            "width": resolution.get("width"),
            "height": resolution.get("height"),
        },
        "device_model": _adb_shell_text(serial, "getprop", "ro.product.model"),
        "manufacturer": _adb_shell_text(serial, "getprop", "ro.product.manufacturer"),
    }
    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "duration_ms": _duration_ms([item for item in actions if isinstance(item, dict)]),
        "steps_recorded": steps_written,
        "manual_step_annotations": manual_step_annotations,
        "missing_artifacts": missing_artifacts,
    }
    source_refs_payload = {
        "schema_version": SCHEMA_VERSION,
        "data_source_path": str(data_source_path),
        "recorded_initial_state": str(initial_state_path) if initial_state_path.is_file() else None,
        "source_session_id": test_meta.get("latest_run_id") or test_meta.get("recorded_at") or None,
        "actions_path": str(actions_path),
        "expected_final_path": str(final_expected_src) if final_expected_src.is_file() else None,
        "final_expected_exported": "final_expected.png" if final_expected_copied else None,
    }

    _write_json(episode_dir / "episode.json", episode_payload)
    _write_json(episode_dir / "environment.json", environment_payload)
    _write_json(episode_dir / "summary.json", summary_payload)
    _write_json(episode_dir / "source_refs.json", source_refs_payload)

    _update_taxonomy(training_taxonomy_categories_path(), "categories", category_name)
    _update_taxonomy(
        training_taxonomy_flows_path(),
        "flows",
        flow_name,
        {"category": category_slug, "category_name": category_name},
    )
    _update_manifest(
        {
            "episode_id": final_episode_id,
            "category": category_slug,
            "flow": flow_slug,
            "objective": objective_text,
            "success_criteria_final": success_text,
            "path": str(episode_dir),
            "created_at": created_at,
            "step_count": steps_written,
            "status": "completed",
        }
    )

    return True, str(episode_dir)


__all__ = ["create_training_episode_draft", "export_training_episode"]
