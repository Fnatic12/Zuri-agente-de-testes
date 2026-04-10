from __future__ import annotations


def build_adf_document(text: str) -> dict:
    normalized = str(text or "").strip()
    if not normalized:
        normalized = "Sem descricao."

    content = []
    for block in normalized.split("\n\n"):
        lines = [line.rstrip() for line in block.splitlines()]
        paragraph_content = []
        for idx, line in enumerate(lines):
            if idx:
                paragraph_content.append({"type": "hardBreak"})
            if line:
                paragraph_content.append({"type": "text", "text": line})
        if not paragraph_content:
            paragraph_content = [{"type": "text", "text": " "}]
        content.append({"type": "paragraph", "content": paragraph_content})

    return {"version": 1, "type": "doc", "content": content}
