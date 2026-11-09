"""
Combine in-common-with (ICW) edges with the segment-based placement.

For each tester and platform with an ICW graph (icw_io):

1. **Validation**: for matches the segments already place confidently,
   how often do their confidently placed shared matches vote the same
   grandparent? That measures how far ICW can be trusted here.
2. **Candidates**: matches without a confident placement get the
   neighbours' vote, if at least `MIN_VOTES` neighbours vote and
   `MIN_SHARE` of them agree. The vote settles the side; the match's own
   unresolved segments, read on that side (`if_paternal`/`if_maternal`),
   then pick the grandparent, or the couple when both carry DNA. Written
   as low-weight assertions.
3. **Conflicts**: shared-match pairs both placed confidently but on
   different parents' sides. Each is a pile-up, a double relationship, a
   placement error or a phasing error worth a look.
   Matches descending from a grandparent couple (split placement, or a
   tree MRCA couple at grandparent level) are labelled by side only and
   vote for the side only (see COUPLE_*).
4. **Clusters**: the composition of each Genetic Affairs cluster by
   placement.
5. **Deeper lineage**: tree-linked matches (gedcom_io, via
   dnapainter_export.deep_codes) hand their deeper code to shared matches
   placed on the same grandparent. A candidate, not a finding.

Sketch. Weights are counts, not cM. Pile-up masking is not applied.
"""
from collections import Counter, defaultdict

import pandas as pd

GP = ("FF", "FM", "MF", "MM")
MIN_AGREE, MIN_CM = 0.75, 10.0
MIN_VOTES, MIN_SHARE = 2, 0.75
# A match descending from a grandparent COUPLE (a paternal first cousin,
# a half-sibling by twin fathers) shares DNA on both grandparents of one
# side. Placement shows it as a split; the tree as an MRCA couple at
# grandparent level (code "F" or "M"). Such matches are labelled by side
# only, and vote for the side only.
COUPLE_MIN_SHARE, COUPLE_MIN_CM = 0.25, 100.0


def pooled_couples(placed_all):
    """(platform, match_key) -> side, for matches whose placed DNA, pooled
    over all siblings, is split over both grandparents of one side. One
    sibling may by chance have inherited only one grandparent's part of a
    couple match's DNA; together they show both."""
    g = placed_all.groupby(["platform", "match_key"])[list(GP)].sum()
    out = {}
    for (plat, k), r in g.iterrows():
        for side in "FM":
            a, b = r[side + "F"], r[side + "M"]
            if a + b >= COUPLE_MIN_CM and min(a, b) / (a + b) >= COUPLE_MIN_SHARE:
                out[(plat, k)] = side
    return out


def confident(placed, deep=None, couples=None):
    """match_key -> label: a grandparent code ("FM"), or a side ("F", "M")
    for a grandparent couple (this tester's split, the siblings' pooled
    split in `couples`, or the tree)."""
    out = {}
    for (plat, k), side in (couples or {}).items():
        if (placed.platform == plat).any() and k in set(placed.match_key):
            out[k] = side
    for r in placed.itertuples():
        for side in "FM":
            a, b = getattr(r, side + "F", 0) or 0, getattr(r, side + "M", 0) or 0
            if a + b >= COUPLE_MIN_CM and min(a, b) / (a + b) >= COUPLE_MIN_SHARE:
                out[r.match_key] = side
        if r.match_key not in out and r.placement in GP and r.agreement >= MIN_AGREE \
                and r.placed_cM >= MIN_CM:
            out[r.match_key] = r.placement
    for k, code in (deep or {}).items():
        if code in ("F", "M"):            # tree: MRCA couple at grandparent level
            out[k] = code
    return out


def readings(segs):
    """(match_key) -> {"F": Counter(FF/FM cM), "M": Counter(MF/MM cM)} from
    segments whose parent is unknown: which grandparent each would be on
    if it were paternal (if_paternal) or maternal (if_maternal)."""
    out = defaultdict(lambda: {"F": Counter(), "M": Counter()})
    u = segs[(segs.parent.fillna("") == "") & (segs.chrom.astype(str) != "X")]
    for side, col in (("F", "if_paternal"), ("M", "if_maternal")):
        v = u[u[col].fillna("").isin(GP)]
        for k, g, cm in zip(v.match_key, v[col], v.cM):
            out[k][side][g] += cm
    return out


