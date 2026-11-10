"""
Read MyHeritage "shared DNA segments" exports (Swedish UI: "Gemensamma
DNA-matchningssegment"), in the column spellings seen so far:

  2020 (sv): DNA-matchnings-ID, Namn, Matchnamn, Kromosom, Starta plats,
             Avsluta plats, Börja RSID, Avsluta RSID, Centimorgan, Snp's
  2021 (sv): ... Namn på matchning, ... Startplats, ... SNPs
  English:   DNA Match ID, Name, Match name, Chromosome, Start Location,
             End Location, Start RSID, End RSID, Centimorgans, SNPs

  one-to-many (en, 2026): Name, Match Name, Chromosome, Start Location,
             End Location, Start RSID, End RSID, Centimorgans, SNPs
             (no match ID column; rows with Match Name "All selected DNA
             Matches" are triangulated segments, see read_triangulated)

MyHeritage removed the all-matches export in October 2023. What remains is
"Download shared DNA info" in the one-to-many chromosome browser, covering
only the matches selected there: a PARTIAL list, so the absence of a match
from it means nothing (kits.py marks it `partial`).

The match ID is "D-<tester kit>-D-<match kit>", so the second half
identifies the match across all of a family's kits, independent of name
spelling. That becomes `match_key`. Without an ID column, `match_key` is
"name:<normalised match name>"; such keys do not join with ID keys.
"""
from pathlib import Path

import pandas as pd

import family_filter
import textfix
import identity

COLS = {
    "DNA-matchnings-ID": "pair_id", "DNA Match ID": "pair_id",
    "Namn": "name", "Name": "name",
    "Matchnamn": "match", "Namn på matchning": "match", "Match name": "match",
    "Match Name": "match",
    "Kromosom": "chrom", "Chromosome": "chrom",
    "Starta plats": "start", "Startplats": "start", "Start Location": "start",
    "Avsluta plats": "end", "End Location": "end",
    "Börja RSID": "start_rsid", "Start RSID": "start_rsid",
    "Avsluta RSID": "end_rsid", "End RSID": "end_rsid",
    "Centimorgan": "cM", "Centimorgans": "cM",
    "Snp's": "snps", "SNPs": "snps",
}
PAIR = identity.MH_PAIR      # "D-<donor kit>-D-<match kit>"


def read_segments(path, subject):
    s = textfix.fix_frame(pd.read_csv(path, encoding="utf-8-sig", dtype=str))
    s = s.rename(columns={c: COLS.get(c.strip(), c) for c in s.columns})
    # hand-merged downloads can repeat the header row mid-file
    s = s[pd.to_numeric(s.start, errors="coerce").notna()]
    # one-to-many: rows shared with ALL selected matches (triangulated) are
    # not a person; read them with read_triangulated()
    s = s[s["match"].str.strip() != TRIANGULATED]
    if "pair_id" in s:
        ids = s.pair_id.str.extract(PAIR)
        tester, key = ids[0], ids[1].str.upper()
    else:                                    # one-to-many export: names only
        tester = pd.Series(None, index=s.index, dtype=object)
        key = "name:" + s["match"].str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    out = pd.DataFrame(dict(
        subject=subject,
        tester_kit=tester, match_key=key,
        match=s["match"].str.strip(),
        chrom=s.chrom.str.strip(),
        start=pd.to_numeric(s.start), end=pd.to_numeric(s.end),
        cM=pd.to_numeric(s.cM), snps=pd.to_numeric(s.snps),
        start_rsid=s.get("start_rsid"), end_rsid=s.get("end_rsid"),
    ))
    out["source"] = Path(path).name
    out = family_filter.drop_exact_duplicates(out, Path(path).name)
    bad = out.match_key.isna().sum()
    if bad:
        print(f"{Path(path).name}: {bad} rows without a parsable match ID")
    return out


TRIANGULATED = "All selected DNA Matches"


def read_triangulated(path):
    """Segments a one-to-many download lists as shared by the tester and
    every selected match (MyHeritage's triangulation), as chrom/start/end/cM."""
    s = textfix.fix_frame(pd.read_csv(path, encoding="utf-8-sig", dtype=str))
    s = s.rename(columns={c: COLS.get(c.strip(), c) for c in s.columns})
    s = s[s["match"].str.strip() == TRIANGULATED]
    return pd.DataFrame(dict(chrom=s.chrom.str.strip(), start=pd.to_numeric(s.start),
                             end=pd.to_numeric(s.end), cM=pd.to_numeric(s.cM)))


def matches_from_segments(segs):
    """MyHeritage segment exports carry no match list; derive one."""
    g = segs.groupby("match_key")
    return pd.DataFrame(dict(match=g["match"].first(), shared_cM=g.cM.sum(),
                             longest_cM=g.cM.max(), n_segments=g.size())).reset_index()
