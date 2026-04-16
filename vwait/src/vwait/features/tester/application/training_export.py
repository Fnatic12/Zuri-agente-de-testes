from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from vwait.core.paths import (
    build_run_id,
    ensure_data_roots,
    normalize_segment,
    tester_actions_path,
    tester_expected_final_path,
    tester_recorded_dir,
    tester_recorded_frames_dir,
    tester_test_metadata_path,
    training_episode_dir,
)
from vwait.platform.adb import resolve_adb_path


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _copy_image(src: Path | None, dst: Path) -> bool:
    if not src or not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _save_diff_image(expected_path: Path | None, observed_path: Path | None, diff_path: Path) -> bool:
    if not expected_path or not observed_path or not expected_path.is_file() or not observed_path.is_file():
        return False
    try:
        expected = Image.open(expected_path).convert("RGB")
        observed = Image.open(observed_path).convert("RGB")
        if observed.size != expected.size:
            observed = observed.resize(expected.size)
        diff = ImageChops.difference(expected, observed)
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff.save(diff_path)
        return True
    except Exception:
        return False


def _split_lines(raw_text: str | None) -> list[str]:
    return [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]


def _adb_shell_text(serial: str | None, *shell_args: str) -> str:
    adb_path = resolve_adb_path()
    if not adb_path:
        return ""
    cmd = [adb_path]
    if serial:
        cmd += ["-s", serial]
    cmd += ["shell", *shell_args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _wm_resolution(serial: str | None) -> dict[str, int | None]:
    raw = _adb_shell_text(serial, "wm", "size")
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
    return {"width": width, "height": height}


def _collect_environment(serial: str | None, input_source: str | None, fallback_resolution: dict[str, int | None]) -> dict[str, Any]:
    resolution = _wm_resolution(serial)
    width = resolution.get("width") or fallback_resolution.get("width")
    height = resolution.get("height") or fallback_resolution.get("height")
    return {
        "captured_at": datetime.now().isoformat(),
        "serial": serial or "",
        "device_family": _adb_shell_text(serial, "getprop", "ro.product.model"),
        "manufacturer": _adb_shell_text(serial, "getprop", "ro.product.manufacturer"),
        "software_version": _adb_shell_text(serial, "getprop", "ro.build.display.id"),
        "android_version": _adb_shell_text(serial, "getprop", "ro.build.version.release"),
        "language": _adb_shell_text(serial, "getprop", "persist.sys.locale") or _adb_shell_text(serial, "getprop", "ro.product.locale"),
        "theme": "",
        "input_source": input_source or "",
        "resolution": {
            "width": int(width) if width else None,
            "height": int(height) if height else None,
        },
    }


def _fallback_intent(action_type: str, step_id: int) -> str:
    label = str(action_type or "acao").strip().lower()
    if label == "tap":
        return f"executar tap do passo {step_id}"
    if label == "swipe":
        return f"executar swipe do passo {step_id}"
    if label == "long_press":
        return f"executar long press do passo {step_id}"
    return f"executar acao do passo {step_id}"


def _fallback_expected_outcome(action_type: str, step_id: int) -> str:
    label = str(action_type or "acao").strip().lower()
    return f"estado esperado apos {label} do passo {step_id}"


def _normalized_action_payload(action: dict[str, Any]) -> dict[str, Any]:
    payload = dict(action or {})
    resolution = payload.get("resolucao") or {}
    width = int(resolution.get("largura") or 0)
    height = int(resolution.get("altura") or 0)
    output = {
        "type": payload.get("tipo"),
        "gesture": payload.get("gesture"),
        "coordinates_abs": {},
        "coordinates_norm": {},
    }

    def _norm_x(value: Any) -> float | None:
        if value is None or width <= 1:
            return None
        return round(float(value) / float(width - 1), 6)

    def _norm_y(value: Any) -> float | None:
        if value is None or height <= 1:
            return None
        return round(float(value) / float(height - 1), 6)

    if payload.get("tipo") in {"tap", "long_press"}:
        x = payload.get("x")
        y = payload.get("y")
        output["coordinates_abs"] = {"x": x, "y": y}
        output["coordinates_norm"] = {"x": _norm_x(x), "y": _norm_y(y)}
        if "duracao_s" in payload:
            output["duration_s"] = payload.get("duracao_s")
    else:
        x1 = payload.get("x1")
        y1 = payload.get("y1")
        x2 = payload.get("x2")
        y2 = payload.get("y2")
        output["coordinates_abs"] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        output["coordinates_norm"] = {
            "x1": _norm_x(x1),
            "y1": _norm_y(y1),
            "x2": _norm_x(x2),
            "y2": _norm_y(y2),
        }
        if "duracao_ms" in payload:
            output["duration_ms"] = payload.get("duracao_ms")

    output["resolution"] = {
        "width": width or None,
        "height": height or None,
    }
    return output


def export_training_episode(
    *,
    category: str,
    test_name: str,
    domain: str,
    goal: str,
    serial: str | None = None,
    input_source: str | None = None,
    step_intents_text: str | None = None,
    step_expected_text: str | None = None,
) -> tuple[bool, str]:
    ensure_data_roots()

    category_norm = normalize_segment(category)
    test_name_norm = normalize_segment(test_name)
    domain_norm = normalize_segment(domain or category_norm)
    episode_id = build_run_id()
    episode_dir = training_episode_dir(domain_norm, test_name_norm, episode_id)
    steps_root = episode_dir / "steps"

    actions_payload = _load_json(tester_actions_path(category_norm, test_name_norm))
    actions = actions_payload.get("acoes")
    if not isinstance(actions, list) or not actions:
        return False, "Nenhuma acao encontrada para exportar."

    test_meta = _load_json(tester_test_metadata_path(category_norm, test_name_norm))
    recorded_dir = tester_recorded_dir(category_norm, test_name_norm)
    frames_dir = tester_recorded_frames_dir(category_norm, test_name_norm)
    initial_state_path = recorded_dir / "initial_state.png"
    expected_final_path = tester_expected_final_path(category_norm, test_name_norm)

    step_intents = _split_lines(step_intents_text)
    step_expected = _split_lines(step_expected_text)

    fallback_resolution = {"width": None, "height": None}
    first_action = actions[0].get("acao", {}) if isinstance(actions[0], dict) else {}
    if isinstance(first_action, dict):
        raw_res = first_action.get("resolucao") or {}
        fallback_resolution = {
            "width": raw_res.get("largura"),
            "height": raw_res.get("altura"),
        }

    environment = _collect_environment(serial, input_source or str(actions_payload.get("fonte") or ""), fallback_resolution)

    episode_dir.mkdir(parents=True, exist_ok=True)

    steps_written = 0
    previous_after_expected = initial_state_path if initial_state_path.is_file() else None
    for index, item in enumerate(actions, start=1):
        if not isinstance(item, dict):
            continue
        action = item.get("acao") if isinstance(item.get("acao"), dict) else {}
        image_name = str(item.get("imagem") or "").strip()
        if not image_name:
            image_name = f"frame_{index:02d}.png"

        after_expected_src = frames_dir / image_name
        after_observed_src = after_expected_src if after_expected_src.is_file() else None
        before_src = previous_after_expected if previous_after_expected and previous_after_expected.is_file() else after_expected_src

        step_dir = steps_root / f"{index:04d}"
        before_dst = step_dir / "before.png"
        after_observed_dst = step_dir / "after_observed.png"
        after_expected_dst = step_dir / "after_expected.png"
        diff_dst = step_dir / "diff.png"

        _copy_image(before_src, before_dst)
        _copy_image(after_observed_src, after_observed_dst)
        _copy_image(after_expected_src, after_expected_dst)
        _save_diff_image(after_expected_dst if after_expected_dst.is_file() else None, after_observed_dst if after_observed_dst.is_file() else None, diff_dst)

        intent = step_intents[index - 1] if index - 1 < len(step_intents) else _fallback_intent(action.get("tipo"), index)
        expected_outcome = (
            step_expected[index - 1]
            if index - 1 < len(step_expected)
            else _fallback_expected_outcome(action.get("tipo"), index)
        )

        similarity = 1.0 if after_expected_dst.is_file() and after_observed_dst.is_file() else 0.0
        step_payload = {
            "step_id": index,
            "intent": intent,
            "expected_outcome": expected_outcome,
            "action": _normalized_action_payload(action),
            "timing": {
                "action_timestamp": item.get("action_timestamp") or item.get("timestamp"),
                "screenshot_timestamp": item.get("screenshot_timestamp"),
                "duration_s": action.get("duracao_s"),
                "duration_ms": action.get("duracao_ms"),
            },
            "artifacts": {
                "before_image": "before.png" if before_dst.is_file() else "",
                "after_observed_image": "after_observed.png" if after_observed_dst.is_file() else "",
                "after_expected_image": "after_expected.png" if after_expected_dst.is_file() else "",
                "diff_image": "diff.png" if diff_dst.is_file() else "",
            },
            "validation": {
                "status": "ok",
                "similarity": similarity,
                "step_result": "passed",
            },
            "source_refs": {
                "actions_json": str(tester_actions_path(category_norm, test_name_norm)),
                "recorded_frame": str(after_expected_src) if after_expected_src else "",
            },
        }
        _write_json(step_dir / "step.json", step_payload)
        previous_after_expected = after_expected_src if after_expected_src.is_file() else previous_after_expected
        steps_written += 1

    episode_payload = {
        "episode_id": episode_id,
        "domain": domain_norm,
        "catalog": category_norm,
        "test_name": test_name_norm,
        "goal": goal.strip() or f"validar {test_name_norm}",
        "source_test_ref": str(Path("Data") / "catalog" / "tester" / category_norm / test_name_norm),
        "golden": True,
        "input_source": input_source or actions_payload.get("fonte") or test_meta.get("input_source") or "",
        "labels": {
            "final_result": "passed",
            "contains_failures": False,
        },
    }
    _write_json(episode_dir / "episode.json", episode_payload)
    _write_json(episode_dir / "environment.json", environment)
    _write_json(
        episode_dir / "summary.json",
        {
            "total_steps": steps_written,
            "passed_steps": steps_written,
            "failed_steps": 0,
            "avg_similarity": 1.0 if steps_written else 0.0,
            "expected_final_image": "expected_final.png" if expected_final_path.is_file() else "",
        },
    )

    if expected_final_path.is_file():
        _copy_image(expected_final_path, episode_dir / "expected_final.png")

    source_meta = {
        "test_metadata": test_meta,
        "actions_path": str(tester_actions_path(category_norm, test_name_norm)),
        "expected_final_path": str(expected_final_path),
        "initial_state_path": str(initial_state_path) if initial_state_path.is_file() else "",
    }
    _write_json(episode_dir / "source_refs.json", source_meta)

    return True, str(episode_dir)


__all__ = ["export_training_episode"]
