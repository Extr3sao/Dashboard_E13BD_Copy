from pathlib import Path

import pytest
from fastapi import HTTPException

from src.api import post_crq_operational_docs


def _build_definitions(tmp_path: Path):
    audit_path = tmp_path / "auditoria_post_crq.md"
    explanation_path = tmp_path / "EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md"
    audit_path.write_text("# Audit\n", encoding="utf-8")
    explanation_path.write_text("# Explanation\n", encoding="utf-8")
    return {
        "post_crq_audit": {
            "title": "Auditoria post-CRQ",
            "filename": audit_path.name,
            "kind": "query_markdown",
            "path_resolver": lambda: str(audit_path),
        },
        "check_quality_explanation": {
            "title": "Explicacion checks de calidad",
            "filename": explanation_path.name,
            "kind": "explanation_markdown",
            "path_resolver": lambda: str(explanation_path),
        },
    }


def test_list_post_crq_operational_documents_strips_utf8_bom(tmp_path, monkeypatch):
    definitions = _build_definitions(tmp_path)
    audit_path = Path(definitions["post_crq_audit"]["path_resolver"]())
    audit_path.write_bytes("\ufeff# Audit amb BOM\n".encode("utf-8"))
    monkeypatch.setattr(
        post_crq_operational_docs,
        "_DOCUMENT_DEFINITIONS",
        definitions,
    )
    monkeypatch.setattr(
        post_crq_operational_docs,
        "_history_root",
        lambda: tmp_path / "history",
    )

    payload = post_crq_operational_docs.list_post_crq_operational_documents()

    audit_item = next(item for item in payload["items"] if item["id"] == "post_crq_audit")
    assert audit_item["content"] == "# Audit amb BOM\n"
    assert not audit_item["content"].startswith("\ufeff")


def test_list_post_crq_operational_documents_returns_expected_items(tmp_path, monkeypatch):
    monkeypatch.setattr(
        post_crq_operational_docs,
        "_DOCUMENT_DEFINITIONS",
        _build_definitions(tmp_path),
    )
    monkeypatch.setattr(
        post_crq_operational_docs,
        "_history_root",
        lambda: tmp_path / "history",
    )

    payload = post_crq_operational_docs.list_post_crq_operational_documents()

    assert payload["count"] == 2
    assert {item["id"] for item in payload["items"]} == {
        "post_crq_audit",
        "check_quality_explanation",
    }
    assert all(item["version"] for item in payload["items"])


def test_update_post_crq_operational_document_rejects_stale_version(tmp_path, monkeypatch):
    monkeypatch.setattr(
        post_crq_operational_docs,
        "_DOCUMENT_DEFINITIONS",
        _build_definitions(tmp_path),
    )
    monkeypatch.setattr(
        post_crq_operational_docs,
        "_history_root",
        lambda: tmp_path / "history",
    )

    current = post_crq_operational_docs.list_post_crq_operational_documents()["items"][0]

    post_crq_operational_docs.update_post_crq_operational_document(
        "post_crq_audit",
        "# Audit changed once\n",
        expected_version=current["version"],
    )

    with pytest.raises(HTTPException) as exc_info:
        post_crq_operational_docs.update_post_crq_operational_document(
            "post_crq_audit",
            "# Audit changed twice\n",
            expected_version=current["version"],
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["current"]["content"] == "# Audit changed once\n"


def test_update_post_crq_operational_document_tracks_history_and_allows_force_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(
        post_crq_operational_docs,
        "_DOCUMENT_DEFINITIONS",
        _build_definitions(tmp_path),
    )
    monkeypatch.setattr(
        post_crq_operational_docs,
        "_history_root",
        lambda: tmp_path / "history",
    )

    current = post_crq_operational_docs.list_post_crq_operational_documents()["items"][0]

    updated = post_crq_operational_docs.update_post_crq_operational_document(
        "post_crq_audit",
        "# Audit changed once\n",
        expected_version=current["version"],
    )

    history = post_crq_operational_docs.list_post_crq_operational_document_history("post_crq_audit")
    assert history["count"] == 1
    assert history["items"][0]["content"] == "# Audit changed once\n"
    assert updated["history_entry"]["version"] == updated["item"]["version"]

    forced = post_crq_operational_docs.update_post_crq_operational_document(
        "post_crq_audit",
        "# Audit forced overwrite\n",
        expected_version=current["version"],
        force_overwrite=True,
    )
    assert forced["item"]["content"] == "# Audit forced overwrite\n"

    history_after_force = post_crq_operational_docs.list_post_crq_operational_document_history("post_crq_audit")
    assert history_after_force["count"] == 2
    assert history_after_force["items"][0]["content"] == "# Audit forced overwrite\n"


def test_update_post_crq_operational_document_persists_without_utf8_bom(tmp_path, monkeypatch):
    definitions = _build_definitions(tmp_path)
    monkeypatch.setattr(
        post_crq_operational_docs,
        "_DOCUMENT_DEFINITIONS",
        definitions,
    )
    monkeypatch.setattr(
        post_crq_operational_docs,
        "_history_root",
        lambda: tmp_path / "history",
    )

    current = post_crq_operational_docs.list_post_crq_operational_documents()["items"][0]
    audit_path = Path(definitions["post_crq_audit"]["path_resolver"]())

    updated = post_crq_operational_docs.update_post_crq_operational_document(
        "post_crq_audit",
        "\ufeff# Audit normalitzat\n",
        expected_version=current["version"],
    )

    assert updated["item"]["content"] == "# Audit normalitzat\n"
    assert audit_path.read_bytes().startswith(b"# Audit normalitzat")
    assert not audit_path.read_bytes().startswith(b"\xef\xbb\xbf")
