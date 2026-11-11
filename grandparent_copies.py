"""
Recursive deduction, first step: split a grandparent's own two copies
(design-copy-model.md, "Recursive deduction: requirements").

The siblings' copy from one grandparent G (say FM, the father's maternal
copy) is a mosaic of G's two own copies, P (from G's father) and M (from
G's mother), switching at the crossovers of G's meiosis to the siblings'
parent. G's other children, seen through their tested descendants
("lines"), share that copy with the siblings only where they carry the
same one of G's copies, so their segments end at those crossovers. So:

  edges()     G's crossovers: spots where segments of at least
              `min_lines` independent lines end, away from the siblings'
              own crossovers on that parent;
  stretches() the copy between edges, with a parity that flips at each;
  name()      which parity is M, from claims through G's mother only
              (claims through G's father are held out: they are the test);
  shares()    for each group of held-out relatives, how much of their
              segment length lands on P, on M, or on unnamed stretches.

Everything is in cM and generic; the inputs are segments already placed
on G's copy in the siblings (10 cM and up: shorter ends are noise).
`evaluate()` runs it on the simulator's grandmother scenario against the
truth. Sketch, checked only on the simulator so far.
"""
from collections import defaultdict

import numpy as np
import pandas as pd

import simulate as S

TOL_CM = 1.0       # ends of different lines this close are one spot
NEAR_CM = 1.5      # a sibling crossover this close explains an end cluster
MIN_CM = 10.0      # segments shorter than this are left out
TIP_CM = 1.0       # ends this close to where the copy's coverage stops are cuts


def edges(segs, sib_xo=None, bounds=None, min_lines=2, tol=TOL_CM, near=NEAR_CM, spans=None):
    """segs: chrom, start_cm, end_cm, line (child-line segments on G's
    copy). sib_xo: chrom, cm (the siblings' crossovers on that parent).
    bounds: {chrom: (lo, hi)} coverage of the copy (default: the segments'
    own extent). spans: segments of anyone on G's copy (chrom, start_cm,
    end_cm); one running more than 2 * tol past a spot on both sides shows
    the copy is unbroken there, which vetoes an edge. Returns chrom, cm,
    lines (count), ends."""
    out = []
    for c, g in segs.groupby("chrom"):
        lo, hi = (bounds or {}).get(c, (g.start_cm.min(), g.end_cm.max()))
        pts = []
        for line, h in g.groupby("line"):
            # one point per line per spot: siblings sharing one end are one end
            e = np.sort(np.r_[h.start_cm.to_numpy(), h.end_cm.to_numpy()])
            e = e[(e > lo + TIP_CM) & (e < hi - TIP_CM)]
            keep = [x for i, x in enumerate(e) if i == 0 or x - e[i - 1] > tol]
            pts += [(x, line) for x in keep]
        pts.sort()
        xo = (np.sort(sib_xo[sib_xo.chrom == c].cm.to_numpy())
              if sib_xo is not None and len(sib_xo) else np.array([]))
        cur = []
        for p in pts + [(np.inf, None)]:
            if cur and (p[0] - cur[0][0] > 2 * tol):
                lines = {q[1] for q in cur}
                at = float(np.median([q[0] for q in cur]))
                sp = spans[spans.chrom == c] if spans is not None else None
                spanned = sp is not None and ((sp.start_cm < at - 2 * tol) & (sp.end_cm > at + 2 * tol)).any()
                if (len(lines) >= min_lines and not spanned
                        and not (len(xo) and np.min(np.abs(xo - at)) <= near)):
                    out.append(dict(chrom=c, cm=at, lines=len(lines), ends=len(cur)))
                cur = []
            cur.append(p)
    return pd.DataFrame(out, columns=["chrom", "cm", "lines", "ends"])


STEP_CM = 0.5
RATE = 1.25 / 100   # crossovers per cM in a female meiosis (simulator's rate)
# flip probability at a called edge, by how many lines end there (simulator,
# 3-9 child lines of first cousins: a third of one-line spots, three in four
# two-line spots and nearly all spots of three or more are true edges)
EDGE_FLIP = {1: 0.3, 2: 0.75, 3: 0.97}
ANCHOR_P = 0.98     # how sure a mother-side segment makes a cell M
MIN_POST = 0.9      # cells named only this sure


