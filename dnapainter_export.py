"""
Write the computed painting back as DNA Painter profile backups, one per
tester, to explore (and correct) in DNA Painter's own chromosome view.

Each backup holds:

- **phased blocks**: the visual-phasing grandparent painting (siblings
  only), one group per grandparent copy, in a pale tint;
- **placed match segments**: segments of at least `min_cM` that
  match_placement put on a grandparent copy. A match the family tree places
  deeper (gedcom_io.matches_in_tree) goes to the group of the person its
  DNA came through, if that agrees with the segment's grandparent; else it
  stays at the grandparent and the note says what the tree claims.

Groups follow the lineage-code convention dnapainter_io reads: "FMF Erik
Example / Anna Example" = segments that came via the father's
mother's father, named after his parents. So a backup written here reads
back as assertions like a hand-painted one (asserted_by is in the notes).

Codes are relative to the siblings. The mother's profile drops the leading
"M" (her MF is her F).

Sketch: the output is meant for looking, not as evidence. Every segment
note says how it was placed. Pile-up bins are not masked here.
"""
import colorsys
import json
from pathlib import Path

import pandas as pd

BASE = {"FF": "#2b6cb0", "FM": "#2f855a", "MF": "#c05621", "MM": "#805ad5"}


def _shade(code, pale=False):
    """Colour family by grandparent; deeper codes vary lightness and hue."""
    h, l, s = colorsys.rgb_to_hls(*[int(BASE[code[:2]][i:i + 2], 16) / 255 for i in (1, 3, 5)])
    if pale:
        l, s = 0.88, 0.45
    else:
        extra = code[2:]
        for k, c in enumerate(extra):
            h += (0.035 if c == "F" else -0.035) / (k + 1)
            l += (0.07 if c == "M" else -0.05) / (k + 1)
        l = min(max(l, 0.25), 0.7)
    r, g, b = colorsys.hls_to_rgb(h % 1, l, s)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def couple_names(tree, proband, code):
    """Names of the parents of the person at `code` above the proband."""
    if tree is None:
        return ""
    at = {c: x for x, c in tree.ancestors(tree.id(proband), max_depth=len(code) + 1)}
    if code not in at:
        return ""
    names = []
    for par in sorted(tree.parents(at[code]), key=lambda p: tree.people[p]["sex"] != "M"):
        p = tree.people[par]
        names.append(f"{p['given']} {p['surname']}".strip())
    return " / ".join(names)


def deep_codes(tree, proband, placed_matches):
    """match_key -> lineage code of the person the shared DNA came through,
    from tree persons named like the match (weak: a name join)."""
    if tree is None:
        return {}
    import gedcom_io
    df = gedcom_io.matches_in_tree(tree, proband, placed_matches)
    out = {}
    for m in df.itertuples():
        codes = [c for c in str(m.mrca_code).split() if c]
        if not codes:
            continue
        # couple MRCA (codes differing in the last letter) -> their child's code
        pre = codes[0] if len(codes) == 1 else _common_prefix(codes)
        key = placed_matches.loc[placed_matches.match == m.match, "match_key"]
        for k in key.unique():
            out[k] = pre
    return out


def _common_prefix(codes):
    p = codes[0]
    for c in codes[1:]:
        while not c.startswith(p):
            p = p[:-1]
    return p


def backup(profile, sex, blocks, segs, deep, tree, proband, strip=0, min_cM=12.0,
           tree_min_cM=7.0, label=""):
    """blocks: phased grandparent segments (subject, chrom, start, end,
    lineage, snps) or empty; segs: placed segments of one tester."""
    groups, gidx, out = [], {}, []

    def group(code, kind):
        key = (code, kind)
        if key not in gidx:
            own = code[strip:]
            names = couple_names(tree, proband, code)
            if kind == "block":
                name = f"{own} phased copy ({names or code})"
            else:
                name = f"{own} {names}".strip() if names else f"{own} matches"
            gidx[key] = len(groups)
            groups.append(dict(name=name, side="pat" if own[0] == "F" else "mat",
                               color=_shade(code, pale=(kind == "block")),
                               notes=f"\n\n{label}: {'visual-phasing block' if kind == 'block' else 'placed match segments'}, lineage {code} relative to the siblings\n",
                               ancestor=1, order=len(groups), spec=""))
        return gidx[key]

    sid = 0
    for b in blocks.itertuples():
        if b.lineage not in BASE:
            continue
        sid += 1
        out.append(dict(chromosome=str(b.chrom), start=str(int(b.start)), end=str(int(b.end)),
                        group=group(b.lineage, "block"), id=sid, cM="", SNPs=str(int(b.snps)),
                        notes=f"{label}: phased block, {b.snps} informative SNPs",
                        match=f"Phased {b.lineage[strip:]} block", certainty=2))
    for s in segs.itertuples():
        gp = s.grandparent
        if gp not in BASE or str(s.chrom) == "X":
            continue
        code, note = gp, ""
        d = deep.get(s.match_key)
        if d:
            if d.startswith(gp):
                code = d
            else:
                note = f" Tree path {d} disagrees with placement {gp}."
        if s.cM < (tree_min_cM if d else min_cM):
            continue
        sid += 1
        out.append(dict(chromosome=str(s.chrom), start=str(int(s.start)), end=str(int(s.end)),
                        group=group(code, "match"), id=sid, cM=f"{s.cM:.1f}", SNPs="",
                        notes=(f"{label}: {s.platform}, {s.parent_reason}; grandparent {gp} "
                               f"(purity {s.purity:.2f}).{note}" + (f" Tree path {d}." if d and not note else "")),
                        match=str(s.match), certainty=2 if d and not note else 1))
    groups.sort(key=lambda g: g["order"])
    return (f"{profile}{sex}" + json.dumps(out, ensure_ascii=False, separators=(",", ":"))
            + json.dumps(groups, ensure_ascii=False, separators=(",", ":"))
            + f"Generated {label}. Phased blocks (pale) and placed match segments; "
              "lineage codes relative to the siblings.")


