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
(merged).

Segment ends are soft crossover votes (_end_transitions): an end is, with
probability END_CROSSOVER (1/2: half the meioses that can cut a shared
segment are on our side) times the claim's weight, a crossover on our
copy, spread over the meioses on our side and placed with END_SD_CM
spread. On simulated families this made conflicts a more reliable sign of
a false segment (81% false, from 64%) and left accuracy as it was (slightly
up), at the price of fewer confident calls. Every setting is somewhat
underconfident (calls at 0.7-0.9 are right 84-90% of the time): counting
each segment once is conservative; calibrating that is open.

Phased siblings (SiblingCopyModel): the phasing's copy labels per sibling
and parent (phasing_labels.copy_label_runs) let all siblings' claims name
one shared state per parent. On simulated families this takes confident
grandparent calls from 15% of the genome to 94% (right 99.8% of the time).
Unlike the painting, which names the copies once per chromosome by
majority vote, it can follow the claims where the phasing's labels flip
meaning (two siblings recombining at one spot looks the same as one doing
so, from sibling data alone).

Not yet used: a parent's kit beyond the phasing, sex-specific maps (see the
design note).

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
# segment ends: an end is a crossover on the tester's own copy with this
# probability (times the claim's weight), placed with this spread (cM)
END_CROSSOVER = 0.5
END_SD_CM = 1.0


def states(side, depth):
    """Lineage codes of one copy at `depth` (side "F" or "M")."""
    return [side + "".join(t) for t in product("FM", repeat=depth - 1)]


def transition(depth, r):
    """S x S matrix for one step with crossover probability r per meiosis
    (a number, or one per letter 2..depth)."""
    S = states("F", depth)
    rs = np.broadcast_to(np.asarray(r, float), (depth - 1,))
    T = np.zeros((len(S), len(S)))
    for i, a in enumerate(S):
        for j, b in enumerate(S):
            p, broke = 1.0, False
            for k in range(1, depth):
                if broke:
                    p *= 0.5                     # deeper letters drawn afresh
                elif a[k] != b[k]:
                    p *= rs[k - 1]
                    broke = True
                else:
                    p *= 1 - rs[k - 1]
            T[i, j] = p
    return T / T.sum(1, keepdims=True)


def real_probability(cM):
    """Chance that a vendor segment of cM length is real IBD (logistic in cM)."""
    return 1 / (1 + np.exp(-(np.asarray(cM, float) - FALSE_AT) / FALSE_SCALE))


def weight_to_confidence(weight):
    """The assertion weights used by the phasing (documented 10, confirmed
    tree link 3, name join 1, DNA Painter 1) as a chance the link is right."""
    return 1 - 0.5 ** np.asarray(weight, float)


def _forward_backward(E, T, Tt=None):
    """E: n x S per-point likelihoods; T: S x S; Tt: {t: S x S} for the
    steps into point t that differ (segment ends). Returns n x S posteriors."""
    n, S = E.shape
    Tt = Tt or {}
    a = np.zeros((n, S))
    v = np.full(S, 1 / S) * E[0]
    a[0] = v / v.sum()
    for t in range(1, n):
        v = (a[t - 1] @ Tt.get(t, T)) * E[t]
        a[t] = v / v.sum()
    b = np.ones((n, S))
    for t in range(n - 2, -1, -1):
        v = Tt.get(t + 1, T) @ (E[t + 1] * b[t + 1])
        b[t] = v / v.sum()
    post = a * b
    return post / post.sum(1, keepdims=True)


