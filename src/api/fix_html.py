import re
with open('post_crq_audit.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_header_wrap = '''def _pdf_header_wrap(value: Any) -> str:
    text = _normalize_text(value) or "-"
    if len(text) > 20 and " " in text:
        parts = text.split(" ")
        lines: List[str] = []
        current = ""
        for part in parts:
            candidate = f"{current} {part}".strip()
            if current and len(candidate) > 18:
                lines.append(html.escape(current))
                current = part
            else:
                current = candidate
        if current:
            lines.append(html.escape(current))
        return "<br/>".join(lines)
    return html.escape(text)'''

new_cell_wrap = '''def _pdf_cell_wrap(value: Any, column_name: Optional[str] = None) -> str:
    text = _normalize_text(value) or "-"
    normalized = _normalize_key(column_name or "")
    protected = {
        "taula",
        "table",
        "objecte",
        "sequencia",
        "sequence",
        "constraint_fk",
        "nom_constraint",
        "num_files",
        "data_modificacio_objecte",
        "data_modificacio_taula",
        "darrera_estadistica",
    }
    if normalized in protected and len(text) <= 34:
        return html.escape(text)
    if len(text) <= 22:
        return html.escape(text)
    if "_" in text:
        groups = text.split("_")
        lines: List[str] = []
        current = []
        current_len = 0
        for group in groups:
            projected = current_len + len(group) + (1 if current else 0)
            threshold = 22 if normalized in protected else 16
            if current and projected > threshold:
                lines.append("_".join(current))
                current = [group]
                current_len = len(group)
            else:
                current.append(group)
                current_len = projected
        if current:
            lines.append("_".join(current))
        return "<br/>".join(html.escape(line) for line in lines)
    chunk_size = 22 if normalized in protected else 18
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    return "<br/>".join(html.escape(c) for c in chunks)'''


header_regex = r'def _pdf_header_wrap\(value: Any\) -> str:.*?return text'
cell_regex = r'def _pdf_cell_wrap\(value: Any, column_name: Optional\[str\] = None\) -> str:.*?return "<br/>"\.join\(chunks\)'


content = re.sub(header_regex, new_header_wrap, content, flags=re.DOTALL)
content = re.sub(cell_regex, new_cell_wrap, content, flags=re.DOTALL)

with open('post_crq_audit.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Replaced ok")
