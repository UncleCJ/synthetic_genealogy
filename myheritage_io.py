"""
Read MyHeritage "shared DNA segments" exports (Swedish UI: "Gemensamma
DNA-matchningssegment"), in the column spellings seen so far:

  2020 (sv): DNA-matchnings-ID, Namn, Matchnamn, Kromosom, Starta plats,
             Avsluta plats, Börja RSID, Avsluta RSID, Centimorgan, Snp's
  2021 (sv): ... Namn på matchning, ... Startplats, ... SNPs
  English:   DNA Match ID, Name, Match name, Chromosome, Start Location,
             End Location, Start RSID, End RSID, Centimorgans, SNPs

MyHeritage removed the all-matches export in October 2023; these files
predate that. The per-selection "Download shared DNA info" from the
one-to-many chromosome browser lists triangulated segments first and is
not handled here.

The match ID is "D-<tester kit>-D-<match kit>", so the second half
identifies the match across all of a family's kits, independent of name
spelling. That becomes `match_key`.
"""
import re
from pathlib import Path

import pandas as pd

COLS = {
    "DNA-matchnings-ID": "pair_id", "DNA Match ID": "pair_id",
    "Namn": "name", "Name": "name",
    "Matchnamn": "match", "Namn på matchning": "match", "Match name": "match",
    "Kromosom": "chrom", "Chromosome": "chrom",
    "Starta plats": "start", "Startplats": "start", "Start Location": "start",
    "Avsluta plats": "end", "End Location": "end",
    "Börja RSID": "start_rsid", "Start RSID": "start_rsid",
    "Avsluta RSID": "end_rsid", "End RSID": "end_rsid",
    "Centimorgan": "cM", "Centimorgans": "cM",
    "Snp's": "snps", "SNPs": "snps",
}
# kit IDs are UUID-shaped, but not always hex (e.g. D-83V49427-5Q6G-...)
PAIR = re.compile(r"^(D-[0-9A-Z-]{36})-(D-[0-9A-Z-]{36})$", re.I)


def read_segments(path, subject):
    s = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    s = s.rename(columns={c: COLS.get(c.strip(), c) for c in s.columns})
    ids = s.pair_id.str.extract(PAIR)
    out = pd.DataFrame(dict(
        subject=subject,
        tester_kit=ids[0], match_key=ids[1].str.upper(),
        match=s["match"].str.strip(),
        chrom=s.chrom.str.strip(),
        start=pd.to_numeric(s.start), end=pd.to_numeric(s.end),
        cM=pd.to_numeric(s.cM), snps=pd.to_numeric(s.snps),
        start_rsid=s.get("start_rsid"), end_rsid=s.get("end_rsid"),
    ))
    out["source"] = Path(path).name
    bad = out.match_key.isna().sum()
    if bad:
        print(f"{Path(path).name}: {bad} rows without a parsable match ID")
    return out


def matches_from_segments(segs):
    """MyHeritage segment exports carry no match list; derive one."""
    g = segs.groupby("match_key")
    return pd.DataFrame(dict(match=g["match"].first(), shared_cM=g.cM.sum(),
                             longest_cM=g.cM.max(), n_segments=g.size())).reset_index()
