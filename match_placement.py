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
  * the mother matches them, but the segment reaches EXCESS_CM or more
    beyond her segments with them -> paternal (containment: she carries
    all of the child's maternal DNA). Only for exports of one vintage.
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
import pandas as pd

from intervals import overlap

OTHER_COPY_CM = 20
PURE = 0.8               # share of a segment on one grandparent to call it
OTHER = {"MF": "MM", "MM": "MF"}


_overlap = overlap      # older name, used by importers


def drop_family(segs, family):
    """Remove the nuclear family's own kits from a segment list; `family` is a
    family_filter.FamilyFilter (whole names or MyHeritage kits)."""
    return segs[~family.mask(segs)]


def painting_id(path):
    """A short checksum of a painting file: corrections name the painting
    they were made for."""
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_painting(data_dir, corrected=True):
    """The grandparent painting (phasing_labels.py), with the short-block
    corrections of sibling_consistency.py applied when they were made for
    this very painting (their `painting` column is its checksum). Stale
    corrections, made for an earlier painting, are ignored."""
    import outputs
    orig = data_dir.layer("output") / "phasing_grandparent_segments.csv"
    paint = outputs.read(data_dir, "phasing_grandparent_segments.csv", dtype={"chrom": str})
    paint["corrected_from"] = ""
    if not corrected or not outputs.has(data_dir, "phasing_corrections.csv"):
        return paint
    try:
        fixes = outputs.read(data_dir, "phasing_corrections.csv", dtype={"chrom": str})
    except pd.errors.EmptyDataError:
        return paint
    if not len(fixes) or "painting" not in fixes or (fixes.painting != painting_id(orig)).any():
        return paint
    for f in fixes.itertuples():
        m = ((paint.subject == f.subject) & (paint.chrom == str(f.chrom)) & (paint.parent == f.parent)
             & (paint.start == f.start) & (paint.end == f.end) & (paint.lineage == f.old))
        paint.loc[m, "corrected_from"] = f.old
        paint.loc[m, "lineage"] = f.new
    return paint


def painting_lookup(paint, subject):
    p = paint[paint.subject == subject]
    return {k: g[["start", "end", "lineage"]].to_numpy()
            for k, g in p.groupby(["chrom", "parent"])}


def _sure(look):
    """The purity a reading needs: PURE for a painting, the copy model's
    own threshold (min_p) for a copy model."""
    return getattr(look, "min_p", PURE)


def grandparent_of(look, chrom, parent, start, end):
    """(lineage, purity) of a child's copy over [start, end]. `look` is a
    painting lookup (painting_lookup) or a copy model (copy_model.py),
    whose purity is the probability of the grandparent over the segment."""
    if hasattr(look, "grandparent_of"):
        return look.grandparent_of(chrom, parent, start, end)
    rows = look.get((chrom, parent))
    if rows is None:
        return "", 0.0
    ov = _overlap(start, end, rows[:, 0].astype(float), rows[:, 1].astype(float))
    by = pd.Series(ov, index=rows[:, 2]).groupby(level=0).sum().drop("?", errors="ignore")
    if by.empty or by.max() == 0:
        return "", 0.0
    return by.idxmax(), float(by.max() / (end - start))


def _uncovered_cm(seg, others):
    """cM of a child's segment not covered by the mother's segments with the
    same match: the uncovered share of its bp times its own cM (pro rata
    within the child's segment only; the mother's cM can't be spread by bp,
    since cM/Mb varies too much along a chromosome). What a child got from
    the mother, she carries too, so a maternal segment has nothing left
    over beyond the vendors' endpoint noise."""
    if others is None or not len(others):
        return float(seg.cM)
    o = others[others.chrom == seg.chrom].sort_values("start")
    covered, reach = 0, seg.start
    for a, b in zip(o.start, o.end):      # union of her intervals inside it
        a, b = max(a, reach), min(b, seg.end)
        if b > a:
            covered += b - a
            reach = b
    return float(seg.cM) * (1 - covered / max(seg.end - seg.start, 1))


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
# Raised from 1.7 after a counterexample: a maternal match (painted MMM,
# clustered with maternal matches, child total 69 cM, segments implying the
# mother shares > 40 cM) was missing from the mother's 35-400 cM run. The run
# seems not to list every match in its window (a cap on the number of
# matches?), so absence is trusted only for large child totals.
WINDOW_MARGIN = 3.0

# Containment: a child's segment with a match the mother also has, reaching
# at least EXCESS_CM beyond her segments with that match, holds DNA she does
# not share with them, so it is paternal. 7 cM = the inference floor, well
# above endpoint noise. Example: a paternal 1C1R (350+ cM with each child)
# whom the mother matches on two stray 7-8 cM segments; one child's 25 cM
# segment overlapping her 8 cM one was called maternal. Only between exports
# at most SAME_VINTAGE_DAYS apart, since vendors recompute segments over the
# years (one match went from 21 to 10 cM between 2023 and 2026 at FTDNA).
EXCESS_CM = 7.0
SAME_VINTAGE_DAYS = 31


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
    same_vintage = abs((child["date"] - mum["date"]).days) <= SAME_VINTAGE_DAYS
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
        elif same_vintage and _uncovered_cm(s, by_key.get(s.match_key)) >= EXCESS_CM:
            side.append("F")
            why.append("%.0f cM beyond the mother's segments with this match"
                       % _uncovered_cm(s, by_key.get(s.match_key)))
        elif _best_overlap(s, by_key.get(s.match_key)) >= 0.5:
            side.append("M"); why.append("mother shares overlapping segment")
        else:
            side.append(""); why.append("mother matches them elsewhere only")
    return child["segs"].assign(parent=side, parent_reason=why)


def place_child(segs, look):
    pure = _sure(look)
    res = [grandparent_of(look, s.chrom, s.parent, s.start, s.end)
           if s.parent and s.chrom != "X" else ("", 0.0) for s in segs.itertuples()]
    out = segs.assign(grandparent=[r[0] for r in res], purity=[r[1] for r in res])
    out["straddles_crossover"] = (out.grandparent != "") & (out.purity < pure)
    out.loc[out.straddles_crossover, "grandparent"] = ""
    # where the parent is unknown, both readings: which grandparent if
    # paternal, which if maternal (same grandparent on both = side unknown
    # but each reading is internally simple)
    unres = (out.parent == "") & (out.chrom != "X")
    for par, col in (("F", "if_paternal"), ("M", "if_maternal")):
        out[col] = ""
        out.loc[unres, col] = [
            g if p >= pure else "" for g, p in
            (grandparent_of(look, s.chrom, par, s.start, s.end) for s in out[unres].itertuples())]
    return out


def place_child_both(segs, paint_look, model):
    """Grandparents from the copy model, with the painting's reading kept
    beside it (painting_grandparent, painting_purity) as the check.
    straddles_crossover stays the painting's: it is about the painting's
    crossovers; `purity` is the copy model's probability."""
    p = place_child(segs, paint_look)
    m = place_child(segs, model)
    out = m.assign(painting_grandparent=p.grandparent.where(p.grandparent != "", ""),
                   painting_purity=p.purity, straddles_crossover=p.straddles_crossover)
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
                if not mine or purity < _sure(c["look"]):
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


# ------------------------------------------------- the side from siblings
# A real segment of the child's with a match is on one parent's copy, and
# every full sibling carrying the same copy of that parent there shares it
# with the match too; a sibling carrying the other copy does not (unless
# the match is related on both sides). The phasing's copy labels say which
# siblings carry the same copy of each parent, so the pattern of which
# siblings have the segment names the side. Per other sibling the outcome
# is "has" (an overlapping segment with that match), "lacks" (lists the
# match, but not here) or "unlisted" (does not list the match at all; used
# only when that sibling's export is no older than the child's). Their
# chances, given the same or the other copy, are learnt from the segments
# whose side the mother's list already gives, per platform and size band.
# Held out on one family (2026-11-11), sides given at 0.9 or more were right
# 98.6-98.9% of the time where the mother shares the segment (10-20 cM;
# 97-100% from 20 cM), but only 64-82% at 7-10 cM, so smaller segments get
# no side from here.
SIDE_MIN_P = 0.9
SIDE_BANDS = (10, 20)           # cM band edges; segments under the first get no side here
OUTCOMES = ("has", "lacks", "unlisted")


def _band(cM):
    b = sum(cM >= e for e in SIDE_BANDS)
    return b if b else None


def label_lookup(labels):
    """phasing_labels.copy_label_runs rows -> {(sibling, chrom, parent):
    (starts, ends, labels)}."""
    return {k: (g.start.to_numpy(float), g.end.to_numpy(float), g.label.to_numpy())
            for k, g in labels.assign(chrom=labels.chrom.astype(str))
            .groupby(["sibling", "chrom", "parent"])}


def label_over(look, sib, chrom, parent, start, end, share=0.9):
    """The sibling's copy label of `parent` over [start, end], when one label
    covers at least `share` of it; else None."""
    r = look.get((sib, str(chrom), parent))
    if r is None:
        return None
    ov = _overlap(start, end, r[0], r[1])
    if not len(ov) or ov.max() <= 0:
        return None
    by = pd.Series(ov).groupby(r[2]).sum()
    return int(by.idxmax()) if by.max() >= share * (end - start) else None


def sibling_evidence(c, others, look):
    """Per segment of child c (rows of c["segs"], which must have `parent`):
    a list of (outcome, same_F, same_M) for each other sibling whose labels
    decide both sides there."""
    idx = [(o, dict(tuple(o["segs"].groupby("match_key")))) for o in others]
    out = []
    for s in c["segs"].itertuples():
        ev = []
        if s.chrom != "X" and _band(s.cM):
            mine = {p: label_over(look, c["subject"], s.chrom, p, s.start, s.end) for p in "FM"}
            if None not in mine.values():
                for o, by_key in idx:
                    theirs = {p: label_over(look, o["subject"], s.chrom, p, s.start, s.end) for p in "FM"}
                    if None in theirs.values():
                        continue
                    if _best_overlap(s, by_key.get(s.match_key)) >= 0.5:
                        outcome = "has"
                    elif s.match_key in o["keys"]:
                        outcome = "lacks"
                    elif o["date"] >= c["date"]:
                        outcome = "unlisted"
                    else:
                        continue
                    ev.append((o["subject"], outcome, mine["F"] == theirs["F"], mine["M"] == theirs["M"]))
        out.append(ev)
    return out


def side_rates(rows):
    """rows: (band, side, evidence) for segments of known side. Returns
    {(band, same): {outcome: probability}} (add-one smoothed)."""
    counts = {(b, same): dict.fromkeys(OUTCOMES, 1.0) for b in range(1, len(SIDE_BANDS) + 1)
              for same in (True, False)}
    for band, side, ev in rows:
        for _, outcome, sf, sm in ev:
            counts[(band, sf if side == "F" else sm)][outcome] += 1
    return {k: {o: n / sum(v.values()) for o, n in v.items()} for k, v in counts.items()}


def side_posterior(band, ev, rates):
    """P(paternal) from the siblings' outcomes (prior 1/2)."""
    import math
    lf = lm = 0.0
    for _, outcome, sf, sm in ev:
        lf += math.log(rates[(band, sf)][outcome])
        lm += math.log(rates[(band, sm)][outcome])
    return 1 / (1 + math.exp(lm - lf))


def sides_from_siblings(children, labels, min_p=SIDE_MIN_P):
    """Fill in the side of children's segments the mother's list leaves
    open, from which siblings share them (see above). children: kit dicts
    with `segs` already carrying parent / parent_reason. Only phased
    siblings (in `labels`) with full exports take part. Returns the rates
    learnt, per platform's children."""
    look = label_lookup(labels)
    phased = set(labels.sibling)
    kids = [c for c in children if c["subject"] in phased and not c.get("partial")]
    if len(kids) < 2:
        return None
    ev = {c["subject"]: sibling_evidence(c, [o for o in kids if o is not c], look) for c in kids}
    rows = [(_band(s.cM), s.parent, e) for c in kids
            for s, e in zip(c["segs"].itertuples(), ev[c["subject"]])
            if s.parent in ("F", "M") and s.chrom != "X" and e]
    rates = side_rates(rows)
    for c in kids:
        segs = c["segs"].copy()
        par, why = segs.parent.tolist(), segs.parent_reason.tolist()
        for i, (s, e) in enumerate(zip(segs.itertuples(), ev[c["subject"]])):
            if s.parent or not e:
                continue
            pf = side_posterior(_band(s.cM), e, rates)
            p = max(pf, 1 - pf)
            if p >= min_p:
                par[i] = "F" if pf >= 0.5 else "M"
                why[i] = (f"siblings ({p:.2f}): " + ", ".join(f"{n} {o}" for n, o, _, _ in e)
                          + f"; {why[i]}")
        c["segs"] = segs.assign(parent=par, parent_reason=why)
    return rates


def run_platform(children, mother, paint, models=None, labels=None):
    """children: list of kit dicts; mother: kit dict. Kit dict keys:
    subject, sex, date (Timestamp), segs, keys (set), meta (per-match).
    models: {subject: copy model}; a child with one is placed through it
    (the painting's reading kept beside), the others through the painting.
    labels: the phasing's copy labels; with them, segments the mother's
    list leaves without a side get one from the siblings where it is sure
    (sides_from_siblings).
    The mother's segments are voted by her children with the same choice."""
    models = models or {}
    for c in children:
        c["look"] = painting_lookup(paint, c["subject"])
        if mother is None:
            c["segs"] = c["segs"].assign(parent="", parent_reason="no mother export on this platform")
        else:
            c["segs"] = phase_child(c, mother)
    if labels is not None:
        sides_from_siblings(children, labels)
    for c in children:
        phased = c["segs"]
        if c["subject"] in models:
            c["segs"] = place_child_both(phased, c["look"], models[c["subject"]])
            c["look"] = models[c["subject"]]
        else:
            c["segs"] = place_child(phased, c["look"])
        c["placed"] = per_match(c["segs"], c["meta"])
    if mother is not None:
        # a partial export (selected matches only) cannot show what a child lacks
        mother["segs"] = place_mother(mother, [c for c in children if not c.get("partial")])
        mother["placed"] = per_match(mother["segs"], mother["meta"])
    return children, mother
