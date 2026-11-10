"""
Read FamilyTreeDNA Family Finder exports: the match list
("<kit>_Family_Finder_Matches_<date>.csv") and the chromosome browser
segments ("<kit>_Chromosome_Browser_Results_<date>.csv").

The segment file names a match only by "First Middle Last" with irregular
spacing; the match list has the parts separately. Both are whitespace-
normalised into `match_key`. Names that occur twice in a match list are
kept but flagged `ambiguous`, since their segments cannot be told apart.

Segments come out in the same columns as dnapainter_io assertions
(subject, chrom, start, end, cM, snps, match) plus provenance, so both can
be queried together.
"""
import re
from pathlib import Path

import pandas as pd

import family_filter
import identity
import textfix

_WS = re.compile(r"\s+")


_key = identity.ftdna_key     # the segment export writes a comma in a name as "-"


def read_matches(path, subject):
    m = textfix.fix_frame(pd.read_csv(path, encoding="utf-8-sig", dtype=str))
    parts = m[["First Name", "Middle Name", "Last Name"]].fillna("")
    m["match_key"] = (parts["First Name"] + " " + parts["Middle Name"] + " "
                      + parts["Last Name"]).map(_key)
    m["ambiguous"] = m.match_key.duplicated(keep=False)
    m["shared_cM"] = pd.to_numeric(m["Shared DNA"], errors="coerce")
    m["longest_cM"] = pd.to_numeric(m["Longest Block"], errors="coerce")
    m["match_date"] = pd.to_datetime(m["Match Date"], errors="coerce")
    m["x_cM"] = pd.to_numeric(m["X-Match"].str.extract(r"([\d.]+)")[0], errors="coerce")
    m["subject"] = subject
    m["source"] = Path(path).name
    return m


def read_segments(path, subject):
    s = textfix.fix_frame(pd.read_csv(path, encoding="utf-8-sig", dtype=str))
    out = pd.DataFrame(dict(
        subject=subject,
        match=s["Match Name"].map(lambda x: _WS.sub(" ", str(x)).strip()),
        match_key=s["Match Name"].map(_key),
        chrom=s["Chromosome"].str.strip(),
        start=pd.to_numeric(s["Start Location"]),
        end=pd.to_numeric(s["End Location"]),
        cM=pd.to_numeric(s["Centimorgans"]),
        snps=pd.to_numeric(s["Matching SNPs"]),
    ))
    out["source"] = Path(path).name
    return family_filter.drop_exact_duplicates(out, Path(path).name)


def _latest(d, pattern):
    # the data folder's own glob() looks across input/, output/, ... (config.py)
    files = sorted((d if hasattr(d, "layer") else Path(d)).glob(pattern))   # dates sort lexically
    if not files:
        raise FileNotFoundError(f"{d}/{pattern}")
    return files[-1]


def load_kit(data_dir, kit, subject):
    """Newest matches and segments for one kit (the two exports name their
    dates differently: 2026-11-08 vs 20261108), segments joined to match
    metadata."""
    m = read_matches(_latest(data_dir, f"{kit}_Family_Finder_Matches_*.csv"), subject)
    s = read_segments(_latest(data_dir, f"{kit}_Chromosome_Browser_Results_2*.csv"), subject)
    meta = m.drop_duplicates("match_key")[["match_key", "Full Name", "ambiguous",
                                           "shared_cM", "Matching Bucket"]]
    s = s.merge(meta, on="match_key", how="left")
    unjoined = s["Full Name"].isna().sum()
    if unjoined:
        print(f"{kit}: {unjoined} segments whose name is not in the match list")
    return m, s
