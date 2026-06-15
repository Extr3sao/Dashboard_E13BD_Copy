import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from src.api.post_crq_audit import resolve_post_crq_markdown_path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_check_explanation_path() -> str:
    return str(_project_root() / "EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md")


_DOCUMENT_DEFINITIONS = {
    "post_crq_audit": {
        "title": "Auditoria post-CRQ",
        "filename": "auditoria_post_crq.md",
        "kind": "query_markdown",
        "path_resolver": resolve_post_crq_markdown_path,
    },
    "check_quality_explanation": {
        "title": "Explicacion checks de calidad",
        "filename": "EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md",
        "kind": "explanation_markdown",
        "path_resolver": _resolve_check_explanation_path,
    },
}


def _resolve_document_definition(document_id: str) -> Dict[str, Any]:
    definition = _DOCUMENT_DEFINITIONS.get(str(document_id or "").strip())
    if not definition:
        raise HTTPException(status_code=404, detail="Document operatiu no trobat")
    return definition


def _read_document_content(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Fitxer no trobat: {path.name}") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"No s'ha pogut llegir el fitxer: {path.name}") from exc


def _normalize_document_content(content: str) -> str:
    return str(content or "").removeprefix("\ufeff")


def _document_version(content: str) -> str:
    normalized_content = _normalize_document_content(content)
    return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()


def _history_root() -> Path:
    return _project_root() / "data" / "post_crq_doc_versions"


def _history_dir(document_id: str) -> Path:
    return _history_root() / document_id


def _history_snapshot_id(version: str) -> str:
    timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}_{version[:12]}"


def _history_snapshot_path(document_id: str, snapshot_id: str) -> Path:
    return _history_dir(document_id) / f"{snapshot_id}.json"


def _ensure_history_dir(document_id: str) -> Path:
    directory = _history_dir(document_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _serialize_document(document_id: str) -> Dict[str, Any]:
    definition = _resolve_document_definition(document_id)
    path = Path(definition["path_resolver"]()).resolve()
    content = _normalize_document_content(_read_document_content(path))
    last_modified = datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=datetime.timezone.utc)
    return {
        "id": document_id,
        "title": definition["title"],
        "filename": definition["filename"],
        "kind": definition["kind"],
        "content_type": "markdown",
        "content": content,
        "version": _document_version(content),
        "updated_at": last_modified.isoformat().replace("+00:00", "Z"),
        "size_bytes": path.stat().st_size,
    }


def _write_history_snapshot(document_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_history_dir(document_id)
    snapshot_id = _history_snapshot_id(item["version"])
    payload = {
        "snapshot_id": snapshot_id,
        "document_id": document_id,
        "title": item["title"],
        "filename": item["filename"],
        "kind": item["kind"],
        "content_type": item["content_type"],
        "content": item["content"],
        "version": item["version"],
        "saved_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "updated_at": item["updated_at"],
        "size_bytes": item["size_bytes"],
    }
    _history_snapshot_path(document_id, snapshot_id).write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return payload


def list_post_crq_operational_document_history(document_id: str, limit: int = 10) -> Dict[str, Any]:
    _resolve_document_definition(document_id)
    history_dir = _history_dir(document_id)
    if not history_dir.exists():
        return {"items": [], "count": 0}

    items: List[Dict[str, Any]] = []
    for path in sorted(history_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append(payload)

    limited_items = items[: max(1, int(limit or 10))]
    return {
        "items": limited_items,
        "count": len(limited_items),
    }


def list_post_crq_operational_documents() -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for document_id in _DOCUMENT_DEFINITIONS:
        items.append(_serialize_document(document_id))
    return {
        "items": items,
        "count": len(items),
    }


def update_post_crq_operational_document(
    document_id: str,
    content: str,
    *,
    expected_version: Optional[str] = None,
    force_overwrite: bool = False,
) -> Dict[str, Any]:
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="El contingut del document ha de ser text")
    normalized_content = _normalize_document_content(content)

    current = _serialize_document(document_id)
    if expected_version and current["version"] != expected_version and not force_overwrite:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Conflicte de versio: el document ha canviat al servidor.",
                "current": current,
            },
        )
    if current["content"] == normalized_content:
        return {
            "item": current,
            "history_entry": None,
        }

    definition = _resolve_document_definition(document_id)
    path = Path(definition["path_resolver"]()).resolve()
    try:
        path.write_text(normalized_content, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"No s'ha pogut desar el fitxer: {path.name}") from exc

    updated_item = _serialize_document(document_id)
    history_entry = _write_history_snapshot(document_id, updated_item)
    return {
        "item": updated_item,
        "history_entry": history_entry,
    }
