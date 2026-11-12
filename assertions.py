"""Assertions: claims with provenance, in one shape, from every source.

Two kinds of claim: **descent** (match m descends from the ancestor on path P,
or from a couple; no interval) and **lineage** (over [start, end] of `chrom`,
one of the subject's copies came down path P; `copy` is F/M when known, ""
for "one of the two"). Both share the record `COLUMNS`; interval columns are
empty for descent claims. `group` is the independence key: claims sharing it
are one piece of evidence (by default the match). `lineage` is kept at full
depth; use lineage.grandparent() at grandparent level.

    source        file (output/)                  kind of state
    documented    assertions_documented.csv       rebuilt (from [[anchors]], hand-kept)
    tree          assertions_tree.csv             rebuilt (from the GEDCOM + [[identity]])
    dnapainter    assertions_dnapainter.csv       rebuilt (from DNA Painter backups)
    icw           assertions_icw.csv              rebuilt (from shared-match lists)

read() returns any of them in the common shape, with the original columns kept
beside it. Sketch: errata, store edits and research entries are not read here yet.

Concept: docs/concepts.md, "Assertions with provenance".
"""
import pandas as pd

COLUMNS = ["assertion_id", "kind", "subject", "match_key", "match", "chrom", "start", "end",
           "lineage", "copy", "weight", "group", "evidence", "asserted_by", "source", "date"]

# the sources that can name grandparents in the phasing ([phasing] anchors)
ANCHOR_SOURCES = ("documented", "tree", "dnapainter")

FILES = {"documented": "assertions_documented.csv",
         "tree": "assertions_tree.csv",
         "dnapainter": "assertions_dnapainter.csv",
         "icw": "assertions_icw.csv"}


def normalise(df, source):
    """Bring one source's table into the common shape (COLUMNS first,
    every original column kept after them)."""
    df = df.copy()
    if not len(df):
        return pd.DataFrame(columns=COLUMNS + ["source_kind"])
    if "match_key" not in df:
        df["match_key"] = df.get("match", "")
    if source == "icw":
        # one vote per match and tester: a grandparent or side, no interval
        df["kind"] = df["kind"].map({"icw_candidate": "descent",
                                     "icw_deeper_hint": "descent"}).fillna(df["kind"])
        df["weight"] = pd.to_numeric(df.get("share"), errors="coerce").fillna(1.0)
        df["evidence"] = df.get("why", "")
        if "assertion_id" not in df:
            df["assertion_id"] = ["icw:" + "{}:{}:{}".format(r.subject, r.match_key, r.lineage)
                                  for r in df.itertuples()]
    if source == "dnapainter":
        df["weight"] = 1.0
    for c in COLUMNS:
        if c not in df:
            df[c] = float("nan") if c in ("start", "end", "weight") else ""
    df["copy"] = df["copy"].fillna("")
    df["group"] = df["group"].where(df["group"].astype(str) != "", df["match_key"])
    df["lineage"] = df["lineage"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    df["source_kind"] = source
    return df[COLUMNS + ["source_kind"] + [c for c in df.columns if c not in COLUMNS + ["source_kind"]]]


def read(data_dir, sources, kinds=None):
    """Assertions from the given sources (names in FILES) that exist, in
    the common shape: from the store's assertion table (outputs.py) when
    it holds every source asked for, else from the files.
    kinds: keep only these (e.g. {"lineage"})."""
    import outputs
    out = outputs.read_assertions(data_dir, list(sources))
    if out is not None:
        return out[out.kind.isin(kinds)] if kinds is not None else out
    parts = []
    for s in sources:
        p = data_dir / FILES[s]
        if not p.exists():
            continue
        d = pd.read_csv(p, dtype={"chrom": str, "lineage": str}, low_memory=False)
        parts.append(normalise(d, s))
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLUMNS)
    if kinds is not None:
        out = out[out.kind.isin(kinds)]
    return out


def one_per_group(df, weight="weight"):
    """Weights rescaled so each independence group sums to its largest
    single weight: one match counts once, however often it is repeated.
    (A sketch of "one match counts once"; correlated groups, e.g. several
    tested members of one family, are not merged here.)"""
    w = pd.to_numeric(df[weight], errors="coerce").fillna(1.0)
    tot = w.groupby(df["group"]).transform("sum")
    top = w.groupby(df["group"]).transform("max")
    return df.assign(**{weight: w * top / tot.where(tot > 0, 1)})
