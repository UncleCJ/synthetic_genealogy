"""
Family-specific settings live in family.toml (private; never on the
public line). family.example.toml documents the format with made-up
values. Set FAMILY_CONFIG to use another file.
"""
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent


def load(path=None):
    p = Path(path or os.environ.get("FAMILY_CONFIG", ROOT / "family.toml"))
    if not p.exists():
        raise SystemExit(f"{p} not found: copy family.example.toml to family.toml "
                         "and describe your own kits there.")
    cfg = tomllib.loads(p.read_text(encoding="utf-8"))
    cfg["data_dir"] = (p.parent / cfg.get("data_dir", "data")).resolve()
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
