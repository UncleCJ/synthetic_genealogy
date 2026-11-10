"""
Turn documented relatives of a parent into strong lineage assertions for
the children, for phasing_labels to weigh above cluster paintings.

A relative whose tree path is documented on one side of the mother
(e.g. her paternal first cousin -> MF) shares segments with her on that
one copy. For each such segment and each child with a full match list:
  * the child shares it  -> child's maternal copy there is that grandparent
  * the child lacks it   -> the other one (only for segments >= MIN_CM,
                            so detection is not in doubt)

Caveat: a relative related to BOTH of the mother's parents breaks the rule;
the share should then be unusually high for the documented relationship.

The relatives come from [[anchors]] in family.toml. With `mother_kit`
they are judged against the mother's segments; without it (a relative on
the father's side, whose kit we lack) among the siblings: where one sibling
shares a long segment with the relative and another lacks it, the second
carries the other grandparent there.
"""
import pandas as pd

import config
import kits
import match_placement as mp

MIN_CM = 10
WEIGHT = 10           # vote weight of a hand-documented anchor (per SNP)
TREE_WEIGHT = 3       # a confirmed [[identity]] link in the tree
NAME_WEIGHT = 1       # a match joined to a unique tree person by name only
TREE_MIN_CM = 20      # name joins below this total are too often wrong


OTHER = {"FF": "FM", "FM": "FF", "MF": "MM", "MM": "MF"}


def _claims(children, ref, key, lineage, by_mother):
    """Children's segments with `key` -> lineage; reference segments a child
    lacks entirely (>= MIN_CM) -> the other grandparent. `ref` is the
    mother's segments (by_mother) or the union of the siblings' own."""
    out = []
    for child in children:
        c = child["segs"][child["segs"].match_key == key]
        for t in c[c.chrom != "X"].itertuples():
            if by_mother:      # only what lies inside the mother's segments
                r = ref[ref.chrom == t.chrom]
                ov = mp._overlap(t.start, t.end, r.start.to_numpy(), r.end.to_numpy())
                if not len(r) or ov.max() == 0:
                    continue
            out.append(dict(subject=child["subject"], chrom=t.chrom, start=t.start,
                            end=t.end, lineage=lineage, rule="child shares it"))
        for s in ref[(ref.chrom != "X") & (ref.cM >= MIN_CM)].itertuples():
            cc = c[c.chrom == s.chrom]
            if not len(cc) or mp._overlap(s.start, s.end, cc.start.to_numpy(),
                                          cc.end.to_numpy()).max() == 0:
                out.append(dict(subject=child["subject"], chrom=s.chrom, start=s.start,
                                end=s.end, lineage=OTHER[lineage],
                                rule="child lacks it" + ("" if by_mother else
                                                         " (a sibling shares it)")))
    return out


def build(cfg):
    """[[anchors]] with `mother_kit`: judged against the mother's segments
    (FTDNA). Without it (e.g. a paternal-side relative, no father kit):
    judged among the siblings of `group`, using only exports that list the
    match at all, e.g. one-to-many selections that include it."""
    groups = kits.load(cfg)
    rows = []
    for a in cfg.get("anchors", []):
        key, lineage = a["match_key"], a["lineage"]
        g = groups.get(a.get("group", "FTDNA"), {"children": [], "mother": None})
        if "mother_kit" in a:
            mum = g["mother"]
            if mum is None or mum.get("kit") != a["mother_kit"]:
                raise SystemExit(f"anchor {key}: no export for mother kit {a['mother_kit']}")
            ref = mum["segs"][mum["segs"].match_key == key]
            new = _claims(g["children"], ref, key, lineage, by_mother=True)
            src = f"{a['mother_kit']} + children's segments ({a.get('group', 'FTDNA')})"
        else:
            kids = [c for c in g["children"] if key in c["keys"]]
            ref = pd.concat([c["segs"][c["segs"].match_key == key] for c in kids])
            # merge overlapping sibling segments into one reference stretch
            ref = ref.sort_values(["chrom", "start"])
            new = _claims(kids, ref, key, lineage, by_mother=False)
            src = f"siblings' segments ({a.get('group')}): " + ", ".join(c["subject"] for c in kids)
        for r in new:
            r.update(match=key, kind="lineage", weight=a.get("weight", WEIGHT),
                     evidence=a.get("evidence", ""), asserted_by="documented_anchors.py",
                     source=src)
        rows += new
    df = pd.DataFrame(rows).drop_duplicates(["subject", "chrom", "start", "end", "lineage", "match"])
    if len(df):
        df["assertion_id"] = [f"anchor:{r.match}:{r.subject}:{r.chrom}:{r.start}:{r.lineage}"
                              for r in df.itertuples()]
    return df


