"""Which hand-kept private files changed since they were last backed up.

Tracks the Drive-folder backup: what was backed up, with which checksum, and
what has changed since. What is backed up, and where it goes: docs/privacy-workflow.md,
"Backing up the private side" (family.toml, data/notes/**, the store's edit
files, PRIVATE_NOTES.md, and for reading only the small Markdown reports
and docs/concepts.md and roadmap.md).

    python3 backup.py status    # new / changed / unchanged since the last backup
    python3 backup.py mark      # record the current files as backed up
    python3 backup.py mark FILE # ... only these

    python3 backup.py snapshot          # output/ + notes/ as one dated zip
    python3 backup.py snapshot --input  # ... and the downloads in input/ too
    python3 backup.py snapshot --to DIR

A snapshot is for reading the results elsewhere, not the backup of record. It is
written to --to, else `[backup] snapshot_dir` in family.toml, else
data/snapshots/. On the other computer unzip it and run
`python3 serve.py --dir <unzipped folder>`. The record of the last backup is
data/cache/backup_state.json (private); the upload itself is done by hand or
through the Drive connector.
"""
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import config

ROOT = Path(__file__).parent
# Rebuilt reports copied to Drive for reading (small Markdown only).
REPORTS = ("revelations.md", "prospects.md", "relationship_check.md",
           "icw_report.md", "errata_report.md")
# Public docs copied beside PRIVATE_NOTES.md for claude.ai chats.
DOCS = ("concepts.md", "roadmap.md")


def files(cfg):
    D = Path(cfg["data_dir"])
    # the config actually loaded: FAMILY_CONFIG names another family's
    # family.toml, backed up to that family's own folder
    other = os.environ.get("FAMILY_CONFIG")
    out = {"family.toml": (Path(other) if other else ROOT / "family.toml", "config")}
    if not other and (ROOT / "PRIVATE_NOTES.md").exists():
        out["PRIVATE_NOTES.md"] = (ROOT / "PRIVATE_NOTES.md", "Claude")
    if not other:   # public docs, copied for chats that cannot reach GitHub
        for name in DOCS:
            out[f"docs/{name}"] = (ROOT / "docs" / name, "Claude")
    notes = D / "notes"
    if notes.is_dir():
        for p in sorted(notes.rglob("*")):
            if p.is_file() and p.name not in ("INDEX.md", ".DS_Store"):
                rel = p.relative_to(D)
                out[str(rel)] = (p, str(Path(*rel.parts[:-1])))
    for name in ("tree_edits.json", "tree_notes.md"):
        p = D / "store" / name
        if p.exists():
            out[f"store/{name}"] = (p, "store")
    for name in REPORTS:
        p = D / "output" / name
        if p.exists():
            out[f"output/{name}"] = (p, "reports")
    return out


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def state_path(cfg):
    return Path(cfg["data_dir"]) / "cache" / "backup_state.json"


def load_state(cfg):
    p = state_path(cfg)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def status(cfg):
    st = load_state(cfg)
    rows = []
    for key, (p, folder) in files(cfg).items():
        old = st.get(key, {}).get("sha256")
        kind = "new" if old is None else ("changed" if old != sha(p) else "unchanged")
        rows.append((kind, key, folder, p.stat().st_size, st.get(key, {}).get("at", "")))
    for key in st:
        if key not in files(cfg):
            rows.append(("gone locally", key, st[key].get("folder", ""), 0, st[key].get("at", "")))
    return rows


def mark(cfg, only=None):
    st = load_state(cfg)
    now = datetime.now().isoformat(timespec="minutes")
    for key, (p, folder) in files(cfg).items():
        if only and key not in only and str(p) not in only:
            continue
        st[key] = dict(sha256=sha(p), size=p.stat().st_size, folder=folder, at=now)
    state_path(cfg).parent.mkdir(parents=True, exist_ok=True)
    state_path(cfg).write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding="utf-8")
    return len(st)


def snapshot(cfg, with_input=False, to=None):
    """Zip output/ (at the top), notes/ (as notes/) and serve.py; with
    with_input also input/ (as input/). Returns the zip's path."""
    D = Path(cfg["data_dir"])
    dest = Path(to or cfg.get("backup", {}).get("snapshot_dir") or D / "snapshots").expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    zp = dest / f"synthetic_genealogy_{'output+input' if with_input else 'output'}_{stamp}.zip"
    parts = [(D / "output", ""), (D / "notes", "notes/")] + ([(D / "input", "input/")] if with_input else [])
    tmp = zp.with_suffix(".zip.part")           # a synced folder never sees half a zip
    n = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for src, prefix in parts:
            if not src.is_dir():
                continue
            for p in sorted(src.rglob("*")):
                if p.is_file() and p.name != ".DS_Store":
                    z.write(p, prefix + p.relative_to(src).as_posix())
                    n += 1
        z.write(ROOT / "serve.py", "serve.py")
        z.writestr("README.txt", f"synthetic_genealogy snapshot, {stamp}. Private: names and DNA results.\n\n"
                   "Browse:  python3 serve.py --dir .   (then http://127.0.0.1:8000)\n"
                   "The pipeline's outputs are at the top, the hand-kept notes in notes/"
                   + (", the downloads as received in input/" if with_input else "") + ".\n")
    tmp.replace(zp)
    return zp, n


def _main(argv):
    cfg = config.load()
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        rows = status(cfg)
        todo = [r for r in rows if r[0] != "unchanged"]
        for kind, key, folder, size, at in sorted(rows, key=lambda r: (r[0] == "unchanged", r[1])):
            print(f"{kind:13} {key:55} -> {folder:16} {size:7} {('last ' + at) if at else ''}")
        print(f"{len(todo)} to back up, {len(rows) - len(todo)} unchanged")
    elif cmd == "snapshot":
        to = argv[argv.index("--to") + 1] if "--to" in argv else None
        zp, n = snapshot(cfg, "--input" in argv, to)
        print(f"wrote {zp} ({n} files, {zp.stat().st_size / 1e6:.0f} MB)")
    elif cmd == "mark":
        print(f"recorded {mark(cfg, set(argv[1:]) or None)} files as backed up")
    else:
        print(__doc__)


if __name__ == "__main__":
    _main(sys.argv[1:])