class CopyModel:
    """Fit with claims for one tester: DataFrame with chrom, start, end
    (bp), lineage (code), w (0..1), claim_id; optional cM."""

    def __init__(self, genetic_map=None, depth=3, step_cm=STEP_CM, ends=True,
                 end_sd_cm=END_SD_CM, end_crossover=END_CROSSOVER):
        self.gm = genetic_map or iv.GeneticMap.flat()
        self.depth, self.step = depth, step_cm
        self.r = 0.5 * (1 - np.exp(-2 * step_cm / 100))    # Haldane
        self.T = transition(depth, self.r)
        self.ends, self.end_sd, self.end_q = ends, end_sd_cm, end_crossover

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

    def _end_transitions(self, grid, cc, skip=None):
        """Segment ends as soft crossover votes: {grid index: S x S}.

        A segment shared via code c (k letters) is cut by a crossover in
        any of the meioses along the shared path: k + 1 on our side (the
        parent's, the grandparent's, ..., the couple member's down to c),
        as many on the match's side. So an end is, with probability end_q *
        w (end_q about 1/2), a crossover on our copy, spread evenly over
        those k + 1 meioses; the meiosis of the ancestor with code c[:j]
        changes letter j + 1. Letters deeper than the model's depth are not
        modelled, so their share of the vote is simply lost. The crossover
        is placed with normal spread end_sd_cm around the end. Ends near a
        chromosome's ends are left out (cut there, not recombined)."""
        if not self.ends or not len(cc):
            return {}
        from math import erf, sqrt
        top = grid[-1]
        keep = {}                                 # t -> per-level product of (1 - b)
        L = self.depth - 1
        for r in cc.itertuples():
            if skip is not None and r.claim_id == skip:
                continue
            k_len = len(r.lineage)                               # full depth of the claim
            per = self.end_q * r.w / (k_len + 1)                 # per meiosis on our side
            letters = range(2, min(self.depth, k_len + 2) + 1)  # modelled letters it can change
            for e in (r.a_cm, r.b_cm):
                if e < 2 * self.end_sd or e > top - 2 * self.end_sd:
                    continue
                lo = np.searchsorted(grid, e - 3 * self.end_sd)
                hi = np.searchsorted(grid, e + 3 * self.end_sd)
                for t in range(max(lo, 1), min(hi + 1, len(grid))):
                    a, b = grid[t - 1], grid[t]
                    mass = 0.5 * (erf((b - e) / (self.end_sd * sqrt(2))) - erf((a - e) / (self.end_sd * sqrt(2))))
                    q = per * mass
                    if q <= 1e-7:
                        continue
                    k = keep.setdefault(t, np.ones(L))
                    for j in letters:
                        k[j - 2] *= 1 - q
        return {t: transition(self.depth, 1 - (1 - self.r) * k) for t, k in keep.items()}

    def _posterior(self, grid, cc, side, skip=None):
        if not len(cc):
            return np.full((len(grid), 2 ** (self.depth - 1)), 1 / 2 ** (self.depth - 1))
        return _forward_backward(self._factors(grid, cc, side, skip=skip), self.T,
                                 self._end_transitions(grid, cc, skip=skip))

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
            P = self._posterior(grid, cc, side, skip=r.claim_id)
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