def tree_claims(cfg, groups=None):
    """Lineage claims from the tree: each match that the tree joins to one
    person whose shared DNA must come through one grandparent (the `via`
    code has length >= 2) votes like an anchor, weighted by how the join
    was made. Judged against the mother's segments where her export lists
    the match, else among the siblings that list it."""
    import gedcom_io
    try:
        tree, proband = gedcom_io.load(cfg)
    except (KeyError, FileNotFoundError) as e:
        print("tree anchors skipped:", e)
        return pd.DataFrame()
    groups = groups or kits.load(cfg)
    identities = gedcom_io.load_identities(cfg)
    hand = {a["match_key"] for a in cfg.get("anchors", [])}
    rows = []
    for gname, g in groups.items():
        kids, mum = g["children"], g["mother"]
        segs = pd.concat([k["segs"] for k in kids + ([mum] if mum else [])])
        tot = segs[segs.chrom != "X"].groupby("match_key").agg(match=("match", "first"),
                                                              cM=("cM", "sum"))
        tot = tot[~tot.index.isin(hand)]
        hits = gedcom_io.matches_in_tree(tree, proband, tot.reset_index())
        if not len(hits):
            continue
        for name, h in hits.groupby("match"):
            if h.person.nunique() != 1:                  # ambiguous name
                continue
            codes = [c for c in str(h.mrca_code.iloc[0]).split() if c]
            if not codes:
                continue
            pre = codes[0] if len(codes) == 1 else _prefix(codes)
            if len(pre) < 2:                             # couple at grandparent level
                continue
            lineage = pre[:2]
            confirmed = gedcom_io._norm(name) in identities
            key = tot.index[tot.match == name][0]
            if not confirmed and tot.loc[key, "cM"] < TREE_MIN_CM:
                continue
            if mum is not None and lineage[0] == "M" and key in mum["keys"]:
                ref = mum["segs"][mum["segs"].match_key == key]
                new = _claims(kids, ref, key, lineage, by_mother=True)
                src = f"mother's and children's segments ({gname})"
            else:
                have = [c for c in kids if key in c["keys"]]
                if not have:
                    continue
                ref = pd.concat([c["segs"][c["segs"].match_key == key] for c in have])
                new = _claims(have, ref.sort_values(["chrom", "start"]), key, lineage,
                              by_mother=False)
                src = f"siblings' segments ({gname}): " + ", ".join(c["subject"] for c in have)
            how = "confirmed identity" if confirmed else "name join"
            for r in new:
                r.update(match=name, match_key=key, kind="lineage",
                         weight=TREE_WEIGHT if confirmed else NAME_WEIGHT,
                         evidence=f"tree ({how}): {h.person.iloc[0]}, MRCA {h.mrca.iloc[0]} "
                                  f"[{h.mrca_code.iloc[0]}]",
                         asserted_by="documented_anchors.tree_claims", source=src)
            rows += new
    df = pd.DataFrame(rows)
    if len(df):
        df = df.drop_duplicates(["subject", "chrom", "start", "end", "lineage", "match"])
        df["assertion_id"] = [f"tree:{r.match_key}:{r.subject}:{r.chrom}:{r.start}:{r.lineage}"
                              for r in df.itertuples()]
    return df


def _prefix(codes):
    out = ""
    for chars in zip(*codes):
        if len(set(chars)) > 1:
            break
        out += chars[0]
    return out


if __name__ == "__main__":
    cfg = config.load()
    sources = config.anchor_sources(cfg)
    df = build(cfg)
    out = cfg["data_dir"] / "assertions_documented.csv"
    df.to_csv(out, index=False)
    print(df.groupby(["subject", "lineage", "rule"]).size() if len(df) else "no anchors", "->", out)
    if "tree" in sources:
        t = tree_claims(cfg)
        out = cfg["data_dir"] / "assertions_tree.csv"
        t.to_csv(out, index=False)
        if len(t):
            t["how"] = t.evidence.str.extract(r"tree \(([^)]+)\)")[0]
            print(f"tree anchors: {t.match.nunique()} matches, {len(t)} claims ->", out)
            print(t.groupby(["how", "lineage"]).match.nunique().unstack(fill_value=0).to_string())
