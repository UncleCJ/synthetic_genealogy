"""The pipeline's tables go through the store: each step writes its tables
here, and the next step reads them from here, not from loose CSV files.

    outputs.write(D, "placed_segments.csv", df)     # CSV view + store table
    outputs.read(D, "placed_segments.csv", dtype={"chrom": str})
    outputs.artifacts(D)                            # what is there, written by which step, when

D is the data folder (cfg["data_dir"]). Each table lives in data/store/tree.sqlite
as `out_<name>`; the `artifact` table says which step wrote it, when, how many
rows and the column types. The CSV in data/output/ is the readable view.
Tables are stored as reading their CSV gives them. Writing an assertion file
(assertions.FILES) also refreshes the store's `assertion` table for that
source (assertions.read() reads from it).

Rebuilt state only: hand-kept files never go through here. If the store is
missing or was rebuilt without a table, read() falls back to the CSV.
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

import pandas as pd

STORE = "tree.sqlite"


def _db(data_dir):
    path = data_dir.layer("store") / STORE
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("create table if not exists artifact (name text primary key, tbl text, step text, "
               "written text, rows integer, dtypes text)")
    return db


def _table(name):
    return "out_" + re.sub(r"\W+", "_", os.path.splitext(name)[0]).strip("_").lower()


def _step():
    return os.path.splitext(os.path.basename(sys.argv[0] or "?"))[0] or "?"


def _csv_path(data_dir, name):
    return data_dir.layer("output") / name


def _put(db, tbl, df):
    df.to_sql(tbl, db, if_exists="replace", index=False, chunksize=5000)
    return json.dumps({c: str(t) for c, t in df.dtypes.items()})


def _restore(df, dtypes):
    for c, t in dtypes.items():
        if c not in df:
            continue
        if t == "bool":
            df[c] = df[c].astype(bool)
        elif t.startswith(("float", "int")):
            df[c] = pd.to_numeric(df[c])
            if t.startswith("float"):
                df[c] = df[c].astype(float)
        elif t == "object":
            df[c] = df[c].astype(object).where(df[c].notna(), float("nan"))
    return df


def write(data_dir, name, df, step=None):
    """Write `df` as output/<name> (the view) and as a store table."""
    path = _csv_path(data_dir, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    back = pd.read_csv(path, low_memory=False) if path.stat().st_size > 1 else pd.DataFrame()
    db = _db(data_dir)
    try:
        tbl = _table(name)
        if len(back.columns):
            dtypes = _put(db, tbl, back)
        else:
            db.execute(f"drop table if exists {tbl}")
            dtypes = "{}"
        db.execute("insert or replace into artifact values (?, ?, ?, ?, ?, ?)",
                   (name, tbl, step or _step(), datetime.now().isoformat(timespec="seconds"),
                    len(back), dtypes))
        import assertions
        src = {v: k for k, v in assertions.FILES.items()}.get(name)
        if src:
            _refresh_assertions(db, src, path)
        db.commit()
    finally:
        db.close()
    return path


def _refresh_assertions(db, source, path):
    import assertions
    d = (pd.read_csv(path, dtype={"chrom": str, "lineage": str}, low_memory=False)
         if path.stat().st_size > 1 else pd.DataFrame())
    n = assertions.normalise(d, source)
    cols = assertions.COLUMNS + ["source_kind"]
    extra = [c for c in n.columns if c not in cols]
    rows = n[cols].copy()
    rows["source_kind"] = source
    rows["extra"] = [json.dumps({c: (None if pd.isna(v) else v) for c, v in zip(extra, r)},
                                default=str, ensure_ascii=False)
                     for r in n[extra].itertuples(index=False)] if extra else "{}"
    have = [r[1] for r in db.execute("pragma table_info(assertion)")]
    if have and have != list(rows.columns):
        db.execute("drop table assertion")
        have = []
    if have:
        db.execute("delete from assertion where source_kind = ?", (source,))
    if len(rows):
        rows.to_sql("assertion", db, if_exists="append", index=False)
    elif not have:
        pd.DataFrame(columns=rows.columns).to_sql("assertion", db, index=False)
    dt = {c: str(t) for c, t in rows.dtypes.items()}
    db.execute("insert or replace into artifact values (?, ?, ?, ?, ?, ?)",
               ("assertion:" + source, "assertion", _step(), datetime.now().isoformat(timespec="seconds"),
                len(rows), json.dumps(dt)))


def _artifact(db, name):
    return db.execute("select tbl, dtypes from artifact where name = ?", (name,)).fetchone()


def has(data_dir, name):
    """True if the table exists (in the store, or as a CSV)."""
    path = data_dir.layer("store") / STORE
    if path.exists():
        db = sqlite3.connect(path)
        try:
            if db.execute("select 1 from sqlite_master where name = 'artifact'").fetchone() \
                    and _artifact(db, name):
                return True
        finally:
            db.close()
    return _csv_path(data_dir, name).exists() or (data_dir / name).exists()


def read(data_dir, name, dtype=None, usecols=None):
    """A table as its step wrote it, from the store (else from the CSV).
    dtype: columns to read as str, like pd.read_csv(dtype={...: str});
    usecols: only these columns."""
    df = _read(data_dir, name, dtype)
    return df[list(usecols)] if usecols is not None else df


def _read(data_dir, name, dtype):
    path = data_dir.layer("store") / STORE
    df = None
    if path.exists():
        db = sqlite3.connect(path)
        try:
            a = (_artifact(db, name)
                 if db.execute("select 1 from sqlite_master where name = 'artifact'").fetchone() else None)
            if a:
                tbl, dtypes = a
                exists = db.execute("select 1 from sqlite_master where name = ?", (tbl,)).fetchone()
                df = (_restore(pd.read_sql(f"select * from {tbl}", db), json.loads(dtypes))
                      if exists else pd.DataFrame())
        finally:
            db.close()
    if df is None:
        csv = _csv_path(data_dir, name)
        csv = csv if csv.exists() else data_dir / name
        return pd.read_csv(csv, dtype=dtype, low_memory=False)
    for c, t in (dtype or {}).items():
        if c in df and t is str:
            df[c] = df[c].astype("str")          # as pd.read_csv(dtype=str): NaN kept
    return df


def read_assertions(data_dir, sources):
    """The store's assertion rows for these sources (None if the store has
    none of them yet), with each source's own columns expanded again."""
    path = data_dir.layer("store") / STORE
    if not path.exists():
        return None
    db = sqlite3.connect(path)
    try:
        if not db.execute("select 1 from sqlite_master where name = 'assertion'").fetchone():
            return None
        listed = {r[0][len("assertion:"):] for r in
                  db.execute("select name from artifact where name like 'assertion:%'")}
        if not set(sources) <= listed:
            return None
        q = "select rowid as _row, * from assertion where source_kind in (%s)" % ",".join("?" * len(sources))
        df = pd.read_sql(q, db, params=list(sources))
        # in the order asked for, each source in its file's order
        rank = {s: i for i, s in enumerate(sources)}
        df = (df.assign(_rank=df.source_kind.map(rank)).sort_values(["_rank", "_row"], kind="stable")
              .drop(columns=["_rank", "_row"]).reset_index(drop=True))
        dt = db.execute("select dtypes from artifact where name = ?",
                        ("assertion:" + sources[0],)).fetchone() if sources else None
    finally:
        db.close()
    if not len(df):
        return df.drop(columns=["extra"], errors="ignore")
    df = _restore(df, json.loads(dt[0]) if dt else {})
    extra = pd.DataFrame([json.loads(x) for x in df.pop("extra")], index=df.index)
    df = pd.concat([df, extra[[c for c in extra.columns if c not in df.columns]]], axis=1)
    for c in df.columns:                                   # NULLs as NaN, like a CSV read
        if df[c].dtype == object:
            df[c] = df[c].where(df[c].notna(), float("nan"))
    return df


def artifacts(data_dir):
    path = data_dir.layer("store") / STORE
    if not path.exists():
        return pd.DataFrame(columns=["name", "tbl", "step", "written", "rows"])
    db = sqlite3.connect(path)
    try:
        return pd.read_sql("select name, tbl, step, written, rows from artifact order by written", db)
    finally:
        db.close()


if __name__ == "__main__":
    import config
    print(artifacts(config.load()["data_dir"]).to_string(index=False))