def refine(side, reading):
    """ICW gives the side; the match's own segments, read on that side,
    give the grandparent, or the couple when both carry DNA."""
    c = reading[side] if reading else Counter()
    tot = sum(c.values())
    if tot < 20:
        return side, "side from ICW; too little segment data to pick a grandparent"
    g, v = c.most_common(1)[0]
    if tot >= COUPLE_MIN_CM and (tot - v) / tot >= COUPLE_MIN_SHARE:
        return side, f"segments split {dict((k, round(x)) for k, x in c.items())} cM: a grandparent couple"
    if v / tot >= MIN_AGREE:
        return g, f"segments read on side {side}: {round(v)} of {round(tot)} cM on {g}"
    return side, f"segments read on side {side} disagree ({dict((k, round(x)) for k, x in c.items())} cM)"


def neighbours(edges):
    nb = defaultdict(set)
    for a, b in zip(edges.a_key, edges.b_key):
        nb[a].add(b); nb[b].add(a)
    return nb


def vote(keys, conf):
    """Side first (every labelled neighbour), then grandparent among the
    grandparent-level neighbours of that side. Returns (label, voters,
    share of the side vote). The label is a side ("F") when couple-level
    neighbours dominate or both grandparents of the side get votes."""
    labels = [conf[k] for k in keys if k in conf]
    if not labels:
        return "", 0, 0.0
    sides = Counter(l[0] for l in labels)
    side, n_side = sides.most_common(1)[0]
    n = len(labels)
    gps = Counter(l for l in labels if len(l) == 2 and l[0] == side)
    couples = sum(1 for l in labels if l == side)
    if not gps or couples >= sum(gps.values()):
        return side, n, n_side / n
    gp, g = gps.most_common(1)[0]
    other = sum(gps.values()) - g
    if other / sum(gps.values()) >= COUPLE_MIN_SHARE:
        return side, n, n_side / n
    return gp, n, (g + couples) / n


def analyse(nodes, edges, placed, deep=None, reading=None, couples=None):
    deep = deep or {}
    reading = reading or {}
    conf = confident(placed, deep, couples)
    nb = neighbours(edges)
    names = dict(zip(nodes.match_key, nodes.match))
    rows = []
    for k in nodes.match_key.unique():
        gp, n, share = vote(nb.get(k, ()), conf)
        own = conf.get(k, "")
        if own and gp and n >= MIN_VOTES:
            if own == gp:
                status = "agrees"
            elif own[0] != gp[0]:
                status = "conflicts"
            elif len(own) == 1:
                status = "agrees on side"        # a couple match, voted by grandparent
            elif len(gp) == 1:
                status = "vote split"            # neighbours on both grandparents of the side
            else:
                status = "conflicts"             # the other grandparent of the same side
        elif not own and gp and n >= MIN_VOTES and share >= MIN_SHARE:
            status = "candidate"
        else:
            status = "no call"
        label, why = gp, "ICW vote"
        if status == "candidate":
            label, why = refine(gp[0], reading.get(k))
        if own in ("F", "M") and status != "candidate":
            label, why = own, "grandparent couple (own or siblings' pooled split, or tree)"
        # deeper: tree codes of neighbours on the same grandparent
        target = own or (label if status == "candidate" else "")
        dc = Counter(deep[x] for x in nb.get(k, ()) if x in deep and len(target) == 2
                     and deep[x].startswith(target) and len(deep[x]) > 2)
        rows.append(dict(match_key=k, match=names.get(k, k), own=own, icw_vote=gp, voters=n,
                         share=round(share, 2), status=status, label=label, why=why,
                         own_deep=deep.get(k, ""),
                         deep_from_neighbours=" ".join(f"{c}×{v}" for c, v in dc.most_common(3))))
    res = pd.DataFrame(rows)
    conflicts = []
    for a, b in zip(edges.a_key, edges.b_key):
        if a in conf and b in conf and conf[a][0] != conf[b][0]:
            conflicts.append(dict(a=names.get(a, a), a_place=conf[a], b=names.get(b, b), b_place=conf[b]))
    clusters = None
    if nodes.cluster.astype(str).str.strip().ne("").any():
        cl = nodes.assign(own=nodes.match_key.map(conf).fillna(""))
        clusters = (cl.groupby("cluster").agg(n=("match_key", "size"),
                                              placed=("own", lambda s: (s != "").sum()),
                                              composition=("own", lambda s: " ".join(
                                                  f"{g}:{v}" for g, v in Counter(x for x in s if x).most_common())))
                    .reset_index())
    return res, pd.DataFrame(conflicts), clusters


