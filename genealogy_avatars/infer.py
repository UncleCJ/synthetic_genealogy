"""Spread face evidence through the family tree.

Model (the 'infinitesimal model' from quantitative genetics, per vector dimension):
    face_i  = inherited_i + personal_i          inherited ~ N(0, h2 * A),  personal ~ N(0, 1 - h2)
    photo   = face_i + noise                    noise ~ N(0, tau2)  (pose, lighting, age, grain)
So the prior covariance between two people is K = h2*A + (1 - h2)*I, and each photo is a noisy
look at one person. The posterior mean below is what breeders call BLUP: photographed people
stay close to their photos, and everybody else is pulled toward relatives in proportion to kinship.
Works the same for the 9 drawable traits and the 512-d identity embedding.
"""
from __future__ import annotations
import numpy as np


def infer(A: np.ndarray, photos: dict[int, np.ndarray], h2: float = 0.6, tau2: float = 0.15,
          prior_mean: np.ndarray | None = None):
    """A: n×n relationship matrix. photos: person index -> array (n_photos, d); NaN = not measured.
    Returns (mean n×d, sd n×d) of each person's face vector."""
    n = A.shape[0]
    d = next(iter(photos.values())).shape[1]
    mu = np.zeros(d) if prior_mean is None else prior_mean
    K = h2 * A + (1 - h2) * np.eye(n)
    mean, sd = np.tile(mu, (n, 1)).astype(float), np.ones((n, d)) * np.sqrt(np.diag(K))[:, None]
    for k in range(d):                                   # per dimension, so NaNs are just skipped
        obs = [(i, v[~np.isnan(v[:, k]), k]) for i, v in photos.items()]
        obs = [(i, vals) for i, vals in obs if len(vals)]
        if not obs:
            continue
        o = np.array([i for i, _ in obs])
        ybar = np.array([vals.mean() for _, vals in obs]) - mu[k]
        noise = np.array([tau2 / len(vals) for _, vals in obs])
        Koo = K[np.ix_(o, o)] + np.diag(noise)
        Kxo = K[:, o]
        L = np.linalg.cholesky(Koo)
        alpha = np.linalg.solve(L.T, np.linalg.solve(L, ybar))
        V = np.linalg.solve(L, Kxo.T)
        mean[:, k] = mu[k] + Kxo @ alpha
        sd[:, k] = np.sqrt(np.clip(np.diag(K) - (V * V).sum(0), 0, None))
    return mean, sd


def evidence_level(sd_row: np.ndarray, photographed: bool) -> int:
    """3 dots = photographed, 2 = well pinned by close kin, 1 = weakly, 0 = pure guess."""
    if photographed:
        return 3
    s = float(np.nanmean(sd_row))
    return 2 if s < 0.80 else 1 if s < 0.95 else 0


def side_share(mean: np.ndarray, i: int, father: int | None, mother: int | None) -> float | None:
    """0..1: how much more person i resembles the father's side than the mother's."""
    if father is None or mother is None:
        return None
    df = np.sum((mean[i] - mean[father]) ** 2)
    dm = np.sum((mean[i] - mean[mother]) ** 2)
    return float(dm / (df + dm)) if df + dm > 0 else 0.5


def lookalikes(mean: np.ndarray, ids: list[str], candidates: list[int] | None = None) -> dict[str, tuple[str, float]]:
    """Closest other person by cosine similarity of the (centred) face vectors."""
    X = mean - mean.mean(0)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    S = X @ X.T
    np.fill_diagonal(S, -np.inf)
    cand = np.array(candidates if candidates is not None else range(len(ids)))
    out = {}
    for i, pid in enumerate(ids):
        row = S[i, cand]
        j = cand[int(np.argmax(row))]
        out[pid] = (ids[j], float(S[i, j]))
    return out
