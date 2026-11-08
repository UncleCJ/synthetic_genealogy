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

The relatives come from [[anchors]] in family.toml; only FTDNA exports
are used, since anchors are identified by FTDNA match name.
"""
import pandas as pd

import config
import kits
import match_placement as mp

MIN_CM = 10
WEIGHT = 10           # vote weight relative to a DNA Painter cluster segment


def build(cfg):
    ft = kits.load(cfg).get("FTDNA", {"children": [], "mother": None})
    rows = []
    for a in cfg.get("anchors", []):
        mum = ft["mother"]
        if mum is None or mum.get("kit") != a["mother_kit"]:
            raise SystemExit(f"anchor {a['match_key']}: no FTDNA export for kit {a['mother_kit']}")
        rel = mum["segs"][(mum["segs"].match_key == a["match_key"]) & (mum["segs"].chrom != "X")]
        new = []
        for child in ft["children"]:
            c = child["segs"][child["segs"].match_key == a["match_key"]]
            for s in rel.itertuples():
                cc = c[c.chrom == s.chrom]
                ov = mp._overlap(s.start, s.end, cc.start.to_numpy(), cc.end.to_numpy())
                for t, o in zip(cc.itertuples(), ov):
                    if o > 0:
                        new.append(dict(subject=child["subject"], chrom=s.chrom,
                                        start=max(s.start, t.start), end=min(s.end, t.end),
                                        lineage=a["lineage"], rule="child shares it"))
                if (not len(cc) or ov.max() == 0) and s.cM >= MIN_CM:
                    new.append(dict(subject=child["subject"], chrom=s.chrom,
                                    start=s.start, end=s.end,
                                    lineage=mp.OTHER[a["lineage"]], rule="child lacks it"))
        for r in new:
            r.update(match=a["match_key"], kind="lineage", weight=WEIGHT,
                     evidence=a.get("evidence", ""), asserted_by="documented_anchors.py",
                     source=f"{a['mother_kit']} + children's FTDNA segments")
        rows += new
    df = pd.DataFrame(rows)
    if len(df):
        df["assertion_id"] = [f"anchor:{r.match}:{r.subject}:{r.chrom}:{r.start}"
                              for r in df.itertuples()]
    return df


if __name__ == "__main__":
    cfg = config.load()
    df = build(cfg)
    out = cfg["data_dir"] / "assertions_documented.csv"
    df.to_csv(out, index=False)
    print(df.groupby(["subject", "lineage", "rule"]).size() if len(df) else "no anchors", "->", out)
