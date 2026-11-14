"""
Compare two exports of one family tree, and look for redundancy in one.

    python3 gedcom_audit.py diff OLD.ged NEW.ged
    python3 gedcom_audit.py audit FILE.ged

`diff` matches people by their MyHeritage ID (FACT or RIN "MH:I<n>"), so a
Gramps-cleaned export and a raw MyHeritage export of the same tree line up.
It reports people added and removed, and for people in both: changed
names, birth and death dates, and changed parents. Nothing is merged.

    python3 gedcom_audit.py cross THEIRS.ged PROBAND [OURS.ged OUR_PROBAND]

`cross` compares the ancestors of a match's tree (another vendor's
export, or one typed up by hand) with ours (family.toml's tree and
proband unless given): the same person in both (name and birth year,
birth parish beside it) with the relationship that would follow, then
the parishes and the non-patronymic surnames both ancestries hold, with
their years and lineage codes. PROBAND is an xref, a FACT value or a
name pattern. Candidates only: a name match is no identity
(concepts.md); confirm one by hand before `[[identity]]`. Unvalidated.

`audit` reports what tends to pile up in vendor exports:
- source records with the same title (e.g. one per Smart Match),
- citations repeated on one event (same source and page),
- events repeated on one person (same tag, date and place),
- people with the same name and birth year (possible duplicates),
- people without a MyHeritage ID,
- families with the same couple, and children listed twice,
- children perhaps under the wrong union (`misplaced`): born after the
  mother's death, or more than ten months after the father's; born before
  the union's marriage while the parent's earlier partner was alive and
  married to them; a mother under 14 or over 50, a father under 14, at
  the birth. Each names the parent's other unions that could hold the
  child. Dates are read to the day where written; a vague one only
  counts when its whole range is on the wrong side. Candidates for a
  look, not errors: a premarital child of the new couple trips the
  second rule too.
"""
import sys
from collections import Counter, defaultdict

import gedcom_io as g
import identity


def _mh(tree, i):
    return identity.mh_id(tree.people[i]["facts"])


def diff(old, new):
    a, b = g.Tree(old, keep_unlinked=True), g.Tree(new, keep_unlinked=True)   # the whole files
    am = {_mh(a, i): i for i in a.people if _mh(a, i)}
    bm = {_mh(b, i): i for i in b.people if _mh(b, i)}
    added = sorted(set(bm) - set(am), key=lambda k: int(k.split("I")[-1]))
    removed = sorted(set(am) - set(bm), key=lambda k: int(k.split("I")[-1]))
    changes = defaultdict(list)
    for k in set(am) & set(bm):
        p, q = a.people[am[k]], b.people[bm[k]]
        if (p["given"], p["surname"]) != (q["given"], q["surname"]):
            changes["name"].append((k, f"{p['given']} {p['surname']}", f"{q['given']} {q['surname']}"))
        for ev in ("birth", "death"):
            x, y = (p[ev] or {}), (q[ev] or {})
            if (x.get("date"), x.get("place")) != (y.get("date"), y.get("place")):
                if x.get("date") or y.get("date"):
                    changes[ev].append((k, f"{x.get('date','')} {x.get('place','')}".strip(),
                                        f"{y.get('date','')} {y.get('place','')}".strip()))
        pa = sorted(_mh(a, x) or x for x in a.parents(am[k]))
        pb = sorted(_mh(b, x) or x for x in b.parents(bm[k]))
        if pa != pb:
            changes["parents"].append((k, " + ".join(pa) or "-", " + ".join(pb) or "-"))
    return a, b, added, removed, changes


def _nkey(s):
    """A name compared across trees: spelling noise folded, C as K."""
    import gazetteer
    return gazetteer.fold(identity.name_key(s)).replace("c", "k")


def _parish(place, names, memo):
    """The one parish group a place string names, or None."""
    if place not in memo:
        import gazetteer
        memo[place] = None
        for part in gazetteer.plac_parts(place):
            c = names.candidates(part)
            if len(c) == 1:
                memo[place] = next(iter(c))
                break
    return memo[place]


def _proband(tree, ref):
    try:
        return tree.id(ref)
    except KeyError:
        hits = tree.find(ref)
        if len(hits) != 1:
            raise SystemExit(f"proband {ref!r}: {len(hits)} people match; give an xref")
        return hits[0]


