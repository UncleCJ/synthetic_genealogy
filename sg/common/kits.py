"""
Build kit dicts (subject, sex, platform, date, segs, keys, meta) from the
[[segment_exports]] in family.toml, for match_placement and friends.
"""
import re
from pathlib import Path

import pandas as pd

from sg.common import family_filter
from sg.readers import ftdna_io
from sg.genetics import match_placement as mp
from sg.readers import myheritage_io as mh


def _family(cfg):
    return family_filter.from_config(cfg)


def ftdna_kit(cfg, kit, subject):
    D = cfg["data_dir"]
    m, s = ftdna_io.load_kit(D, kit, subject)
    meta = m.rename(columns={"Full Name": "match"})[
        ["match_key", "match", "shared_cM", "longest_cM", "Matching Bucket",
         "Relationship Range", "Linked Relationship", "match_date",
         "Ancestral Surnames", "x_cM"]]
    date = pd.Timestamp(re.search(r"(\d{4}-\d\d-\d\d)", m.source.iloc[0]).group(1))
    return dict(subject=subject, platform="FTDNA", date=date,
                segs=mp.drop_family(s, _family(cfg)), keys=set(m.match_key),
                meta=meta, kit=kit)


def segs_only_kit(cfg, segs, subject, platform, date):
    segs = mp.drop_family(segs, _family(cfg))
    return dict(subject=subject, platform=platform, date=pd.Timestamp(date),
                segs=segs, keys=set(segs.match_key),
                meta=mh.matches_from_segments(segs))


def load(cfg):
    """{group: {"children": [kit, ...], "mother": kit or None}}; group is the
    platform, or "<platform> (selection)" for partial exports."""
    D = cfg["data_dir"]
    out = {}
    for e in cfg.get("segment_exports", []):
        subj, plat = e["subject"], e["platform"]
        if plat == "FTDNA" and "kit" in e:
            k = ftdna_kit(cfg, e["kit"], subj)
        elif plat == "FTDNA":
            k = segs_only_kit(cfg, ftdna_io.read_segments(D / e["file"], subj),
                              subj, plat, e["date"])
        elif plat == "MyHeritage":
            k = segs_only_kit(cfg, mh.read_segments(D / e["file"], subj),
                              subj, plat, e["date"])
        else:
            raise ValueError(f"unknown platform {plat}")
        # when each match was first seen (match_placement.first_seen): this
        # accession, an older one of the same kit, FTDNA's match date
        seen = dict.fromkeys(k["keys"], k["date"])
        if "earlier" in e:
            old = e["earlier"]
            read = mh.read_segments if plat == "MyHeritage" else ftdna_io.read_segments
            d = pd.Timestamp(old["date"])
            seen.update(dict.fromkeys(set(read(D / old["file"], subj).match_key), d))
        if "match_date" in k["meta"]:
            for key, d in k["meta"].dropna(subset=["match_date"]).groupby("match_key").match_date.min().items():
                seen[key] = min(seen.get(key, d), d)
        k["first_seen"] = seen
        k["sex"] = cfg["people"][subj].get("sex")
        k["partial"] = e.get("partial", False)   # selected matches only
        # a selection where the same matches were looked up for every kit in
        # the group: absence from it counts (match_placement.phase_child)
        k["same_selection"] = e.get("same_selection", False)
        # partial exports form their own group: they are not a match list
        group = e.get("group", plat + (" (selection)" if k["partial"] else ""))
        p = out.setdefault(group, {"children": [], "mother": None})
        if subj == cfg["mother"]:
            p["mother"] = k
        else:
            p["children"].append(k)
    # A mother's match window from an AutoCluster run on a platform where her
    # segment export is older (see match_placement.phase_child). In
    # family.toml:  [[mother_window]]  platform = "MyHeritage",
    # file = "<AutoCluster CSV>" (its HTML beside it gives min_cm/max_cm),
    # date = "<run date>"
    for w in cfg.get("mother_window", []):
        from sg.readers import icw_io
        ids, names, lo, hi = icw_io.autocluster_window(D / w["file"])
        g = out.get(w.get("group", w["platform"]))
        if g and g["mother"] is not None:
            g["mother"]["window"] = dict(ids=ids, names=names, min_cm=w.get("min_cm", lo),
                                         max_cm=w.get("max_cm", hi), date=pd.Timestamp(w["date"]),
                                         source=w["file"])
    return out


