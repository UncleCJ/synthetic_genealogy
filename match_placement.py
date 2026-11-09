"""
Place children's and their mother's DNA matches on the children's
grandparents, from segment lists of any vendor.

Inputs
------
- per kit: segments (subject, match_key, match, chrom, start, end, cM),
  the set of match keys in its full match list, and the export date
  (ftdna_io, myheritage_io)
- each child's grandparent painting from visual phasing
  (phasing_grandparent_segments.csv, phasing_labels.py)

Reasoning, per segment
----------------------
Child's segment:
  * the mother has the same match on an overlapping segment -> maternal
  * the match is absent from the mother's list -> paternal
    (what the child got from her, she carries too). Needs her export to
    be at least as recent as the child's; otherwise a newer match is
    simply missing. Small segments that are false (IBS) also land here,
    so "paternal by absence" is weaker than "maternal by overlap".
  * the mother matches them, but elsewhere -> unresolved
  then the child's painting on that parent's track names the grandparent;
  a segment straddling the child's crossover is flagged (false segment,
  or the crossover is misplaced).

Mother's segment (her two copies are MF and MM), voted by every child
on the same platform:
  * the child shares it -> it is on the copy the child got there
  * a long segment (>= OTHER_COPY_CM) the child lacks, in a stretch where
    the child's maternal copy is one grandparent throughout -> the OTHER
    copy. Long, because a match list needs ~20 cM in total, and only if
    the child's export is at least as recent as the mother's.
  Children voting differently -> "conflict".
"""
import numpy as np
import pandas as pd

OTHER_COPY_CM = 20
PURE = 0.8               # share of a segment on one grandparent to call it
OTHER = {"MF": "MM", "MM": "MF"}


def _overlap(a0, a1, b0, b1):
    return np.clip(np.minimum(a1, b1) - np.maximum(a0, b0), 0, None)


def drop_family(segs, family):
    """Remove the nuclear family's own kits from a segment list; `family` is a
    family_filter.FamilyFilter (whole names or MyHeritage kits)."""
    return segs[~family.mask(segs)]


def load_painting(data_dir):
    """The grandparent painting: the corrected one (sibling_consistency.py)
    when it is newer than phasing_labels.py's output, else the original."""
    import pandas as pd
    orig = data_dir / "phasing_grandparent_segments.csv"
    corr = data_dir / "phasing_grandparent_segments_corrected.csv"
    path = corr if corr.exists() and corr.stat().st_mtime >= orig.stat().st_mtime else orig
    return pd.read_csv(path, dtype={"chrom": str}, low_memory=False)


def painting_lookup(paint, subject):
    p = paint[paint.subject == subject]
    return {k: g[["start", "end", "lineage"]].to_numpy()
            for k, g in p.groupby(["chrom", "parent"])}


def grandparent_of(look, chrom, parent, start, end):
    """(lineage, purity) of a child's copy over [start, end]."""
    rows = look.get((chrom, parent))
    if rows is None:
        return "", 0.0
    ov = _overlap(start, end, rows[:, 0].astype(float), rows[:, 1].astype(float))
    by = pd.Series(ov, index=rows[:, 2]).groupby(level=0).sum().drop("?", errors="ignore")
    if by.empty or by.max() == 0:
        return "", 0.0
    return by.idxmax(), float(by.max() / (end - start))


def _best_overlap(seg, others):
    if others is None or not len(others):
        return 0.0
    o = others[others.chrom == seg.chrom]
    if not len(o):
        return 0.0
    return float(_overlap(seg.start, seg.end, o.start.to_numpy(),
                          o.end.to_numpy()).max() / (seg.end - seg.start))


# Checked on matches the segment rules already decide (MyHeritage, 2026-11-09):
# at child totals >= 1.7 x the window's floor, 21/21 maternal matches were in the
# mother's window and 22/22 paternal ones absent; at 1.25 x, 9 of 48 maternal
# matches were missing (vendor totals for mother and child differ that much).
WINDOW_MARGIN = 1.7


def phase_child(child, mum):
    """child, mum: kit dicts. Adds parent ('F'/'M'/'') and parent_reason."""
    by_key = dict(tuple(mum["segs"].groupby("match_key")))
    absence_ok = mum["date"] >= child["date"]
    # A newer child export can still use absence for matches it already had
    # in an export no newer than the mother's: they existed when hers was made.
    old = (child.get("old_keys", set())
           if child.get("old_date") is not None and child["old_date"] <= mum["date"] else set())
    # A mother's AutoCluster window (every match she shares min..max cM with,
    # on a date no older than the child's export). A maternal match sharing
    # at least WINDOW_MARGIN * min with the child shares at least about that
    # with the mother, so it would be listed. Upper bound: max/2, since a
    # maternal match the child shares more with could exceed max with her.
    win = mum.get("window")
    if win is not None and win["date"] >= child["date"] and win["min_cm"] and win["max_cm"]:
        import icw_io
        tot = child["segs"].groupby("match_key").cM.sum()
        names = child["segs"].drop_duplicates("match_key").set_index("match_key").match.map(icw_io.name_key)
        lo, hi = WINDOW_MARGIN * win["min_cm"], win["max_cm"] / 2
        win_absent = {k for k, t in tot.items() if lo <= t <= hi and k not in win["ids"]
                      and names.get(k) not in win["names"]}
    else:
        win_absent = set()
    side, why = [], []
    for s in child["segs"].itertuples():
        if s.chrom == "X":
            if child.get("sex") == "M":
                side.append("M"); why.append("X chromosome (son)")
            else:
                side.append(""); why.append("X chromosome (daughter)")
        elif s.match_key not in mum["keys"]:
            if absence_ok:
                side.append("F"); why.append("match absent from mother's list")
            elif s.match_key in old:
                side.append("F"); why.append("match absent from mother's list (already in child's older export)")
            elif s.match_key in win_absent:
                side.append("F"); why.append("match absent from mother's AutoCluster window")
            else:
                side.append(""); why.append("mother's list older than child's")
        elif _best_overlap(s, by_key.get(s.match_key)) >= 0.5:
            side.append("M"); why.append("mother shares overlapping segment")
        else:
            side.append(""); why.append("mother matches them elsewhere only")
    return child["segs"].assign(parent=side, parent_reason=why)


