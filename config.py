"""Family-specific settings live in family.toml (private; never on the
public line). examples/family.example.toml documents the format with made-up
values. Set FAMILY_CONFIG to use another file.

family.toml says what was received and how to read it (testers, kits, export
files, tree, settings). Hand-found research (documented relatives, confirmed
match -> tree person links, identical twins) is kept in
`data/notes/assertions.toml` (examples/assertions.example.toml); load() merges
it in: cfg["anchors"], cfg["identity"] and cfg["mz_twins"] hold the entries of
both files (family.toml first, for older setups).

The data folder (`data_dir`, default `data/`) is split by what a file is
(docs/data.md): input/, notes/, store/, cache/, output/. Code needs no
knowledge of this: `cfg["data_dir"] / "name"` (and config.path) finds an
existing file in whichever folder holds it, and sends a new file to output/
unless it is a known notes, store or cache file; `.glob()` searches all folders.
"""
import os
import tomllib
from pathlib import Path

import assertions

ROOT = Path(__file__).parent

LAYERS = ("notes", "store", "cache", "input", "output")
HOME = {"errata.toml": "notes", "plac_map.toml": "notes", "research": "notes",
        "assertions.toml": "notes",
        "tree.sqlite": "store", "tree_edits.json": "store", "tree_notes.md": "store",
        "geocode_private.json": "cache", "relationship_cm.csv": "cache"}


class DataDir(type(Path())):
    """The data folder; `/` and glob() look across its layers."""

    def with_segments(self, *parts):          # derived paths are plain paths
        return Path(*parts)

    def layer(self, name):
        return Path(self) / name

    def __truediv__(self, name):
        root = Path(self)
        name = str(name)
        first = Path(name).parts[0] if name else ""
        if first in LAYERS:
            return root / name
        for layer in LAYERS:
            if (root / layer / name).exists():
                return root / layer / name
        if (root / name).exists():
            return root / name                 # not sorted yet
        home = root / HOME.get(first, "output")
        home.mkdir(parents=True, exist_ok=True)
        return home / name

    def glob(self, pattern, **kw):
        root = Path(self)
        seen = []
        for d in [root / layer for layer in LAYERS] + [root]:
            if d.is_dir():
                for p in d.glob(pattern, **kw):
                    if p.is_file() and p not in seen:
                        seen.append(p)
        return iter(seen)


def load(path=None):
    p = Path(path or os.environ.get("FAMILY_CONFIG", ROOT / "family.toml"))
    if not p.exists():
        raise SystemExit(f"{p} not found: copy examples/family.example.toml to family.toml "
                         "and describe your own kits there.")
    cfg = tomllib.loads(p.read_text(encoding="utf-8"))
    cfg["data_dir"] = DataDir((p.parent / cfg.get("data_dir", "data")).resolve())
    hand = cfg["data_dir"].layer("notes") / "assertions.toml"
    cfg["assertions_file"] = hand if hand.exists() else None
    if hand.exists():
        extra = tomllib.loads(hand.read_text(encoding="utf-8"))
        unknown = set(extra) - set(HAND_KEPT)
        if unknown:
            raise SystemExit(f"{hand}: unknown section(s) {sorted(unknown)}; known: {list(HAND_KEPT)}")
        for k in HAND_KEPT:
            cfg[k] = cfg.get(k, []) + extra.get(k, [])
    people = cfg.get("people", {})
    cfg["children"] = [k for k, v in people.items() if v.get("role") == "child"]
    cfg["mother"] = next((k for k, v in people.items() if v.get("role") == "mother"), None)
    return cfg


# sections of notes/assertions.toml (lists of tables)
HAND_KEPT = ("anchors", "identity", "mz_twins")


def path(cfg, name):
    return cfg["data_dir"] / name


def display_name(cfg, subject):
    return cfg.get("people", {}).get(subject, {}).get("name", subject)


GRANDPARENT_DEFAULTS = {"FF": "paternal grandfather", "FM": "paternal grandmother",
                        "MF": "maternal grandfather", "MM": "maternal grandmother"}


def grandparent_label(cfg, code):
    return f"{code} – " + cfg.get("grandparents", {}).get(code, GRANDPARENT_DEFAULTS[code])




PLACEMENT_METHODS = ("copy_model", "painting")


def placement_method(cfg):
    """Which belief names the grandparent of a placed segment ([placement]
    method in family.toml): "copy_model" (default: the copy model where a
    tester has one, the painting for the rest) or "painting" (as before
    2026-11-10). The other is kept beside it as a check."""
    m = (cfg.get("placement") or {}).get("method", "copy_model")
    if m not in PLACEMENT_METHODS:
        raise SystemExit(f"[placement] method: {m!r}; known: {list(PLACEMENT_METHODS)}")
    return m


def anchor_sources(cfg):
    """Which lineage assertions name the grandparents in the phasing
    ([phasing] anchors in family.toml). Default: hand-documented anchors
    and tree links; DNA Painter paintings only when listed, so that by
    default they stay an independent check of the placement."""
    src = (cfg.get("phasing") or {}).get("anchors", ["documented", "tree"])
    bad = set(src) - set(assertions.ANCHOR_SOURCES)
    if bad:
        raise SystemExit(f"[phasing] anchors: unknown source(s) {sorted(bad)}; "
                         f"known: {sorted(assertions.ANCHOR_SOURCES)}")
    return list(src)
