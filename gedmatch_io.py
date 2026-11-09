"""
Read saved GEDmatch one-to-one comparison pages and use them to check the
phasing model.

GEDmatch's one-to-one compare, saved as HTML, lists segments as rows of
"chr  start  end  cM  SNPs" (GRCh37). Two saves per sibling pair are
useful: the default comparison (every shared segment, half identical or
more: "IBD") and the one restricted to fully identical regions ("FIR").
Together they give GEDmatch's own NIR / HIR / FIR call along the genome,
an independent algorithm on the same raw data.

`agreement(results, sibs, comparisons)` compares that with the model's
pairwise state (visual_phasing.run results), weighted by base pairs.
Expect disagreement at segment edges and where GEDmatch's minimum segment
size (often 7 cM) hides short shared stretches the model still calls HIR.

In family.toml:

    [[gedmatch_pair]]
    a = "anna"
    b = "bertil"
    ibd = "vp2020/GEDmatch Anna-Bertil-full.html"
    fir = "vp2020/GEDmatch FIR Anna-Bertil.html"
"""
import html
import re

import numpy as np
import pandas as pd

ROW = re.compile(r"\b(\d{1,2}|X)\s+([\d,]+)\s+([\d,]+)\s+([\d.]+)\s+([\d,]+)\b")


def read_one_to_one(path):
    t = html.unescape(re.sub(r"<[^>]+>", " ", open(path, encoding="utf-8", errors="replace").read()))
    return pd.DataFrame([(c, int(s.replace(",", "")), int(e.replace(",", "")), float(cm), int(n.replace(",", "")))
                         for c, s, e, cm, n in ROW.findall(t)],
                        columns=["chrom", "start", "end", "cM", "snps"])


def _inside(pos, df):
    m = np.zeros(len(pos), bool)
    for r in df.itertuples():
        m |= (pos >= r.start) & (pos <= r.end)
    return m


def agreement(results, sibs, comparisons):
    """comparisons: list of dicts a, b, ibd (DataFrame), fir (DataFrame).
    Returns {(a, b): 3x3 bp matrix}, rows GEDmatch NIR/HIR/FIR, columns
    the model's."""
    import visual_phasing as vp
    idx = {k: n for n, k in enumerate(sibs)}
    out = {}
    for c in comparisons:
        conf = np.zeros((3, 3))
        i, j = idx[c["a"]], idx[c["b"]]
        for ch, R in results.items():
            pos = R["pos"]
            S = np.array([vp.STATES[s] for s in R["path"]])
            cA = np.stack([np.zeros(len(S), int), S[:, 0], S[:, 1]], 1)
            cB = np.stack([np.zeros(len(S), int), S[:, 2], S[:, 3]], 1)
            model = (cA[:, i] == cA[:, j]).astype(int) + (cB[:, i] == cB[:, j])
            g = np.where(_inside(pos, c["fir"][c["fir"].chrom == ch]), 2,
                         np.where(_inside(pos, c["ibd"][c["ibd"].chrom == ch]), 1, 0))
            w = np.r_[np.diff(pos), 0].astype(float)
            for gi in range(3):
                for mi in range(3):
                    conf[gi, mi] += w[(g == gi) & (model == mi)].sum()
        out[(c["a"], c["b"])] = conf
    return out


if __name__ == "__main__":
    import config
    import sibling_consistency as sc
    import visual_phasing as vp
    cfg = config.load()
    D = cfg["data_dir"]
    comps = [dict(a=p["a"], b=p["b"], ibd=read_one_to_one(D / p["ibd"]), fir=read_one_to_one(D / p["fir"]))
             for p in cfg.get("gedmatch_pair", [])]
    kits = {k: D / f for k, f in cfg["raw_kits"]["children"].items()}
    mum = vp.load_raw(D / cfg["raw_kits"]["mother"], "mum")
    segs = pd.read_csv(D / "placed_segments.csv", low_memory=False, dtype={"chrom": str})
    res = vp.run(kits, parent=mum, ibd=sc.ibd_intervals(sc.shared_pairs(segs, list(kits))))
    tot = agreement(res, vp.SIBS, comps)
    allc = sum(tot.values())
    print(f"bp agreement with GEDmatch NIR/HIR/FIR: {np.trace(allc) / allc.sum():.1%}")
    for k, c in tot.items():
        print(f"  {k}: {np.trace(c) / c.sum():.1%}  (rows GEDmatch NIR/HIR/FIR, columns model, Mb) "
              f"{np.round(c / 1e6).astype(int).tolist()}")
