"""
Which hand-kept private files changed since they were last backed up.

The private side of the project lives in two places: the jj `private`
commit (local history, never pushed) and a Drive folder (the backup that
survives this computer). This script keeps track of the second: what was
backed up, with which checksum, and what has changed since.

Backed up (small text, kept by hand, not rebuildable):

    family.toml                       -> config/
    data/notes/** (not INDEX.md)      -> notes/...
    data/store/tree_edits.json        -> store/
    data/store/tree_notes.md          -> store/

Downloads in data/input/ go to the archive folders they came from, by
their own naming rules (WORKFLOW.md); everything in data/output/ and
data/cache/ is rebuildable and not backed up.

    python3 backup.py status    # new / changed / unchanged since the last backup
    python3 backup.py mark      # record the current files as backed up
    python3 backup.py mark FILE # ... only these

The record of the last backup is data/cache/backup_state.json (private).
The upload itself is done by hand or by a Claude session through the Drive
connector; see WORKFLOW.md.
"""
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import config

ROOT = Path(__file__).parent


def files(cfg):
    D = Path(cfg["data_dir"])
    out = {"family.toml": (ROOT / "family.toml", "config")}
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


def _main(argv):
    cfg = config.load()
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        rows = status(cfg)
        todo = [r for r in rows if r[0] != "unchanged"]
        for kind, key, folder, size, at in sorted(rows, key=lambda r: (r[0] == "unchanged", r[1])):
            print(f"{kind:13} {key:55} -> {folder:16} {size:7} {('last ' + at) if at else ''}")
        print(f"{len(todo)} to back up, {len(rows) - len(todo)} unchanged")
    elif cmd == "mark":
        print(f"recorded {mark(cfg, set(argv[1:]) or None)} files as backed up")
    else:
        print(__doc__)


if __name__ == "__main__":
    _main(sys.argv[1:])
