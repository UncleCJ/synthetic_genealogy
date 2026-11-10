"""
The copy model: for one tester, a belief along each chromosome about which
ancestor each of the two copies came from, sharpened by whatever evidence
there is. First version: a single donor, evidence = descent claims on
match segments (docs/design-copy-model.md).

State. The paternal copy and the maternal copy are modelled apart (a claim
with a lineage code says which copy it is about: codes start with F or
M). Each copy's state is its lineage code at a chosen `depth`: depth 3
gives four states per copy (FFF FFM FMF FMM for the paternal one).

Transitions. Moving along the chromosome, letter j of the code changes
when the meiosis of the ancestor at level j - 1 had a crossover there
(probability from the genetic map, Haldane). When letter j changes, the
deeper letters now refer to another person's genome, so they are drawn
afresh. One map for all meioses for now (sex-averaged).

Evidence. A claim "this segment's match descends via code c" (c at least
two letters, so that it says more than the side) says the copy c[0] is
under c throughout the segment, unless the claim is wrong. Its weight w is
the chance that it is right: the link's confidence times the chance that
a segment of that length is real (short vendor segments are often false,
FALSE_AT). The claim enters as the factor (1 - w) + w * [state under c] on
the grid points inside the segment, tempered so that the whole segment
counts as one observation. Overlapping segments of one match count once
(merged). Not yet used: segment ends as crossover votes, genotypes,
siblings, a parent's kit (see the design note).

Output. Forward-backward posteriors per grid point (STEP_CM apart), blocks
of the most likely state with their mean posterior, and per claim a
leave-one-out verdict: the posterior that its copy is under its code,
computed without the claim itself.

Sketch, unvalidated beyond the simulator (tests/test_copy_model.py).
"""
from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd

import intervals as iv
import lineage as lin

STEP_CM = 0.5
FALSE_AT = 7.0          # a vendor segment of FALSE_AT cM is real with probability 1/2
FALSE_SCALE = 2.0       # ... rising with length on this scale (logistic)
CHROM_END_CM = {c: None for c in iv.AUTOSOMES}


def states(side, depth):
    """Lineage codes of one copy at `depth` (side "F" or "M")."""
    return [side + "".join(t) for t in product("FM", repeat=depth - 1)]


def transition(depth, r):
    """S x S matrix for one step with crossover probability r per meiosis."""
    S = states("F", depth)
    T = np.zeros((len(S), len(S)))
    for i, a in enumerate(S):
        for j, b in enumerate(S):
            p, broke = 1.0, False
            for k in range(1, depth):
                if broke:
                    p *= 0.5                     # deeper letters drawn afresh
                elif a[k] != b[k]:
                    p *= r
                    broke = True
                else:
                    p *= 1 - r
            T[i, j] = p
    return T / T.sum(1, keepdims=True)


def real_probability(cM):
    """Chance that a vendor segment of cM length is real IBD (logistic in cM)."""
    return 1 / (1 + np.exp(-(np.asarray(cM, float) - FALSE_AT) / FALSE_SCALE))


def weight_to_confidence(weight):
    """The assertion weights used by the phasing (documented 10, confirmed
    tree link 3, name join 1, DNA Painter 1) as a chance the link is right."""
    return 1 - 0.5 ** np.asarray(weight, float)


def _forward_backward(E, T):
    """E: n x S per-point likelihoods; T: S x S. Returns n x S posteriors."""
    n, S = E.shape
    a = np.zeros((n, S))
    v = np.full(S, 1 / S) * E[0]
    a[0] = v / v.sum()
    for t in range(1, n):
        v = (a[t - 1] @ T) * E[t]
        a[t] = v / v.sum()
    b = np.ones((n, S))
    for t in range(n - 2, -1, -1):
        v = T @ (E[t + 1] * b[t + 1])
        b[t] = v / v.sum()
    post = a * b
    return post / post.sum(1, keepdims=True)


