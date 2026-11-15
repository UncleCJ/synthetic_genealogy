"""Read MyHeritage "shared DNA segments" exports (Swedish UI: "Gemensamma
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

The one-to-many export covers only the matches selected, so it is a PARTIAL
list (kits.py marks it `partial`).

The match ID "D-<donor kit>-D-<match kit>" gives `match_key` ("D-<match
kit>"); without an ID column it is "name:<normalised match name>", which does
not join with ID keys.
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
        donor, key = ids[0], ids[1].str.upper()
    else:                                    # one-to-many export: names only
        donor = pd.Series(None, index=s.index, dtype=object)
        key = "name:" + s["match"].str.strip().str.lower().str.replace(r"\s+", " ", regex=True)
    out = pd.DataFrame(dict(
        subject=subject,
        donor_kit=donor, match_key=key,
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

# A MyHeritage match list (xlsx, one row per match), in the spellings seen
# (Swedish UI, 2021); the English ones are guesses, unvalidated. Values map
# onto the match-entry fields (kits.ENTRY).
LIST_COLS = {
    "DNA-matchnings-ID": "pair_id", "DNA Match ID": "pair_id", "Full Name": "match",
    "Match Date": "match_date", "Ålder": "age", "Age": "age", "Land": "country", "Country": "country",
    "Kontakta DNA-matchning": "contact_url", "Contact DNA Match": "contact_url",
    "DNA hanterat av": "managed_by", "DNA managed by": "managed_by",
    "Kontakta DNA-chef": "manager_contact_url", "Contact DNA manager": "manager_contact_url",
    "Status": "status", "Relationship Range": "relationship_range",
    "Suggested Relationship": "suggested_relationship", "Shared cM": "shared_cM",
    "Andel gemensamt DNA": "shared_pct", "Shared DNA": "shared_pct",
    "Antal gemensamma segment": "n_segments", "Shared segments": "n_segments",
    "Longest Block": "longest_cM", "Linked Relationship": "linked_relationship",
    "Granska DNA-matchningssida": "match_url", "Review DNA Match": "match_url",
    "Har släktträd": "has_tree", "Has family tree": "has_tree",
    "Antal individer i trädet": "tree_size", "People in tree": "tree_size",
    "Träd administrerad av": "tree_manager", "Tree managed by": "tree_manager",
    "Visa släktträd": "tree_url", "View family tree": "tree_url",
    "Kontakta släkträdsansvarig": "tree_contact_url", "Contact tree manager": "tree_contact_url",
    "Antal Smart Matches": "smart_matches", "Smart Matches": "smart_matches", "Email": "email",
    "Gemensamma fäderneärvda efternamn": "shared_surnames", "Shared ancestral surnames": "shared_surnames",
    "Ancestral Surnames": "ancestral_surnames", "Y-DNA Haplogroup": "y_haplogroup",
    "mtDNA Haplogroup": "mt_haplogroup", "Notes": "notes",
    "Har Theory of Family Relativity™": "tofr", "Has Theory of Family Relativity™": "tofr",
    "Matching Bucket": "bucket",
}
YES = {"ja", "yes", "true", "1"}


def _num(s):
    """"2 031,3" (Swedish thousands and decimals) or "28.0" -> float."""
    return pd.to_numeric(s.astype("string").str.replace(r"[\s\u00a0]", "", regex=True)
                         .str.replace(",", ".", regex=False), errors="coerce")


def read_match_list(path, subject):
    """A MyHeritage match list (xlsx or csv) as match entries: match_key
    ("D-<match kit>" from the pair ID, as read_segments makes it), match and
    the LIST_COLS fields present; rows without a pair ID are dropped."""
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        rows = xlsx_rows(path)
        d = pd.DataFrame(rows[1:], columns=[str(c).strip() for c in rows[0]] + [
            f"_{i}" for i in range(len(rows[0]), max(map(len, rows)))]) if rows else pd.DataFrame()
    else:
        d = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    d = textfix.fix_frame(d.astype("string")).rename(columns=lambda c: LIST_COLS.get(c, c))
    d = d.loc[:, [c for c in dict.fromkeys(LIST_COLS.values()) if c in d]]
    ids = d.pair_id.astype("string").str.strip().str.extract(PAIR) if "pair_id" in d else None
    if ids is None or ids[1].isna().all():
        raise ValueError(f"{path.name}: no DNA match IDs: not a MyHeritage match list")
    d["match_key"] = ids[1].str.upper()
    d = d[d.match_key.notna()].drop(columns="pair_id")
    for c in ("shared_cM", "shared_pct", "n_segments", "longest_cM", "tree_size", "smart_matches"):
        if c in d:
            d[c] = _num(d[c])
    for c in ("has_tree", "tofr"):
        if c in d:
            d[c] = d[c].str.strip().str.lower().isin(YES)
    if "match_date" in d:
        d["match_date"] = pd.to_datetime(d.match_date, errors="coerce")
    d["subject"] = subject
    d["source"] = path.name
    return d.reset_index(drop=True)


def xlsx_rows(path, sheet=1):
    """The cells of one worksheet of an xlsx file as lists of strings, read
    from the zip without a spreadsheet library (shared and inline strings,
    plain values; no dates or formulas worked out)."""
    import zipfile
    import xml.etree.ElementTree as ET
    m = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(path)
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        ss = ["".join(t.text or "" for t in si.iter(m + "t"))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(m + "si")]

    def col(ref):
        n = 0
        for ch in "".join(c for c in ref if c.isalpha()):
            n = n * 26 + ord(ch.upper()) - 64
        return n - 1
    rows = []
    for row in ET.fromstring(z.read(f"xl/worksheets/sheet{sheet}.xml")).iter(m + "row"):
        cells = {}
        for c in row.iter(m + "c"):
            v, t = c.find(m + "v"), c.get("t")
            if t == "s" and v is not None:
                val = ss[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(m + "t"))
            else:
                val = v.text if v is not None else ""
            cells[col(c.get("r"))] = val
        rows.append([cells.get(i, "") for i in range(max(cells, default=-1) + 1)])
    return rows


def read_triangulated(path):
    """Segments a one-to-many download lists as shared by the donor and
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
