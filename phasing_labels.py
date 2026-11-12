"""
Name the anonymous sides and grandparents of a three-sibling phasing.

visual_phasing.run() returns, per chromosome, two parental sides A/B and,
per sibling and side, a 0/1 "which grandparent" label, both arbitrary. This
module names them from a parent's raw kit (which of A/B is maternal) and
from lineage assertions (documented_anchors; optionally dnapainter_io),
which vote on what each 0/1 label means. Assertions that disagree with the
majority are reported, not dropped.

Output: per-assertion verdicts, derived grandparent segments (themselves
assertions, citing the assertions they rest on), and a painting PNG.

How it works: docs/genetics.md, "Phasing".
"""
import numpy as np
import pandas as pd

import outputs

WINDOW = 301      # informative SNPs in the rolling mother vote
MIN_BLOCK = 200   # shorter side-swap runs are absorbed into neighbours


def _smooth_runs(lab, min_len):
    """Absorb runs shorter than min_len into the preceding run."""
    lab = lab.copy()
    starts = np.flatnonzero(np.r_[True, lab[1:] != lab[:-1]])
    ends = np.r_[starts[1:], len(lab)]
    for s, e in zip(starts, ends):
        if e - s < min_len and s > 0:
            lab[s:e] = lab[s - 1]
    return lab


