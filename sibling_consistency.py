"""Check the grandparent painting against matches shared by siblings.

Two full siblings sharing a segment with one match, on the same parent's side
with (nearly) the same ends, carry the same grandparent copy there; each
disagreeing pair is listed with the painted blocks and their informative-SNP
counts. `correct()` writes a corrected painting, relabelling a block to the
other siblings' grandparent when at least `MIN_PAIRS` disagreeing pairs cover
it, none agree with it, and it has fewer than `MAX_SNPS` informative SNPs.
Sketch: thresholds are judgement calls, not calibrated.

How it works: docs/genetics.md, "Placement".
"""
from collections import defaultdict

import numpy as np
import pandas as pd

import outputs

import match_placement as mp
from intervals import jaccard

MIN_CM, MIN_JACCARD = 10.0, 0.9
MIN_PAIRS, MAX_SNPS = 2, 1500


def shared_pairs(segs, children):
    """Same match, same platform, two siblings, near-identical ends."""
    s = segs[segs.subject.isin(children) & (segs.chrom.astype(str) != "X") & (segs.cM >= MIN_CM)]
    out = []
    for (plat, key, chrom), g in s.groupby(["platform", "match_key", "chrom"]):
        if g.subject.nunique() < 2:
            continue
        r = g.to_dict("records")
        for i in range(len(r)):
            for j in range(i + 1, len(r)):
                a, b = r[i], r[j]
                if a["subject"] == b["subject"]:
                    continue
                if jaccard(a["start"], a["end"], b["start"], b["end"]) < MIN_JACCARD:
                    continue
                pa, pb = str(a.get("parent") or ""), str(b.get("parent") or "")
                pa = "" if pa == "nan" else pa
                pb = "" if pb == "nan" else pb
                if pa and pb and pa != pb:
                    continue
                parent = pa or pb
                if not parent:
                    continue
                out.append(dict(platform=plat, match_key=key, match=a["match"], chrom=str(chrom),
                                start=max(a["start"], b["start"]), end=min(a["end"], b["end"]),
                                cM=min(a["cM"], b["cM"]), parent=parent,
                                sib_a=a["subject"], sib_b=b["subject"]))
    return pd.DataFrame(out)


def ibd_intervals(pairs, parent_side={"F": "A", "M": "B"}):
    """Merge shared pairs into (sib_a, sib_b, side, chrom, start, end)
    intervals for visual_phasing.run(ibd=...). With the tested mother in the
    model as side B, the father's side is A."""
    rows = []
    for (a, b, par, chrom), g in pairs.assign(
            sa=pairs[["sib_a", "sib_b"]].min(1), sb=pairs[["sib_a", "sib_b"]].max(1)
    ).groupby(["sa", "sb", "parent", "chrom"]):
        g = g.sort_values("start")
        cur = None
        for r in g.itertuples():
            if cur and r.start <= cur[1]:
                cur[1] = max(cur[1], r.end); cur[2] += 1
            else:
                if cur:
                    rows.append((a, b, parent_side[par], chrom, cur[0], cur[1], cur[2]))
                cur = [r.start, r.end, 1]
        if cur:
            rows.append((a, b, parent_side[par], chrom, cur[0], cur[1], cur[2]))
    return pd.DataFrame(rows, columns=["sib_a", "sib_b", "side", "chrom", "start", "end", "pairs"])


def _block(paint, subject, chrom, parent, start, end):
    p = paint[(paint.subject == subject) & (paint.chrom.astype(str) == chrom) & (paint.parent == parent)]
    ov = np.minimum(p.end, end) - np.maximum(p.start, start)
    p = p[ov > 0].assign(ov=ov[ov > 0])
    if p.empty:
        return None
    return p.sort_values("ov").iloc[-1]