def posterior(E, spans, anchors, bounds, step=STEP_CM):
    """Per chromosome, a two-state chain along G's copy (P / M): a flip at
    the base female rate, likely at a called edge, nearly impossible where
    a segment on the copy spans the step; mother-side segments (anchors)
    say M. Returns a grid: chrom, cm, p_M, name (P, M, or "")."""
    out = []
    for c, (lo, hi) in bounds.items():
        x = np.arange(lo + step / 2, hi, step)
        n = len(x)
        flip = np.full(n, RATE * step)
        for e in (E[E.chrom == c].itertuples() if len(E) else []):
            i = min(np.searchsorted(x, e.cm), n - 1)
            flip[i] = max(flip[i], EDGE_FLIP[min(e.lines, 3)])
        sp = spans[spans.chrom == c]
        for r in sp.itertuples():               # flip between i-1 and i lies inside a segment
            flip[(x - step / 2 > r.start_cm + TOL_CM) & (x - step / 2 < r.end_cm - TOL_CM)] = 1e-6
        em = np.full((n, 2), 0.5)               # columns: P, M
        for r in anchors[anchors.chrom == c].itertuples():
            sel = (x > r.start_cm) & (x < r.end_cm)
            em[sel] = em[sel] * [1 - ANCHOR_P, ANCHOR_P] * 2
        f = np.zeros((n, 2)); bwd = np.ones((n, 2))
        f[0] = em[0] / em[0].sum()
        for i in range(1, n):
            q = flip[i]
            f[i] = em[i] * (f[i - 1] * (1 - q) + f[i - 1][::-1] * q)
            f[i] /= f[i].sum()
        for i in range(n - 2, -1, -1):
            q = flip[i + 1]
            v = em[i + 1] * bwd[i + 1]
            bwd[i] = v * (1 - q) + v[::-1] * q
            bwd[i] /= bwd[i].sum()
        pm = f[:, 1] * bwd[:, 1] / (f * bwd).sum(1)
        nm = np.where(pm >= MIN_POST, "M", np.where(pm <= 1 - MIN_POST, "P", ""))
        out.append(pd.DataFrame(dict(chrom=c, cm=x, p_M=pm, name=nm)))
    return pd.concat(out, ignore_index=True)


def shares(grid, segs, step=STEP_CM):
    """Per group: segment cM on P-named, M-named and unnamed cells, and the
    share on P among the named."""
    acc = defaultdict(lambda: {"P": 0.0, "M": 0.0, "": 0.0})
    for c, g in segs.groupby("chrom"):
        G = grid[grid.chrom == c]
        for r in g.itertuples():
            for k, v in G[(G.cm > r.start_cm) & (G.cm < r.end_cm)].name.value_counts().items():
                acc[r.group][k] += v * step
    rows = [dict(group=g, P=v["P"], M=v["M"], unnamed=v[""],
                 share_P=v["P"] / (v["P"] + v["M"]) if v["P"] + v["M"] else np.nan)
            for g, v in acc.items()]
    return pd.DataFrame(rows, columns=["group", "P", "M", "unnamed", "share_P"])


def mean_pm(grid, segs, step=STEP_CM):
    """Per group: the mean posterior of M over its segments' cells (cM
    weighted). The copy test reads the father-side group against
    mother-side relatives left out one at a time: on G's paternal copy it
    sits low, through her mother it sits as high as they do."""
    acc = defaultdict(lambda: [0.0, 0])
    for c, g in segs.groupby("chrom"):
        G = grid[grid.chrom == c]
        for r in g.itertuples():
            v = G.p_M[(G.cm > r.start_cm) & (G.cm < r.end_cm)]
            acc[r.group][0] += v.sum()
            acc[r.group][1] += len(v)
    return {k: s / n for k, (s, n) in acc.items() if n}


# ------------------------------------------------------------ simulator
def _switches(mosaic, a_set):
    """Positions (cM) where a mosaic switches between labels in a_set and not."""
    out = []
    for i in range(1, len(mosaic)):
        if (mosaic[i - 1][2] in a_set) != (mosaic[i][2] in a_set):
            out.append(mosaic[i][0])
    return out