def main():
    import config
    import icw_io
    cfg = config.load()
    D = cfg["data_dir"]
    nodes, edges = icw_io.load(cfg)
    placed = pd.read_csv(D / "placed_matches.csv", low_memory=False)
    segs = pd.read_csv(D / "placed_segments.csv", low_memory=False,
                       usecols=["platform", "subject", "match_key", "chrom", "cM", "parent",
                                "if_paternal", "if_maternal"])
    couples = pooled_couples(placed)
    deep = {}
    if cfg.get("gedcom"):
        import dnapainter_export
        import gedcom_io
        tree, proband = gedcom_io.load(cfg)
        deep = dnapainter_export.deep_codes(tree, proband, placed)
    assertions = []
    md = ["# In-common-with (ICW) evidence against the placement",
                      "", "Generated by `icw_phasing.py`. Votes are counts of confidently placed shared matches "
                      f"(agreement ≥ {MIN_AGREE}, ≥ {MIN_CM:g} cM placed); a candidate needs ≥ {MIN_VOTES} voters "
                      f"and ≥ {MIN_SHARE:.0%} agreement. Candidates are hints, not placements.", ""]
    for (subj, plat), n in nodes.groupby(["subject", "platform"]):
        e = edges[(edges.subject == subj) & (edges.platform == plat)]
        p = placed[(placed.subject == subj) & (placed.platform == plat)]
        sg = segs[(segs.subject == subj) & (segs.platform == plat)]
        res, conf, clusters = analyse(n, e, p, deep, readings(sg), couples)
        st = res.status.value_counts()
        ag, sd, co, sp = (st.get("agrees", 0), st.get("agrees on side", 0), st.get("conflicts", 0),
                          st.get("vote split", 0))
        md += [f"## {config.display_name(cfg, subj)}, {plat}: {len(n)} matches, {len(e)} shared-match pairs", "",
               f"- Validation: where both exist, the ICW vote agrees with the segment placement for "
               f"**{ag + sd} of {ag + sd + co}** matches ({(ag + sd) / max(ag + sd + co, 1):.0%}; "
               f"{sd} of them couple matches agreeing on the side). Votes split over both "
               f"grandparents of the right side, so no grandparent call: {sp}.",
               f"- Candidates for unplaced matches: {st.get('candidate', 0)}. No call: {st.get('no call', 0)}.",
               f"- Pairs placed on different parents' sides: {len(conf)}.", ""]
        cand = res[res.status == "candidate"].sort_values("voters", ascending=False)
        if len(cand):
            md += ["| candidate | ICW vote | voters | share | label | why | deeper hint |",
                   "|---|---|---|---|---|---|---|"]
            md += [f"| {r.match} | {r.icw_vote} | {r.voters} | {r.share} | {r.label} | {r.why} | {r.deep_from_neighbours} |"
                   for r in cand.head(30).itertuples()] + [""]
        bad = res[res.status == "conflicts"].sort_values("voters", ascending=False)
        if len(bad):
            md += ["Matches whose shared matches vote against their own placement:", "",
                   "| match | placed | ICW vote | voters | share |", "|---|---|---|---|---|"]
            md += [f"| {r.match} | {r.own} | {r.icw_vote} | {r.voters} | {r.share} |"
                   for r in bad.head(20).itertuples()] + [""]
        deeper = res[(res.deep_from_neighbours != "") & (res.own_deep == "")]
        if len(deeper):
            md += ["Deeper-lineage hints (tree-linked shared matches on the same grandparent):", "",
                   "| match | placed / candidate | hint |", "|---|---|---|"]
            md += [f"| {r.match} | {r.own or r.icw_vote} | {r.deep_from_neighbours} |"
                   for r in deeper.head(30).itertuples()] + [""]
        if clusters is not None and len(clusters):
            md += ["Clusters by placement:", "", "| cluster | matches | placed | composition |", "|---|---|---|---|"]
            md += [f"| {r.cluster} | {r.n} | {r.placed} | {r.composition} |"
                   for r in clusters.sort_values("n", ascending=False).itertuples()] + [""]
        for r in cand.itertuples():
            assertions.append(dict(subject=subj, platform=plat, match_key=r.match_key, match=r.match,
                                   lineage=r.label, kind="icw_candidate", why=r.why, icw_vote=r.icw_vote,
                                   voters=r.voters, share=r.share,
                                   deeper_hint=r.deep_from_neighbours, asserted_by="icw_phasing.py",
                                   source=", ".join(sorted(e.source.unique()))))
        for r in deeper[deeper.status != "candidate"].itertuples():
            assertions.append(dict(subject=subj, platform=plat, match_key=r.match_key, match=r.match,
                                   lineage=r.deep_from_neighbours.split("×")[0], kind="icw_deeper_hint",
                                   voters=r.voters, share=r.share, deeper_hint=r.deep_from_neighbours,
                                   asserted_by="icw_phasing.py", source=", ".join(sorted(e.source.unique()))))
    (D / "icw_report.md").write_text("\n".join(md), encoding="utf-8")
    pd.DataFrame(assertions).to_csv(D / "assertions_icw.csv", index=False)
    print("\n".join(l for l in md if l.startswith(("## ", "- "))))


if __name__ == "__main__":
    main()
