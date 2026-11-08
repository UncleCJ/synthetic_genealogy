"""File cache: avatars/<backend>/<person-id>-<fingerprint>.<ext> plus a JSON index.

Paid or slow backends are called at most once per (person, attributes, backend version).
Hand-picked or real photos dropped in avatars/override/<person-id>.* always win.
"""
from __future__ import annotations
import json, re
from pathlib import Path
from .person import Person
from .backends import Backend


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:60]


class AvatarCache:
    def __init__(self, root: str | Path = "avatars"):
        self.root = Path(root)
        self.index_path = self.root / "index.json"
        self.index = json.loads(self.index_path.read_text()) if self.index_path.exists() else {}

    def get(self, p: Person, backend: Backend, refresh: bool = False) -> Path:
        override = next((self.root / "override").glob(f"{_slug(p.id)}.*"), None) \
            if (self.root / "override").exists() else None
        if override:
            return override
        fp = p.fingerprint(backend.version)
        path = self.root / backend.name / f"{_slug(p.id)}-{fp}.{backend.ext}"
        if refresh or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            for old in path.parent.glob(f"{_slug(p.id)}-*.{backend.ext}"):
                old.unlink()                     # drop stale versions of this person
            path.write_bytes(backend.generate(p))
            self.index.setdefault(p.id, {})[backend.name] = str(path.relative_to(self.root))
            self.index_path.write_text(json.dumps(self.index, indent=1, ensure_ascii=False))
        return path