class CopyModel:
    """Fit with claims for one tester: DataFrame with chrom, start, end
    (bp), lineage (code), w (0..1), claim_id; optional cM."""

    def __init__(self, genetic_map=None, depth=3, step_cm=STEP_CM):
        self.gm = genetic_map or iv.GeneticMap.flat()
        self.depth, self.step = depth, step_cm
        r = 0.5 * (1 - np.exp(-2 * step_cm / 100))         # Haldane
        self.T = transition(depth, r)

    def _grid(self, chrom, claims, length_cm=None):
        hi = length_cm if length_cm is not None else (
            float(self.gm.cm(chrom, self.gm.points[chrom][0][-1])) if not self.gm.is_flat
            else max(float(self.gm.cm(chrom, claims.end.max())) if len(claims) else 0, 1.0) + 1)
        return np.arange(0, hi + self.step, self.step)

    def fit(self, claims, lengths_cm=None):
        """claims: see class doc. lengths_cm: {chrom: length} for the grid
        (else from the map, or the claims). Returns self."""
        c = claims.copy()
        c["chrom"] = c.chrom.astype(str)
        c = c[c.lineage.astype(str).str.len() >= 2]
        c["a_cm"] = [float(self.gm.cm(ch, x)) for ch, x in zip(c.chrom, c.start)]
        c["b_cm"] = [float(self.gm.cm(ch, x)) for ch, x in zip(c.chrom, c.end)]
        c["code"] = c.lineage.astype(str).str[: self.depth]
        self.claims = c
        self.post, self.grid = {}, {}
        for chrom, cc in c.groupby("chrom"):
            grid = self._grid(chrom, cc, (lengths_cm or {}).get(chrom))
            self.grid[chrom] = grid
            for side in "FM":
                self.post[(chrom, side)] = self._posterior(grid, cc[cc.code.str[0] == side], side)
        return self

    def _factors(self, grid, cc, side, skip=None):
        S = states(side, self.depth)
        logE = np.zeros((len(grid), len(S)))
        for r in cc.itertuples():
            if skip is not None and r.claim_id == skip:
                continue
            inside = (grid >= r.a_cm) & (grid <= r.b_cm)
            n = inside.sum()
            if not n:
                continue
            compat = np.array([s.startswith(r.code) for s in S], float)
            f = (1 - r.w) + r.w * compat
            logE[inside] += np.log(f) / n                    # the segment counts once
        return np.exp(logE - logE.max(1, keepdims=True))

    def _posterior(self, grid, cc, side):
        if not len(cc):
            return np.full((len(grid), 2 ** (self.depth - 1)), 1 / 2 ** (self.depth - 1))
        return _forward_backward(self._factors(grid, cc, side), self.T)

    # --------------------------------------------------------- reading it
    def at(self, chrom, side, pos_bp):
        """Posterior over the copy's states at bp positions (n x S)."""
        chrom = str(chrom)
        cm = self.gm.cm(chrom, pos_bp)
        g, P = self.grid.get(chrom), self.post.get((chrom, side))
        if g is None:
            return np.full((np.size(cm), 2 ** (self.depth - 1)), 1 / 2 ** (self.depth - 1))
        idx = np.clip(np.searchsorted(g, cm), 0, len(g) - 1)
        return P[idx]

    def marginal(self, chrom, side, pos_bp, code):
        """P(copy under `code`) at positions (code shorter than depth sums
        over its states)."""
        S = states(side, self.depth)
        sel = np.array([s.startswith(code[: self.depth]) for s in S])
        return self.at(chrom, side, pos_bp)[:, sel].sum(1)

    def blocks(self, level=None, min_post=0.0):
        """Runs of the most likely code at `level` letters (default depth),
        per chromosome and copy: chrom, side, start_cm, end_cm, start, end
        (bp), lineage, posterior (mean over the run)."""
        level = level or self.depth
        rows = []
        for (chrom, side), P in self.post.items():
            S = states(side, self.depth)
            codes = sorted({s[:level] for s in S})
            M = np.stack([P[:, [s.startswith(k) for s in S]].sum(1) for k in codes], 1)
            best = M.argmax(1)
            g = self.grid[chrom]
            starts = np.flatnonzero(np.r_[True, best[1:] != best[:-1]])
            ends = np.r_[starts[1:], len(best)]
            for a, b in zip(starts, ends):
                p = float(M[a:b, best[a]].mean())
                if p < min_post:
                    continue
                rows.append(dict(chrom=chrom, side=side, start_cm=g[a], end_cm=g[b - 1],
                                 start=float(self.gm.bp(chrom, g[a])), end=float(self.gm.bp(chrom, g[b - 1])),
                                 lineage=codes[best[a]], posterior=round(p, 3)))
        return pd.DataFrame(rows)

    def verdicts(self):
        """Per claim: the posterior, without that claim, that its copy is
        under its code over the segment (leave-one-out), and the verdict."""
        rows = []
        for r in self.claims.itertuples():
            grid = self.grid[r.chrom]
            side = r.code[0]
            cc = self.claims[(self.claims.chrom == r.chrom) & (self.claims.code.str[0] == side)]
            P = _forward_backward(self._factors(grid, cc, side, skip=r.claim_id), self.T)
            inside = (grid >= r.a_cm) & (grid <= r.b_cm)
            S = states(side, self.depth)
            sel = np.array([s.startswith(r.code) for s in S])
            p = float(P[inside][:, sel].sum(1).mean()) if inside.any() else float("nan")
            prior = sel.mean()
            rows.append(dict(claim_id=r.claim_id, chrom=r.chrom, lineage=r.lineage, code=r.code,
                             support=round(p, 3), prior=round(float(prior), 3),
                             verdict=("agrees" if p >= 0.5 + prior / 2 else
                                      "conflicts" if p <= prior / 2 else "unclear")))
        return pd.DataFrame(rows)


