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
up), at the price of fewer confident calls.

Calibration (calibration(), 2026-11-10). Counting each segment once left
the single-donor model underconfident (calls it gave 0.8-0.9 were right
97% of the time on simulated families). Counting it twice (EVIDENCE)
brings the expected calibration error at grandparent level from 0.10 to
0.06 and lowers the log loss; on real data the bins the painting can judge
fit too (said 0.85, agreeing 0.88; said 0.93, agreeing 0.94), and the
share it is sure of rises from 21% to 33%. The sibling model is calibrated
counting once (SIBLING_EVIDENCE; ECE 0.03), and overconfident at twice.

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
# How many observations one segment counts as, fitted so that the
# posteriors mean what they say (calibration(); set per model class).
# The single-donor model loses part of a segment's evidence through the
# crossovers it allows inside the segment, so a segment there counts twice;
# in the sibling model the grandparent letter is pinned by the phasing and
# once is right (counting twice makes it overconfident).
EVIDENCE = 2.0
SIBLING_EVIDENCE = 1.0
# placement: a segment goes on a grandparent when the model gives it this
# probability over the segment (a straddled crossover averages lower)
MIN_P = 0.9


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

    EVIDENCE = EVIDENCE
    min_p = MIN_P          # placement (match_placement) reads a grandparent this sure

    def __init__(self, genetic_map=None, depth=3, step_cm=STEP_CM, ends=True,
                 end_sd_cm=END_SD_CM, end_crossover=END_CROSSOVER, evidence=None):
        self.gm = genetic_map or iv.GeneticMap.flat()
        self.depth, self.step = depth, step_cm
        self.r = 0.5 * (1 - np.exp(-2 * step_cm / 100))    # Haldane
        self.T = transition(depth, self.r)
        self.ends, self.end_sd, self.end_q = ends, end_sd_cm, end_crossover
        self.evidence = self.EVIDENCE if evidence is None else evidence

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
            logE[inside] += self.evidence * np.log(f) / n    # the segment counts `evidence` times
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

    def _gp_cumsum(self, chrom, side):
        """Running sum of P(copy under side+"F") along the grid (cached)."""
        cache = self.__dict__.setdefault("_gp_cache", {})
        key = (chrom, side)
        if key not in cache:
            S = states(side, self.depth)
            pf = self.post[key][:, [s[1] == "F" for s in S]].sum(1)
            cache[key] = np.r_[0.0, np.cumsum(pf)]
        return cache[key]

    def grandparent_of(self, chrom, side, start, end):
        """(grandparent code, probability) of the copy on `side` over
        [start, end] bp: the posterior that the copy is under each
        grandparent, averaged over the segment. A segment across a
        crossover of the copy averages towards 1/2."""
        chrom = str(chrom)
        g = self.grid.get(chrom)
        if g is None or (chrom, side) not in self.post:
            return "", 0.5
        a, b = float(self.gm.cm(chrom, start)), float(self.gm.cm(chrom, end))
        i, j = np.searchsorted(g, a), np.searchsorted(g, b, side="right")
        if j <= i:
            i = min(int(np.searchsorted(g, (a + b) / 2)), len(g) - 1)
            j = i + 1
        c = self._gp_cumsum(chrom, side)
        pf = (c[j] - c[i]) / (j - i)
        return (side + "F", float(pf)) if pf >= 0.5 else (side + "M", float(1 - pf))

    def grandparents(self, chrom, side, starts, ends):
        """grandparent_of for many segments of one chromosome and copy at
        once: (codes, probabilities) as arrays, the same numbers."""
        chrom = str(chrom)
        n = len(starts)
        g = self.grid.get(chrom)
        if g is None or (chrom, side) not in self.post:
            return np.full(n, "", object), np.full(n, 0.5)
        a = self.gm.cm(chrom, np.asarray(starts, float))
        b = self.gm.cm(chrom, np.asarray(ends, float))
        i, j = np.searchsorted(g, a), np.searchsorted(g, b, side="right")
        short = j <= i
        i = np.where(short, np.minimum(np.searchsorted(g, (a + b) / 2), len(g) - 1), i)
        j = np.where(short, i + 1, j)
        c = self._gp_cumsum(chrom, side)
        pf = (c[j] - c[i]) / (j - i)
        f = pf >= 0.5
        return np.where(f, side + "F", side + "M").astype(object), np.where(f, pf, 1 - pf)

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
    EVIDENCE = SIBLING_EVIDENCE
    # chance that the phasing's label is wrong at a point: the sibling then
    # carries the other copy (the real phasing agrees with the tested
    # mother on 99.8-100% of each chromosome)
    LABEL_ERROR = 0.005

    def __init__(self, labels, genetic_map=None, depth=3, label_error=None, **kw):
        super().__init__(genetic_map, depth=depth, **kw)
        self.label_error = self.LABEL_ERROR if label_error is None else label_error
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
            logE[inside] += self.evidence * np.log(f) / len(inside)
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
        e = self.label_error
        for k, st in enumerate(self.joint):
            for gg in (0, 1):
                here = g == gg
                out[here, S.index(self.lineage_of(st, gg, side))] += (1 - e) * P[here, k]
                out[here, S.index(self.lineage_of(st, 1 - gg, side))] += e * P[here, k]
        out[g < 0] = 1 / len(S)
        return out

    def for_sibling(self, sib):
        """A plain CopyModel view of one sibling (at(), blocks(), accuracy())."""
        m = CopyModel(self.gm, depth=self.depth, step_cm=self.step, evidence=self.evidence)
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


