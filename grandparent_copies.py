"""
Recursive deduction, first step: split a grandparent's own two copies
(docs/genetics.md, "Recursive deduction").

The siblings' copy from one grandparent G is a mosaic of G's two own copies,
P (from G's father) and M (from G's mother); G's other descendants' segment
ends and relatives through her mother separate them.

  edges()     G's crossovers, from where independent lines' segments end;
  stretches() the copy between edges, with a parity that flips at each;
  name()      which parity is M, from claims through G's mother only;
  shares()    for each group of held-out relatives, how much of their
              segment length lands on P, on M, or on unnamed stretches.

Everything is in cM and generic; the inputs are segments already placed
on G's copy in the siblings (10 cM and up: shorter ends are noise).
`evaluate()` runs it on the simulator's grandmother scenario against the
truth; `run_real()` (`python3 grandparent_copies.py --real`, private
output) on the family's placed segments, grouped from the tree and the
lineage claims.

How it works: docs/genetics.md, "Recursive deduction".
Sketch, checked only on the simulator so far.
"""
from collections import defaultdict

import numpy as np
import pandas as pd

import outputs
import simulate as S

TOL_CM = 1.0       # ends of different lines this close are one spot
NEAR_CM = 1.5      # a sibling crossover this close explains an end cluster
MIN_CM = 10.0      # segments shorter than this are left out
TIP_CM = 1.0       # ends this close to where the copy's coverage stops are cuts
GENOME_CM = 6800   # both copies: expected shared cM = 2 * kinship * GENOME_CM
JOIN_MIN_FRAC = 0.3  # a name join to a line must share this share of what the tree expects


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


def posterior(E, spans, anchors, bounds, step=STEP_CM, anchors_p=None):
    """Per chromosome, a two-state chain along G's copy (P / M): a flip at
    the base female rate, likely at a called edge, nearly impossible where
    a segment on the copy spans the step; mother-side segments (anchors)
    say M, and father-side ones (anchors_p, only where that side is not
    the question) say P. Returns a grid: chrom, cm, p_M, name (P, M, or "")."""
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
            # the same margin as edges(): a segment's own noisy end must not veto its edge
            flip[(x - step / 2 > r.start_cm + 2 * TOL_CM) & (x - step / 2 < r.end_cm - 2 * TOL_CM)] = 1e-6
        em = np.full((n, 2), 0.5)               # columns: P, M
        for r in anchors[anchors.chrom == c].itertuples():
            sel = (x > r.start_cm) & (x < r.end_cm)
            em[sel] = em[sel] * [1 - ANCHOR_P, ANCHOR_P] * 2
        if anchors_p is not None:
            for r in anchors_p[anchors_p.chrom == c].itertuples():
                sel = (x > r.start_cm) & (x < r.end_cm)
                em[sel] = em[sel] * [ANCHOR_P, 1 - ANCHOR_P] * 2
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


def copy_test(name, rel, bounds, use_p=False, n_perm=2000, seed=0):
    """The copy test per relative, with a null. `rel`: segments of the
    relatives through G's father (group "P") and mother ("M"), one key per
    relative in `line`. Each relative is read with itself left out of the
    anchors; the p-value comes from shuffling the P/M labels (one-sided).
    With use_p the father side names cells too (acc: how often a held-out
    relative is read on its own side).
    `name(anchors_M, anchors_P, bounds) -> grid` is the naming chain
    (posterior() or posterior_joint() with the rest fixed).
    Returns dict(per, diff, p, acc, n_P, n_M).
    How it works: docs/genetics.md, "Recursive deduction"."""
    rows = []
    for line, g in rel.groupby("line"):
        others = rel[rel.line != line]
        b = {c: bounds[c] for c in g.chrom.unique() if c in bounds}
        gr = name(others[others.group == "M"], others[others.group == "P"] if use_p else None, b)
        rows.append(dict(line=line, group=g.group.iloc[0], cM=g.cM.sum() if "cM" in g else np.nan,
                         pM=mean_pm(gr, g.assign(group="x")).get("x", np.nan)))
    per = pd.DataFrame(rows, columns=["line", "group", "cM", "pM"]).dropna(subset=["pM"])
    v, lab = per.pM.to_numpy(), (per.group == "M").to_numpy()
    nP, nM = int((~lab).sum()), int(lab.sum())
    if not nP or not nM:
        return dict(per=per, diff=np.nan, p=np.nan, acc=np.nan, n_P=nP, n_M=nM)
    diff = v[lab].mean() - v[~lab].mean()
    rng = np.random.default_rng(seed)
    null = np.array([(lambda L: v[L].mean() - v[~L].mean())(rng.permutation(lab)) for _ in range(n_perm)])
    dec = np.abs(v - 0.5) >= 0.1
    acc = float(((v > 0.5) == lab)[dec].mean()) if dec.any() else np.nan
    return dict(per=per, diff=float(diff), p=float((1 + (null >= diff).sum()) / (1 + n_perm)),
                acc=acc, n_P=nP, n_M=nM)


