"""Relationship matrices: how much of their 'inheritable face' two people are expected to share.

A[i, j] = expected fraction of DNA shared by descent (1 = self, .5 parent/child or full siblings,
.25 grandparent / aunt / half-sibling, .125 first cousins, ...). Built with Henderson's
tabular method from father/mother links. Where you have real DNA matches, the shared cM can
replace the pedigree's expectation (actual sharing varies a lot beyond the 1st cousin level).
"""
from __future__ import annotations
import numpy as np

GENOME_CM = 6800.0   # ~ total autosomal cM counting both copies; parent/child share ~3400 -> 0.5


def pedigree_matrix(ids: list[str], father: dict[str, str], mother: dict[str, str],
                    mz_twins: list[tuple[str, str]] = ()) -> np.ndarray:
    """mz_twins: identical-twin pairs. They are one genome, so the second twin copies the first's
    row, and everything descending from either twin follows automatically."""
    order = _topological(ids, father, mother)
    pos = {pid: k for k, pid in enumerate(order)}
    twin = {}
    for a, b in mz_twins:
        if a in pos and b in pos:
            first, second = sorted((a, b), key=pos.get)
            twin[second] = first
    n = len(order)
    A = np.zeros((n, n))
    for i, pid in enumerate(order):
        if pid in twin:                       # identical twin: same genome as the earlier-processed twin
            t = pos[twin[pid]]
            A[i, :i] = A[:i, i] = A[t, :i]
            A[i, i] = A[t, i] = A[i, t] = A[t, t]
            continue
        s, d = pos.get(father.get(pid)), pos.get(mother.get(pid))
        for j in range(i):
            v = 0.5 * ((A[j, s] if s is not None else 0) + (A[j, d] if d is not None else 0))
            A[i, j] = A[j, i] = v
        A[i, i] = 1 + (0.5 * A[s, d] if s is not None and d is not None else 0)  # inbreeding term
    idx = [pos[pid] for pid in ids]          # back to caller's order
    return A[np.ix_(idx, idx)]


def apply_shared_cm(A: np.ndarray, ids: list[str], shared_cm: dict[tuple[str, str], float]) -> np.ndarray:
    """Overwrite pairs that have a DNA measurement, then repair to a valid covariance.

    Caveat: MyHeritage/FTDNA totals count half-identical cM, so full siblings (who also share
    regions on both copies) come out near 0.38 instead of 0.5. Keep the pedigree value for them.
    """
    A = A.copy()
    pos = {pid: k for k, pid in enumerate(ids)}
    for (a, b), cm in shared_cm.items():
        if a in pos and b in pos:
            A[pos[a], pos[b]] = A[pos[b], pos[a]] = cm / GENOME_CM
    w, V = np.linalg.eigh(A)
    return (V * np.clip(w, 1e-6, None)) @ V.T  # nearest positive-definite matrix


def _topological(ids, father, mother):
    done, out = set(), []
    def visit(pid):
        if pid in done or pid not in ids_set:
            return
        done.add(pid)
        for parent in (father.get(pid), mother.get(pid)):
            if parent:
                visit(parent)
        out.append(pid)
    ids_set = set(ids)
    for pid in ids:
        visit(pid)
    return out