class SiblingCopyModel(CopyModel):
    """Full siblings phased against each other (phasing_labels.
    copy_label_runs): per parent, each sibling's label says which of that
    parent's two copies it carries. The copy model then holds one belief
    per parent, shared by all siblings: which label is the grandfather's
    copy (h), and the deeper letters on each of the two copies (d0, d1).
    Every sibling's claims inform the same state, so a label named by one
    sibling's relative is named for all who carry that copy, and the
    siblings' own crossovers come from the phasing, not from the claims.

    State per parent P at depth D: (h, d0, d1), h in {0, 1} (copy `h` is
    grandparent P+"F"), d0, d1 the D-2 deeper letters of each copy; 8
    states at depth 3. A sibling with label g there is under
    P + ("F" if g == h else "M") + d_g. h is constant along a chromosome
    (a small rate H_SWITCH allows for phasing errors); each copy's deeper
    letters change at crossovers in the meioses above the parent (per
    copy, as transition() for those letters). Segment ends vote for those
    deeper crossovers on the copy the sibling carries there; the sibling's
    own crossovers (letter 2) are known from the labels already.
    Sketch: phasing errors in the labels are only absorbed by H_SWITCH and
    the soft claims; no genotype likelihood enters here."""

    H_SWITCH = 1e-4

    def __init__(self, labels, genetic_map=None, depth=3, **kw):
        super().__init__(genetic_map, depth=depth, **kw)
        self.labels = labels.assign(chrom=labels.chrom.astype(str))
        self.sub = [s[1:] for s in states("F", depth - 1)]          # deeper letters: "F", "M" at depth 3
        n = len(self.sub)
        self.joint = [(h, i, j) for h in (0, 1) for i in range(n) for j in range(n)]
        Th = np.array([[1 - self.H_SWITCH, self.H_SWITCH], [self.H_SWITCH, 1 - self.H_SWITCH]])
        self.Tsub = transition(depth - 1, self.r) if depth > 2 else np.ones((1, 1))
        self.T = np.kron(Th, np.kron(self.Tsub, self.Tsub))
        self.Th = Th

    def _label_at(self, chrom, sib, side, grid):
        L = self.labels[(self.labels.chrom == chrom) & (self.labels.sibling == sib) & (self.labels.parent == side)]
        out = np.full(len(grid), -1)
        for r in L.itertuples():
            a, b = float(self.gm.cm(chrom, r.start)), float(self.gm.cm(chrom, r.end))
            out[(grid >= a) & (grid <= b)] = r.label
        return out

    def lineage_of(self, state, g, side):
        h, i, j = state
        return side + ("F" if g == h else "M") + self.sub[i if g == 0 else j]

    def fit(self, claims, lengths_cm=None):
        """claims: as CopyModel, plus `subject` (the sibling)."""
        c = claims.copy()
        c["chrom"] = c.chrom.astype(str)
        c = c[c.lineage.astype(str).str.len() >= 2]
        c["a_cm"] = [float(self.gm.cm(ch, x)) for ch, x in zip(c.chrom, c.start)]
        c["b_cm"] = [float(self.gm.cm(ch, x)) for ch, x in zip(c.chrom, c.end)]
        c["code"] = c.lineage.astype(str).str[: self.depth]
        self.claims = c
        self.sibs = sorted(self.labels.sibling.unique())
        self.post, self.grid, self.g = {}, {}, {}
        for chrom in sorted(set(self.labels.chrom)):
            cc = c[c.chrom == chrom]
            grid = self._grid(chrom, cc, (lengths_cm or {}).get(chrom))
            self.grid[chrom] = grid
            for side in "FM":
                self.g[(chrom, side)] = {s: self._label_at(chrom, s, side, grid) for s in self.sibs}
                self.post[(chrom, side)] = self._joint_posterior(chrom, side, cc[cc.code.str[0] == side])
        return self

    def _joint_factors(self, chrom, side, cc, skip=None):
        grid = self.grid[chrom]
        logE = np.zeros((len(grid), len(self.joint)))
        for r in cc.itertuples():
            if skip is not None and r.claim_id == skip:
                continue
            g = self.g[(chrom, side)].get(r.subject)
            if g is None:
                continue
            inside = np.flatnonzero((grid >= r.a_cm) & (grid <= r.b_cm) & (g >= 0))
            if not len(inside):
                continue
            f = np.empty((len(inside), len(self.joint)))
            for k, st in enumerate(self.joint):
                compat = np.array([self.lineage_of(st, gg, side).startswith(r.code) for gg in (0, 1)], float)
                f[:, k] = (1 - r.w) + r.w * compat[g[inside]]
            logE[inside] += np.log(f) / len(inside)
        return np.exp(logE - logE.max(1, keepdims=True))

    def _joint_ends(self, chrom, side, cc, skip=None):
        """Segment ends: votes for crossovers in the deeper letters of the
        copy the sibling carries at the end (letters 3 ..)."""
        if not self.ends or not len(cc) or self.depth < 3:
            return {}
        from math import erf, sqrt
        grid = self.grid[chrom]
        top, L = grid[-1], self.depth - 2
        keep = {}
        for r in cc.itertuples():
            if skip is not None and r.claim_id == skip:
                continue
            g = self.g[(chrom, side)].get(r.subject)
            if g is None:
                continue
            k_len = len(r.lineage)
            per = self.end_q * r.w / (k_len + 1)
            letters = range(3, min(self.depth, k_len + 2) + 1)
            for e in (r.a_cm, r.b_cm):
                if e < 2 * self.end_sd or e > top - 2 * self.end_sd:
                    continue
                lo = np.searchsorted(grid, e - 3 * self.end_sd)
                hi = np.searchsorted(grid, e + 3 * self.end_sd)
                for t in range(max(lo, 1), min(hi + 1, len(grid))):
                    if g[t] < 0:
                        continue
                    a, b = grid[t - 1], grid[t]
                    mass = 0.5 * (erf((b - e) / (self.end_sd * sqrt(2))) - erf((a - e) / (self.end_sd * sqrt(2))))
                    q = per * mass
                    if q <= 1e-7:
                        continue
                    k = keep.setdefault(t, np.ones((2, L)))
                    for j in letters:
                        k[g[t], j - 3] *= 1 - q
        out = {}
        for t, k in keep.items():
            T0 = transition(self.depth - 1, 1 - (1 - self.r) * k[0])
            T1 = transition(self.depth - 1, 1 - (1 - self.r) * k[1])
            out[t] = np.kron(self.Th, np.kron(T0, T1))
        return out

    def _joint_posterior(self, chrom, side, cc, skip=None):
        if not len(cc):
            return np.full((len(self.grid[chrom]), len(self.joint)), 1 / len(self.joint))
        return _forward_backward(self._joint_factors(chrom, side, cc, skip), self.T,
                                 self._joint_ends(chrom, side, cc, skip))

    # ------------------------------------------------------- per sibling
    def sibling_posterior(self, chrom, side, sib, P=None):
        """n x S posterior over the sibling's own lineage codes (states())."""
        S = states(side, self.depth)
        P = self.post[(chrom, side)] if P is None else P
        g = self.g[(chrom, side)][sib]
        out = np.zeros((len(g), len(S)))
        for k, st in enumerate(self.joint):
            for gg in (0, 1):
                idx = S.index(self.lineage_of(st, gg, side))
                out[g == gg, idx] += P[g == gg, k]
        out[g < 0] = 1 / len(S)
        return out

    def for_sibling(self, sib):
        """A plain CopyModel view of one sibling (at(), blocks(), accuracy())."""
        m = CopyModel(self.gm, depth=self.depth, step_cm=self.step)
        m.grid = self.grid
        m.post = {(c, s): self.sibling_posterior(c, s, sib) for (c, s) in self.post}
        m.claims = self.claims[self.claims.subject == sib]
        return m

    def verdicts(self):
        rows = []
        for r in self.claims.itertuples():
            side = r.code[0]
            cc = self.claims[(self.claims.chrom == r.chrom) & (self.claims.code.str[0] == side)]
            if r.subject not in self.g.get((r.chrom, side), {}):
                continue
            P = self.sibling_posterior(r.chrom, side, r.subject,
                                       self._joint_posterior(r.chrom, side, cc, skip=r.claim_id))
            grid = self.grid[r.chrom]
            inside = (grid >= r.a_cm) & (grid <= r.b_cm)
            S = states(side, self.depth)
            sel = np.array([s.startswith(r.code) for s in S])
            p = float(P[inside][:, sel].sum(1).mean()) if inside.any() else float("nan")
            prior = sel.mean()
            rows.append(dict(claim_id=r.claim_id, subject=r.subject, chrom=r.chrom, lineage=r.lineage,
                             code=r.code, support=round(p, 3), prior=round(float(prior), 3),
                             verdict=("agrees" if p >= 0.5 + prior / 2 else
                                      "conflicts" if p <= prior / 2 else "unclear")))
        return pd.DataFrame(rows)


