"""
Places in the tree store: the public gazetteer as an import step.

    python3 tree_store.py import-places [label]

One import (origin "import:gazetteer <label> <date>"): replaces the
imported rows of table `place` with the gazetteer (parishes "parish:<name>",
villages, farms, crofts "<Parish>/<Name>", plus parishes from the full list
that events link to), keeps place rows edited in the store, then sets
event.place_id and event.place_how for every event with a place text or
address, resolved as a whole string (gazetteer.resolve_plac); towns and
regions are looked up through geocode.py (street parts never sent, cached
in cache/geocode_private.json; offline=True or GEOCODE_OFFLINE=1 uses the
cache alone) and get private ids "osm:<type>/<id>". Events edited in the
store keep their place_id; event.place is never changed. Not yet:
valid_from/valid_to and county or härad at an event's date.
How it works: docs/records.md, "The tree store".
"""
import json
import os
import sys
from datetime import date

import gazetteer as gz


def import_places(store, label="gazetteer", gaz=None, offline=None):
    import config
    gaz = gaz or gz.load(config.load())
    origin = f"import:gazetteer {label} {date.today().isoformat()}"
    db = store.db
    db.execute("delete from place where origin like 'import:%'")
    rows = []
    for name, p in gaz.parishes.items():
        rows.append((f"parish:{name}", name, "parish", None, name, p.get("wikidata"),
                     p.get("archive"), None, None, p.get("lat"), p.get("lon"),
                     "parish" if p.get("lat") else None, "wikidata" if p.get("lat") else None,
                     json.dumps(p.get("aliases", []), ensure_ascii=False),
                     json.dumps({k: p[k] for k in ("archive_from", "harad", "label") if p.get(k)},
                                ensure_ascii=False), origin))
    for pid, p in gaz.places.items():
        parent = p.get("within") or f"parish:{p.get('parish')}"
        kind = p.get("kind") or ("farm part" if gz.generic(p.get("name")) else "")
        rows.append((pid, p.get("name"), kind, parent, p.get("parish"), None, None, None, None,
                     p.get("lat"), p.get("lon"), p.get("geo_level"), p.get("geo_source"),
                     json.dumps(p.get("variants", []), ensure_ascii=False),
                     json.dumps({k: p[k] for k in ("tora", "note") if p.get(k)} |
                                ({"checked": True} if p.get("checked") else {}), ensure_ascii=False),
                     origin))
    db.executemany("insert or ignore into place values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    # link events (imported ones; edited events keep their link)
    import geocode
    private = geocode.Cache(config.load()["data_dir"] / "geocode_private.json")
    if offline is None:
        offline = os.environ.get("GEOCODE_OFFLINE") == "1"
    geocode.OFFLINE[0] = offline           # towns: new strings looked up online, then cached
    stats, cache, towns = {}, {}, {}
    events = db.execute("select n, place, extra from event where origin not like 'edit:%' "
                        "and (place <> '' or extra like '%\"ADDR\"%')").fetchall()
    for n, text, extra in events:
        via = "plac"
        if not text:
            text, via = addr_text(extra), "addr"
            if not text:
                continue
        if text not in cache:
            pid, how = gaz.resolve_plac(text)
            if not pid:
                _, rule, _, part = gaz.explain_plac(text)      # a town: look up its name alone
                try:
                    hit = (geocode.locality(private, part) if rule.startswith("town") else None) \
                        or geocode.locality(private, text)
                except (RuntimeError, OSError) as e:          # no network: the cache alone from here
                    print(f"geocode offline from here ({e})", file=sys.stderr)
                    geocode.OFFLINE[0] = True
                    hit = geocode.locality(private, text)
                if hit:
                    pid, how = f"osm:{hit[3].split(':', 1)[1]}", "town"
                    towns[pid] = (hit[4], hit)
            cache[text] = (pid, how)
        pid, how = cache[text]
        how = f"{how} ({via})" if how and via == "addr" else how
        db.execute("update event set place_id=?, place_how=? where n=?", (pid, how or None, n))
        key = (how or "unresolved").replace(" (addr)", "")
        stats[key] = stats.get(key, 0) + 1
        if via == "addr":
            stats["from address"] = stats.get("from address", 0) + 1
    private.save()
    # parishes outside the gazetteer that events link to (explain_plac read
    # them from the full parish list): rows from that list, public like the
    # gazetteer's
    db.executemany("insert or ignore into place values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   listed_parishes(db, origin))
    # towns and regions outside the gazetteer: private, so only in the store
    db.executemany("insert or ignore into place values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   [(pid, name, h[2], None, None, None, None, None, None, h[0], h[1], h[2], h[3],
                     "[]", "{}", origin) for pid, (name, h) in towns.items()])
    db.commit()
    located = db.execute("select count(*) from event e join place p on p.id = e.place_id "
                         "where p.lat is not null and p.kind <> 'parish'").fetchone()[0]
    store.note("import", f"places from the gazetteer as '{label}': {len(gaz.parishes)} parishes, "
                         f"{len(gaz.places)} places; events linked: "
                         + ", ".join(f"{k} {v}" for k, v in sorted(stats.items()))
                         + f"; {located} at a farm, village or town of their own (not just the parish)")
    return dict(parishes=len(gaz.parishes), places=len(gaz.places), located=located, **stats)


