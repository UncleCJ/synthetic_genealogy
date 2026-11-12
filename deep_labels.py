"""
Deep labels: what the copy model says about each tester's great-grandparents
(level 3: FFF, FFM, ... MMM) and why. Reads the copy model's stored tables
(copy_model_blocks, copy_model_verdicts, written by copy_model.py) and the
lineage assertions behind them; fits nothing, so it answers in seconds.

  python3 deep_labels.py                 # every tester: coverage and claims per great-grandparent
  python3 deep_labels.py cj              # one tester, and the deep conflicts to look at first
  python3 deep_labels.py cj --chrom 9    # one chromosome: blocks and the claims on them
  python3 deep_labels.py --png           # the deep painting per tester (deep_labels_<subject>.png)
  python3 deep_labels.py --confirm       # patronymic name joins on deep paths, to confirm by hand first

Bands are sure (posterior >= 0.9), likely (0.7-0.9) and leaning (below 0.7);
each claim carries the copy model's verdict and how its person was joined.
Where a tester has a sibling model, it is read; otherwise the single model.

How it works: docs/genetics.md, "Deep labels and edges".
Sketch, unvalidated: the shading is a reading aid, not a calibration.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

LEVEL = 3
BANDS = [(0.9, "sure"), (0.7, "likely"), (0.0, "leaning")]


def _join(evidence: pd.Series, kind: pd.Series) -> pd.Series:
    """How a claim found its person: 'name join' (patronymic name),
    'distinctive name', 'confirmed', or the source kind."""
    ev = evidence.fillna("").astype(str)
    return np.select([ev.str.startswith("tree (name join)"), ev.str.startswith("tree (distinctive"),
                      ev.str.startswith("tree (confirmed")],
                     ["name join", "distinctive name", "confirmed"], kind.fillna(""))


def load(cfg=None):
    """(blocks, claims): the copy model's blocks, one model per subject
    (siblings where present), and its verdicts with each claim's match,
    position and join."""
    import assertions
    import config
    import outputs
    cfg = cfg or config.load()
    D = cfg["data_dir"]
    b = outputs.read(D, "copy_model_blocks.csv", dtype={"chrom": str})
    v = outputs.read(D, "copy_model_verdicts.csv", dtype={"chrom": str})
    use = b.groupby("subject").model.agg(lambda m: "siblings" if (m == "siblings").any() else "single")
    b = b[b.model == b.subject.map(use)]
    v = v[v.model == v.subject.map(use)]
    a = assertions.read(D, config.anchor_sources(cfg), kinds={"lineage"})
    a = a.rename(columns={"assertion_id": "claim_id"})[["claim_id", "match", "start", "end", "evidence"]]
    c = v.merge(a.drop_duplicates("claim_id"), on="claim_id", how="left")
    c["join"] = _join(c.evidence, c.source_kind)
    for k in ("start", "end"):
        c[k] = pd.to_numeric(c[k], errors="coerce")
    c["lineage"] = c.lineage.astype(str)
    return b, c


def band(p):
    return next(name for lo, name in BANDS if p >= lo)


def coverage(blocks, subject, level=LEVEL):
    """cM per code and band for one subject at `level`."""
    b = blocks[(blocks.subject == subject) & (blocks.level == level)].copy()
    b["cM"] = b.end_cm - b.start_cm
    b["band"] = b.posterior.map(band)
    t = b.pivot_table(index="lineage", columns="band", values="cM", aggfunc="sum", fill_value=0)
    return t.reindex(columns=[n for _, n in BANDS], fill_value=0).round(0).astype(int)


def claim_table(claims, subject, level=LEVEL):
    """Per great-grandparent: claims naming it (lineage at least `level`
    letters) by verdict, and how many came by a name join."""
    c = claims[(claims.subject == subject) & (claims.lineage.str.len() >= level)].copy()
    c["code"] = c.lineage.str[:level]
    t = c.pivot_table(index="code", columns="verdict", values="claim_id", aggfunc="count", fill_value=0)
    t = t.reindex(columns=["agrees", "conflicts", "unclear"], fill_value=0)
    t["name_join"] = c[c["join"] == "name join"].groupby("code").size().reindex(t.index, fill_value=0)
    return t


def conflict_levels(blocks, claims, subject, level=LEVEL):
    """Of the deep claims read against: how many the model puts on another
    grandparent (the claim's side or tree path is wrong at the top) and how
    many on the same grandparent but the other great-grandparent."""
    k = conflicts(blocks, claims, subject, level, top=10 ** 6)
    return k.differs_at.value_counts() if len(k) else pd.Series(dtype=int)


def _code_at(blocks, subject, chrom, side, pos, level=LEVEL):
    b = blocks[(blocks.subject == subject) & (blocks.level == level) & (blocks.chrom == str(chrom))
               & (blocks.side == side) & (blocks.start <= pos) & (blocks.end >= pos)]
    return ("", np.nan) if b.empty else (b.lineage.iloc[0], b.posterior.iloc[0])


def conflicts(blocks, claims, subject, level=LEVEL, top=15):
    """Deep claims the model reads against, largest first, with what the
    model reads there instead."""
    c = claims[(claims.subject == subject) & (claims.lineage.str.len() >= level)
               & (claims.verdict == "conflicts")].sort_values("cM", ascending=False).head(top)
    rows = []
    for r in c.itertuples():
        mid = (r.start + r.end) / 2 if pd.notna(r.start) else np.nan
        code, p = _code_at(blocks, subject, r.chrom, r.lineage[0], mid, level) if pd.notna(mid) else ("", np.nan)
        rows.append(dict(match=r.match, lineage=r.lineage, chrom=r.chrom,
                         Mb=f"{r.start / 1e6:.1f}-{r.end / 1e6:.1f}" if pd.notna(r.start) else "",
                         cM=round(r.cM, 1), support=r.support, join=getattr(r, "join"),
                         model_reads=code, model_p=p,
                         differs_at=("grandparent" if code[:2] != r.lineage[:2] else "great-grandparent") if code else ""))
    return pd.DataFrame(rows)


def confirm_next(claims, level=LEVEL, top=15):
    """The matches whose identity, confirmed by hand, would most sharpen
    the deep labels: claims joined on a patronymic name on a path at least
    `level` deep (distinctive names already count as confirmed), per match
    and path over every tester, largest first. A confirmed identity counts
    0.875 instead of 0.5 (copy_model.weight_to_confidence).
    Segments the model reads against suggest a wrong join: check those
    before confirming."""
    c = claims[(claims.lineage.str.len() >= level) & (claims["join"] == "name join")]
    if c.empty:
        return pd.DataFrame()
    v = c.pivot_table(index=["match", "lineage"], columns="verdict", values="cM",
                      aggfunc="size", fill_value=0)
    v = v.reindex(columns=["agrees", "unclear", "conflicts"], fill_value=0)
    t = c.groupby(["match", "lineage"]).agg(cM=("cM", "sum"), testers=("subject", "nunique"))
    t = t.join(v).sort_values("cM", ascending=False).head(top).reset_index()
    t["cM"] = t.cM.round(0).astype(int)
    return t


def chromosome(blocks, claims, subject, chrom):
    """One chromosome: grandparent and great-grandparent blocks per copy,
    then the deep claims on it."""
    out = []
    for side, name in (("F", "paternal"), ("M", "maternal")):
        out.append(f"\n{name} copy, chr{chrom}")
        b = blocks[(blocks.subject == subject) & (blocks.chrom == str(chrom)) & (blocks.side == side)]
        for lvl in (2, 3):
            for r in b[(b.level == lvl) & (b.end_cm - b.start_cm >= 0.5)].sort_values("start").itertuples():
                out.append(f"  {'  ' * (lvl - 2)}{r.lineage:4s} {r.start / 1e6:6.1f}-{r.end / 1e6:6.1f} Mb  "
                           f"{r.end_cm - r.start_cm:5.1f} cM  p={r.posterior:.2f} ({band(r.posterior)})")
        c = claims[(claims.subject == subject) & (claims.chrom == str(chrom))
                   & (claims.lineage.str[0] == side) & (claims.lineage.str.len() >= LEVEL)].sort_values("start")
        for r in c.itertuples():
            out.append(f"    claim {r.lineage:6s} {r.start / 1e6:6.1f}-{r.end / 1e6:6.1f} Mb {r.cM:5.1f} cM  "
                       f"{r.verdict:9s} support {r.support:.2f}  {getattr(r, 'join')}: {r.match}")
    return "\n".join(out)


def plot(blocks, claims, subject, path, label=None):
    """The deep painting: per chromosome and copy, the grandparent (upper
    half of the lane) and the great-grandparent (lower half), shaded by
    the posterior; deep claims as ticks below the lane, conflicts in red."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from dnapainter_export import _shade
    fig, ax = plt.subplots(figsize=(14, 10))
    b = blocks[blocks.subject == subject]
    c = claims[(claims.subject == subject) & (claims.lineage.str.len() >= LEVEL) & claims.start.notna()]
    used = set()
    for i in range(22):
        chrom, y = str(i + 1), float(i)
        for side, off in (("F", 0.0), ("M", 0.46)):
            for lvl, dy, h in ((2, 0.0, 0.15), (3, 0.15, 0.2)):
                for r in b[(b.chrom == chrom) & (b.side == side) & (b.level == lvl)].itertuples():
                    floor = 0.5 if lvl == 2 else 0.25        # chance level for the code
                    alpha = float(np.clip((r.posterior - floor) / (1 - floor), 0.06, 1.0))
                    ax.barh(y + off + dy, (r.end - r.start) / 1e6, left=r.start / 1e6, height=h,
                            color=_shade(r.lineage), alpha=alpha, lw=0, align="edge")
                    if lvl == 3:
                        used.add(r.lineage)
            for r in c[(c.chrom == chrom) & (c.lineage.str[0] == side)].itertuples():
                bad = r.verdict == "conflicts"
                ax.plot([r.start / 1e6, r.end / 1e6], [y + off + 0.39] * 2, lw=1.6 if bad else 1.0,
                        color="#b00020" if bad else _shade(r.lineage[:LEVEL]), solid_capstyle="butt")
    ax.set_yticks([i + 0.4 for i in range(22)], [str(i + 1) for i in range(22)], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Mb (GRCh37)")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    handles = [Patch(color=_shade(k), label=k) for k in sorted(used)]
    handles.append(Patch(color="#b00020", label="claim the model reads against"))
    ax.legend(handles=handles, loc="lower right", fontsize=7, frameon=False, ncol=2)
    cov = coverage(blocks, subject)
    sure, likely = int(cov["sure"].sum()), int(cov["likely"].sum())
    ax.set_title(f"{label or subject}: copy model at grandparent (upper strip) and great-grandparent "
                 f"(lower strip) level, paternal above maternal; stronger colour = surer.\n"
                 f"Great-grandparent: sure on {sure} cM, likely on {likely} cM. Lines under each lane: "
                 f"claims naming a great-grandparent (red: the model reads against them).", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(argv=None):
    import config
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("subject", nargs="?")
    ap.add_argument("--chrom")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--png", action="store_true", help="write deep_labels_<subject>.png")
    ap.add_argument("--confirm", action="store_true", help="patronymic name joins on deep paths to confirm first")
    args = ap.parse_args(argv)
    cfg = config.load()
    blocks, claims = load(cfg)
    pd.set_option("display.width", 200)
    if args.confirm:
        print("matches joined on a patronymic name on deep paths, by cM over all testers "
              "(segments by verdict; any conflicts: check the join first)")
        print(confirm_next(claims, top=args.top).to_string(index=False))
        return
    subjects = [args.subject] if args.subject else sorted(blocks.subject.unique())
    for s in subjects:
        model = blocks[blocks.subject == s].model.iloc[0] if (blocks.subject == s).any() else "-"
        if args.chrom:
            print(f"{s} ({model} model)" + chromosome(blocks, claims, s, args.chrom))
            continue
        cov, ct = coverage(blocks, s), claim_table(claims, s)
        print(f"\n{s} ({model} model): great-grandparents, cM by band and claims by verdict")
        print(cov.join(ct, how="outer").fillna(0).astype(int).to_string())
        lv = conflict_levels(blocks, claims, s)
        if len(lv):
            print("deep conflicts that differ at the " + ", ".join(f"{k}: {v}" for k, v in lv.items()))
        if args.subject:
            k = conflicts(blocks, claims, s, top=args.top)
            if len(k):
                print(f"\ndeep claims the model reads against (largest {len(k)}):")
                print(k.to_string(index=False))
        if args.png:
            path = cfg["data_dir"] / f"deep_labels_{s}.png"
            plot(blocks, claims, s, path, config.display_name(cfg, s) if s in cfg.get("people", {}) else s)
            print(f"-> {path}")


if __name__ == "__main__":
    main()