def _ancestry(tree, proband, names, memo, depth):
    """One row per ancestor: keys, years, parishes, all lineage codes."""
    rows = {}
    for x, code in tree.ancestors(proband, max_depth=depth):
        if x in rows:
            rows[x]["codes"].append(code)
            continue
        p = tree.people[x]
        b, d = p["birth"] or {}, p["death"] or {}
        rows[x] = dict(id=x, label=tree.label(x), codes=[code],
                       given=_nkey((p["given"] or "").split(" ")[0]) if p["given"] else "",
                       surname=_nkey(p["surname"]), born=b.get("year"), died=d.get("year"),
                       parishes={q for q in (_parish(e.get("place"), names, memo)
                                             for e in (b, d) if e.get("place")) if q})
        rows[x]["birth_parish"] = _parish(b.get("place"), names, memo) if b.get("place") else None
    return list(rows.values())


def cross(theirs, their_proband, ours=None, our_proband=None, years=5, depth=12):
    """Candidate shared ancestors, shared parishes and shared surnames."""
    import parish_names
    if ours is None:
        ours, our_proband = g.load()
    else:
        ours = g.Tree(ours)
    them = g.Tree(theirs, keep_unlinked=True)
    names, memo = parish_names.load(), {}
    a = _ancestry(ours, _proband(ours, our_proband), names, memo, depth)
    b = _ancestry(them, _proband(them, their_proband), names, memo, depth)
    same = []
    for x in a:
        for y in b:
            if not x["given"] or x["given"] != y["given"]:
                continue
            gap = abs(x["born"] - y["born"]) if x["born"] and y["born"] else None
            parish = x["birth_parish"] and x["birth_parish"] == y["birth_parish"]
            if gap is not None and gap > years:
                continue
            if x["surname"] != y["surname"] and not (parish and gap is not None and gap <= 1):
                continue                     # a woman under her husband's name: needs place and year
            if gap is None and not parish:
                continue
            ca, cb = min(x["codes"], key=len), min(y["codes"], key=len)
            same.append(dict(ours=x["label"], theirs=y["label"], our_codes=x["codes"],
                             their_codes=y["codes"], gap=gap,
                             parish=names.label(x["birth_parish"]) if parish else "",
                             relationship=g.relationship_name(len(ca), len(cb))))
    # the closest pair per line: one whose codes extend another pair's on both sides adds nothing
    pairs = {(c, d) for r in same for c in r["our_codes"] for d in r["their_codes"]}
    for r in same:
        r["above"] = len([1 for c in r["our_codes"] for d in r["their_codes"]
                          for c2, d2 in pairs if c != c2 and c.startswith(c2) and d.startswith(d2)
                          and len(c) - len(c2) == len(d) - len(d2)])
    same = [r for r in same if not r.pop("above")]
    same.sort(key=lambda r: (not r["parish"], r["gap"] if r["gap"] is not None else 99,
                             min(map(len, r["our_codes"]))))

    def spans(rows, key):
        out = defaultdict(list)
        for r in rows:
            for k in key(r):
                out[k].append(r)
        return out

    def summary(rs):
        ys = [y for r in rs for y in (r["born"], r["died"]) if y]
        span = f"{min(ys)}–{max(ys)}" if ys else "?"
        codes = sorted({min(r["codes"], key=len) for r in rs}, key=len)
        return f"{span} {', '.join(codes[:6])}" + (" …" if len(codes) > 6 else "")

    pa, pb = spans(a, lambda r: r["parishes"]), spans(b, lambda r: r["parishes"])
    parishes = [(names.label(q), summary(pa[q]), summary(pb[q])) for q in sorted(set(pa) & set(pb),
                key=lambda q: min(len(c) for r in pa[q] + pb[q] for c in r["codes"]))]
    surn = lambda r: [r["surname"]] if r["surname"] and not identity.PATRONYMIC.search(r["surname"]) else []
    sa, sb = spans(a, surn), spans(b, surn)
    surnames = [(s, summary(sa[s]), summary(sb[s])) for s in sorted(set(sa) & set(sb))]
    return dict(ancestors=(len(a), len(b)), same=same, parishes=parishes, surnames=surnames)


_MON = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}


