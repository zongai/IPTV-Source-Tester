from __future__ import annotations

import hashlib
from pathlib import Path

_BASE_VERSION = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HASH_ROOTS = (_PROJECT_ROOT / "app", _PROJECT_ROOT / "frontend")


def code_revision() -> str:
    """Return a deterministic short revision derived from runtime code/assets.

    This intentionally does not depend on Git or a Docker rebuild. When the
    mounted app/frontend files change, the revision changes automatically.
    """
    h = hashlib.sha256()
    for root in _HASH_ROOTS:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc"}):
            rel = path.relative_to(_PROJECT_ROOT).as_posix().encode("utf-8")
            h.update(rel)
            h.update(b"\0")
            h.update(path.read_bytes())
            h.update(b"\0")
    return h.hexdigest()[:8]


def version_string() -> str:
    return f"{_BASE_VERSION}+{code_revision()}"
