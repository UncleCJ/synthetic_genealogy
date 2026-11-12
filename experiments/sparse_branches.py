"""Research sketch (2026-11-12), unvalidated beyond the simulator: a single donor
without parent or siblings. Anchor a share of the relatives, fit the copy
model, and give every other match a branch posterior over the four
grandparents by combining all its segments. Two ways: the naive product of
per-stretch marginals, and the joint (path) probability from the HMM evidence
ratio Z(anchors + match as g) / Z(anchors). Rounds > 0 promote confident
matches to anchors (self-training), to show why that is unsafe.

Run from the repo root:  EV=1 MINCM=10 python3 experiments/sparse_branches.py 0.6
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
import simulate as sm, copy_model as cm, intervals as iv
GPS = ["FF", "FM", "MF", "MM"]

def seg_gp_probs(model, r):
    """P(copy of side s is under g) averaged over the segment, for the 4 g."""
    out = {}
    for side in "FM":
        if str(r.chrom) not in model.grid:
            for g in GPS:
                if g[0] == side: out[g] = 0.5
            continue
        pts = np.linspace(r.start, r.end, 7)
        P = model.at(str(r.chrom), side, pts)
        S = cm.states(side, model.depth)
        for g in GPS:
            if g[0] == side:
                out[g] = float(P[:, [s.startswith(g) for s in S]].sum(1).mean())
    return out

def match_posterior(model, g_segs):
    logL = np.zeros(4)
    for r in g_segs.itertuples():
        w = float(cm.real_probability(r.cM))
        p = seg_gp_probs(model, r)
        # likelihood of this segment given branch g: real -> lies on copy g[0]
        # and that copy is under g there; false -> uninformative (0.5 baseline)
        logL += np.log([(1 - w) * 0.5 + w * p[g] for g in GPS])
    post = np.exp(logL - logL.max()); return post / post.sum()

def logZ(model, grid, cc, side):
    S = cm.states(side, model.depth)
    logE = np.zeros((len(grid), len(S)))
    for r in cc.itertuples():
        inside = (grid >= r.a_cm) & (grid <= r.b_cm); n = inside.sum()
        if not n: continue
        compat = np.array([s.startswith(r.code) for s in S], float)
        logE[inside] += model.evidence * np.log((1 - r.w) + r.w * compat) / n
    E = np.exp(logE); T = model.T
    v = np.full(len(S), 1 / len(S)) * E[0]; lz = np.log(v.sum()); v /= v.sum()
    for t in range(1, len(grid)):
        v = (v @ T) * E[t]; s = v.sum(); lz += np.log(s); v /= s
    return lz

def as_claims(model, g_segs, code):
    c = cm.claims_from_segments(g_segs, {g_segs.match.iloc[0]: code})
    c["chrom"] = c.chrom.astype(str)
    c["a_cm"] = [float(model.gm.cm(ch, x)) for ch, x in zip(c.chrom, c.start)]
    c["b_cm"] = [float(model.gm.cm(ch, x)) for ch, x in zip(c.chrom, c.end)]
    c["code"] = code; return c

def match_posterior_joint(model, g_segs, base_cache):
    ll = np.zeros(4)
    for k, g in enumerate(GPS):
        mc = as_claims(model, g_segs, g)
        for chrom, cc in mc.groupby("chrom"):
            grid = np.arange(0, sm.CHROM_CM[chrom] + model.step, model.step)
            anc = model.claims[(model.claims.chrom == chrom) & (model.claims.code.str[0] == g[0])]
            key = (chrom, g[0])
            if key not in base_cache: base_cache[key] = logZ(model, grid, anc, g[0])
            ll[k] += logZ(model, grid, pd.concat([anc, cc]), g[0]) - base_cache[key]
    p = np.exp(ll - ll.max()); return p / p.sum()

MINCM = float(__import__("os").environ.get("MINCM", 7))
def run(seed, rpc=3, anchor_frac=0.3, rounds=2):
    rng = np.random.default_rng(seed)
    ped, via = sm.ancestry(depth=4, relatives_per_couple=rpc)
    via = {m: v for m, v in via.items() if len(v) >= 2}
    sim = sm.simulate(ped, seed=seed)
    segs = sm.detect(sim, ["sib1"], seed=seed, matches=list(via)); segs = segs[segs.cM >= MINCM]
    ms = sorted(set(segs.match))
    anchors = set(rng.choice(ms, max(1, int(anchor_frac * len(ms))), replace=False))
    held = [m for m in ms if m not in anchors]
    known = {m: via[m] for m in anchors}; rows = []
    for rnd in range(rounds + 1):
        model = cm.CopyModel(depth=3, ends=False, evidence=float(__import__("os").environ.get("EV", 2))).fit(cm.claims_from_segments(segs, known), lengths_cm=sm.CHROM_CM)
        cache, added = {}, {}
        for m in held:
            if m in known: continue
            g = segs[segs.match == m]
            post = match_posterior_joint(model, g, cache); k = int(post.argmax()); nv = match_posterior(model, g); kn = int(nv.argmax())
            rows.append(dict(seed=seed, round=rnd, match=m, nseg=len(g), truth=via[m][:2], call=GPS[k],
                             p=post[k], right=GPS[k] == via[m][:2],
                             top2=via[m][:2] in [GPS[i] for i in np.argsort(post)[-2:]],
                             p_truth=post[GPS.index(via[m][:2])], pn=nv[kn], right_n=GPS[kn] == via[m][:2]))
            if post[k] >= 0.9: added[m] = GPS[k]
        known.update(added)
    return pd.DataFrame(rows)

if __name__ == "__main__":
    import sys
    frac = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
    df = pd.concat([run(s, anchor_frac=frac) for s in range(8)])
    df["nseg_band"] = pd.cut(df.nseg, [0, 1, 2, 4, 8, 100], labels=["1", "2", "3-4", "5-8", "9+"])
    r0 = df[df["round"] == 0]
    print(f"ROUND 0, {frac:.0%} of matches anchored; 4 grandparents, chance = 0.25")
    print(r0.groupby("nseg_band", observed=True).agg(n=("right", "size"), acc=("right", "mean"),
          sure=("p", lambda x: (x >= .9).mean()), top2=("top2", "mean"), p_truth=("p_truth", "mean")).round(2))
    sn = r0[r0.pn >= .9]; print("NAIVE product of marginals: acc", round(r0.right_n.mean(),3), "sure", len(sn), "right", round(sn.right_n.mean(),3)); print("JOINT acc", round(r0.right.mean(),3)); s = r0[r0.p >= .9]; print("sure (>=0.9):", len(s), "of", len(r0), "right:", round(s.right.mean(), 3))
    # calibration
    r0 = r0.assign(b=pd.cut(r0.p, [0, .5, .7, .9, 1.01]))
    print(r0.groupby("b", observed=True).agg(n=("right","size"), said=("p","mean"), right=("right","mean")).round(2))
    for rnd in (1, 2):
        d = df[df["round"] == rnd]; s = d[d.p >= .9]
        print(f"ROUND {rnd}: unnamed before {len(d)}, newly sure {len(s)}, right {s.right.mean():.3f}" if len(s) else f"ROUND {rnd}: none")
