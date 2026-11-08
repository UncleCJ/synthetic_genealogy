"""Simulated check of the whole idea, with no real photos needed.

1. Invent a 3-generation family and simulate inherited faces (infinitesimal model).
2. 'Photograph' some of them (noisy observations, several photos for a few).
3. Infer everyone from the tree and compare with the hidden truth.

    python -m genealogy_avatars.kindemo            -> avatars/kindemo.html + printed scores
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
from .person import Person
from .traits import D, to_render
from .kinship import pedigree_matrix
from .infer import infer, evidence_level, side_share, lookalikes
from .procedural import render

FAMILY = [  # id, name, sex, born, father, mother
    ("gfp", "Grandpa (father's side)", "M", 1946, None, None),
    ("gmp", "Grandma (father's side)", "F", 1948, None, None),
    ("gfm", "Grandpa (mother's side)", "M", 1945, None, None),
    ("gmm", "Grandma (mother's side)", "F", 1949, None, None),
    ("dad", "Father", "M", 1972, "gfp", "gmp"),
    ("aunt", "Aunt (father's sister)", "F", 1975, "gfp", "gmp"),
    ("mum", "Mother", "F", 1974, "gfm", "gmm"),
    ("uncle", "Uncle (mother's brother)", "M", 1971, "gfm", "gmm"),
    ("s1", "Aunt's husband", "M", 1973, None, None),
    ("s2", "Uncle's wife", "F", 1972, None, None),
    ("me", "Me", "M", 1998, "dad", "mum"),
    ("sis", "Sister", "F", 2001, "dad", "mum"),
    ("bro", "Brother", "M", 2004, "dad", "mum"),
    ("cp", "Cousin (father's side)", "F", 2000, "s1", "aunt"),
    ("cm", "Cousin (mother's side)", "M", 1999, "uncle", "s2"),
]
PHOTOS = {"me": 3, "sis": 2, "mum": 2, "gfp": 1, "uncle": 1, "cm": 1, "s2": 1}


def simulate(seed: int = 40, h2: float = 0.6, tau2: float = 0.15):
    rng = np.random.default_rng(seed)
    ids = [f[0] for f in FAMILY]
    g = {}
    for pid, _, _, _, fa, mo in FAMILY:            # FAMILY is listed parents-first
        if fa is None:
            g[pid] = rng.normal(0, 1, D)
        else:                                      # mid-parent + Mendelian sampling
            g[pid] = (g[fa] + g[mo]) / 2 + rng.normal(0, np.sqrt(0.5), D)
    truth = np.array([np.sqrt(h2) * g[p] + np.sqrt(1 - h2) * rng.normal(0, 1, D) for p in ids])
    photos = {ids.index(p): truth[ids.index(p)] + rng.normal(0, np.sqrt(tau2), (n, D))
              for p, n in PHOTOS.items()}
    return ids, truth, photos


def main(out_dir: str = "avatars") -> None:
    ids, truth, photos = simulate()
    father = {f[0]: f[4] for f in FAMILY if f[4]}
    mother = {f[0]: f[5] for f in FAMILY if f[5]}
    A = pedigree_matrix(ids, father, mother)
    mean, sd = infer(A, photos)

    people = [Person(pid, name, sex, born, 45) for pid, name, sex, born, _, _ in FAMILY]
    hidden = [k for k in range(len(ids)) if k not in photos]
    r_tree = np.corrcoef(mean[hidden].ravel(), truth[hidden].ravel())[0, 1]
    print(f"Unphotographed people: correlation inferred vs hidden truth = {r_tree:.2f} "
          f"(a pure guess scores 0)")
    for pid, (other, s) in lookalikes(mean, ids, candidates=sorted(photos)).items():
        print(f"  {pid:6} most resembles photographed {other:6} (cos {s:+.2f})")

    cards = {"truth": [], "photos": [], "tree": []}
    pos = {p: k for k, p in enumerate(ids)}
    for k, p in enumerate(people):
        side = side_share(mean, k, pos.get(father.get(p.id)), pos.get(mother.get(p.id)))
        cards["truth"].append(render(p, traits=to_render(truth[k])))
        if k in photos:
            cards["photos"].append(render(p, traits=to_render(photos[k].mean(0)), evidence=3))
        else:
            cards["photos"].append(render(Person(p.id, p.name, "U"), evidence=0))
        cards["tree"].append(render(p, traits=to_render(mean[k]),
                                    evidence=evidence_level(sd[k], k in photos), side=side))
    rows = "".join(
        f"<h2>{title}</h2><div class=row>" + "".join(
            f"<figure>{svg}<figcaption>{people[k].name}</figcaption></figure>"
            for k, svg in enumerate(cards[key])) + "</div>"
        for key, title in [("truth", "Hidden truth (simulated)"),
                           ("photos", "What the photos alone show"),
                           ("tree", "After the tree pulls on everyone")])
    html = f"""<!doctype html><meta charset=utf-8><title>Kinship avatars</title>
<style>body{{font:13px system-ui;margin:1.5rem;background:#faf8f4;color:#222}}
.row{{display:flex;flex-wrap:wrap;gap:.6rem}}figure{{margin:0;width:110px;text-align:center}}
svg{{width:100px;height:100px}}@media(prefers-color-scheme:dark){{body{{background:#1b1b1b;color:#eee}}}}</style>
<h1>Kinship avatars</h1><p>Dots: 3 = photographed, 2 = well inferred, 1 = weak, 0 = guess.
Bar: blue = resembles father's side, orange = mother's side. Correlation for unphotographed
people: {r_tree:.2f}.</p>{rows}"""
    Path(out_dir).mkdir(exist_ok=True)
    (Path(out_dir) / "kindemo.html").write_text(html, encoding="utf-8")
    print(f"-> {out_dir}/kindemo.html")
    return cards, people


if __name__ == "__main__":
    main()