def place(segs, models, min_p=MIN_P):
    """Placement through the copy model: match segments with a known side
    (`parent`, F/M, from the mother's list as in match_placement) go on
    the grandparent the tester's copy model gives at least `min_p` over
    the segment. Adds cm_grandparent ("" when not sure enough), cm_p (the
    probability of the more likely grandparent), and for segments whose
    side is unknown both readings (cm_if_paternal, cm_if_maternal, "" when
    not sure). models: {subject: CopyModel}; other subjects stay unplaced."""
    gp, pr, if_f, if_m = [], [], [], []
    for r in segs.itertuples():
        m = models.get(r.subject)
        par = r.parent if isinstance(r.parent, str) else ""
        if m is None or str(r.chrom) not in iv.AUTOSOMES:
            gp.append(""); pr.append(np.nan); if_f.append(""); if_m.append("")
            continue
        if par in ("F", "M"):
            code, p = m.grandparent_of(r.chrom, par, r.start, r.end)
            gp.append(code if p >= min_p else ""); pr.append(round(p, 3)); if_f.append(""); if_m.append("")
        else:
            gp.append(""); pr.append(np.nan)
            for side, out in (("F", if_f), ("M", if_m)):
                code, p = m.grandparent_of(r.chrom, side, r.start, r.end)
                out.append(code if p >= min_p else "")
    return segs.assign(cm_grandparent=gp, cm_p=pr, cm_if_paternal=if_f, cm_if_maternal=if_m)


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


def calibration(model, sim, who, level=2, n=2000, seed=0, bins=(0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0001)):
    """Is the model's confidence what it says? At random positions (both
    copies), the posterior of the most likely code at `level` against the
    truth: per bin of that posterior, the mean posterior and the share
    right, plus the expected calibration error (ece: |said - right|
    weighted by the bin's share) and the mean log loss of the truth."""
    import simulate as sm
    rng = np.random.default_rng(seed)
    chroms = list(model.grid)
    said, right, ll = [], [], []
    for _ in range(n):
        side = "FM"[int(rng.integers(2))]
        S = states(side, model.depth)
        codes = sorted({s[:level] for s in S})
        c = str(rng.choice(chroms))
        cm = rng.uniform(0, sm.CHROM_CM[c])
        bp = float(model.gm.bp(c, cm))
        truth = sim.lineage(who, c, bp)["FM".index(side)][:level]
        P = model.at(c, side, [bp])[0]
        m = np.array([P[[s.startswith(k) for s in S]].sum() for k in codes])
        said.append(m.max())
        right.append(codes[int(m.argmax())] == truth)
        ll.append(-np.log(max(m[codes.index(truth)], 1e-6)) if truth in codes else np.nan)
    d = pd.DataFrame(dict(said=said, right=right))
    d["bin"] = pd.cut(d.said, bins, right=False)
    t = d.groupby("bin", observed=True).agg(n=("right", "size"), said=("said", "mean"), right=("right", "mean"))
    ece = float((t.n * (t.said - t.right).abs()).sum() / t.n.sum())
    return t, dict(ece=ece, log_loss=float(np.nanmean(ll)), accuracy=float(d.right.mean()))


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