def check(pairs, paint):
    look = {s: mp.painting_lookup(paint, s) for s in paint.subject.unique()}
    rows = []
    for r in pairs.itertuples():
        ga, pa = mp.grandparent_of(look[r.sib_a], r.chrom, r.parent, r.start, r.end)
        gb, pb = mp.grandparent_of(look[r.sib_b], r.chrom, r.parent, r.start, r.end)
        ba = _block(paint, r.sib_a, r.chrom, r.parent, r.start, r.end)
        bb = _block(paint, r.sib_b, r.chrom, r.parent, r.start, r.end)
        rows.append(dict(r._asdict(), gp_a=ga, purity_a=round(pa, 2), gp_b=gb, purity_b=round(pb, 2),
                         block_a=None if ba is None else f"{int(ba.start)}-{int(ba.end)}",
                         snps_a=None if ba is None else int(ba.snps),
                         block_b=None if bb is None else f"{int(bb.start)}-{int(bb.end)}",
                         snps_b=None if bb is None else int(bb.snps),
                         consistent=bool(ga and gb and ga == gb)))
    return pd.DataFrame(rows).drop(columns=["Index"], errors="ignore")


def correct(paint, checked):
    """Relabel weak blocks that disagreeing pairs outvote. Returns
    (corrected paint, corrections)."""
    votes = defaultdict(lambda: {"against": [], "for": 0})
    for r in checked.itertuples():
        for me, other, gme, gother, blk, snps in (("sib_a", "sib_b", r.gp_a, r.gp_b, r.block_a, r.snps_a),
                                                    ("sib_b", "sib_a", r.gp_b, r.gp_a, r.block_b, r.snps_b)):
            if not blk or not gme:
                continue
            key = (getattr(r, me), r.chrom, r.parent, blk)
            if r.consistent:
                votes[key]["for"] += 1
            elif gother:
                votes[key]["against"].append((gother, getattr(r, other), r.match, r.cM, snps))
    paint = paint.copy()
    paint["corrected_from"] = ""
    fixes = []
    for (subj, chrom, parent, blk), v in votes.items():
        against = v["against"]
        if len(against) < MIN_PAIRS or v["for"] > 0:
            continue
        labels = {g for g, *_ in against}
        if len(labels) != 1:
            continue
        snps = against[0][4]
        if snps is None or snps >= MAX_SNPS:
            continue
        new = labels.pop()
        s, e = map(int, blk.split("-"))
        m = ((paint.subject == subj) & (paint.chrom.astype(str) == chrom) & (paint.parent == parent)
             & (paint.start == s) & (paint.end == e))
        old = paint.loc[m, "lineage"].iloc[0]
        paint.loc[m, "corrected_from"] = old
        paint.loc[m, "lineage"] = new
        fixes.append(dict(subject=subj, chrom=chrom, parent=parent, start=s, end=e, snps=snps,
                          old=old, new=new, pairs=len(against),
                          evidence="; ".join(f"{m} ({cm:.1f} cM, with {o})" for _, o, m, cm, _ in against)))
    return paint, pd.DataFrame(fixes)


def main():
    import config
    cfg = config.load()
    D = cfg["data_dir"]
    children = cfg["children"]
    segs = outputs.read(D, "placed_segments.csv", dtype={"chrom": str})
    # always check the uncorrected painting, so corrections don't vote for themselves
    paint = outputs.read(D, "phasing_grandparent_segments.csv", dtype={"chrom": str})
    pairs = shared_pairs(segs, children)
    checked = check(pairs, paint)
    outputs.write(D, "sibling_consistency.csv", checked)
    bad = checked[~checked.consistent & (checked.gp_a != "") & (checked.gp_b != "")]
    print(f"{len(checked)} sibling pairs sharing a segment end to end; "
          f"{(checked.consistent).sum()} consistent, {len(bad)} disagree")
    print(bad.groupby(["chrom", "parent"]).size().sort_values(ascending=False).head(15).to_string())
    fixed, fixes = correct(paint, checked)
    # corrections name the painting they were made for (match_placement.load_painting)
    import match_placement as mp
    fixes = fixes.assign(painting=mp.painting_id(D / "phasing_grandparent_segments.csv")) if len(fixes) \
        else pd.DataFrame(columns=["subject", "chrom", "parent", "start", "end", "snps", "old", "new",
                                   "pairs", "evidence", "painting"])
    outputs.write(D, "phasing_corrections.csv", fixes)
    outputs.write(D, "phasing_grandparent_segments_corrected.csv", fixed)   # for reading
    print(fixes.to_string(index=False) if len(fixes) else "no corrections")
    return checked, fixed, fixes


if __name__ == "__main__":
    main()
