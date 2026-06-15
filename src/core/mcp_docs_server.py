"""
MCP server that exposes this project's Markdown documentation as MCP resources.

Goal: let external MCP clients (e.g., a NotebookLM integration) ingest the docs
without requiring us to "push" anything. The client can list resources and read
their text content over MCP stdio transport.

No extra dependencies beyond `mcp` (available in the system Python in this env).
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import mcp.types as types
from mcp.server import Server


APP_NAME = os.environ.get("MCP_DOCS_SERVER_NAME", "dashboard-e13db-docs")
URI_PREFIX = "docs://notebooklm/"

# Repo root: .../src/core/mcp_docs_server.py -> parents[2] == repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORT_ROOT = REPO_ROOT / "notebooklm_export"


def _safe_relpath(p: Path, base: Path) -> str:
    rel = p.resolve().relative_to(base.resolve())
    # Always use forward slashes in URIs/titles.
    return rel.as_posix()


def _resource_uri(rel: str) -> str:
    # Encode path segments to keep URI parseable.
    return URI_PREFIX + quote(rel, safe="/-_.~")


def _uri_to_rel(uri: str) -> str:
    parsed = urlparse(uri)
    # Expect `docs://notebooklm/<path>`
    if f"{parsed.scheme}://{parsed.netloc}/" != URI_PREFIX:
        raise ValueError(f"Unsupported resource URI: {uri}")
    return unquote(parsed.path.lstrip("/"))


def _index_markdown_files() -> list[Path]:
    # Prefer the export folder if present (already curated).
    if EXPORT_ROOT.exists():
        paths: list[Path] = []
        for p in [EXPORT_ROOT / "INDEX.md", EXPORT_ROOT / "TUTORIAL.md"]:
            if p.exists():
                paths.append(p)
        for sub in ["product_docs", "agent_docs"]:
            d = EXPORT_ROOT / sub
            if d.exists():
                paths.extend(sorted(d.rglob("*.md")))
        return paths

    # Fallback: scan repo for *.md (excluding node_modules/venv/build artifacts)
    exclude = {"node_modules", ".venv", "dist", "build", ".git"}
    out: list[Path] = []
    for p in REPO_ROOT.rglob("*.md"):
        if any(part in exclude for part in p.parts):
            continue
        out.append(p)
    return sorted(out)


DOC_FILES = _index_markdown_files()

# Map `rel` (within EXPORT_ROOT or REPO_ROOT) to absolute file path.
DOC_MAP: dict[str, Path] = {}
BASE_FOR_RELS = EXPORT_ROOT if EXPORT_ROOT.exists() else REPO_ROOT
for p in DOC_FILES:
    try:
        rel = _safe_relpath(p, BASE_FOR_RELS)
    except Exception:
        continue
    DOC_MAP[rel] = p


app = Server(APP_NAME)


@app.list_resources()
async def list_resources() -> types.ListResourcesResult:
    resources: list[types.Resource] = []
    for rel, path in sorted(DOC_MAP.items()):
        uri = _resource_uri(rel)
        mime, _ = mimetypes.guess_type(path.name)
        mime = mime or "text/markdown"
        resources.append(
            types.Resource(
                name=rel,
                title=rel,
                uri=uri,
                description="Project documentation (Markdown).",
                mimeType=mime,
                size=path.stat().st_size if path.exists() else None,
                meta={"source_path": str(path)},
            )
        )
    return types.ListResourcesResult(resources=resources)


@app.read_resource()
async def read_resource(uri: str) -> types.ReadResourceResult:
    rel = _uri_to_rel(uri)
    path = DOC_MAP.get(rel)
    if not path:
        raise ValueError(f"Unknown doc: {rel}")

    text = path.read_text(encoding="utf-8", errors="replace")
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "text/markdown"
    return types.ReadResourceResult(
        contents=[types.TextResourceContents(uri=uri, mimeType=mime, text=text)]
    )


if __name__ == "__main__":
    # Stdio transport (typical for MCP clients).
    from mcp.server.stdio import stdio_server

    asyncio.run(stdio_server(app))

