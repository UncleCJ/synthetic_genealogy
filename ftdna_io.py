"""
Read FamilyTreeDNA Family Finder exports: the match list
("<kit>_Family_Finder_Matches_<date>.csv") and the chromosome browser
segments ("<kit>_Chromosome_Browser_Results_<date>.csv").

The segment file names a match only by "First Middle Last" with irregular
spacing; the match list has the parts separately. Both are whitespace-
normalised into `match_key`. Names that occur twice in a match list are
kept but flagged `ambiguous`, since their segments cannot be told apart.

Both readers also take the tables on FTDNA's web pages, copied into a
spreadsheet and saved as CSV (one file per tab): a match list (or one
filtered "in common with" a match) with one "Name" column, and the
chromosome browser's table. Their columns are mapped onto the export's
(`_web_columns`), so a pasted file comes out like an exported one, minus
what the page does not show (match date, bucket). Pasted names carry a
title ("Mr. "), as some exported names do (in "Full Name", or as the
first name); the key drops it everywhere, so lists and segments join.

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


# web page column -> export column; an older match export says "Shared cM"
_WEB = {"Name": "Full Name", "Match Name": "Match Name", "Shared cM": "Shared DNA",
        "X Match": "X-Match", "Y Haplog": "Y-DNA Haplogroup",
        "mt Haplog": "mtDNA Haplogroup", "Centimorgans(cM)": "Centimorgans"}
_TITLE = re.compile(r"^(mr|mrs|ms|miss|dr)\.\s+", re.I)
_NUMERIC = ["Shared DNA", "Longest Block", "Start Location", "End Location",
            "Centimorgans", "Matching SNPs"]


def _web_columns(df):
    """A pasted web table in the export's columns and cell formats."""
    df = df.rename(columns={c: _WEB[c.strip()] for c in df.columns if c.strip() in _WEB})
    df = df.replace({"\u2014": None, "\u2013": None})        # the page's dash for "none"
    for c in _NUMERIC:
        if c in df:
            df[c] = df[c].str.replace(",", "", regex=False).str.strip()
    for c, junk in (("Relationship Range", r"\s*Link on Family Tree\s*"),
                    ("Ancestral Surnames", r"\s*View Details\s*$")):
        if c in df:
            df[c] = df[c].str.replace(junk, "", regex=True).str.strip()
    return df


def read_matches(path, subject):
    m = _web_columns(textfix.fix_frame(pd.read_csv(path, encoding="utf-8-sig", dtype=str)))
    if "First Name" in m:
        parts = m[["First Name", "Middle Name", "Last Name"]].fillna("")
        names = parts["First Name"] + " " + parts["Middle Name"] + " " + parts["Last Name"]
    else:                                     # pasted: one name column
        names = m["Full Name"]
    m["match_key"] = names.map(lambda x: _key(_TITLE.sub("", str(x).strip())))
    for c in ("Match Date", "X-Match", "Matching Bucket", "Linked Relationship"):
        if c not in m:
            m[c] = None
    m["ambiguous"] = m.match_key.duplicated(keep=False)
    m["shared_cM"] = pd.to_numeric(m["Shared DNA"], errors="coerce")
    m["longest_cM"] = pd.to_numeric(m["Longest Block"], errors="coerce")
    m["match_date"] = pd.to_datetime(m["Match Date"], errors="coerce")
    m["x_cM"] = pd.to_numeric(m["X-Match"].astype("string").str.extract(r"([\d.]+)")[0], errors="coerce")
    m["subject"] = subject
    m["source"] = Path(path).name
    return m


def read_segments(path, subject):
    s = _web_columns(textfix.fix_frame(pd.read_csv(path, encoding="utf-8-sig", dtype=str)))
    name = s["Match Name"].map(lambda x: _TITLE.sub("", _WS.sub(" ", str(x)).strip()))
    out = pd.DataFrame(dict(
        subject=subject,
        match=name,
        match_key=name.map(_key),
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
