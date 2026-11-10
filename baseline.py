"""
Freeze the pipeline's tables and compare a later run with them: the
safety net for refactors that should not change results.

    python3 baseline.py freeze [label]     # copy output/ tables to cache/baseline/<label>/
    python3 baseline.py compare [label]    # what differs now (default: newest baseline)
    python3 baseline.py list

Only the tables and reports are kept (CSV, Markdown, DNA Painter text);
images and HTML are left out. A baseline is private (it is output) and
lives in data/cache/, so it is not backed up and can be deleted at will.

The comparison is per file:
  * CSV: rows added and removed (rows compared whole, order ignored), and
    for files with a natural key, which columns changed on matching rows;
  * other text: lines added and removed.
Columns that only record when or by what a row was made (e.g. asserted_by,
source) are left out of the comparison, so a renamed module doesn't show
up as a changed result. A refactor that should change nothing must
report "same" for every file.
"""
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd

import config

KEEP = (".csv", ".md", ".txt")
SKIP = {"pipeline_log.md"}           # differs every run
IGNORE_COLS = {"asserted_by", "source", "origin"}
# natural keys: rows matching on these are compared column by column
KEYS = {
    "placed_matches.csv": ["subject", "platform", "match_key"],
    "phasing_verdicts.csv": ["assertion_id"],
    "prospects.csv": ["match_key"],
    "assertions_documented.csv": ["assertion_id"],
    "assertions_tree.csv": ["assertion_id"],
    "assertions_icw.csv": ["assertion_id"],
}


def _root(cfg):
    return cfg["data_dir"].layer("cache") / "baseline"


def _tables(out):
    return sorted(p for p in out.iterdir()
                  if p.is_file() and p.suffix in KEEP and p.name not in SKIP)


def freeze(cfg, label=None):
    out = cfg["data_dir"].layer("output")
    dest = _root(cfg) / (label or date.today().isoformat())
    dest.mkdir(parents=True, exist_ok=True)
    files = _tables(out)
    for p in files:
        shutil.copy2(p, dest / p.name)
    print(f"{len(files)} files -> {dest}")
    return dest


def _read(p):
    return pd.read_csv(p, dtype=str, keep_default_na=False, low_memory=False)


def compare_csv(old, new, key=None):
    a, b = _read(old), _read(new)
    cols = [c for c in a.columns if c in b.columns and c not in IGNORE_COLS]
    gone, added = sorted(set(a.columns) - set(b.columns)), sorted(set(b.columns) - set(a.columns))
    ra = a[cols].apply(tuple, axis=1).value_counts()
    rb = b[cols].apply(tuple, axis=1).value_counts()
    removed = int((ra - rb.reindex(ra.index, fill_value=0)).clip(lower=0).sum())
    new_rows = int((rb - ra.reindex(rb.index, fill_value=0)).clip(lower=0).sum())
    notes = []
    if gone or added:
        notes.append(f"columns removed {gone} added {added}")
    if key and all(k in cols for k in key) and (removed or new_rows):
        m = a[cols].drop_duplicates(key).merge(b[cols].drop_duplicates(key), on=key,
                                                suffixes=("_old", "_new"))
        changed = {c: int((m[c + "_old"] != m[c + "_new"]).sum())
                   for c in cols if c not in key}
        changed = {c: n for c, n in changed.items() if n}
        if changed:
            notes.append(f"{len(m)} rows by key; changed: "
                         + ", ".join(f"{c} {n}" for c, n in sorted(changed.items(), key=lambda x: -x[1])))
    same = not (removed or new_rows or gone or added)
    return same, f"{len(a)} -> {len(b)} rows, -{removed} +{new_rows}" + (
        "; " + "; ".join(notes) if notes else "")


def compare_text(old, new):
    a = old.read_text(encoding="utf-8", errors="replace").splitlines()
    b = new.read_text(encoding="utf-8", errors="replace").splitlines()
    sa, sb = pd.Series(a).value_counts(), pd.Series(b).value_counts()
    removed = int((sa - sb.reindex(sa.index, fill_value=0)).clip(lower=0).sum())
    added = int((sb - sa.reindex(sb.index, fill_value=0)).clip(lower=0).sum())
    return not (removed or added), f"{len(a)} -> {len(b)} lines, -{removed} +{added}"


def compare(cfg, label=None):
    root = _root(cfg)
    if label is None:
        dirs = sorted(d for d in root.iterdir() if d.is_dir()) if root.exists() else []
        if not dirs:
            raise SystemExit("no baseline: run `python3 baseline.py freeze` first")
        base = dirs[-1]
    else:
        base = root / label
    out = cfg["data_dir"].layer("output")
    print(f"baseline {base.name} vs {out}")
    n_diff = 0
    names = sorted({p.name for p in _tables(base)} | {p.name for p in _tables(out)})
    for name in names:
        old, new = base / name, out / name
        if not old.exists() or not new.exists():
            print(f"  {'new' if not old.exists() else 'gone':8s} {name}")
            n_diff += 1
            continue
        same, what = (compare_csv(old, new, KEYS.get(name)) if name.endswith(".csv")
                      else compare_text(old, new))
        n_diff += not same
        print(f"  {'same' if same else 'DIFFERS':8s} {name}: {what}")
    print(f"{n_diff} of {len(names)} files differ")
    return n_diff


if __name__ == "__main__":
    a = sys.argv[1:]
    cfg = config.load()
    if a[:1] == ["freeze"]:
        freeze(cfg, a[1] if len(a) > 1 else None)
    elif a[:1] == ["compare"]:
        sys.exit(1 if compare(cfg, a[1] if len(a) > 1 else None) else 0)
    elif a[:1] == ["list"]:
        r = _root(cfg)
        for d in sorted(r.iterdir()) if r.exists() else []:
            print(d.name, len(list(d.iterdir())), "files")
    else:
        print(__doc__)
