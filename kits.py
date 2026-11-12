"""
Build kit dicts (subject, sex, platform, date, segs, keys, meta) from the
[[segment_exports]] in family.toml, for match_placement and friends.
"""
import re

import pandas as pd

import family_filter
import ftdna_io
import match_placement as mp
import myheritage_io as mh


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
        if "earlier" in e:   # an older full export of the same kit: its match
            old = e["earlier"]   # keys predate it (see match_placement.phase_child)
            read = mh.read_segments if plat == "MyHeritage" else ftdna_io.read_segments
            k["old_keys"] = set(read(D / old["file"], subj).match_key)
            k["old_date"] = pd.Timestamp(old["date"])
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
        import icw_io
        ids, names, lo, hi = icw_io.autocluster_window(D / w["file"])
        g = out.get(w.get("group", w["platform"]))
        if g and g["mother"] is not None:
            g["mother"]["window"] = dict(ids=ids, names=names, min_cm=w.get("min_cm", lo),
                                         max_cm=w.get("max_cm", hi), date=pd.Timestamp(w["date"]),
                                         source=w["file"])
    return out