def listed_parishes(db, origin):
    """Place rows for linked parish ids ("parish:Burlöv") with no row yet,
    from parish_names: its församling's Wikidata item, archive code and
    point (else its socken's)."""
    import parish_names
    names = parish_names.load()
    missing = [r[0] for r in db.execute(
        "select distinct e.place_id from event e left join place p on p.id = e.place_id "
        "where e.place_id like 'parish:%' and p.id is null")]
    rows = []
    for pid in missing:
        name = pid[len("parish:"):]
        g = names.by_label(name)
        if g is None:
            continue
        qs = sorted(names.members(g),
                    key=lambda q: names.items[q]["kind"] != "församling")
        item = names.items[qs[0]]
        pt = next((names.items[q] for q in qs if names.items[q].get("lat")), {})
        lat, lon = (float(pt["lat"]), float(pt["lon"])) if pt else (None, None)
        rows.append((pid, name, "parish", None, name, item["qid"], item.get("archive") or None,
                     None, None, lat, lon, "parish" if pt else None,
                     "wikidata parish list" if pt else None, "[]",
                     json.dumps({"label": item["label"], "from": "parish list"}, ensure_ascii=False),
                     origin))
    return rows


def addr_text(extra):
    """MyHeritage 2026 writes residences as ADDR (ADR1 farm, ADR2 croft,
    CITY parish, STAE county, CTRY country): the parts as one place string."""
    for node in json.loads(extra or "[]"):
        if node.get("tag") == "ADDR":
            parts = [node.get("value", "")] + [s["value"] for t in ("ADR1", "ADR2", "ADR3", "CITY",
                                                                     "STAE", "CTRY")
                                                for s in node.get("sub", []) if s["tag"] == t]
            return ", ".join(p.strip() for p in parts if p and p.strip())
    return ""


def events_with_coords(store, owner=None):
    """Events joined to their place's coordinates (falling back to the
    parish's point), for maps: (owner, n, tag, type, date, place text,
    place id, name, lat, lon, level)."""
    q = ("select e.owner, e.n, e.tag, e.type, e.date, e.place, e.place_id, p.name, "
         "coalesce(p.lat, pp.lat), coalesce(p.lon, pp.lon), "
         "case when p.lat is not null then coalesce(p.geo_level, 'farm') "
         "when pp.lat is not null then 'parish' end "
         "from event e left join place p on p.id = e.place_id "
         "left join place pp on pp.id = 'parish:' || p.parish "
         "where e.place_id is not null" + (" and e.owner = ?" if owner else ""))
    return store.db.execute(q, (owner,) if owner else ()).fetchall()