def evaluate(seed=0, min_lines=1, sibs=("sib1", "sib2", "sib3"), spans_from="all", **scenario):
    """Run on one simulated grandmother family; compare with the truth.
    Placement on G's copy is taken from the truth (the copy model places
    99% right on real data), so this measures the recursion alone."""
    ped, groups = S.grandmother(siblings=len(sibs), **scenario)
    sim = S.simulate(ped, seed=seed)
    segs = S.detect(sim, list(sibs), seed=seed, matches=list(sibs) + list(groups), join=True)
    G = sim.genomes["FM"]
    P_set = {lab for c in G["F"] for _, _, lab in G["F"][c]}
    G_set = P_set | {lab for c in G["M"] for _, _, lab in G["M"][c]}
    gm = sim.maps["average"]
    segs = segs[segs.match.isin(list(groups)) & segs.real & (segs.cM >= MIN_CM) & (segs.true_copy == "F")
                & segs.founder_copy.isin(G_set)].copy()
    segs["start_cm"] = [float(gm.cm(c, x)) for c, x in zip(segs.chrom, segs.start)]
    segs["end_cm"] = [float(gm.cm(c, x)) for c, x in zip(segs.chrom, segs.end)]
    segs["line"] = segs.match
    segs["group"] = segs.match.map(groups)
    bounds = {c: (0.0, float(L)) for c, L in S.CHROM_CM.items()}
    xo = pd.DataFrame([dict(chrom=c, cm=x) for s in sibs for c in S.CHROM_CM
                       for x in _switches(sim.genomes[s]["F"][c], G_set)], columns=["chrom", "cm"])
    spans = segs if spans_from == "all" else segs[segs.group.isin(["child", "M"])]
    E = edges(segs[segs.group == "child"], xo, bounds, min_lines=min_lines, spans=spans)
    true_E = pd.DataFrame([dict(chrom=c, cm=x) for c in S.CHROM_CM
                           for x in _switches(sim.genomes["F"]["M"][c], P_set)], columns=["chrom", "cm"])

    def carried(c, x):    # does any sibling carry the father's maternal copy here?
        return any(sim.copy_at(s, "F", c, x) in G_set for s in sibs)
    visible = [r for r in true_E.itertuples() if carried(r.chrom, max(r.cm - 0.5, 0))
               and carried(r.chrom, r.cm + 0.5)]
    hit = lambda c, x, D: len(D) and (np.abs(D[D.chrom == c].cm.to_numpy() - x) <= NEAR_CM).any()
    found = sum(bool(hit(r.chrom, r.cm, E)) for r in visible)
    right = sum(bool(hit(r.chrom, r.cm, true_E)) for r in E.itertuples())
    grid = posterior(E, spans, segs[segs.group == "M"], bounds)
    vis = np.array([carried(c, x) for c, x in zip(grid.chrom, grid.cm)])
    truth = np.array([sim.copy_at("F", "M", c, x) in P_set for c, x in zip(grid.chrom, grid.cm)])
    g2 = grid[vis]
    nm = g2.name.to_numpy()
    named = (nm != "").mean() if len(nm) else 0.0
    ok = ((nm == "P") == truth[vis])[nm != ""]
    named, ok, tot = named, ok.sum(), 1
    st = grid
    sh = shares(grid, segs[segs.group != "child"]).set_index("group").share_P
    pm = mean_pm(grid, segs[segs.group.str.startswith(("P", "sister"))])
    loo = []                    # mother-side relatives, each left out of the anchors
    anchors = segs[segs.group == "M"]
    for m in anchors.match.unique():
        gr = posterior(E, spans, anchors[anchors.match != m], bounds)
        loo.append(mean_pm(gr, anchors[anchors.match == m]).get("M", np.nan))
    return dict(seed=seed, true_edges=len(true_E), visible=len(visible), found=found,
                called=len(E), right=right,
                recall=found / max(len(visible), 1), precision=right / max(len(E), 1),
                named=named, naming_acc=ok / max((nm != '').sum(), 1),
                P_on_P=sh.get("P", np.nan), M_on_P=sh.get("M", np.nan),
                full_on_P=sh.get("sister_full", np.nan), half_on_P=sh.get("sister_half", np.nan),
                pM_P=pm.get("P", np.nan), pM_M_loo=np.nanmean(loo) if loo else np.nan,
                pM_full=pm.get("sister_full", np.nan), pM_half=pm.get("sister_half", np.nan))


def sweep(seeds=10, children=(2, 4, 6, 9), depths=(1, 2), min_lines=(1,)):
    rows = []
    for d in depths:
        for k in children:
            for ml in min_lines:
                r = pd.DataFrame([evaluate(s, min_lines=ml, children=k, child_depth=d)
                                  for s in range(seeds)])
                rows.append(dict(depth=d, children=k, min_lines=ml,
                                 **r.drop(columns="seed").mean().round(3).to_dict()))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    cols = ["depth", "children", "min_lines", "visible", "recall", "precision", "named",
            "naming_acc", "P_on_P", "M_on_P", "full_on_P", "half_on_P"]
    print(sweep()[cols].to_string(index=False))