# What a match list says about a match, beyond its segments: the superset of
# the vendors' fields (FTDNA match lists, MyHeritage match lists,
# AutoCluster runs). (field, label, group, meaning); a source fills what it has.
ENTRY = [
    ("match_date", "Matched", "match", "When the vendor first listed them"),
    ("status", "Status", "match", "The vendor's mark on the match (MyHeritage: new, viewed, ...)"),
    ("relationship_range", "Relationship range", "match", "The vendor's estimate from the shared DNA"),
    ("suggested_relationship", "Suggested relationship", "match", "The vendor's most likely relationship"),
    ("linked_relationship", "Linked relationship", "match", "The relationship from where someone linked them in the vendor's tree"),
    ("bucket", "Bucket", "match", "FTDNA's side: paternal, maternal or both, from linked relatives"),
    ("smart_matches", "Smart Matches", "match", "MyHeritage: people in their tree that match people in ours"),
    ("tofr", "Theory of Family Relativity", "match", "MyHeritage offers a theory of how you are related"),
    ("cluster", "Cluster", "match", "Their AutoCluster cluster (0: none)"),
    ("shared_cM", "Shared cM", "dna", "The vendor's total"),
    ("shared_pct", "Shared %", "dna", "Share of the genome, as the vendor gives it"),
    ("n_segments", "Segments", "dna", "Shared segments, as the vendor counts them"),
    ("longest_cM", "Longest cM", "dna", "The longest shared segment"),
    ("x_cM", "X cM", "dna", "Shared on the X chromosome"),
    ("y_haplogroup", "Y haplogroup", "dna", "Their direct paternal line"),
    ("mt_haplogroup", "mt haplogroup", "dna", "Their direct maternal line"),
    ("age", "Age", "person", "Their age band"),
    ("country", "Country", "person", "Where they live"),
    ("managed_by", "Kit managed by", "person", "Who manages the kit, if not they"),
    ("email", "Email", "contact", "Their address for matches (FTDNA)"),
    ("contact_url", "Contact", "contact", "Write to them at the vendor"),
    ("manager_contact_url", "Contact the kit manager", "contact", "Write to whoever manages the kit"),
    ("match_url", "Match page", "contact", "The vendor's page on this match"),
    ("has_tree", "Has a tree", "tree", "They have a family tree at the vendor"),
    ("tree_size", "Tree size", "tree", "People in their tree"),
    ("tree_manager", "Tree managed by", "tree", "Who keeps their tree"),
    ("tree_url", "Their tree", "tree", "Their tree at the vendor"),
    ("tree_contact_url", "Contact the tree manager", "tree", "Write to whoever keeps their tree"),
    ("shared_surnames", "Shared surnames", "tree", "Surnames in both trees (MyHeritage)"),
    ("ancestral_surnames", "Ancestral surnames", "tree", "Surnames they list for their ancestors"),
    ("notes", "Notes", "tree", "Notes kept at the vendor on this match"),
]


def match_entries(cfg):
    """Match-list entries, one row per (subject, platform group, match_key),
    with the ENTRY fields any source gives, plus match, sources and
    list_date. Sources: FTDNA match lists of [[segment_exports]] kits, a
    match list named by `match_list = "<file>"` on a [[segment_exports]]
    entry (FTDNA or MyHeritage; dated by `match_list_date`, else `date`),
    and AutoCluster runs in [[icw]]. Where several give a field, the newest
    list wins. The nuclear family is left out, as from the segments."""
    from sg.readers import icw_io
    D = cfg["data_dir"]
    parts = []
    for e in cfg.get("segment_exports", []):
        group = e.get("group", e["platform"] + (" (selection)" if e.get("partial") else ""))
        if e["platform"] == "FTDNA" and "kit" in e:
            f = ftdna_io._latest(D, f"{e['kit']}_Family_Finder_Matches_*.csv")
            day = re.search(r"(\d{4}-\d\d-\d\d)", f.name)
            parts.append(ftdna_io.entries(ftdna_io.read_matches(f, e["subject"])).assign(
                platform=group, list_date=pd.Timestamp(day.group(1)) if day else pd.NaT))
        if e.get("match_list"):
            f = D / e["match_list"]
            read = (lambda f, s: ftdna_io.entries(ftdna_io.read_matches(f, s))) if e["platform"] == "FTDNA" \
                else mh.read_match_list
            parts.append(read(f, e["subject"]).assign(
                platform=group, list_date=pd.Timestamp(str(e.get("match_list_date") or e.get("date")))))
    for x in cfg.get("icw", []):
        if x["kind"] != "autocluster":
            continue
        nodes, _ = icw_io.autocluster_matrix(D / x["file"], x["subject"], x.get("platform", "MyHeritage"))
        day = pd.to_datetime(re.search(r"- (\w+ \d\d? \d{4})\.", str(x["file"])).group(1)
                             if re.search(r"- (\w+ \d\d? \d{4})\.", str(x["file"])) else None, errors="coerce")
        parts.append(nodes.rename(columns={"cM": "shared_cM"}).assign(
            platform=x.get("group", x.get("platform", "MyHeritage")), list_date=day, source=Path(x["file"]).name))
    cols = ["subject", "platform", "match_key", "match", "list_date", "source"] + [f for f, *_ in ENTRY]
    if not parts:
        return pd.DataFrame(columns=cols)
    e = pd.concat(parts, ignore_index=True)
    e = e.mask(e.map(lambda x: isinstance(x, str) and not x.strip()))     # a blank cell says nothing
    e = e[e.match_key.notna() & e.match.notna()]
    e = e[~_family(cfg).mask(e)]
    e = e.reindex(columns=cols).sort_values("list_date", ascending=False, na_position="last")
    keys = ["subject", "platform", "match_key"]
    src = e.groupby(keys).source.agg(lambda s: "; ".join(dict.fromkeys(s.dropna().astype(str))))
    out = e.drop(columns="source").groupby(keys, sort=False).first()      # first non-null, newest list first
    return out.join(src.rename("sources")).reset_index()