def fit_models(cfg, gm=None, quiet=False):
    """The copy model each tester has, from the [phasing] anchors sources:
    phased siblings share one SiblingCopyModel (copy labels from the
    phasing), other testers with lineage claims get a CopyModel of their
    own. Returns ({subject: model}, {subject: "siblings" | "single"},
    {subject: claims}, the SiblingCopyModel or None)."""
    import assertions
    import config
    import outputs
    D = cfg["data_dir"]
    gm = gm or iv.GeneticMap.load(cfg, quiet=True)
    lengths = {c: float(gm.points[c][1][-1]) for c in gm.points} if not gm.is_flat else None
    sources = config.anchor_sources(cfg)
    a = assertions.read(D, sources, kinds={"lineage"})
    subjects = sorted(a.subject.dropna().unique()) if len(a) else []
    claims = {s: claims_for(D, s, sources, gm).assign(subject=s) for s in subjects}
    labels = (outputs.read(D, "phasing_copy_labels.csv", dtype={"chrom": str})
              if outputs.has(D, "phasing_copy_labels.csv") else None)
    phased = [s for s in (sorted(labels.sibling.unique()) if labels is not None else []) if s in claims]
    models, kind, J = {}, {}, None
    if phased:
        J = SiblingCopyModel(labels[labels.sibling.isin(phased)], gm, depth=3).fit(
            pd.concat([claims[s] for s in phased], ignore_index=True), lengths_cm=lengths)
        for s in phased:
            models[s], kind[s] = J.for_sibling(s), "siblings"
    for s in subjects:
        if s not in models:
            models[s], kind[s] = CopyModel(gm, depth=3).fit(claims[s], lengths_cm=lengths), "single"
    if not quiet:
        print(f"copy models ({gm.name}, {', '.join(sources)}): "
              + ", ".join(f"{s} ({k})" for s, k in kind.items()))
    return models, kind, claims, J


def compare_placement(placed, models, verdicts=None, phasing_verdicts=None, dnapainter=None, paint=None):
    """Copy-model placement against today's (painting) placement, on the
    checks of docs/design-copy-model.md that apply to naming grandparents:
    how much each places and how often they agree; siblings sharing a match
    segment end to end landing on the same grandparent; DNA Painter
    paintings (held out when not an anchor source); tree links judged
    leave-one-out. Returns (summary rows, markdown)."""
    import match_placement as mp
    import sibling_consistency as sc
    gps = set(lin.GRANDPARENTS)
    rows = []
    s = placed[placed.subject.isin(models) & placed.parent.isin(["F", "M"])]
    for subj, g in s.groupby("subject"):
        a, b = g.grandparent.isin(gps), g.cm_grandparent.isin(gps)
        both = a & b
        rows.append(dict(subject=subj, sided=len(g), sided_cM=round(g.cM.sum()),
                         painting=int(a.sum()), painting_cM=round(g.cM[a].sum()),
                         copy_model=int(b.sum()), copy_model_cM=round(g.cM[b].sum()),
                         both=int(both.sum()),
                         agree=round(float((g.grandparent[both] == g.cm_grandparent[both]).mean()), 3)
                         if both.any() else None))
    out = ["# Placement through the copy model\n\n",
           "Beside today's placement, not instead of it. The side of each segment comes from the "
           "mother's list as today; the grandparent from the copy model (sure at "
           f"{MIN_P}) instead of the painting (purity {mp.PURE}).\n\n",
           "## Segments placed\n\n", pd.DataFrame(rows).to_markdown(index=False), "\n"]
    # siblings sharing a segment end to end with a match
    pairs = sc.shared_pairs(placed, sorted(models))
    if len(pairs):
        look = ({x: mp.painting_lookup(paint, x) for x in models} if paint is not None else None)
        res = []
        for r in pairs.itertuples():
            ga, pa = models[r.sib_a].grandparent_of(r.chrom, r.parent, r.start, r.end)
            gb, pb = models[r.sib_b].grandparent_of(r.chrom, r.parent, r.start, r.end)
            d = dict(cm_both=pa >= MIN_P and pb >= MIN_P, cm_same=ga == gb)
            if look is not None:
                xa, qa = mp.grandparent_of(look[r.sib_a], r.chrom, r.parent, r.start, r.end)
                xb, qb = mp.grandparent_of(look[r.sib_b], r.chrom, r.parent, r.start, r.end)
                d.update(p_both=bool(xa and xb and qa >= mp.PURE and qb >= mp.PURE), p_same=xa == xb)
            res.append(d)
        res = pd.DataFrame(res)
        rows_sc = []
        for name, both, same in (("painting", "p_both", "p_same"), ("copy model", "cm_both", "cm_same")):
            if both not in res:
                continue
            sure = res[res[both]]
            rows_sc.append(dict(placement=name, pairs=len(res), both_placed=len(sure),
                                same=int(sure[same].sum()),
                                share=round(float(sure[same].mean()), 3) if len(sure) else None))
        out += ["\n## Siblings sharing a match segment end to end\n\n",
                "A shared segment is one piece of one parent's DNA: both siblings must have it on the "
                "same grandparent. Not fully held out for either: the phasing's HMM uses these pairs "
                "as soft evidence, and the copy model takes its copy labels from that phasing (it "
                "only names the copies differently). The painting here is the corrected one, as "
                "placement uses it.\n\n",
                pd.DataFrame(rows_sc).to_markdown(index=False), "\n"]
    if dnapainter is not None and len(dnapainter):
        out += ["\n## DNA Painter paintings\n\n", dnapainter.to_markdown(index=False), "\n"]
    if verdicts is not None:
        v = verdicts[verdicts.source_kind == "tree"]
        t = (v.groupby(["model", "verdict"]).size().unstack(fill_value=0).reset_index())
        out += ["\n## Tree links, leave-one-out\n\n",
                "Each tree-linked claim judged by the model without it (copy_model_verdicts.csv)",
                "; the painting's own leave-one-out verdicts (phasing_verdicts.csv) beside it" if phasing_verdicts is not None else "",
                ".\n\n", t.to_markdown(index=False), "\n"]
        if phasing_verdicts is not None:
            pv = phasing_verdicts[phasing_verdicts.assertion_id.astype(str).str.startswith("tree:")]
            out += ["\nPainting (phasing_labels):\n\n",
                    pv.verdict.value_counts().rename_axis("verdict").reset_index().to_markdown(index=False), "\n"]
    return pd.DataFrame(rows), "".join(out)


