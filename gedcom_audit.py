"""
Compare two exports of one family tree, and look for redundancy in one.

    python3 gedcom_audit.py diff OLD.ged NEW.ged
    python3 gedcom_audit.py audit FILE.ged

`diff` matches people by their MyHeritage ID (FACT or RIN "MH:I<n>"), so a
Gramps-cleaned export and a raw MyHeritage export of the same tree line up.
It reports people added and removed, and for people in both: changed
names, birth and death dates, and changed parents. Nothing is merged.

`audit` reports what tends to pile up in vendor exports:
- source records with the same title (e.g. one per Smart Match),
- citations repeated on one event (same source and page),
- events repeated on one person (same tag, date and place),
- people with the same name and birth year (possible duplicates),
- people without a MyHeritage ID,
- families with the same couple, and children listed twice.
"""
import sys
from collections import Counter, defaultdict

import gedcom_io as g


def _mh(tree, i):
    return next((f for f in tree.people[i]["facts"] if f.startswith("MH:")), None)


def diff(old, new):
    a, b = g.Tree(old), g.Tree(new)
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


def audit(path):
    recs = g.parse(path)
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
    t = g.Tree(path)
    for i, p in t.people.items():
        y = (p["birth"] or {}).get("year")
        if p["given"] and p["surname"] and y:
            same[(p["given"].lower(), p["surname"].lower(), y)].append(t.label(i))
    out["possible duplicate people (same name and birth year)"] = [v for v in same.values() if len(v) > 1]
    couples = Counter((f["husb"], f["wife"]) for f in t.families.values() if f["husb"] and f["wife"])
    out["families with the same couple"] = sum(n - 1 for n in couples.values() if n > 1)
    out["children listed twice in one family"] = sum(len(f["children"]) - len({c for c, _ in f["children"]})
                                                    for f in t.families.values())
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
    elif cmd == "audit":
        for k, v in audit(args[0]).items():
            if isinstance(v, dict):
                print(f"{k}: {len(v)}")
                for t, n in sorted(v.items(), key=lambda x: -x[1])[:10]:
                    print(f"   {n} x {t[:90]}")
            elif isinstance(v, list):
                print(f"{k}: {len(v)}")
                for x in v[:15]:
                    print("   ", " | ".join(x))
            else:
                print(f"{k}: {v}")
