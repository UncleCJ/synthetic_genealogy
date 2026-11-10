"""
Assertions: claims with provenance, in one shape, from every source.

Two kinds of claim are kept apart, because a model needs them apart:

* **descent** (genealogical): match m descends from the proband's ancestor
  on path P ("FMF" = the father's mother's father), or from a couple
  (P is then the couple's child on the proband's line, "FM" for the
  couple FMF & FMM). No interval: it is about people. Sources: hand
  anchors ([[anchors]]), the tree (name joins and confirmed identities),
  DNA Painter group names, shared-match votes.
* **lineage** (on a chromosome): over [start, end] of `chrom`, one of the
  subject's copies came down path P. Derived from a descent claim and the
  match's segments (documented_anchors), or painted by hand (DNA Painter).
  `copy` says which copy when it is known (F/M, from a tested parent or a
  phasing); "" means only "one of the two", which is all a single
  unphased donor can say.

The record (COLUMNS) is the same for both; interval columns are empty for
descent claims. `group` is the independence key: claims sharing it are
one piece of evidence (by default the match, so one match counts once
however many testers, vendors or segments repeat it). `lineage` is kept
at full depth; code that works at grandparent level takes
lineage.grandparent() of it.

Where assertions come from and what kind of state they are:

    source        file (output/)                  kind of state
    documented    assertions_documented.csv       rebuilt (from [[anchors]], hand-kept)
    tree          assertions_tree.csv             rebuilt (from the GEDCOM + [[identity]])
    dnapainter    assertions_dnapainter.csv       rebuilt (from DNA Painter backups)
    icw           assertions_icw.csv              rebuilt (from shared-match lists)

read() returns any of them in the common shape, with the original
columns kept beside it.

Sketch: errata, store edits and research entries are claims too but are
not read here yet (they are about records and people, not DNA).
"""
import pandas as pd

COLUMNS = ["assertion_id", "kind", "subject", "match_key", "match", "chrom", "start", "end",
           "lineage", "copy", "weight", "group", "evidence", "asserted_by", "source", "date"]

FILES = {"documented": "assertions_documented.csv",
         "tree": "assertions_tree.csv",
         "dnapainter": "assertions_dnapainter.csv",
         "icw": "assertions_icw.csv"}


def normalise(df, source):
    """Bring one source's table into the common shape (COLUMNS first,
    every original column kept after them)."""
    df = df.copy()
    if not len(df):
        return pd.DataFrame(columns=COLUMNS)
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
            df[c] = ""
    df["copy"] = df["copy"].fillna("")
    df["group"] = df["group"].where(df["group"].astype(str) != "", df["match_key"])
    df["lineage"] = df["lineage"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    df["source_kind"] = source
    return df[COLUMNS + ["source_kind"] + [c for c in df.columns if c not in COLUMNS + ["source_kind"]]]


def read(data_dir, sources, kinds=None):
    """Assertions from the given sources (names in FILES) that exist, in
    the common shape. kinds: keep only these (e.g. {"lineage"})."""
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