def main():
    """The copy models (fit_models), each tester also alone (the single
    model from their own claims, for comparison): blocks, leave-one-out
    verdicts, and placement through them against the painting's
    (copy_model_placement.md). Placement itself (revelations.py) fits the
    same models when [placement] method is "copy_model"."""
    import config
    import outputs
    cfg = config.load()
    D = cfg["data_dir"]
    gm = iv.GeneticMap.load(cfg, quiet=True)
    lengths = {c: float(gm.points[c][1][-1]) for c in gm.points} if not gm.is_flat else None
    paint = (outputs.read(D, "phasing_grandparent_segments.csv", dtype={"chrom": str})
             if outputs.has(D, "phasing_grandparent_segments.csv") else None)
    blocks, verdicts = [], []
    use, kind, claims, J = fit_models(cfg, gm)
    subjects = sorted(claims)
    models = {s: ("siblings", m) for s, m in use.items() if kind[s] == "siblings"}
    if J is not None:
        verdicts.append(J.verdicts().assign(model="siblings").merge(
            J.claims[["claim_id", "source_kind", "cM"]], on="claim_id", how="left"))
    for subj in subjects:
        cl = claims[subj]
        single = use[subj] if kind[subj] == "single" else CopyModel(gm, depth=3).fit(cl, lengths_cm=lengths)
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

    # placement through the copy model, beside today's (placed_segments.csv)
    if not outputs.has(D, "placed_segments.csv"):
        return
    import match_placement as mp
    placed = outputs.read(D, "placed_segments.csv", dtype={"chrom": str})
    placed["parent"] = placed.parent.fillna("")
    if "painting_grandparent" in placed:           # placed through the copy model: compare with the painting's reading
        has = placed.painting_purity.notna()       # rows placed through a copy model ("" read back as NaN)
        placed.loc[has, "grandparent"] = placed.painting_grandparent[has].fillna("")
        placed.loc[has, "purity"] = placed.painting_purity[has]
    placed["grandparent"] = placed.grandparent.fillna("")
    cmp_ = place(placed[placed.subject.isin(use)], use)
    cols = ["platform", "subject", "match_key", "match", "chrom", "start", "end", "cM", "parent",
            "parent_reason", "grandparent", "purity", "cm_grandparent", "cm_p", "cm_if_paternal",
            "cm_if_maternal"]
    outputs.write(D, "copy_model_placed_segments.csv", cmp_[cols])
    meta = cmp_[["match_key", "match"]].drop_duplicates("match_key")
    pm = pd.concat([mp.per_match(g.assign(grandparent=g.cm_grandparent), meta).assign(platform=pl, subject=sj)
                    for (pl, sj), g in cmp_.groupby(["platform", "subject"])], ignore_index=True)
    outputs.write(D, "copy_model_placed_matches.csv", pm)
    dp = None
    try:
        import revelations
        a = revelations.check_dnapainter(placed[placed.subject.isin(use)])
        b = revelations.check_dnapainter(cmp_.assign(grandparent=cmp_.cm_grandparent))
        if len(a) or len(b):
            def score(d, name):
                ok = d.gp_ok.dropna()
                return dict(placement=name, compared=len(d), grandparent_called=len(ok),
                            agree=int((ok == True).sum()), share=round(float((ok == True).mean()), 3) if len(ok) else None)
            dp = pd.DataFrame([score(a, "painting"), score(b, "copy model")])
    except Exception as e:                       # the check is optional
        print("  (DNA Painter check skipped:", e, ")")
    pv = (outputs.read(D, "phasing_verdicts.csv", dtype={"chrom": str})
          if outputs.has(D, "phasing_verdicts.csv") else None)
    summary, report = compare_placement(cmp_, use, v, pv, dp, mp.load_painting(D))
    (D / "copy_model_placement.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
