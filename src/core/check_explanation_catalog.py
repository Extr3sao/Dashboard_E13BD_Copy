import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


REQUIRED_FIELDS = {
    "que_detecta": "No informat.",
    "per_que_es_important": "No informat.",
    "impacte_sobre_lot": "No informat.",
    "com_revisar": "No informat.",
    "com_corregir": "No informat.",
    "limitacions": "No informat.",
    "columnes_taula_recomanades": [],
    "validacio_posterior": "No informat.",
}

SECTION_KEYS = {
    "que detecta": "que_detecta",
    "quÃ¨ detecta": "que_detecta",
    "per que es important": "per_que_es_important",
    "per quÃ¨ Ã©s important": "per_que_es_important",
    "impacte sobre el lot": "impacte_sobre_lot",
    "com s'ha de revisar": "com_revisar",
    "com revisar": "com_revisar",
    "com es pot corregir": "com_corregir",
    "com corregir": "com_corregir",
    "limitacions o falsos positius": "limitacions",
    "limitacions o falsos positius possibles": "limitacions",
    "dades que s'han de mostrar a la taula": "columnes_taula_recomanades",
    "dades que cal mostrar a la taula": "columnes_taula_recomanades",
    "validacio posterior": "validacio_posterior",
    "validaciÃ³ posterior": "validacio_posterior",
}


def _catalog_path() -> Path:
    return Path(__file__).resolve().parents[2] / "EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md"


def _normalize_heading(value: str) -> str:
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\s+", " ", text)
    return text


def _clean_lines(lines: List[str]) -> str:
    content = "\n".join(line.rstrip() for line in lines).strip()
    return re.sub(r"\n{3,}", "\n\n", content)


def _load_check_explanation_catalog_from_path(path: Path) -> Dict[str, Dict[str, Any]]:
    content = path.read_text(encoding="utf-8")
    blocks = re.split(r"^##\s+", content, flags=re.MULTILINE)
    catalog: Dict[str, Dict[str, Any]] = {}

    for raw_block in blocks:
        block = raw_block.strip()
        if not block or not block.startswith("CHECK_"):
            continue

        lines = block.splitlines()
        header = lines[0].strip()
        match = re.match(r"(CHECK_\d+)\s*[-—â€”]\s*(.+)", header)
        if not match:
            continue

        check_id = match.group(1).strip().upper()
        title = match.group(2).strip()
        entry: Dict[str, Any] = {"check_id": check_id, "title": title}
        current_key = ""
        buffer: List[str] = []

        def flush() -> None:
            nonlocal buffer, current_key
            if not current_key:
                buffer = []
                return
            value = _clean_lines(buffer)
            if current_key == "columnes_taula_recomanades":
                entry[current_key] = [
                    line.lstrip("- ").strip()
                    for line in value.splitlines()
                    if line.strip()
                ]
            else:
                entry[current_key] = value
            buffer = []

        for line in lines[1:]:
            section_match = re.match(r"^###\s+(.+)$", line.strip())
            if section_match:
                flush()
                current_key = SECTION_KEYS.get(_normalize_heading(section_match.group(1)), "")
                continue
            buffer.append(line)

        flush()
        for key, default_value in REQUIRED_FIELDS.items():
            entry.setdefault(key, default_value)
        catalog[check_id] = entry

    return catalog


def render_check_explanation_catalog_entry(entry: Dict[str, Any]) -> str:
    lines = [
        f"## {entry['check_id']} — {entry['title']}",
        "### Què detecta",
        str(entry.get("que_detecta") or REQUIRED_FIELDS["que_detecta"]),
        "### Per què és important",
        str(entry.get("per_que_es_important") or REQUIRED_FIELDS["per_que_es_important"]),
        "### Impacte sobre el lot",
        str(entry.get("impacte_sobre_lot") or REQUIRED_FIELDS["impacte_sobre_lot"]),
        "### Com s'ha de revisar",
        str(entry.get("com_revisar") or REQUIRED_FIELDS["com_revisar"]),
        "### Com es pot corregir",
        str(entry.get("com_corregir") or REQUIRED_FIELDS["com_corregir"]),
        "### Limitacions o falsos positius",
        str(entry.get("limitacions") or REQUIRED_FIELDS["limitacions"]),
        "### Dades que s'han de mostrar a la taula",
    ]
    lines.extend(f"- {item}" for item in (entry.get("columnes_taula_recomanades") or []))
    lines.extend(
        [
            "### Validació posterior",
            str(entry.get("validacio_posterior") or REQUIRED_FIELDS["validacio_posterior"]),
        ]
    )
    return "\n".join(lines).strip()


def load_check_explanation_catalog_from_path(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    target = Path(path) if path else _catalog_path()
    return _load_check_explanation_catalog_from_path(target)


@lru_cache(maxsize=1)
def load_check_explanation_catalog() -> Dict[str, Dict[str, Any]]:
    return load_check_explanation_catalog_from_path(_catalog_path())