def _span(ev):
    """(earliest, latest) day of an event's GEDCOM date as date.toordinal(),
    None without a usable date. ABT/EST/CAL widen by a year; BEF and AFT
    leave the other end open."""
    import calendar
    import datetime as dt
    if not ev or not ev.get("date"):
        return None
    w = ev["date"].upper().replace("(", " ").split()
    q = w[0] if w and w[0] in ("ABT", "EST", "CAL", "BEF", "AFT", "BET", "FROM", "TO") else ""
    nums = []
    i = 0
    while i < len(w):                       # day? month? year, in that order
        if w[i].isdigit() and len(w[i]) == 4:
            y = int(w[i])
            m = _MON.get(w[i - 1]) if i >= 1 else None
            d = int(w[i - 2]) if m and i >= 2 and w[i - 2].isdigit() else None
            lo = dt.date(y, m or 1, d or 1)
            hi = dt.date(y, m or 12, d or calendar.monthrange(y, m or 12)[1])
            nums.append((lo.toordinal(), hi.toordinal()))
        i += 1
    if not nums:
        return None
    lo, hi = min(x for x, _ in nums), max(x for _, x in nums)
    if q in ("ABT", "EST", "CAL"):
        lo, hi = lo - 365, hi + 365
    elif q == "BEF":
        lo = None
    elif q == "AFT":
        lo, hi = lo, None
    return lo, hi


def misplaced(t):
    """Children perhaps under the wrong union: list of dicts (child, union,
    why, candidates), see the module docstring."""
    out = []
    unions = defaultdict(list)                  # parent -> unions they are a partner in
    for f in t.families.values():
        for q in (f["husb"], f["wife"]):
            if q:
                unions[q].append(f)
    span = lambda i, e: _span(t.people[i][e]) if i else None
    after = lambda a, b, gap=0: a and b and a[0] is not None and b[1] is not None and a[0] > b[1] + gap
    for f in t.families.values():
        m_start = _span(f.get("marriage"))
        for c, _ in f["children"]:
            b = span(c, "birth")
            if not b:
                continue
            why = []      # (reason, the parent whose other unions could hold the child)
            mother, father = f["wife"], f["husb"]
            if mother and after(b, span(mother, "death")):
                why.append(("born after the mother's death", father))
            if father and after(b, span(father, "death"), 300):
                why.append(("born over ten months after the father's death", mother))
            for par, via, who, lo_age, hi_age in ((mother, father, "mother", 14, 50), (father, mother, "father", 14, None)):
                pb = span(par, "birth")
                if pb and None not in pb and None not in b:
                    if b[1] < pb[0] + lo_age * 365:
                        why.append((f"the {who} under {lo_age} at the birth", via))
                    elif hi_age and b[0] > pb[1] + (hi_age + 1) * 365:
                        why.append((f"the {who} over {hi_age} at the birth", via))
            if m_start and m_start[0] is not None and b[1] is not None and b[1] < m_start[0]:
                for par in (father, mother):
                    for g in unions.get(par, []):
                        z = g["wife"] if par == g["husb"] else g["husb"]
                        gm = _span(g.get("marriage"))
                        if g is not f and z and gm and gm[1] is not None and b[0] is not None \
                                and gm[1] < b[0] and after(span(z, "death"), b):
                            why.append(("born before this marriage, while the parent's earlier partner lived", par))
            seen = set()
            for text, via in why:
                if text in seen:
                    continue
                seen.add(text)
                cands = []
                for g in unions.get(via, []):
                    z = g["wife"] if via == g["husb"] else g["husb"]
                    gap = 0 if z == g["wife"] else 300
                    if g is not f and not (z and after(b, span(z, "death"), gap)):
                        cands.append(g["id"] + (f" ({t.label(z)})" if z else " (partner unrecorded)"))
                out.append(dict(child=t.label(c), union=f["id"], why=text, candidates=cands))
    return out


