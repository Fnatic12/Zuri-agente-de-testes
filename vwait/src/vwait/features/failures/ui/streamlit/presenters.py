from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import streamlit as st

from ...application import ticket_export_rows as build_failure_ticket_export_rows
from .state import FAILURE_JIRA_FLASH_KEY
from .theme import apply_panel_button_theme


EXPORT_HEADERS = (
    "Record ID",
    "Coluna",
    "Categoria",
    "Teste",
    "Resumo",
    "Workflow",
    "Sync Jira",
    "Issue",
    "Status issue",
    "Responsavel",
    "Prioridade",
    "Resultado final",
    "Status logs",
    "Gerado em",
    "Atualizado em",
    "URL issue",
)


def titulo_painel(titulo: str, subtitulo: str = "") -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            color-scheme: dark;
            --motion-quick: 170ms;
            --motion-smooth: 240ms;
            --motion-curve: cubic-bezier(0.22, 1, 0.36, 1);
        }}
        @keyframes panel-fade-slide {{
            from {{
                opacity: 0;
                transform: translate3d(0, 10px, 0);
            }}
            to {{
                opacity: 1;
                transform: translate3d(0, 0, 0);
            }}
        }}
        @keyframes modal-overlay-in {{
            from {{
                opacity: 0;
                backdrop-filter: blur(0);
                -webkit-backdrop-filter: blur(0);
            }}
            to {{
                opacity: 1;
                backdrop-filter: blur(6px);
                -webkit-backdrop-filter: blur(6px);
            }}
        }}
        @keyframes modal-surface-in {{
            from {{
                opacity: 0;
                transform: translate3d(0, 14px, 0) scale(0.985);
            }}
            to {{
                opacity: 1;
                transform: translate3d(0, 0, 0) scale(1);
            }}
        }}
        html, body, [class*="css"]  {{
            background: #0B0C10 !important;
            color: #E0E0E0 !important;
        }}
        .stApp {{
            background: radial-gradient(circle at 20% 0%, #111827 0%, #070b12 55%, #05070c 100%) !important;
            color: #e5e7eb !important;
        }}
        [data-testid="stAppViewContainer"] {{
            background: radial-gradient(circle at 20% 0%, #111827 0%, #070b12 55%, #05070c 100%) !important;
        }}
        [data-testid="stHeader"] {{
            display: none !important;
            height: 0 !important;
        }}
        [data-testid="stToolbar"] {{
            display: none !important;
        }}
        .main .block-container, .block-container {{
            background: transparent !important;
        }}
        .block-container {{
            padding-top: 1.1rem;
            max-width: 1320px;
            animation: panel-fade-slide 260ms var(--motion-curve) both;
        }}
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, rgba(12, 18, 31, 0.92), rgba(8, 12, 22, 0.94)) !important;
            border-right: 1px solid rgba(96, 165, 250, 0.12) !important;
            box-shadow: 18px 0 36px rgba(2, 6, 23, 0.22) !important;
            backdrop-filter: blur(10px) saturate(124%);
            -webkit-backdrop-filter: blur(10px) saturate(124%);
            transition:
                transform var(--motion-smooth) var(--motion-curve),
                opacity var(--motion-smooth) ease,
                box-shadow var(--motion-smooth) ease,
                border-color var(--motion-smooth) ease;
        }}
        .main-title {{
            font-size: 2.05rem;
            line-height: 1.18;
            text-align: center;
            background: linear-gradient(90deg, #22d3ee 0%, #8b5cf6 48%, #d946ef 76%, #fb7185 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
            letter-spacing: -0.4px;
            margin-top: 0.15em;
            margin-bottom: 0.2em;
        }}
        .subtitle {{
            text-align: center;
            color: #b4c0d2;
            font-size: 0.95rem;
            margin-bottom: 1.1em;
        }}
        .clean-card {{
            position: relative;
            overflow: hidden;
            background: linear-gradient(180deg, rgba(17, 25, 40, 0.78), rgba(10, 16, 28, 0.74));
            border: 1px solid rgba(94, 115, 140, 0.34);
            border-radius: 18px;
            padding: 0.88rem 0.96rem;
            margin-bottom: 0.65rem;
            box-shadow: 0 18px 32px rgba(2, 6, 23, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(18px) saturate(150%);
            -webkit-backdrop-filter: blur(18px) saturate(150%);
            transition:
                transform var(--motion-smooth) var(--motion-curve),
                box-shadow var(--motion-smooth) ease,
                border-color var(--motion-smooth) ease,
                background var(--motion-quick) ease;
            will-change: transform, box-shadow;
        }}
        .clean-card::before {{
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0));
            pointer-events: none;
        }}
        .clean-card:hover {{
            transform: translate3d(0, -2px, 0);
            border-color: rgba(125, 211, 252, 0.24);
            box-shadow: 0 24px 38px rgba(2, 6, 23, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.04);
        }}
        .card-kpi-label {{
            color: #9fb0c7;
            font-size: 0.78rem;
            margin-bottom: 0.15rem;
        }}
        .card-kpi-value {{
            color: #f8fbff;
            font-weight: 700;
            font-size: 1.34rem;
            line-height: 1.1;
        }}
        [data-testid="stTextInputRootElement"] > div,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        [data-testid="stTextArea"] textarea {{
            background: rgba(18, 26, 40, 0.78) !important;
            border: 1px solid rgba(94, 115, 140, 0.34) !important;
            border-radius: 16px !important;
            box-shadow: 0 12px 28px rgba(2, 6, 23, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.03) !important;
            backdrop-filter: blur(18px) saturate(140%);
            -webkit-backdrop-filter: blur(18px) saturate(140%);
            transition:
                transform var(--motion-quick) var(--motion-curve),
                border-color var(--motion-quick) ease,
                box-shadow var(--motion-quick) ease,
                background var(--motion-quick) ease;
        }}
        [data-testid="stTextInputRootElement"] > div:hover,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover,
        [data-testid="stTextArea"] textarea:hover {{
            transform: translate3d(0, -1px, 0);
            border-color: rgba(118, 151, 194, 0.42) !important;
        }}
        [data-testid="stTextInputRootElement"] > div:focus-within,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div:focus-within,
        [data-testid="stTextArea"] textarea:focus {{
            border-color: rgba(96, 165, 250, 0.44) !important;
            box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.14), 0 18px 34px rgba(2, 6, 23, 0.22) !important;
            transform: translate3d(0, -1px, 0);
        }}
        [data-testid="stTextInputRootElement"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] * {{
            color: #e8edf6 !important;
        }}
        div[data-baseweb="popover"] > div {{
            border-radius: 18px !important;
            border: 1px solid rgba(96, 165, 250, 0.14) !important;
            box-shadow: 0 24px 42px rgba(2, 6, 23, 0.28) !important;
            backdrop-filter: blur(16px) saturate(136%);
            -webkit-backdrop-filter: blur(16px) saturate(136%);
            animation: panel-fade-slide 180ms var(--motion-curve) both;
        }}
        [data-testid="stDialog"] {{
            background: rgba(5, 9, 18, 0.18) !important;
            backdrop-filter: blur(6px) saturate(118%);
            -webkit-backdrop-filter: blur(6px) saturate(118%);
            animation: modal-overlay-in 180ms ease-out both;
        }}
        [data-testid="stDialog"] > div {{
            background: linear-gradient(180deg, rgba(14, 20, 34, 0.96), rgba(9, 14, 25, 0.94)) !important;
            border: 1px solid rgba(96, 165, 250, 0.16) !important;
            border-radius: 24px !important;
            box-shadow: 0 36px 80px rgba(2, 6, 23, 0.46) !important;
            backdrop-filter: blur(24px) saturate(140%);
            -webkit-backdrop-filter: blur(24px) saturate(140%);
            animation: modal-surface-in 240ms var(--motion-curve) both;
            transform-origin: top center;
        }}
        [data-testid="stDialog"] [data-testid="stVerticalBlock"] {{
            gap: 0.65rem;
        }}
        [data-testid="stForm"] button[kind="secondary"],
        [data-testid="stForm"] button[kind="primary"] {{
            border-radius: 14px !important;
            transition: transform 180ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 180ms ease, filter 180ms ease !important;
            will-change: transform, box-shadow;
        }}
        [data-testid="stForm"] button[kind="secondary"]:hover,
        [data-testid="stForm"] button[kind="primary"]:hover {{
            transform: translate3d(0, -1px, 0);
            box-shadow: 0 14px 24px rgba(2, 6, 23, 0.24) !important;
            filter: saturate(112%);
        }}
        [data-testid="stForm"] button[kind="secondary"]:active,
        [data-testid="stForm"] button[kind="primary"]:active {{
            transform: translate3d(0, 0, 0);
        }}
        @media (prefers-reduced-motion: reduce) {{
            *,
            *::before,
            *::after {{
                animation-duration: 1ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 1ms !important;
                scroll-behavior: auto !important;
            }}
        }}
        </style>
        <h1 class="main-title">{titulo}</h1>
        <p class="subtitle">{subtitulo}</p>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_card(label: str, value: str) -> None:
    st.markdown(
        (
            "<div class='clean-card'>"
            f"<div class='card-kpi-label'>{label}</div>"
            f"<div class='card-kpi-value'>{value}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_jira_flash_message() -> None:
    payload = st.session_state.pop(FAILURE_JIRA_FLASH_KEY, None)
    if not isinstance(payload, dict):
        return
    message = str(payload.get("message") or "").strip()
    if not message:
        return
    level = str(payload.get("type") or "info").strip().lower()
    if level == "success":
        st.success(message)
    elif level == "error":
        st.error(message)
    else:
        st.info(message)
    issue_url = str(payload.get("issue_url") or "").strip()
    if issue_url:
        st.markdown(f"[Abrir issue no Jira]({issue_url})")


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


def _xlsx_row(row_number: int, values: list[Any]) -> str:
    cells = [
        _xlsx_inline_cell(f"{_excel_column_name(column_index)}{row_number}", value)
        for column_index, value in enumerate(values, start=1)
    ]
    return f'<row r="{row_number}">{"".join(cells)}</row>'


def build_status_workbook(records: list[dict[str, Any]]) -> bytes:
    rows = [list(EXPORT_HEADERS), *build_failure_ticket_export_rows(records)]
    last_col = _excel_column_name(len(EXPORT_HEADERS))
    last_row = max(1, len(rows))
    sheet_ref = f"A1:{last_col}{last_row}"
    sheet_data = "".join(_xlsx_row(row_number, row_values) for row_number, row_values in enumerate(rows, start=1))
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

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
        '<sheets><sheet name="Tickets" sheetId="1" r:id="rId1"/></sheets>'
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


__all__ = [
    "FAILURE_JIRA_FLASH_KEY",
    "apply_panel_button_theme",
    "build_status_workbook",
    "render_jira_flash_message",
    "render_kpi_card",
    "titulo_painel",
]
