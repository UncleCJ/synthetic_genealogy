"""Research sketch (2026-11-12): how much does one close relative name a
single donor's copies, compared with tree-linked distant relatives?

Pedigree: `simulate.ancestry` (depth 4, two tested relatives per ancestral
couple) plus a tested maternal grandmother (MM) and a maternal half-sibling.
Crossovers from Ped-sim (sex-specific Bherer map, Campbell interference)
or, as a cross-check, from the built-in simulator (Poisson, flat map).
Vendor noise from simulate.detect (end noise, false 7-10 cM segments).

Evidence regimes for the copy model of the donor (sib1), no parent, no
siblings:
  anchors      30% of the distant relatives, claims at their tree path (>= 10 cM)
  gm           the grandmother's segments: the maternal copy is MM there
  gm+absence   ... and MF in the gaps between them (shrunk by a margin, long gaps only)
  halfsib      the half-sibling's own anchored maternal-side segments moved
               onto the donor: same code where the two share IBD, the other
               grandparent in the gaps (the mother passed the other copy)
Measured: per copy, the share of the genome named at grandparent level
with posterior >= 0.9, and how often that is right.

Usage (from the repo root):
  python3 experiments/close_relatives.py --pedsim PATH/ped-sim --simmap PATH/refined_mf.simmap \
      --intf PATH/nu_p_campbell.tsv --families 6
  python3 experiments/close_relatives.py --families 6          # built-in simulator only
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # the repo root
import copy_model as cm   # noqa: E402
import intervals as iv    # noqa: E402
import simulate as sm     # noqa: E402

MIN_ANCHOR_CM = 10.0
MARGIN_CM = 2.0           # gaps shrunk by this at each end (end noise)
MIN_GAP_CM = 5.0          # shorter gaps are not read as absence
CLOSE_W = 0.95            # confidence of a close relative's presence/absence claim


def pedigree():
    ped, via = sm.ancestry(depth=4, relatives_per_couple=2)
    ped.add("hs_dad", "M")
    ped.add("halfsib", "F", father="hs_dad", mother="M")
    return ped, via


def to_cm(gm, segs):
    return segs.assign(a=[float(gm.cm(c, x)) for c, x in zip(segs.chrom, segs.start)],
                       b=[float(gm.cm(c, x)) for c, x in zip(segs.chrom, segs.end)])


def spans(sim):
    return {c: (min(m[0][0] for m in (sim.genomes["sib1"]["F"][c], sim.genomes["sib1"]["M"][c])),
                sim.lengths[c]) for c in sim.lengths}


def gaps(intervals_cm, lo, hi, margin=MARGIN_CM, min_len=MIN_GAP_CM):
    """Stretches of [lo, hi] not covered, shrunk by `margin` where they meet a
    segment (not at the chromosome ends), kept when at least min_len long."""
    out, x = [], lo
    for a, b in iv.merge(sorted(intervals_cm)):
        g0, g1 = (x if x == lo else x + margin), a - margin
        if g1 - g0 >= min_len:
            out.append((g0, g1))
        x = max(x, b)
    g0 = x if x == lo else x + margin
    if hi - g0 >= min_len:
        out.append((g0, hi))
    return out


def claim(gm, subject, match, chrom, a, b, code, w):
    return dict(subject=subject, match=match, chrom=str(chrom), start=float(gm.bp(chrom, a)),
                end=float(gm.bp(chrom, b)), cM=b - a, lineage=code, w=w,
                claim_id=f"{subject}:{match}:{chrom}:{a:.1f}:{code}")


def close_claims(sim, segs, relative, code_present, code_absent=None):
    """Presence (and absence) claims from a close relative on the donor's copy."""
    gm, rows = sim.maps["average"], []
    s = to_cm(gm, segs[(segs.match == relative) & (segs.cM >= 7)])
    for c, (lo, hi) in spans(sim).items():
        here = [(r.a, r.b) for r in s[s.chrom == c].itertuples()]
        for a, b in iv.merge(sorted(here)):
            rows.append(claim(gm, "sib1", relative, c, a, b, code_present, CLOSE_W))
        if code_absent:
            for a, b in gaps(here, lo, hi):
                rows.append(claim(gm, "sib1", relative + ":absent", c, a, b, code_absent, CLOSE_W))
    return rows


def halfsib_claims(sim, segs_sib, segs_hs, anchors, via):
    """The half-sibling's anchored maternal-side segments, moved onto the
    donor through their shared IBD (same code) or its gaps (the other
    grandparent, two letters)."""
    gm, rows = sim.maps["average"], []
    shared = to_cm(gm, segs_sib[(segs_sib.match == "halfsib") & (segs_sib.cM >= 7)])
    own = to_cm(gm, segs_hs[segs_hs.match.isin([m for m in anchors if via[m].startswith("M")])
                            & (segs_hs.cM >= MIN_ANCHOR_CM)])
    sp = spans(sim)
    for c, g in own.groupby("chrom"):
        same = iv.merge(sorted((r.a, r.b) for r in shared[shared.chrom == c].itertuples()))
        other = gaps([(a, b) for a, b in same], *sp[c])
        for r in g.itertuples():
            code = via[r.match]
            if len(code) < 2:
                continue
            flip = code[0] + ("M" if code[1] == "F" else "F")
            wr = float(0.95 * cm.real_probability(r.cM)) * CLOSE_W
            for ivs, cd in ((same, code), (other, flip)):
                for a, b in ivs:
                    lo, hi = max(a, r.a), min(b, r.b)
                    if hi - lo >= 2:
                        rows.append(claim(gm, "sib1", f"hs:{r.match}", c, lo, hi, cd, wr))
    return rows