def audit(path):
    recs = g.parse(path, keep_unlinked=True)
    out = {}
    titles = Counter(next((s["value"] for s in r["sub"] if s["tag"] == "TITL"), "")
                     for r in recs if r["tag"] == "SOUR")
    out["source titles used by more than one source record"] = {t: n for t, n in titles.items() if n > 1}
    rep_cit, rep_ev, no_id, same = Counter(), Counter(), 0, defaultdict(list)

    def flat(n):            # a node and everything under it, as one comparable value
        return (n["tag"], n["value"], tuple(flat(s) for s in n["sub"] if s["tag"] not in ("_UPD", "CHAN")))

    for r in recs:
        if r["tag"] != "INDI":
            continue
        # citations: MyHeritage attaches them to the person (1 SOUR + PAGE),
        # Gramps to events; count both. A repeat = same source and page.
        cits = Counter()
        for e in r["sub"]:
            for s in ([e] if e["tag"] == "SOUR" else [x for x in e["sub"] if x["tag"] == "SOUR"]):
                cits[(e["tag"], s["value"], next((x["value"] for x in s["sub"] if x["tag"] == "PAGE"), ""))] += 1
        rep_cit["repeated"] += sum(n - 1 for n in cits.values() if n > 1)
        rep_cit["total"] += sum(cits.values())
        evs = Counter(flat(e) for e in r["sub"]
                      if e["tag"] not in ("NAME", "SEX", "FAMC", "FAMS", "RIN", "_UID", "_UPD", "FACT", "CHAN", "SOUR"))
        rep_ev["repeated"] += sum(n - 1 for n in evs.values() if n > 1)
        rep_ev["total"] += sum(evs.values())
        if not any(s["tag"] in ("RIN", "FACT") and s["value"].startswith("MH:") for s in r["sub"]):
            no_id += 1
    out["citations repeated on one person or event (same source and page)"] = f"{rep_cit['repeated']} of {rep_cit['total']}"
    out["events repeated on one person (identical including all details)"] = f"{rep_ev['repeated']} of {rep_ev['total']}"
    out["people without a MyHeritage ID"] = no_id
    t = g.Tree(path, keep_unlinked=True)
    for i, p in t.people.items():
        y = (p["birth"] or {}).get("year")
        if p["given"] and p["surname"] and y:
            same[(p["given"].lower(), p["surname"].lower(), y)].append(t.label(i))
    out["possible duplicate people (same name and birth year)"] = [v for v in same.values() if len(v) > 1]
    couples = Counter((f["husb"], f["wife"]) for f in t.families.values() if f["husb"] and f["wife"])
    out["families with the same couple"] = sum(n - 1 for n in couples.values() if n > 1)
    out["children listed twice in one family"] = sum(len(f["children"]) - len({c for c, _ in f["children"]})
                                                    for f in t.families.values())
    out["children perhaps under the wrong union"] = [
        f"{m['child']} in {m['union']}: {m['why']}" + (f"; perhaps {', '.join(m['candidates'])}" if m["candidates"] else "")
        for m in misplaced(t)]
    return out


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    if cmd == "diff":
        a, b, added, removed, ch = diff(*args)
        print(f"people: {len(a.people)} -> {len(b.people)}; added {len(added)}, removed {len(removed)}")
        for k in removed[:40]:
            print("  removed", a.label(a.id(k)))
        for kind, rows in ch.items():
            print(f"{kind} changed: {len(rows)}")
            for k, x, y in rows[:25]:
                print(f"  {b.label(b.id(k))}: {x!r} -> {y!r}")
    elif cmd == "cross":
        r = cross(*args[:4])
        print(f"ancestors: ours {r['ancestors'][0]}, theirs {r['ancestors'][1]}")
        print(f"possibly the same person: {len(r['same'])}")
        for s in r["same"][:40]:
            gap = "?" if s["gap"] is None else s["gap"]
            print(f"  {s['ours']} [{'/'.join(s['our_codes'])}] = {s['theirs']} [{'/'.join(s['their_codes'])}]"
                  f"  years ±{gap}{', born ' + s['parish'] if s['parish'] else ''} -> {s['relationship']}")
        for title, rows in (("parishes in both", r["parishes"]), ("surnames in both (not patronymic)", r["surnames"])):
            print(f"{title}: {len(rows)}")
            for k, x, y in rows[:40]:
                print(f"  {k}: ours {x} | theirs {y}")
    elif cmd == "audit":
        for k, v in audit(args[0]).items():
            if isinstance(v, dict):
                print(f"{k}: {len(v)}")
                for t, n in sorted(v.items(), key=lambda x: -x[1])[:10]:
                    print(f"   {n} x {t[:90]}")
            elif isinstance(v, list):
                print(f"{k}: {len(v)}")
                for x in v[:15]:
                    print("   ", x if isinstance(x, str) else " | ".join(x))
            else:
                print(f"{k}: {v}")
