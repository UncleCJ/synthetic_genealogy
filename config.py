"""
Family-specific settings live in family.toml (private; never on the
public line). family.example.toml documents the format with made-up
values. Set FAMILY_CONFIG to use another file.

The data folder (private, `data_dir`, default `data/`) is split by what a
file is (DATA.md):

    input/   downloads as received: vendor exports, GEDCOMs, raw kits,
             archives' pages. Code never writes here.
    notes/   files kept by hand: errata.toml, plac_map.toml, research/
    store/   tree.sqlite (rebuildable) with tree_edits.json and
             tree_notes.md (not rebuildable: the edits and their log)
    cache/   answers from web services (private)
    output/  everything the pipeline writes; safe to delete and rerun

Code needs no knowledge of this: `cfg["data_dir"] / "name"` (and
config.path) finds an existing file in whichever folder holds it, and
sends a new file to output/ unless it is one of the known notes, store or
cache files. `.glob()` searches all folders. Files still at the top of
data/ (an unsorted folder) are found too.
"""
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent

LAYERS = ("notes", "store", "cache", "input", "output")
HOME = {"errata.toml": "notes", "plac_map.toml": "notes", "research": "notes",
        "tree.sqlite": "store", "tree_edits.json": "store", "tree_notes.md": "store",
        "geocode_private.json": "cache"}


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
        raise SystemExit(f"{p} not found: copy family.example.toml to family.toml "
                         "and describe your own kits there.")
    cfg = tomllib.loads(p.read_text(encoding="utf-8"))
    cfg["data_dir"] = DataDir((p.parent / cfg.get("data_dir", "data")).resolve())
    people = cfg.get("people", {})
    cfg["children"] = [k for k, v in people.items() if v.get("role") == "child"]
    cfg["mother"] = next((k for k, v in people.items() if v.get("role") == "mother"), None)
    return cfg


def path(cfg, name):
    return cfg["data_dir"] / name


def display_name(cfg, subject):
    return cfg.get("people", {}).get(subject, {}).get("name", subject)


GRANDPARENT_DEFAULTS = {"FF": "paternal grandfather", "FM": "paternal grandmother",
                        "MF": "maternal grandfather", "MM": "maternal grandmother"}


def grandparent_label(cfg, code):
    return f"{code} – " + cfg.get("grandparents", {}).get(code, GRANDPARENT_DEFAULTS[code])


ANCHOR_FILES = {"documented": "assertions_documented.csv",
                "tree": "assertions_tree.csv",
                "dnapainter": "assertions_dnapainter.csv"}


def anchor_sources(cfg):
    """Which lineage assertions name the grandparents in the phasing
    ([phasing] anchors in family.toml). Default: hand-documented anchors
    and tree links; DNA Painter paintings only when listed, so that by
    default they stay an independent check of the placement."""
    src = (cfg.get("phasing") or {}).get("anchors", ["documented", "tree"])
    bad = set(src) - set(ANCHOR_FILES)
    if bad:
        raise SystemExit(f"[phasing] anchors: unknown source(s) {sorted(bad)}; "
                         f"known: {sorted(ANCHOR_FILES)}")
    return list(src)
