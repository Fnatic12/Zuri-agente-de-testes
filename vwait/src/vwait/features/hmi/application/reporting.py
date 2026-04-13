import json
import os
from io import BytesIO
from datetime import datetime, UTC
from html import escape
from typing import Any, Dict, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

import cv2

REPORT_HEADERS = ("tela", "layout", "tipografia", "icones", "espacamento", "cores", "status")


def get_validation_dir(test_dir: str) -> str:
    return os.path.join(test_dir, "hmi_validation")


def save_validation_report(test_dir: str, library_index: Dict, validation_result: Dict) -> str:
    output_dir = get_validation_dir(test_dir)
    overlays_dir = os.path.join(output_dir, "overlays")
    masks_dir = os.path.join(output_dir, "diff_masks")
    heatmaps_dir = os.path.join(output_dir, "heatmaps")
    aligned_dir = os.path.join(output_dir, "aligned")
    os.makedirs(overlays_dir, exist_ok=True)
    os.makedirs(masks_dir, exist_ok=True)
    os.makedirs(heatmaps_dir, exist_ok=True)
    os.makedirs(aligned_dir, exist_ok=True)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "figma_dir": library_index.get("figma_dir"),
        "library_generated_at": library_index.get("generated_at"),
        "summary": validation_result.get("summary", {}),
        "items": [],
    }

    for item in validation_result.get("items", []):
        serializable = dict(item)
        debug_images = serializable.pop("debug_images", {}) or {}

        base_name = os.path.splitext(os.path.basename(item["screenshot_path"]))[0]
        overlay_path = None
        diff_mask_path = None
        heatmap_path = None
        aligned_path = None

        overlay = debug_images.get("overlay")
        diff_mask = debug_images.get("diff_mask")
        heatmap = debug_images.get("heatmap")
        aligned = debug_images.get("aligned")
        if overlay is not None:
            overlay_path = os.path.join(overlays_dir, f"{base_name}_overlay.png")
            cv2.imwrite(overlay_path, overlay)
        if diff_mask is not None:
            diff_mask_path = os.path.join(masks_dir, f"{base_name}_mask.png")
            cv2.imwrite(diff_mask_path, diff_mask)
        if heatmap is not None:
            heatmap_path = os.path.join(heatmaps_dir, f"{base_name}_heatmap.png")
            cv2.imwrite(heatmap_path, heatmap)
        if aligned is not None:
            aligned_path = os.path.join(aligned_dir, f"{base_name}_aligned.png")
            cv2.imwrite(aligned_path, aligned)

        serializable["artifacts"] = {
            "overlay_path": overlay_path,
            "diff_mask_path": diff_mask_path,
            "heatmap_path": heatmap_path,
            "aligned_path": aligned_path,
        }
        payload["items"].append(serializable)

    report_path = os.path.join(output_dir, "resultado_hmi.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return report_path


def load_validation_report(test_dir: str) -> Dict:
    report_path = os.path.join(get_validation_dir(test_dir), "resultado_hmi.json")
    with open(report_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _safe_ratio(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def _status_tag(score: float | None, ok_threshold: float, warn_threshold: float) -> str:
    if score is None:
        return "N/A"
    if score >= ok_threshold:
        return "OK"
    if score >= warn_threshold:
        return "Atencao"
    return "NOK"


def _format_scored_cell(score: float | None, ok_threshold: float, warn_threshold: float) -> str:
    if score is None:
        return "N/A"
    return f"{_status_tag(score, ok_threshold, warn_threshold)} ({score:.1%})"


def _format_screen_label(item: Dict[str, Any]) -> str:
    matched_name = str(item.get("screen_name") or "").strip()
    screenshot_name = os.path.splitext(os.path.basename(str(item.get("screenshot_path") or "").strip()))[0]
    if matched_name and screenshot_name and matched_name.casefold() != screenshot_name.casefold():
        return f"{matched_name} ({screenshot_name})"
    return matched_name or screenshot_name or "sem_tela"


def _format_overall_status(item: Dict[str, Any]) -> str:
    final_score = _safe_ratio((item.get("scores") or {}).get("final"))
    raw_status = str(item.get("status") or "").strip().upper()
    labels = {
        "PASS": "Aprovado",
        "PASS_WITH_WARNINGS": "Aprovado com ressalvas",
        "FAIL_COMPONENT_STATE": "Falha de componente",
        "FAIL_CRITICAL_REGION": "Falha em regiao critica",
        "FAIL_SCREEN_MISMATCH": "Reprovado",
    }
    label = labels.get(raw_status, raw_status or "Sem status")
    if final_score is None:
        return label
    return f"{label} ({final_score:.1%})"


def _dimension_cells(item: Dict[str, Any]) -> Dict[str, str]:
    scores = item.get("scores") or {}
    diff_summary = item.get("diff_summary") or {}
    reference_path = str(item.get("reference_path") or "").strip()
    if not reference_path:
        return {
            "layout": "Sem referencia",
            "tipografia": "Sem referencia",
            "icones": "Sem referencia",
            "espacamento": "Sem referencia",
            "cores": "Sem referencia",
        }

    layout_score = _safe_ratio(scores.get("structure"))
    text_score = _safe_ratio(scores.get("text", diff_summary.get("text_score")))
    spacing_score = min(
        score for score in (
            _safe_ratio(scores.get("grid_avg")),
            _safe_ratio(scores.get("grid_min")),
            _safe_ratio(diff_summary.get("worst_cell_score")),
        ) if score is not None
    ) if any(
        score is not None for score in (
            _safe_ratio(scores.get("grid_avg")),
            _safe_ratio(scores.get("grid_min")),
            _safe_ratio(diff_summary.get("worst_cell_score")),
        )
    ) else None
    color_score = _safe_ratio(diff_summary.get("pixel_match_ratio", scores.get("pixel")))
    component_score = _safe_ratio(scores.get("component"))
    toggle_count = int(diff_summary.get("toggle_count", 0) or 0)
    critical_failures = item.get("critical_region_failures") or []

    layout_cell = _format_scored_cell(layout_score, 0.94, 0.82)
    if critical_failures:
        layout_cell = "NOK (regiao critica)"

    icons_cell = _format_scored_cell(component_score, 0.90, 0.75)
    if toggle_count > 0:
        label = "toggle" if toggle_count == 1 else "toggles"
        icons_cell = f"NOK ({toggle_count} {label})"

    return {
        "layout": layout_cell,
        "tipografia": _format_scored_cell(text_score, 0.92, 0.75),
        "icones": icons_cell,
        "espacamento": _format_scored_cell(spacing_score, 0.96, 0.88),
        "cores": _format_scored_cell(color_score, 0.985, 0.94),
    }


def build_validation_dimension_rows(report: Dict[str, Any]) -> list[Dict[str, str]]:
    rows: list[Dict[str, str]] = []
    for item in report.get("items", []) or []:
        dimensions = _dimension_cells(item)
        rows.append(
            {
                "tela": _format_screen_label(item),
                "layout": dimensions["layout"],
                "tipografia": dimensions["tipografia"],
                "icones": dimensions["icones"],
                "espacamento": dimensions["espacamento"],
                "cores": dimensions["cores"],
                "status": _format_overall_status(item),
            }
        )
    return rows


def _excel_column_name(column_number: int) -> str:
    label = ""
    current = max(1, int(column_number))
    while current:
        current, remainder = divmod(current - 1, 26)
        label = chr(65 + remainder) + label
    return label


def _xlsx_inline_cell(cell_ref: str, value: Any) -> str:
    raw_text = str(value or "")
    clean_text = "".join(ch for ch in raw_text if ch in ("\n", "\t") or ord(ch) >= 32)
    preserve_attr = ' xml:space="preserve"' if clean_text != clean_text.strip() or "\n" in clean_text else ""
    return (
        f'<c r="{cell_ref}" t="inlineStr">'
        f"<is><t{preserve_attr}>{escape(clean_text)}</t></is>"
        "</c>"
    )


def _xlsx_row(row_number: int, values: Sequence[Any]) -> str:
    cells = [
        _xlsx_inline_cell(f"{_excel_column_name(column_index)}{row_number}", value)
        for column_index, value in enumerate(values, start=1)
    ]
    return f'<row r="{row_number}">{"".join(cells)}</row>'


def build_validation_dimension_workbook(rows: Sequence[Dict[str, Any]]) -> bytes:
    workbook_rows = [list(REPORT_HEADERS)]
    for row in rows:
        workbook_rows.append([row.get(header, "") for header in REPORT_HEADERS])

    last_col = _excel_column_name(len(REPORT_HEADERS))
    last_row = max(1, len(workbook_rows))
    sheet_ref = f"A1:{last_col}{last_row}"
    sheet_data = "".join(_xlsx_row(row_number, values) for row_number, values in enumerate(workbook_rows, start=1))
    stamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{sheet_ref}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        "</sheetView></sheetViews>"
        '<sheetFormatPr defaultRowHeight="18"/>'
        f"<sheetData>{sheet_data}</sheetData>"
        f'<autoFilter ref="{sheet_ref}"/>'
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Validacao HMI" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>VWAIT</Application>"
        "</Properties>"
    )
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>VWAIT</dc:creator>"
        "<cp:lastModifiedBy>VWAIT</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified>'
        "</cp:coreProperties>"
    )

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types_xml)
        workbook.writestr("_rels/.rels", root_rels_xml)
        workbook.writestr("docProps/app.xml", app_xml)
        workbook.writestr("docProps/core.xml", core_xml)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        workbook.writestr("xl/styles.xml", styles_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
    return output.getvalue()