def plot(profile, blocks, segs, deep, path, min_cM=12.0, strip=0):
    """One tester: two lanes per chromosome (paternal above maternal), phased
    blocks as pale background, placed match segments on top."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    fig, ax = plt.subplots(figsize=(14, 9))
    used = {}
    for i, chrom in enumerate([str(c) for c in range(1, 23)]):
        y = i * 1.0
        for b in blocks[blocks.chrom.astype(str) == chrom].itertuples():
            if b.lineage in BASE:
                lane = 0 if b.lineage[0] == "F" else 0.42
                ax.barh(y + lane, (b.end - b.start) / 1e6, left=b.start / 1e6, height=0.4,
                        color=_shade(b.lineage, pale=True), lw=0)
        d = segs[(segs.chrom.astype(str) == chrom) & segs.grandparent.isin(list(BASE))]
        for s in d.itertuples():
            code = deep.get(s.match_key, "")
            code = code if code.startswith(s.grandparent) else s.grandparent
            if s.cM < (7 if code != s.grandparent else min_cM):
                continue
            lane = 0 if s.grandparent[0] == "F" else 0.42
            deep_seg = len(code) > 2
            c = _shade(code)
            used[code] = c
            ax.barh(y + lane + (0.05 if deep_seg else 0.12), (s.end - s.start) / 1e6,
                    left=s.start / 1e6, height=0.3 if deep_seg else 0.16,
                    color=c, alpha=0.95 if deep_seg else 0.35, lw=0)
    ax.set_yticks([i + 0.4 for i in range(22)], [str(c) for c in range(1, 23)], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Mb (GRCh37)")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    handles = [Patch(color=c, label=k[strip:]) for k, c in sorted(used.items(), key=lambda kv: (len(kv[0]), kv[0]))]
    ax.legend(handles=handles[:24], loc="lower right", fontsize=7, frameon=False, ncol=2,
              title="placed match segments (deep codes: tree-linked)", title_fontsize=7)
    ax.set_title(f"{profile}: phased grandparent copies (pale) and placed match segments ≥ {min_cM:g} cM "
                 f"(tree-linked ≥ 7 cM, darker); paternal lane above maternal", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(min_cM=12.0):
    import config
    cfg = config.load()
    D = cfg["data_dir"]
    blocks = pd.read_csv(D / "phasing_grandparent_segments.csv", low_memory=False)
    segs = pd.read_csv(D / "placed_segments.csv", low_memory=False)
    placed = pd.read_csv(D / "placed_matches.csv", low_memory=False)
    tree, proband = None, None
    if cfg.get("gedcom"):
        import gedcom_io
        tree, proband = gedcom_io.load(cfg)
    deep = deep_codes(tree, proband, placed)
    label = f"synthetic_genealogy {pd.Timestamp.today().date()}"
    for key, p in cfg["people"].items():
        if p.get("role") not in ("child", "mother"):
            continue
        strip = 1 if p["role"] == "mother" else 0
        b = blocks[blocks.subject == key] if strip == 0 else blocks.iloc[0:0]
        s = segs[segs.subject == key]
        if s.empty:
            continue
        sex = {"M": "Male", "F": "Female"}.get(p.get("sex"), "")
        name = f"{config.display_name(cfg, key)} phased {pd.Timestamp.today().date()}"
        text = backup(name, sex, b, s, deep, tree, proband, strip=strip, min_cM=min_cM, label=label)
        out = D / f"dnapainter_phased_{key}.txt"
        out.write_text(text, encoding="utf-8")
        plot(config.display_name(cfg, key), b, s, deep, D / f"painting_{key}.png", min_cM, strip)
        n = text.count('"chromosome"')
        print(f"{key}: {n} segments -> {out.name}, painting_{key}.png")


if __name__ == "__main__":
    main()