def accuracy(model, sim, n=600, seed=0):
    rng = np.random.default_rng(seed)
    gm, sp, out = sim.maps["average"], spans(sim), {}
    chroms = list(sp)
    w = np.array([sp[c][1] - sp[c][0] for c in chroms])
    for side in "FM":
        S = cm.states(side, model.depth)
        codes = [side + "F", side + "M"]
        conf = right = 0
        for _ in range(n):
            c = chroms[rng.choice(len(chroms), p=w / w.sum())]
            x = rng.uniform(*sp[c])
            bp = float(gm.bp(c, x))
            truth = sim.lineage("sib1", c, bp)["FM".index(side)][:2]
            P = model.at(c, side, [bp])[0]
            m = np.array([P[[s.startswith(k) for s in S]].sum() for k in codes])
            if m.max() >= 0.9:
                conf += 1
                right += codes[int(m.argmax())] == truth
        out[side] = (conf / n, right / conf if conf else np.nan)
    return out


def one_family(sim, via, seed, holes=0.0):
    rng = np.random.default_rng(seed)
    rels = list(via)
    segs = sm.detect(sim, ["sib1"], seed=seed, matches=rels + ["MM", "halfsib"])
    segs_hs = sm.detect(sim, ["halfsib"], seed=seed + 1000, matches=rels)
    if holes:   # vendor dropout inside long close-relative segments
        keep = []
        for r in segs.itertuples(index=False):
            r = r._asdict()
            if r["match"] in ("MM", "halfsib") and r["cM"] > 20 and rng.random() < holes:
                gm = sim.maps["average"]
                a, b = float(gm.cm(r["chrom"], r["start"])), float(gm.cm(r["chrom"], r["end"]))
                L = rng.uniform(3, 8)
                x = rng.uniform(a + 5, b - 5 - L)
                keep += [dict(r, end=float(gm.bp(r["chrom"], x)), cM=x - a),
                         dict(r, start=float(gm.bp(r["chrom"], x + L)), cM=b - x - L)]
            else:
                keep.append(r)
        segs = pd.DataFrame(keep)
    anchors = list(rng.choice(rels, int(0.3 * len(rels)), replace=False))
    gm = sim.maps["average"]
    big = segs[segs.cM >= MIN_ANCHOR_CM]
    A = cm.claims_from_segments(big, {m: via[m] for m in anchors}, gm=gm).to_dict("records")
    G = close_claims(sim, segs, "MM", "MM")
    GA = close_claims(sim, segs, "MM", "MM", "MF")
    HS = halfsib_claims(sim, segs, segs_hs, anchors, via)
    regimes = {"anchors": A, "anchors+gm": A + G, "anchors+gm+absence": A + GA,
               "gm+absence alone": GA, "anchors+halfsib": A + HS, "anchors+gm+absence+halfsib": A + GA + HS}
    rows = []
    for name, cl in regimes.items():
        df = pd.DataFrame(cl)
        model = cm.CopyModel(genetic_map=gm, depth=3).fit(df, lengths_cm=sim.lengths)
        acc = accuracy(model, sim, seed=seed)
        rows.append(dict(regime=name, pat_named=acc["F"][0], pat_right=acc["F"][1],
                         mat_named=acc["M"][0], mat_right=acc["M"][1]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pedsim"); ap.add_argument("--simmap"); ap.add_argument("--intf")
    ap.add_argument("--families", type=int, default=6)
    ap.add_argument("--holes", type=float, default=0.0)
    ap.add_argument("--work", default="/tmp/close_relatives")
    a = ap.parse_args()
    ped, via = pedigree()
    runs = {"built-in": [sm.simulate(ped, seed=s) for s in range(a.families)]}
    if a.pedsim:
        runs["Ped-sim"] = sm.run_pedsim(ped, a.pedsim, a.simmap, a.work, copies=a.families,
                                        seed=7, intf=a.intf)
    pd.set_option("display.width", 140)
    for label, sims in runs.items():
        rows = []
        for k, sim in enumerate(sims):
            rows += one_family(sim, via, seed=k, holes=a.holes)
        df = pd.DataFrame(rows).groupby("regime", sort=False).mean().round(3)
        print(f"\n== {label} crossovers, {len(sims)} families, holes={a.holes}")
        print(df.to_string())


if __name__ == "__main__":
    main()