def claims_from_segments(segs, via, link_confidence=0.95, gm=None):
    """Simulated or real match segments + {match: via code} -> claims for
    one tester (overlapping segments of a match merged: counted once)."""
    gm = gm or iv.GeneticMap.flat()
    rows = []
    for (m, chrom), g in segs[segs.match.isin(via)].groupby(["match", "chrom"]):
        for a, b in iv.merge(zip(g.start, g.end)):
            cm = float(gm.length(chrom, a, b))
            rows.append(dict(match=m, chrom=str(chrom), start=a, end=b, cM=cm, lineage=via[m],
                             w=float(link_confidence * real_probability(cm))))
    out = pd.DataFrame(rows)
    out["claim_id"] = [f"{r.match}:{r.chrom}:{int(r.start)}" for r in out.itertuples()]
    return out


def accuracy(model, sim, who, level, n=2000, seed=0, chroms=None):
    """Against a simulation's truth: per copy, the share of random
    positions where the most likely code at `level` is right, overall and
    where the posterior is at least 0.9 (with that share of the genome)."""
    import simulate as sm
    rng = np.random.default_rng(seed)
    chroms = chroms or list(model.grid)
    out = {}
    for side in "FM":
        right, conf, conf_right = 0, 0, 0
        S = states(side, model.depth)
        codes = sorted({s[:level] for s in S})
        for _ in range(n):
            c = str(rng.choice(chroms))
            cm = rng.uniform(0, sm.CHROM_CM[c])
            bp = float(model.gm.bp(c, cm))
            truth = sim.lineage(who, c, bp)["FM".index(side)][:level]
            P = model.at(c, side, [bp])[0]
            m = np.array([P[[s.startswith(k) for s in S]].sum() for k in codes])
            call = codes[int(m.argmax())]
            right += call == truth
            if m.max() >= 0.9:
                conf += 1
                conf_right += call == truth
        out[side] = dict(accuracy=right / n, called_share=conf / n,
                         accuracy_when_called=conf_right / conf if conf else float("nan"))
    return out