def place_child(segs, look):
    res = [grandparent_of(look, s.chrom, s.parent, s.start, s.end)
           if s.parent and s.chrom != "X" else ("", 0.0) for s in segs.itertuples()]
    out = segs.assign(grandparent=[r[0] for r in res], purity=[r[1] for r in res])
    out["straddles_crossover"] = (out.grandparent != "") & (out.purity < PURE)
    out.loc[out.straddles_crossover, "grandparent"] = ""
    # where the parent is unknown, both readings: which grandparent if
    # paternal, which if maternal (same grandparent on both = side unknown
    # but each reading is internally simple)
    unres = (out.parent == "") & (out.chrom != "X")
    for par, col in (("F", "if_paternal"), ("M", "if_maternal")):
        out[col] = ""
        out.loc[unres, col] = [
            g if p >= PURE else "" for g, p in
            (grandparent_of(look, s.chrom, par, s.start, s.end) for s in out[unres].itertuples())]
    return out


def place_mother(mum, children):
    """children: kit dicts already placed (segs with grandparent) + 'look'."""
    idx = [(c, dict(tuple(c["segs"].groupby("match_key"))), mum["date"] <= c["date"])
           for c in children]
    gp, why = [], []
    for s in mum["segs"].itertuples():
        votes = []
        if s.chrom != "X":
            for c, by_key, lack_ok in idx:
                mine, purity = grandparent_of(c["look"], s.chrom, "M", s.start, s.end)
                if not mine or purity < PURE:
                    continue
                shared = _best_overlap(s, by_key.get(s.match_key))
                if shared >= 0.5:
                    votes.append((mine, f"{c['subject']} shares it"))
                elif shared == 0 and lack_ok and s.cM >= OTHER_COPY_CM:
                    votes.append((OTHER[mine], f"{c['subject']} lacks it (has {mine} here)"))
        calls = {v for v, _ in votes}
        gp.append(calls.pop() if len(calls) == 1 else ("conflict" if calls else ""))
        why.append("; ".join(r for _, r in votes))
    return mum["segs"].assign(grandparent=gp, reason=why)


def per_match(segs, meta):
    """Aggregate placed segments per match: cM-weighted votes."""
    placed = segs[segs.grandparent.isin(["FF", "FM", "MF", "MM"])]
    votes = placed.pivot_table(index="match_key", columns="grandparent",
                               values="cM", aggfunc="sum", fill_value=0)
    votes = votes.reindex(columns=["FF", "FM", "MF", "MM"], fill_value=0)
    tot = votes.sum(1)
    out = pd.DataFrame(dict(placement=votes.idxmax(1),
                            agreement=(votes.max(1) / tot).round(2),
                            placed_cM=tot.round(1),
                            n_placed=placed.groupby("match_key").size())).join(votes.round(1))
    return meta.drop_duplicates("match_key").merge(out, left_on="match_key",
                                                   right_index=True, how="inner")


def pileups(segs, bin_mb=2, z=3.0):
    """Bins with far more segments than typical (likely IBC/pile-up)."""
    s = segs[segs.chrom != "X"]
    c = (s.assign(bin=((s.start + s.end) / 2 // (bin_mb * 1e6)).astype(int))
         .groupby(["chrom", "bin"]).size().rename("count").reset_index())
    med = c["count"].median()
    mad = (c["count"] - med).abs().median()
    c["z"] = ((c["count"] - med) / (1.4826 * mad)).round(1)
    c["start_Mb"], c["end_Mb"] = c.bin * bin_mb, (c.bin + 1) * bin_mb
    return c[c.z >= z].sort_values("z", ascending=False)[
        ["chrom", "start_Mb", "end_Mb", "count", "z"]]


def run_platform(children, mother, paint):
    """children: list of kit dicts; mother: kit dict. Kit dict keys:
    subject, sex, date (Timestamp), segs, keys (set), meta (per-match)."""
    for c in children:
        c["look"] = painting_lookup(paint, c["subject"])
        if mother is None:
            phased = c["segs"].assign(parent="", parent_reason="no mother export on this platform")
        else:
            phased = phase_child(c, mother)
        c["segs"] = place_child(phased, c["look"])
        c["placed"] = per_match(c["segs"], c["meta"])
    if mother is not None:
        # a partial export (selected matches only) cannot show what a child lacks
        mother["segs"] = place_mother(mother, [c for c in children if not c.get("partial")])
        mother["placed"] = per_match(mother["segs"], mother["meta"])
    return children, mother