def claims_from_segments(segs, via, link_confidence=0.95, gm=None):
    """Simulated or real match segments + {match: via code} -> claims for
    one tester (overlapping segments of a match merged: counted once)."""
    gm = gm or iv.GeneticMap.flat()
    rows = []
    for (subj, m, chrom), g in segs[segs.match.isin(via)].groupby(["subject", "match", "chrom"]):
        for a, b in iv.merge(zip(g.start, g.end)):
            cm = float(gm.length(chrom, a, b))
            rows.append(dict(subject=subj, match=m, chrom=str(chrom), start=a, end=b, cM=cm,
                             lineage=via[m], w=float(link_confidence * real_probability(cm))))
    out = pd.DataFrame(rows)
    out["claim_id"] = [f"{r.subject}:{r.match}:{r.chrom}:{int(r.start)}" for r in out.itertuples()]
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
    labels = (outputs.read(D, "phasing_copy_labels.csv", dtype={"chrom": str})
              if outputs.has(D, "phasing_copy_labels.csv") else None)
    phased = sorted(labels.sibling.unique()) if labels is not None else []
    print(f"copy model: depth 3, map {gm.name}, evidence: {', '.join(sources)}"
          + (f"; phased siblings {', '.join(phased)} jointly (labels from the phasing)" if phased else ""))
    claims = {s: claims_for(D, s, sources, gm).assign(subject=s) for s in subjects}
    models = {}
    if phased:
        J = SiblingCopyModel(labels, gm, depth=3).fit(
            pd.concat([claims[s] for s in phased if s in claims], ignore_index=True), lengths_cm=lengths)
        models.update({s: ("siblings", J.for_sibling(s)) for s in phased})
        verdicts.append(J.verdicts().assign(model="siblings").merge(
            J.claims[["claim_id", "source_kind", "cM"]], on="claim_id", how="left"))
    for subj in subjects:
        cl = claims[subj]
        single = CopyModel(gm, depth=3).fit(cl, lengths_cm=lengths)
        verdicts.append(single.verdicts().assign(subject=subj, model="single").merge(
            cl[["claim_id", "source_kind", "cM"]], on="claim_id", how="left"))
        for name, m in [("single", single)] + ([models[subj]] if subj in models else []):
            blocks.append(m.blocks(level=3).assign(subject=subj, level=3, model=name))
            blocks.append(m.blocks(level=2).assign(subject=subj, level=2, model=name))
            line = f"  {subj:12s} {name:8s} {len(cl):5d} claims"
            if paint is not None:
                c = compare_with_painting(m, paint, subj)
                line += (f"; vs the painting: {c['agreement']:.1%} agree, sure (>= 0.9) on "
                         f"{c['sure_share']:.1%} of it, agreeing there {c['agreement_when_sure']:.1%}")
            print(line)
    outputs.write(D, "copy_model_blocks.csv", pd.concat(blocks, ignore_index=True))
    v = pd.concat(verdicts, ignore_index=True)
    outputs.write(D, "copy_model_verdicts.csv", v)
    print(pd.crosstab([v.model, v.source_kind], v.verdict).to_string())


if __name__ == "__main__":
    main()