def compare_with_painting(model, paint, subject, threshold=0.9):
    """bp-weighted agreement at grandparent level with a painting
    (phasing_grandparent_segments.csv rows of one subject): overall
    (most likely code) and where the model is at least `threshold` sure,
    with the share of the painted genome that is."""
    tot = agree = conf = conf_agree = 0.0
    p = paint[(paint.subject == subject) & paint.lineage.isin(lin.GRANDPARENTS)]
    for r in p.itertuples():
        pos = np.linspace(r.start, r.end, max(2, int((r.end - r.start) / 2e5)))
        w = (r.end - r.start) / len(pos)
        S = states(r.parent, model.depth)
        codes = [r.parent + "F", r.parent + "M"]
        P = model.at(r.chrom, r.parent, pos)
        M = np.stack([P[:, [s.startswith(k) for s in S]].sum(1) for k in codes], 1)
        ok = np.array(codes)[M.argmax(1)] == r.lineage
        sure = M.max(1) >= threshold
        tot += w * len(pos)
        agree += w * ok.sum()
        conf += w * sure.sum()
        conf_agree += w * (ok & sure).sum()
    return dict(agreement=agree / tot if tot else float("nan"), sure_share=conf / tot if tot else float("nan"),
                agreement_when_sure=conf_agree / conf if conf else float("nan"))


def claims_for(data_dir, subject, sources, gm):
    """A tester's lineage assertions as claims (weights as confidences)."""
    import assertions
    a = assertions.read(data_dir, sources, kinds={"lineage"})
    a = a[(a.subject == subject) & a.chrom.astype(str).isin(iv.AUTOSOMES)].copy()
    a["chrom"] = a.chrom.astype(str)
    a["cM"] = [float(gm.length(c, s, e)) for c, s, e in zip(a.chrom, a.start, a.end)]
    w = pd.to_numeric(a.weight, errors="coerce").fillna(1.0)
    a["w"] = weight_to_confidence(w) * real_probability(a.cM)
    a["claim_id"] = a.assertion_id
    return a[["claim_id", "chrom", "start", "end", "lineage", "w", "cM", "source_kind"]]


def main():
    """Beside the current painting, not instead of it: one copy model per
    tester from that tester's own lineage assertions ([phasing] anchors
    sources), no genotypes. Writes copy_model_blocks.csv and
    copy_model_verdicts.csv, and compares with the painting."""
    import config
    import outputs
    cfg = config.load()
    D = cfg["data_dir"]
    gm = iv.GeneticMap.load(cfg, quiet=True)
    lengths = {c: float(gm.points[c][1][-1]) for c in gm.points} if not gm.is_flat else None
    sources = config.anchor_sources(cfg)
    import assertions
    subjects = sorted(assertions.read(D, sources, kinds={"lineage"}).subject.dropna().unique())
    paint = (outputs.read(D, "phasing_grandparent_segments.csv", dtype={"chrom": str})
             if outputs.has(D, "phasing_grandparent_segments.csv") else None)
    blocks, verdicts = [], []
    print(f"copy model: depth 3, map {gm.name}, evidence: {', '.join(sources)} (no genotypes)")
    for subj in subjects:
        cl = claims_for(D, subj, sources, gm)
        m = CopyModel(gm, depth=3).fit(cl, lengths_cm=lengths)
        blocks.append(m.blocks(level=3).assign(subject=subj, level=3))
        blocks.append(m.blocks(level=2).assign(subject=subj, level=2))
        verdicts.append(m.verdicts().assign(subject=subj).merge(
            cl[["claim_id", "source_kind", "cM"]], on="claim_id", how="left"))
        line = f"  {subj:12s} {len(cl):5d} claims"
        if paint is not None:
            c = compare_with_painting(m, paint, subj)
            line += (f"; vs the painting: {c['agreement']:.1%} agree, sure (>= 0.9) on "
                     f"{c['sure_share']:.1%} of it, agreeing there {c['agreement_when_sure']:.1%}")
        print(line)
    outputs.write(D, "copy_model_blocks.csv", pd.concat(blocks, ignore_index=True))
    v = pd.concat(verdicts, ignore_index=True)
    outputs.write(D, "copy_model_verdicts.csv", v)
    print(pd.crosstab(v.source_kind, v.verdict).to_string())


if __name__ == "__main__":
    main()
