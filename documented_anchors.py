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
WEIGHT = 10           # vote weight relative to a DNA Painter cluster segment


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


if __name__ == "__main__":
    cfg = config.load()
    df = build(cfg)
    out = cfg["data_dir"] / "assertions_documented.csv"
    df.to_csv(out, index=False)
    print(df.groupby(["subject", "lineage", "rule"]).size() if len(df) else "no anchors", "->", out)
