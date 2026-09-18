"""Emit a content-addressed inventory (MANIFEST.sha256) for this evidence bundle.

Usage: py make_manifest.py
Writes MANIFEST.sha256 next to this script: "<sha256>  <relative path>" per file,
plus a bundle digest line. It also inventories the archived pre-framework
`.devagent` state (renamed `.devagent.pre-framework-audit`) so the preserved
evidence is checkable, and records it as MANUAL_DEVAGENT_ARCHIVE.sha256.
"""

from __future__ import annotations

import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ARCHIVE = os.path.join(ROOT, ".devagent.pre-framework-audit")
OUT = os.path.join(HERE, "MANIFEST.sha256")
ARCHIVE_OUT = os.path.join(HERE, "MANUAL_DEVAGENT_ARCHIVE.sha256")


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


SKIP = {"MANIFEST.sha256", "MANUAL_DEVAGENT_ARCHIVE.sha256"}


def inventory(root: str) -> list[tuple[str, str]]:
    rows = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {"__pycache__"}]
        for name in sorted(files):
            if name in SKIP:
                continue
            path = os.path.join(base, name)
            rows.append((os.path.relpath(path, root).replace("\\", "/"), sha256(path)))
    return sorted(rows)


def write(root: str, label: str, path: str, out_path: str) -> None:
    rows = inventory(root)
    bundle = hashlib.sha256()
    lines = []
    for rel, digest in rows:
        lines.append(f"{digest}  {rel}")
        bundle.update(f"{digest}  {rel}\n".encode())
    lines.append(f"BUNDLE_SHA256 {bundle.hexdigest()}  ({len(rows)} files)")
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"{label}: {len(rows)} files -> {bundle.hexdigest()}")


def main() -> int:
    write(HERE, "evidence bundle", "MANIFEST.sha256", OUT)
    if os.path.isdir(ARCHIVE):
        write(ARCHIVE, "manual .devagent archive", "arch", ARCHIVE_OUT)
    else:
        print("archive not found; skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