# ------------------------------------------------------------ joint per-line model
P_SEEN = 0.97        # a line carrying the copy here, with a tester holding it: segment seen
EPS_FALSE = 0.003    # a segment seen where the line does not carry the copy (per cell)
C_RATE = 0.02        # per cM: a line's testers gaining or losing the child's piece
MAX_LINES = 5        # the joint state doubles twice per line


def posterior_joint(child, spans, anchors, bounds, visible, step=STEP_CM,
                    max_lines=MAX_LINES, margin=2 * TOL_CM, anchors_p=None):
    """G's copy and her other children's lines in one chain (an option, not
    the default, beside posterior()). `visible(chrom, x) -> {subject: bool
    array}` says where a sibling with data for a line carries G's copy
    (absence is read there); cells within `margin` of a segment end are
    left unread; the `max_lines` lines with most segments are kept.
    Returns the grid of posterior() plus p_flip, the posterior of an s0
    flip between a cell and the one before it.
    How it works: docs/genetics.md, "Recursive deduction"."""
    lines = child.groupby("line").size().sort_values(ascending=False).index[:max_lines].tolist()
    K = len(lines)
    seen = {k: set(child[child.line == k].subject) for k in lines}
    out = []
    for c, (lo, hi) in bounds.items():
        x = np.arange(lo + step / 2, hi, step)
        n = len(x)
        vis = visible(c, x)
        pres = np.zeros((n, K), bool)
        unread = np.zeros((n, K), bool)
        able = np.zeros((n, K), bool)
        for k, ln in enumerate(lines):
            for subj in seen[ln]:
                if subj in vis:
                    able[:, k] |= vis[subj]
            for r in child[(child.line == ln) & (child.chrom == c)].itertuples():
                pres[(x > r.start_cm) & (x < r.end_cm), k] = True
                for e in (r.start_cm, r.end_cm):
                    unread[np.abs(x - e) < margin, k] = True
        obs = np.where(unread, 0, np.where(pres, 1, np.where(able, 2, 0)))   # 0 unread, 1 seen, 2 absent
        pi = np.clip(2 * pres.sum(0) / np.maximum(able.sum(0), 1), 0.1, 0.95) if K else np.zeros(0)
        q0 = np.full(n, RATE * step)
        for r in spans[spans.chrom == c].itertuples():
            q0[(x - step / 2 > r.start_cm + margin) & (x - step / 2 < r.end_cm - margin)] = 1e-6
        am = np.full((n, 2), 1.0)
        for r in anchors[anchors.chrom == c].itertuples():
            sel = (x > r.start_cm) & (x < r.end_cm)
            am[sel] *= [1 - ANCHOR_P, ANCHOR_P]
        if anchors_p is not None:
            for r in anchors_p[anchors_p.chrom == c].itertuples():
                sel = (x > r.start_cm) & (x < r.end_cm)
                am[sel] *= [ANCHOR_P, 1 - ANCHOR_P]
        shape = (2,) * (1 + 2 * K)

        def bshape(ax_vals):          # broadcast helper: {axis: vector}
            v = np.ones(shape)
            for ax, vec in ax_vals:
                sh = [1] * len(shape); sh[ax] = 2
                v = v * np.reshape(vec, sh)
            return v

        seen_m = np.array([[EPS_FALSE, EPS_FALSE], [EPS_FALSE, P_SEEN]])
        absent_m = 1 - seen_m

        def emit(i):
            e = bshape([(0, am[i])])
            for k in range(K):
                if obs[i, k]:
                    m = seen_m if obs[i, k] == 1 else absent_m
                    sh = [1] * len(shape); sh[1 + k] = 2; sh[1 + K + k] = 2
                    e = e * m.reshape(sh)
            return e

        s0_axes = tuple(range(0, 1 + K))
        def lines_T(A, fwd=True):
            for k in range(K):
                q = RATE * step
                A = (1 - q) * A + q * np.flip(A, axis=1 + k)
                M = cm_[k] if fwd else cm_[k].T            # rows: from (c=0 off, c=1 on)
                A = np.moveaxis(np.tensordot(A, M, axes=([1 + K + k], [0])), -1, 1 + K + k)
            return A

        def T(A, i, fwd=True):
            A = (1 - q0[i]) * A + q0[i] * np.flip(A, axis=s0_axes)
            return lines_T(A, fwd)

        # c_k: rows from (off, on); off->on at C_RATE*pi, on->off at C_RATE*(1-pi), so pi is stationary
        cm_ = [np.array([[1 - C_RATE * step * p_, C_RATE * step * p_],
                         [C_RATE * step * (1 - p_), 1 - C_RATE * step * (1 - p_)]]) for p_ in pi]
        init = bshape([(0, [0.5, 0.5])] + [(1 + k, [0.5, 0.5]) for k in range(K)]
                      + [(1 + K + k, [1 - pi[k], pi[k]]) for k in range(K)])
        F = np.empty((n,) + shape); B = np.empty((n,) + shape)
        a = init * emit(0); F[0] = a / a.sum()
        for i in range(1, n):
            a = T(F[i - 1], i) * emit(i)
            F[i] = a / a.sum()
        B[-1] = 1.0
        for i in range(n - 2, -1, -1):
            v = B[i + 1] * emit(i + 1)
            # backward through T: lines part transposed, s0 flip is symmetric
            w = lines_T(v, fwd=False)
            w = (1 - q0[i + 1]) * w + q0[i + 1] * np.flip(w, axis=s0_axes)
            B[i] = w / w.sum()
        post = F * B
        post = post.reshape(n, 2, -1).sum(2)
        pm = post[:, 1] / post.sum(1)
        pf = np.zeros(n)
        for i in range(1, n):
            v = emit(i) * B[i]
            flipped = lines_T(q0[i] * np.flip(F[i - 1], axis=s0_axes))
            stay = lines_T((1 - q0[i]) * F[i - 1])
            fl, st = (flipped * v).sum(), (stay * v).sum()
            pf[i] = fl / (fl + st)
        nm = np.where(pm >= MIN_POST, "M", np.where(pm <= 1 - MIN_POST, "P", ""))
        out.append(pd.DataFrame(dict(chrom=c, cm=x, p_M=pm, name=nm, p_flip=pf)))
    return pd.concat(out, ignore_index=True)