def maternal_side(r, mum):
    """Per SNP: 0 if side A is the mother's, 1 if side B, from her kit.
    `mum` is load_raw() output for the parent (columns a1_*, a2_*)."""
    hap, ref = r["haplotypes"], r["ref"]
    mm = mum.reindex(r["rsid"])
    a1, a2 = mm.iloc[:, 2].to_numpy(), mm.iloc[:, 3].to_numpy()
    mg = np.where(pd.isna(a1), np.nan, (a1 != ref).astype(float) + (a2 != ref))
    sA, sB = hap[:, 0] + hap[:, 1], hap[:, 2] + hap[:, 3]
    okA, okB = sA == mg, sB == mg
    informative = ~np.isnan(sA) & ~np.isnan(sB) & ~np.isnan(mg) & (okA != okB)
    vote = np.where(informative, okB.astype(float) - okA, 0.0)   # +: B is mum
    # rolling sum over the informative SNPs only, then spread to all SNPs
    idx = np.flatnonzero(informative)
    v = vote[idx]
    cs = np.r_[0, np.cumsum(v)]
    i = np.arange(len(v))
    lo, hi = np.clip(i - WINDOW // 2, 0, len(v)), np.clip(i + WINDOW // 2 + 1, 0, len(v))
    roll = cs[hi] - cs[lo]
    lab_inf = (roll > 0).astype(int)
    lab_inf = _smooth_runs(lab_inf, MIN_BLOCK)
    lab = np.zeros(len(vote), int)
    if len(idx):
        nearest = np.clip(np.searchsorted(idx, np.arange(len(vote))), 0, len(idx) - 1)
        lab = lab_inf[nearest]
    agreement = (v > 0).astype(int) == lab_inf
    return lab, informative.sum(), agreement.mean() if len(v) else np.nan


def label(results, sibs, mum, claims):
    """results: visual_phasing.run() output; sibs: its sibling keys;
    mum: load_raw() of the mother; claims: dnapainter_io assertions.
    Returns (per-SNP painting, assertion verdicts, side-check stats)."""
    claims = claims[(claims.kind == "lineage") & (claims.lineage.str.len() >= 2)]
    paint_rows, verdicts, stats = [], [], []
    for chrom, r in results.items():
        pos, P = r["pos"], r["painting"]
        mside, n_inf, agree = maternal_side(r, mum)
        block = np.r_[0, np.cumsum(mside[1:] != mside[:-1])]
        stats.append(dict(chrom=chrom, informative=n_inf, mother_agreement=agree,
                          side_swaps=block[-1]))
        # g[(sib, parent)] = 0/1 label on that parent's track, per SNP
        g = {}
        for s in sibs:
            A, B = P[(s, "A")].to_numpy(), P[(s, "B")].to_numpy()
            g[(s, "M")] = np.where(mside == 0, A, B)
            g[(s, "F")] = np.where(mside == 0, B, A)
        # votes[(block, parent)] -> score for "label 0 is grandfather"
        votes, per_claim = {}, []
        for c in claims[claims.chrom == chrom].itertuples():
            par, gp = c.lineage[0], c.lineage[1]
            if c.subject not in sibs:
                continue
            inside = (pos >= c.start) & (pos <= c.end)
            if inside.sum() < 20:
                per_claim.append((c, None, "too_few_snps", 0)); continue
            for b in np.unique(block[inside]):
                sel = inside & (block == b)
                frac1 = g[(c.subject, par)][sel].mean()
                lab = int(frac1 > 0.5)
                purity = max(frac1, 1 - frac1)
                # label `lab` is grandparent gp -> label 0 is F if (lab==0)==(gp=="F")
                weight = getattr(c, "weight", 1)
                weight = 1 if pd.isna(weight) else weight
                w = sel.sum() * weight * (1 if (lab == 0) == (gp == "F") else -1)
                votes[(b, par)] = votes.get((b, par), 0) + w
                per_claim.append((c, (b, par, lab, gp, w),
                                  "spans_crossover" if purity < 0.9 else "", sel.sum()))
        for c, key, note, n in per_claim:
            v = dict(assertion_id=c.assertion_id, subject=c.subject, chrom=chrom,
                     start=c.start, end=c.end, match=c.match, lineage=c.lineage,
                     snps_used=n)
            if key is None:
                v["verdict"] = note
            else:
                b, par, lab, gp, w = key
                # leave-one-out: judge each claim only by the OTHER claims
                # in its block, so a lone claim cannot confirm itself
                others = votes[(b, par)] - w
                v["note"] = note
                if others == 0:
                    v["verdict"] = "no_other_evidence"
                else:
                    zero_is_F = others > 0
                    says = ("F" if zero_is_F else "M") if lab == 0 else ("M" if zero_is_F else "F")
                    v["verdict"] = "agrees" if says == gp else "conflicts"
                    v["phasing_says"] = par + says
                    v["support"] = round(abs(others) / (abs(others) + abs(w)), 2)
            verdicts.append(v)
        # paint: for each sib, parent: grandparent F/M where the block has votes
        for s in sibs:
            for par in "FM":
                out = np.full(len(pos), "", dtype=object)
                for b in np.unique(block):
                    if (b, par) not in votes or votes[(b, par)] == 0:
                        continue
                    zero_is_F = votes[(b, par)] > 0
                    sel = block == b
                    lab = g[(s, par)][sel]
                    out[sel] = np.where((lab == 0) == zero_is_F, par + "F", par + "M")
                paint_rows.append(pd.DataFrame(dict(chrom=chrom, pos=pos, sibling=s,
                                                    parent=par, grandparent=out)))
    return (pd.concat(paint_rows, ignore_index=True), pd.DataFrame(verdicts),
            pd.DataFrame(stats))


def copy_label_runs(results, sibs, mum):
    """The phasing's raw answer, before any anchor names it: per sibling and
    parent (F/M), which of that parent's two copies the sibling carries
    (label 0/1), as runs along each chromosome. Within one `block` (a run
    where the mother's side is one of A/B throughout) a label means the same
    copy for every sibling; across blocks it may not. For the copy model
    (copy_model.SiblingCopyModel), which names the copies itself."""
    rows = []
    for chrom, r in results.items():
        pos, P = r["pos"], r["painting"]
        mside, _, _ = maternal_side(r, mum)
        block = np.r_[0, np.cumsum(mside[1:] != mside[:-1])]
        for s in sibs:
            A, B = P[(s, "A")].to_numpy(), P[(s, "B")].to_numpy()
            for par, lab in (("M", np.where(mside == 0, A, B)), ("F", np.where(mside == 0, B, A))):
                key = lab * 100000 + block            # a run ends where label or block changes
                starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
                ends = np.r_[starts[1:], len(key)] - 1
                for a, b in zip(starts, ends):
                    rows.append(dict(chrom=chrom, sibling=s, parent=par, start=int(pos[a]), end=int(pos[b]),
                                     label=int(lab[a]), block=int(block[a]), snps=int(b - a + 1)))
    return pd.DataFrame(rows)


def to_segments(paint):
    """Collapse the per-SNP painting into segments (derived assertions)."""
    rows = []
    for (chrom, s, par), d in paint.groupby(["chrom", "sibling", "parent"], sort=False):
        gp, pos = d.grandparent.to_numpy(), d.pos.to_numpy()
        starts = np.flatnonzero(np.r_[True, gp[1:] != gp[:-1]])
        ends = np.r_[starts[1:], len(gp)] - 1
        for a, b in zip(starts, ends):
            rows.append(dict(subject=s, chrom=chrom, start=pos[a], end=pos[b],
                             parent=par, lineage=gp[a] or "?", snps=b - a + 1))
    return pd.DataFrame(rows)


COLORS = {"FF": "#2b6cb0", "FM": "#90cdf4", "MF": "#c53030", "MM": "#fbb6ce",
          "?": "#e2e8f0"}


def plot(segs, sibs, path, names=None):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    names = names or {}
    chroms = sorted(segs.chrom.unique(), key=int)
    fig, ax = plt.subplots(figsize=(14, 0.62 * len(chroms) * len(sibs) / 1.6 + 2))
    y, ticks = 0, []
    for chrom in chroms:
        for s in sibs:
            for k, par in enumerate("FM"):
                d = segs[(segs.chrom == chrom) & (segs.subject == s) & (segs.parent == par)]
                for t in d.itertuples():
                    ax.barh(y + k * 0.42, (t.end - t.start) / 1e6, left=t.start / 1e6,
                            height=0.4, color=COLORS.get(t.lineage, COLORS["?"]), lw=0)
            ticks.append((y + 0.2, f"{chrom}  {names.get(s, s)}"))
            y += 1
        y += 0.6
    ax.set_yticks([t for t, _ in ticks], [l for _, l in ticks], fontsize=6)
    ax.invert_yaxis()
    ax.set_xlabel("Mb (GRCh37)")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(handles=[Patch(color=c, label=l) for l, c in
                       [("FF paternal grandfather", COLORS["FF"]),
                        ("FM paternal grandmother", COLORS["FM"]),
                        ("MF maternal grandfather", COLORS["MF"]),
                        ("MM maternal grandmother", COLORS["MM"]),
                        ("unanchored", COLORS["?"])]],
              loc="lower right", fontsize=8, frameon=False)
    ax.set_title("Grandparent painting from visual phasing (upper bar paternal, lower maternal)")
    fig.tight_layout()
    fig.savefig(path, dpi=130)


if __name__ == "__main__":
    import config
    import visual_phasing as vp

    cfg = config.load()
    D = cfg["data_dir"]
    kits = {k: D / f for k, f in cfg["raw_kits"]["children"].items()}
    mother = D / cfg["raw_kits"]["mother"]
    mum = vp.load_raw(mother, "mum")
    # The mother's genotypes go into the model itself (as side B), and
    # segments siblings share end to end with a match are soft evidence of
    # the same copy there (sibling_consistency.ibd_intervals). Both are
    # optional: without placed_segments.csv only the mother is used.
    ibd = None
    if outputs.has(D, "placed_segments.csv"):
        import sibling_consistency as sc
        segs0 = outputs.read(D, "placed_segments.csv", dtype={"chrom": str})
        ibd = sc.ibd_intervals(sc.shared_pairs(segs0, list(kits)))
        print(f"shared-segment evidence: {len(ibd)} intervals")
    import intervals
    gm = intervals.GeneticMap.load(cfg)
    print("genetic map:", gm)
    results = vp.run(kits, genetic_map=gm, parent=mum, ibd=ibd)
    # anchors: documented relatives, tree links, optionally DNA Painter
    # paintings ([phasing] anchors in family.toml), each a weighted vote
    import assertions
    sources = config.anchor_sources(cfg)
    files = [assertions.FILES[s] for s in sources if outputs.has(D, assertions.FILES[s])]
    claims = assertions.read(D, sources)
    print("anchors:", ", ".join(f"{s} ({(claims.source_kind == s).sum()})" for s in sources))
    paint, verdicts, stats = label(results, vp.SIBS, mum, claims)
    segs = to_segments(paint).assign(
        asserted_by="visual_phasing.py (TEMPER=%s, map %s, mother in model, shared-segment evidence %s)"
                    " + phasing_labels.py" % (vp.TEMPER, gm.name, "on" if ibd is not None else "off"),
        source="raw kits: " + ", ".join(p.name for p in kits.values())
               + "; mother: " + mother.name + "; anchors: " + ", ".join(files))
    outputs.write(D, "phasing_verdicts.csv", verdicts)
    outputs.write(D, "phasing_grandparent_segments.csv", segs)
    outputs.write(D, "phasing_copy_labels.csv", copy_label_runs(results, vp.SIBS, mum))
    outputs.write(D, "phasing_crossovers.csv",
                  pd.concat([r["crossovers"].assign(chrom=c) for c, r in results.items()]))
    plot(segs, vp.SIBS, D / "phasing_grandparents.png",
         {k: config.display_name(cfg, k) for k in vp.SIBS})
    print(stats.to_string())
    src = verdicts.assertion_id.str.split(":").str[0].replace({"anchor": "documented"})
    print(pd.crosstab(src, verdicts.verdict).to_string())