def joint_edges(grid, min_p=0.5):
    """G's crossovers as the joint model reads them: runs of cells whose
    summed flip posterior passes min_p, one edge per run at its weighted
    centre."""
    rows = []
    for c, g in grid.groupby("chrom", sort=False):
        pf, x = g.p_flip.to_numpy(), g.cm.to_numpy()
        on = pf > 0.02
        i = 0
        while i < len(pf):
            if not on[i]:
                i += 1
                continue
            j = i
            while j < len(pf) and on[j]:
                j += 1
            m = pf[i:j].sum()
            if m >= min_p:
                rows.append(dict(chrom=c, cm=float((pf[i:j] * x[i:j]).sum() / m), p=float(min(m, 1))))
            i = j
    return pd.DataFrame(rows, columns=["chrom", "cm", "p"])


# ------------------------------------------------------------ simulator
def _switches(mosaic, a_set):
    """Positions (cM) where a mosaic switches between labels in a_set and not."""
    out = []
    for i in range(1, len(mosaic)):
        if (mosaic[i - 1][2] in a_set) != (mosaic[i][2] in a_set):
            out.append(mosaic[i][0])
    return out


def evaluate(seed=0, min_lines=1, sibs=("sib1", "sib2", "sib3"), spans_from="all", method="edges",
             **scenario):
    """Run on one simulated grandmother family; compare with the truth.
    method "edges": edges() then the naming chain; "joint": posterior_joint.
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
    if method == "joint":
        child, nc = segs[segs.group == "child"], segs[segs.group != "child"]

        def vis_fn(c, x):
            return {s: np.array([sim.copy_at(s, "F", c, v) in G_set for v in x]) for s in sibs}

        def name(am, ap, b):
            return posterior_joint(child, nc, am, b, vis_fn, anchors_p=ap)
        grid = name(segs[segs.group == "M"], None, bounds)
        E = joint_edges(grid)
    else:
        def name(am, ap, b):
            return posterior(E, spans, am, b, anchors_p=ap)
        grid = name(segs[segs.group == "M"], None, bounds)
    true_E = pd.DataFrame([dict(chrom=c, cm=x) for c in S.CHROM_CM
                           for x in _switches(sim.genomes["F"]["M"][c], P_set)], columns=["chrom", "cm"])

    def carried(c, x):    # does any sibling carry the father's maternal copy here?
        return any(sim.copy_at(s, "F", c, x) in G_set for s in sibs)
    visible = [r for r in true_E.itertuples() if carried(r.chrom, max(r.cm - 0.5, 0))
               and carried(r.chrom, r.cm + 0.5)]
    hit = lambda c, x, D: len(D) and (np.abs(D[D.chrom == c].cm.to_numpy() - x) <= NEAR_CM).any()
    found = sum(bool(hit(r.chrom, r.cm, E)) for r in visible)
    right = sum(bool(hit(r.chrom, r.cm, true_E)) for r in E.itertuples())
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
        gr = name(anchors[anchors.match != m], None, bounds)
        loo.append(mean_pm(gr, anchors[anchors.match == m]).get("M", np.nan))
    ct = copy_test(name, segs[segs.group.isin(["P", "M"])], bounds, n_perm=500, seed=seed)
    return dict(seed=seed, true_edges=len(true_E), visible=len(visible), found=found,
                called=len(E), right=right,
                recall=found / max(len(visible), 1), precision=right / max(len(E), 1),
                named=named, naming_acc=ok / max((nm != '').sum(), 1),
                P_on_P=sh.get("P", np.nan), M_on_P=sh.get("M", np.nan),
                full_on_P=sh.get("sister_full", np.nan), half_on_P=sh.get("sister_half", np.nan),
                pM_P=pm.get("P", np.nan), pM_M_loo=np.nanmean(loo) if loo else np.nan,
                pM_full=pm.get("sister_full", np.nan), pM_half=pm.get("sister_half", np.nan),
                copy_diff=ct["diff"], copy_p=ct["p"])


# ------------------------------------------------------------ real data
def real_groups(cfg, code="FM"):
    """Tested relatives by group, from the tree and the lineage claims:
    "child" lines (descendants of the grandparent's other children, one
    line per child; the siblings' parent and an identical twin of theirs
    left out, since the twin is the same meiosis), "sister" lines
    (descendants of her mother's other children), and claims through her
    father (code+"F": "P") or her mother (code+"M": "M"). The parent's
    own line and an identical twin's are "skip". Returns
    {name key: (group, line)}."""
    import assertions
    import gedcom_io
    import identity
    import pandas as pd
    tree, proband = gedcom_io.load(cfg)
    anc = {c: x for x, c in tree.ancestors(tree.id(proband)) if len(c) <= len(code) + 1}
    G, par = anc[code], anc[code[:-1]] if len(code) > 1 else tree.id(proband)
    twins = {tree.id(t["a"]): tree.id(t["b"]) for t in cfg.get("mz_twins", [])}
    skip = {par, twins.get(par), *[a for a, b in twins.items() if b == par]}
    who = {}                                    # tree person -> (group, line)
    for ch in tree.children(G):
        for x, _, _ in tree.descendants(ch):
            who[x] = ("skip" if ch in skip else "child", tree.label(ch))
    mother = anc.get(code + "M")
    for sis in (tree.children(mother) if mother else []):
        if sis == G:
            continue
        for x, _, _ in tree.descendants(sis):
            who[x] = ("sister", tree.label(sis))
    D = cfg["data_dir"]
    placed = outputs.read(D, "placed_matches.csv")
    ids = gedcom_io.load_identities(cfg)
    j = gedcom_io.matches_in_tree(tree, proband, placed.drop_duplicates("match"), ids)
    by_label = {tree.label(i): i for i in who}
    confirmed = {gedcom_io._norm(k) for k in ids}
    tw = {x["a"]: x["b"] for x in cfg.get("mz_twins", [])}
    best = j.groupby(["match", "person"]).shared_cM.max()
    out = {}
    for (m, person), cm in best.items():
        i = by_label.get(person)
        if i is None:
            continue
        # A join by name is kept only if the amount fits: common names join
        # strangers sharing 10-30 cM to lines that should share hundreds.
        exp = 2 * gedcom_io.kinship(tree, tree.id(proband), i, twins=tw) * GENOME_CM
        if gedcom_io._norm(m) not in confirmed and cm < JOIN_MIN_FRAC * exp:
            continue
        out.setdefault(identity.name_key(m), who[i])
    a = assertions.read(D, list(assertions.ANCHOR_SOURCES), kinds={"lineage"})
    L = a.lineage.astype(str)
    for side, grp in (("F", "P"), ("M", "M")):
        for m in a[L.str.startswith(code + side)].match.unique():
            out.setdefault(identity.name_key(m), (grp, grp + ":" + str(m)))
    return out


def run_real(cfg=None, code="FM", sibs=None, use_p=False, method="edges"):
    """The recursion on the family's data: the siblings' segments placed on
    the grandparent `code` (10 cM and up), grouped by real_groups. Prints a
    summary and returns (edges, grid, segments, test numbers). use_p names
    with the father side too (for a grandparent whose father is not in
    question: a check of the naming on real data). method "joint" names
    through posterior_joint, reading where each sibling carries the copy
    from the painting."""
    import config
    import identity
    import intervals as iv
    cfg = cfg or config.load()
    D = cfg["data_dir"]
    gm = iv.GeneticMap.load(cfg, quiet=True)
    groups = real_groups(cfg, code)
    s = outputs.read(D, "placed_segments.csv", dtype={"chrom": str})
    lab = outputs.read(D, "phasing_copy_labels.csv", dtype={"chrom": str})
    sibs = sibs or sorted(lab.sibling.unique())
    s = s[s.subject.isin(sibs) & (s.grandparent == code) & (s.cM >= MIN_CM) & (s.chrom != "X")].copy()
    s["nk"] = s.match.map(identity.name_key)
    rest = s[~s.nk.isin(groups)].copy()
    s = s[s.nk.map(lambda k: k in groups and groups[k][0] != "skip")]
    s["group"] = s.nk.map(lambda k: groups[k][0])
    s["line"] = s.nk.map(lambda k: groups[k][1])
    s["start_cm"] = [float(gm.cm(c, x)) for c, x in zip(s.chrom, s.start)]
    s["end_cm"] = [float(gm.cm(c, x)) for c, x in zip(s.chrom, s.end)]
    xo = []
    for (sib, c), g in lab[lab.parent == code[0]].sort_values("start").groupby(["sibling", "chrom"]):
        g = g.reset_index(drop=True)
        xo += [dict(chrom=c, cm=float(gm.cm(c, (g.end[i - 1] + g.start[i]) / 2)))
               for i in range(1, len(g)) if g.label[i] != g.label[i - 1]]
    xo = pd.DataFrame(xo, columns=["chrom", "cm"])
    allfm = outputs.read(D, "placed_segments.csv", dtype={"chrom": str})
    allfm = allfm[allfm.subject.isin(sibs) & (allfm.grandparent == code) & (allfm.chrom != "X")]
    bounds = {c: (float(gm.cm(c, g.start.min())), float(gm.cm(c, g.end.max())))
              for c, g in allfm.groupby("chrom")}
    E = edges(s[s.group == "child"], xo, bounds, min_lines=1, spans=s)
    if method == "joint":
        pt = outputs.read(D, "phasing_grandparent_segments.csv", dtype={"chrom": str})
        pt = pt[pt.subject.isin(sibs) & (pt.lineage == code)]
        carry = {(r.subject, r.chrom): [] for r in pt.itertuples()}
        for r in pt.itertuples():
            carry[(r.subject, r.chrom)].append((float(gm.cm(r.chrom, r.start)), float(gm.cm(r.chrom, r.end))))

        def vis_fn(c, x):
            out = {}
            for sb in sibs:
                v = np.zeros(len(x), bool)
                for a, b in carry.get((sb, c), []):
                    v |= (x > a) & (x < b)
                out[sb] = v
            return out
        child, nc = s[s.group == "child"], s[s.group != "child"]

        def name(am, ap, b):
            return posterior_joint(child, nc, am, b, vis_fn, anchors_p=ap)
        grid = name(s[s.group == "M"], None, bounds)
        E = joint_edges(grid).assign(lines=0)
    else:
        def name(am, ap, b):
            return posterior(E, s, am, b, anchors_p=ap)
        grid = name(s[s.group == "M"], None, bounds)
    pm = mean_pm(grid, s[s.group.isin(["P", "sister"])])
    loo, anchors = [], s[s.group == "M"]
    for m in anchors.nk.unique():
        gr = name(anchors[anchors.nk != m], None, bounds)
        loo.append(mean_pm(gr, anchors[anchors.nk == m]).get("M", np.nan))
    per = {}
    for (grp, line), g in s.groupby(["group", "line"]):
        per[(grp, line)] = (len(g), round(g.cM.sum()), round(mean_pm(grid, g.assign(group="x")).get("x", np.nan), 2))
    res = dict(lines=s[s.group == "child"].line.nunique(), segs=s.groupby("group").size().to_dict(),
               edges=len(E), edges_3plus=int((E.lines >= 3).sum()) if len(E) else 0,
               named=float((grid.name != "").mean()),
               pM_P=pm.get("P", np.nan), pM_M_loo=float(np.nanmean(loo)) if loo else np.nan,
               pM_sister=pm.get("sister", np.nan))
    ct = copy_test(name, s[s.group.isin(["P", "M"])], bounds, use_p=use_p)
    res.update(copy_diff=ct["diff"], copy_p=ct["p"], held_out_acc=ct["acc"], n_P=ct["n_P"], n_M=ct["n_M"])
    # The matches no group explains, read on a grid named from both sides:
    # a list of whom to ask (or recruit), not evidence for the copy test,
    # since for a contested father the P side is the question.
    rest["start_cm"] = [float(gm.cm(c, x)) for c, x in zip(rest.chrom, rest.start)]
    rest["end_cm"] = [float(gm.cm(c, x)) for c, x in zip(rest.chrom, rest.end)]
    both = name(s[s.group == "M"], s[s.group == "P"], bounds)
    res["others"] = read_others(both, rest)
    return E, grid, s, res, per


def read_others(grid, segs, step=STEP_CM):
    """Per match (column `match`): the siblings sharing its segments here,
    its largest one-sibling cM, the mean P(M) over its segments' cells, and
    the cM on cells read M (p_M > 0.8) and P (p_M < 0.2), summed over
    siblings. Sorted by cM read M: whom to ask first for the mother's side."""
    rows = []
    for m, g in segs.groupby("match"):
        on = {"M": 0.0, "P": 0.0}
        tot, n = 0.0, 0
        for c, gc in g.groupby("chrom"):
            G = grid[grid.chrom == c]
            for r in gc.itertuples():
                v = G.p_M[(G.cm > r.start_cm) & (G.cm < r.end_cm)].to_numpy()
                tot, n = tot + v.sum(), n + len(v)
                on["M"] += (v > 0.8).sum() * step
                on["P"] += (v < 0.2).sum() * step
        rows.append(dict(match=m, sibs=g.subject.nunique(),
                         cM=round(g.groupby("subject").cM.sum().max(), 1),
                         p_M=round(tot / n, 2) if n else np.nan,
                         cM_M=round(on["M"], 1), cM_P=round(on["P"], 1)))
    cols = ["match", "sibs", "cM", "p_M", "cM_M", "cM_P"]
    return pd.DataFrame(rows, columns=cols).sort_values(["cM_M", "cM"], ascending=False, ignore_index=True)


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
    import sys
    pd.set_option("display.width", 200)
    if "--real" in sys.argv:          # private output: names matches
        # --real [CODE] [--use-p] [--joint] [--others]: e.g. --real MF --use-p checks the naming
        # on a grandparent whose father is not in question
        i = sys.argv.index("--real")
        code = sys.argv[i + 1] if len(sys.argv) > i + 1 and not sys.argv[i + 1].startswith("-") else "FM"
        E, grid, segs, res, per = run_real(code=code, use_p="--use-p" in sys.argv,
                                           method="joint" if "--joint" in sys.argv else "edges")
        others = res.pop("others")
        print({k: (round(float(v), 3) if isinstance(v, (float, np.floating)) else v) for k, v in res.items()})
        if "--others" in sys.argv:    # whom to ask: matches no group explains
            import config
            outputs.write(config.load()["data_dir"], f"grandparent_copies_{code}_others.csv", others)
            print(others.head(25).to_string(index=False))
        for (grp, line), (n, cm, pm) in sorted(per.items()):
            print(f"{grp:7} {n:3} segs {cm:5} cM  P(M) {pm:.2f}  {line}")
        sys.exit()
    cols = ["depth", "children", "min_lines", "visible", "recall", "precision", "named",
            "naming_acc", "P_on_P", "M_on_P", "full_on_P", "half_on_P"]
    print(sweep()[cols].to_string(index=False))
