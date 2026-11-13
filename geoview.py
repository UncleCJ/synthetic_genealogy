"""
A geographic data view: every located event and record on one map, with
facet filters (as in Calibre's tag browser), a table, and a link scheme so
other views can open it already filtered.

    python3 geoview.py          # writes data/output/geography.html (private: names)

Points: tree events from the tree store (located through place_id, else
their parish) and household-examination citations from volumes.py (one
point per person, volume and page). Each point carries person, event type,
layer (tree / record), years, date precision, place with its whole
hierarchy (place_hierarchy.py), place precision, relationship to the
proband, branch (FF/FM/MF/MM) and surname. Residences show as stays
(stays.py). Reading of clusters, paths and dates: docs/records.md, "Views".

Link scheme (the part after #, all optional, values comma-separated and
URL-encoded); the page keeps the address in step with the filters:

    person=MH:I1,MH:I2       people (MyHeritage ids)
    lines=1                  draw the path of each selected person (one or two)
    type=residence,birth     event types        layer=tree,record
    branch=FF                family branch (one at a time)
    kin=ancestor,relative    relationship
                             (an address with no filter opens on kin=ancestor;
                             kin=all for every relationship)
    surname=Svenningsson     parish=Källeryd    place=Källeryd/Hagelstorp
    from=1850&to=1900        years (a point counts if its span overlaps)
    q=text                   free text over person, place, detail
    color=branch|type|layer|time|person
                             (none: auto, by person when one to six are chosen,
                             by period within one branch, else by branch)
    open=type,parish         facet groups shown unfolded (default: kin, branch,
                             person; a group in use is always open)
    view=lat,lon,zoom        map position
    bbox=1                   count, list and facets only what is in the map view
                             (the map itself keeps every point)

In the person facet, "+ spouse" adds the spouse and draws both paths,
numbered in date order. Dates read as written, shortened: ~1850 about,
<1850 before, >1850 after, 1850–1860 between or a volume's years.

Sketch: kinship comes from the analysed GEDCOM (config), joined to store
people by MyHeritage id; people only in a newer export show as "unknown".
"""
import base64
import gzip
import html
import json
import re
import sys
import unicodedata
from collections import Counter

import identity
import lineage
from intervals import YEAR, years as _span
TAGS = {"BIRT": "birth", "CHR": "baptism", "BAPM": "baptism", "DEAT": "death", "BURI": "burial",
        "CREM": "burial", "MARR": "marriage", "DIV": "divorce", "ENGA": "engagement",
        "RESI": "residence", "OCCU": "occupation", "EDUC": "education", "EMIG": "emigration",
        "IMMI": "immigration", "CENS": "census", "CONF": "confirmation", "NATU": "naturalisation",
        "PROB": "probate", "_MILT": "military", "EVEN": "event", "FACT": "fact", "RETI": "retirement",
        "GRAD": "graduation", "RELI": "religion", "TITL": "title"}


def _precision(date):
    if not date:
        return "none"
    return "day" if re.search(r"\b\d{1,2}\s+[A-Za-z]{3}\b", date) else (
        "year" if YEAR.search(date) else "none")


def collect(cfg):
    import gazetteer as gz
    import gedcom_io
    import place_store
    import tree_store
    import volumes

    store = tree_store.default_store()
    gaz = gz.load(cfg)
    db = store.db

    # people: names from the store, kinship from the analysed tree
    g = cfg.get("gedcom") or {}
    tree = (gedcom_io.Tree(volumes.config.path(cfg, g["file"]), **gedcom_io.options(cfg))
            if hasattr(volumes, "config") else None)
    if tree is None:
        import config
        tree = gedcom_io.Tree(config.path(cfg, g["file"]), **gedcom_io.options(cfg))
    kin = volumes.kinship(tree, g.get("proband"))
    by_mh = {}
    for i, p in tree.people.items():
        mh = identity.mh_id(p["facts"])
        if mh:
            by_mh[mh] = kin.get(i, ("unlinked", "", ""))
    people = {}
    for pid, given, surname, sex in db.execute("select id, given, surname, sex from person"):
        k = by_mh.get(pid, ("unknown", "", ""))
        people[pid] = dict(id=pid, name=f"{given} {surname}".strip(), surname=surname or "",
                           sex=sex or "", kin=k[0], branch=(k[1] or "").split(" ")[0], lineage=k[2])
    for pid, tag, date in db.execute("select owner, tag, date from event where tag in ('BIRT','DEAT')"):
        if pid in people:
            y, _ = _span(date)
            people[pid]["born" if tag == "BIRT" else "died"] = y
    spouses = {}
    for fid, h, w in db.execute("select id, husb, wife from family"):
        if h and w:
            spouses.setdefault(h, set()).add(w)
            spouses.setdefault(w, set()).add(h)
        for owner in (h, w):
            pass

    # place names and parishes
    pinfo = {pid: (name, parish, kind) for pid, name, parish, kind in
             db.execute("select id, name, parish, kind from place")}

    # every place string the tree writes, completed by the others
    # (place_hierarchy): "Dädesjö, Uppvidinge" -> "..., Småland, Kronobergs län"
    import place_hierarchy
    hier = place_hierarchy.Hierarchy(
        (text, (pid[7:] if pid and pid.startswith("parish:") else pinfo.get(pid, (0, None))[1]))
        for text, pid in db.execute("select place, place_id from event where place is not null"))

    points = []
    fam = {fid: (h, w) for fid, h, w in db.execute("select id, husb, wife from family")}
    for owner, n, tag, typ, date, text, place_id, name, lat, lon, level in \
            place_store.events_with_coords(store):
        if lat is None:
            continue
        who = [owner] if owner in people else [x for x in fam.get(owner, ()) if x]
        y0, y1 = _span(date)
        nm, par, _ = pinfo.get(place_id, (name, None, None))
        if place_id and place_id.startswith("parish:"):
            par = place_id[7:]
        ev = TAGS.get(tag, tag.lower())
        if tag == "EVEN" and typ:
            ev = typ.lower()
        for p in who:
            points.append(dict(p=p, t=ev, l="tree", y0=y0, y1=y1, d=_precision(date), date=date or "",
                               name=hier.label(text or nm or "", par) or nm or text, parish=par or "", place=place_id or "",
                               lv=level or "", lat=round(lat, 5), lon=round(lon, 5),
                               det=text or ""))

    # residence entries -> stays (stays.py); both kept, flagged: agg 0 = raw
    # entry, 1 = aggregated stay, 2 = anything else
    import stays as stays_mod
    res = [pt for pt in points if pt["t"] == "residence"]
    for pt in points:
        pt["agg"] = 0 if pt["t"] == "residence" else 2
    by_person = {}
    for pt in res:
        by_person.setdefault(pt["p"], []).append(pt)
    kind = {pid: k for pid, (_, _, k) in pinfo.items()}
    for pid_, pts in by_person.items():
        agg = stays_mod.aggregate(pts, key=lambda q: q["place"] or q["name"])
        first = {st["key"]: st["items"][0] for st in agg}
        # what the place is, not how precisely it is located: a farm without
        # its own point still counts as a farm
        general = lambda k: (not str(k).count("/") or str(k).startswith(("parish:", "osm:"))
                             or kind.get(k) == "rote")
        for st in stays_mod.drop_general(agg, lambda k: first[k]["parish"], general):
            q = dict(st["items"][0])
            q.update(y0=st["y0"], y1=st["y1"], date=st["label"], agg=1, n=st["n"],
                     d="day" if st["dated"] else ("year" if st["y0"] else "none"),
                     det="; ".join(x for x in (
                         f"{st['n']} residence entries" if st["n"] > 1 else "",
                         f"one of several places in {st['group']}" if st["group"] else "",
                         "also listed as " + ", ".join(dict.fromkeys(
                             a["items"][0]["name"] for a in st.get("also", []))) if st.get("also") else "")
                         if x))
            points.append(q)

    # household-examination citations from the volume pipeline
    rows, _, _ = volumes.run(cfg, riksarkivet_lookups=False)
    seen = set()
    for r in rows:
        if r.get("tier") not in ("mh-record", "ra-full", "ra-link") or not r.get("volume"):
            continue
        mh = r.get("mh_id")
        if mh not in people:
            continue
        key = (mh, r["volume"], r.get("page"))
        if key in seen:
            continue
        seen.add(key)
        pid, how = (r.get("place_id"), "gazetteer") if r.get("place_id") else (f"parish:{r.get('parish')}", "parish")
        c = gaz.coords(pid)
        if not c:
            continue
        y0, y1 = _span(r.get("ra_years") or r.get("years"))
        series = r.get("series", "")
        ev = {"A I": "household examination", "A II a": "household examination",
              "A II": "household examination", "B": "moving", "B I": "moving in",
              "B II": "moving out", "C": "birth record", "E I": "marriage record",
              "F": "death record"}.get(series, "record")
        points.append(dict(p=mh, t=ev, l="record", agg=2, y0=y0, y1=y1, d="year" if y0 else "none",
                           date=f"{y0}–{y1}" if y0 else "",
                           name=hier.label(r.get("place") or r.get("farm") or "", r.get("parish")) or r.get("parish"),
                           parish=r.get("parish", ""), place=r.get("place_id") or "",
                           lv=c[2], lat=round(c[0], 5), lon=round(c[1], 5),
                           det=f"{r['volume']} p. {r.get('page') or '?'}",
                           url=r.get("ra_viewer") or r.get("url") or ""))
    used = {pt["p"] for pt in points}
    ppl = {pid: dict(p, spouses=sorted(s for s in spouses.get(pid, ()) if s in used))
           for pid, p in people.items() if pid in used}
    return ppl, points


def pack(people, points):
    """Strings into lookup tables, points as arrays: a smaller page. Raw
    residence entries (agg 0) stay out: their stays carry them."""
    points = [pt for pt in points if pt.get("agg", 2) != 0]
    tabs = {k: [] for k in ("t", "l", "d", "parish", "lv", "name", "place")}
    idx = {k: {} for k in tabs}

    def code(k, v):
        v = v or ""
        if v not in idx[k]:
            idx[k][v] = len(tabs[k])
            tabs[k].append(v)
        return idx[k][v]
    pids = sorted(people)
    pidx = {p: i for i, p in enumerate(pids)}
    rows = [[pidx[pt["p"]], code("t", pt["t"]), code("l", pt["l"]), pt["y0"], pt["y1"], code("d", pt["d"]),
             pt["lat"], pt["lon"], code("lv", pt["lv"]), code("name", pt["name"]), code("parish", pt["parish"]),
             code("place", pt["place"]), pt["date"], pt["det"], pt.get("url", ""),
             pt.get("agg", 2), pt.get("n", 1)] for pt in points]
    plist = [[people[p]["id"], people[p]["name"], people[p]["surname"], people[p]["kin"], people[p]["branch"],
              people[p].get("lineage", ""), people[p].get("born"), people[p].get("died"),
              [pidx[s] for s in people[p]["spouses"] if s in pidx]] for p in pids]
    return dict(tabs=tabs, people=plist, rows=rows)


DATE_JS = r"""const MON={JAN:'01',FEB:'02',MAR:'03',APR:'04',MAY:'05',JUN:'06',JUL:'07',AUG:'08',SEP:'09',OCT:'10',NOV:'11',DEC:'12'};
function day(x){return x.replace(/^(?:(\d{1,2})\s+)?([A-Za-z]{3})\s+(\d{3,4})$/,(m,d,mo,y)=>MON[mo.toUpperCase()]?y+'-'+MON[mo.toUpperCase()]+(d?'-'+d.padStart(2,'0'):''):m)}
function one(x){x=x.trim();let m;
 if(m=x.match(/^(?:BET|FROM)\s+(.+?)\s+(?:AND|TO)\s+(.+)$/i))return one(m[1])+'–'+one(m[2]);
 if(m=x.match(/^(?:ABT|EST|CAL|ABOUT)\.?\s+(.+)$/i))return '~'+day(m[1]);
 if(m=x.match(/^BEF\.?\s+(.+)$/i))return '<'+day(m[1]);
 if(m=x.match(/^AFT\.?\s+(.+)$/i))return '>'+day(m[1]);
 if(m=x.match(/^FROM\s+(.+)$/i))return day(m[1])+'–';
 if(m=x.match(/^TO\s+(.+)$/i))return '–'+day(m[1]);
 return day(x)}
const fmtDate=s=>s?String(s).split(/;\s*/).map(one).join('; '):'';
// a short span in words between two GEDCOM dates, both full days ("barely a
// day", "12 days", "3 months"); '' from two years up or when either date is
// vaguer than a day, where whole years say it
function shortSpan(a,b){const d=x=>{const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(fmtDate(String(x||'')).split('–')[0]);return m&&m.slice(1).map(Number)};
 const p=d(a),q=d(b);if(!p||!q)return '';const n=Math.round((Date.UTC(q[0],q[1]-1,q[2])-Date.UTC(p[0],p[1]-1,p[2]))/864e5);if(n<0)return '';
 if(n<=1)return 'barely a day';if(n<31)return n+' days';const mo=(q[0]-p[0])*12+q[1]-p[1]-(q[2]<p[2]?1:0);
 return mo<24?(mo===1?'a month':mo+' months'):''}"""   # GEDCOM dates shortened, the same in every view

# Search folding for names and places: historical Swedish spellings meet
# ("Oscar" finds "Oskar", "Gustaf" "Gustav", "Christina" "Kristina"). Accents
# go, plain substring pairs apply in order, then doubled letters inside a word
# become single (Svenning = Svening; "A II" stays apart from "A I"). Applied to
# query and text alike, so a key needn't be a real spelling; it overmatches a
# little (f = v everywhere), which a search box can afford. FOLD_JS is the same
# fold for the pages (fold(x)); name_fold is the tested reference.
NAME_FOLD = (("ph", "f"), ("th", "t"), ("ch", "k"), ("ck", "k"), ("c", "k"),
             ("q", "k"), ("x", "ks"), ("z", "s"), ("w", "v"), ("f", "v"))


def name_fold(s):
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    s = re.sub(r"[*()]", "", s).lower()
    for a, b in NAME_FOLD:
        s = s.replace(a, b)
    return re.sub(r"(?<=[a-z])([a-z])\1+", r"\1", s)


FOLD_JS = ("const NF=" + json.dumps(NAME_FOLD) + r",fold=x=>NF.reduce((s,[a,b])=>s.split(a).join(b),"
           r"x.normalize('NFD').replace(/[\u0300-\u036f*()]/g,'').toLowerCase()).replace(/(?<=[a-z])([a-z])\1+/g,'$1');")

VIEWS = [("family.html", "Family"), ("geography.html", "Geography"), ("archives.html", "Archives")]
NAV_CSS = ("nav.views{display:flex;gap:2px;margin-right:6px}nav.views a{padding:3px 10px;border:1px solid var(--line);"
           "border-radius:6px;text-decoration:none;color:var(--fg);background:var(--card);font-size:13px}"
           "nav.views a.on{background:var(--sel);font-weight:600}nav.views a:hover{border-color:var(--mut)}"
           "nav.views a.home{color:var(--mut)}")


def nav(current):
    """The row of links between the views, the same on each page."""
    links = "".join(f'<a href="{f}"' + (' class="on"' if f == current else "") + f">{t}</a>"
                    for f, t in VIEWS)
    return f'<style>{NAV_CSS}</style><nav class="views"><a class="home" href="index.html" title="All outputs">⌂</a>{links}</nav>'


# The data a view carries, gzipped and base64-encoded (about 18 times smaller
# than the JSON). A template marks its main script <script type="text/plain"
# id="view-js"> starting `const D=DATA;` and puts __DATA__ after it; the loader
# unpacks the data, then runs the main script as an ordinary one. Views work
# opened as files; one that needs a web server says why in <body
# data-serve="...">, and opened as a file shows that and a link instead.
DATA_TAG = '<script id="view-data" type="application/octet-stream">'
LOAD_JS = ("<script>(async()=>{const n=document.body.dataset.serve;if(n&&location.protocol==='file:'){"
           "const u='http://127.0.0.1:8000/'+location.pathname.split('/').pop()+location.hash;"
           "document.body.innerHTML=`<p style=\"max-width:40em;margin:3em auto;font:15px/1.5 system-ui,sans-serif\">${n} "
           "Run <code>python3 serve.py</code> in the project (in an unzipped snapshot, <code>python3 serve.py --dir FOLDER</code>), "
           "then <a href=\"${u}\">open this view there</a>.</p>`;return}"
           "const b=Uint8Array.from(atob(document.getElementById('view-data').textContent),c=>c.charCodeAt(0));"
           "window.DATA=await new Response(new Blob([b]).stream().pipeThrough(new DecompressionStream('gzip'))).json();"
           "const s=document.createElement('script');s.textContent=document.getElementById('view-js').textContent;"
           "document.body.append(s)})()</script>")


def pack_data(data):
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    return base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode("ascii")


def embed(page, data):
    """The template with its data in place of __DATA__."""
    return page.replace("__DATA__", DATA_TAG + pack_data(data) + "</script>" + LOAD_JS)


def embedded(page):
    """(head, data, tail) of a written view; head + pack_data(data) + tail
    writes it back."""
    i = page.index(DATA_TAG) + len(DATA_TAG)
    j = page.index("</script>", i)
    return page[:i], json.loads(gzip.decompress(base64.b64decode(page[i:j]))), page[j:]


SERVED = "The map needs a web server: map tiles are only sent to pages served over http, not to files."


def write(path, data):
    page = HTML.replace("__NAV__", nav("geography.html")).replace("__DATEJS__", DATE_JS)
    path.write_text(embed(page.replace("__SERVE__", html.escape(SERVED)), data),
                    encoding="utf-8")


HTML = r"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Geography</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.Default.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/leaflet.markercluster.min.js"></script>
<style>
:root{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#6b6760;--line:#e2ded6;--card:#fff;--sel:#fff1bf;--acc:#2f6db5;
__LINEAGE__;--none:#8f8a80}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ece9e2;--mut:#9b968c;--line:#34312c;--card:#201f1c;--sel:#4a4220;--acc:#6ea4e6;
__LINEAGE_DARK__;--none:#777}}
*{box-sizing:border-box}html,body{height:100%}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,-apple-system,sans-serif;display:grid;grid-template-columns:290px 1fr;grid-template-rows:auto 1fr}
header{grid-column:1/-1;display:flex;gap:10px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:16px;margin:0 8px 0 0}
input,select,button{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
button{cursor:pointer}button.on{background:var(--sel)}button:disabled{opacity:.45;cursor:default}
#side{overflow:auto;border-right:1px solid var(--line);padding:6px 10px 12px}
#mainp{display:grid;grid-template-rows:minmax(300px,62%) auto 1fr;min-height:0}
#tbar{display:flex;gap:8px;align-items:center;padding:4px 10px;border-top:1px solid var(--line);flex-wrap:wrap}
#tbar #count{font-weight:600;margin-right:auto}
button svg{width:14px;height:14px;vertical-align:-2px;margin-right:4px}
.ctl{background:var(--card);color:var(--fg);padding:5px 6px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.3);display:flex;gap:6px;align-items:center;font:13px/1.4 system-ui,sans-serif}
.flist{max-height:240px;overflow:auto}
.rb{display:inline-block;width:10px;height:10px;border:1.5px solid var(--mut);border-radius:50%;margin-right:5px;vertical-align:-1px}.rb.on{border-color:var(--acc);background:radial-gradient(var(--acc) 40%,transparent 45%)}
.f .yrs{color:var(--mut);font-size:11px;margin-left:4px}
#map{min-height:0}
#tablebox{overflow:auto}
details{border-bottom:1px solid var(--line);padding:4px 0}summary{cursor:pointer;font-weight:600;padding:3px 0;list-style:none;display:flex;justify-content:space-between}
summary::-webkit-details-marker{display:none}summary .act{font-weight:400;color:var(--acc);font-size:12px}
.f{display:flex;justify-content:space-between;gap:6px;padding:1px 4px;border-radius:4px;cursor:pointer;user-select:none}
.f:hover{background:var(--line)}.f.on{background:var(--sel);font-weight:600}.f.zero{opacity:.4}
.f .n{color:var(--mut);font-variant-numeric:tabular-nums}
.sw{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:0}
.fsearch{width:100%;margin:3px 0}
.hist{display:flex;align-items:flex-end;height:46px;gap:1px;margin:4px 0}
.hist{cursor:crosshair;touch-action:none;user-select:none}.hist div{flex:1;background:var(--acc);opacity:.25;min-height:1px;pointer-events:none}.hist div.in{opacity:.9}
.yr{display:flex;gap:6px}.yr input{width:70px}
table{border-collapse:collapse;width:100%}th,td{padding:3px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{position:sticky;top:0;background:var(--card);cursor:pointer;font-weight:600}tr:hover td{background:var(--line);cursor:pointer}
td.wrap{white-space:normal}
.meta{color:var(--mut)}.chip{display:inline-block;border:1px solid var(--line);border-radius:10px;padding:0 7px;margin:2px;cursor:pointer}
.chip:hover{text-decoration:line-through}
.f .act{font-weight:400;color:var(--acc);font-size:12px;margin-left:6px}.f .act:hover{text-decoration:underline}
.clab,.plab{font:600 11px system-ui,sans-serif;color:#1d1c1a;text-shadow:0 0 2px #fff,0 0 2px #fff,0 0 3px #fff;white-space:nowrap}
.clab{position:absolute;left:100%;top:50%;transform:translateY(-50%);margin-left:3px;pointer-events:none}
.leaflet-tooltip.plab{background:none;border:0;box-shadow:none;padding:0}.leaflet-tooltip.plab::before{display:none}#map:not(.close) .plab{display:none}
.pie{border-radius:50%;box-shadow:0 1px 3px rgba(0,0,0,.35)}.pie b{position:absolute;inset:22%;border-radius:50%;background:var(--card);color:var(--fg);display:flex;align-items:center;justify-content:center;font:600 11px system-ui,sans-serif}
.seq{border-radius:50%;color:#fff;font:700 10px/18px system-ui,sans-serif;text-align:center;border:1.5px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)}
.lgd{display:block;max-width:220px}.lgd div{display:flex;gap:6px;align-items:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.lgd .n{color:var(--mut);margin-left:auto;padding-left:8px}
.lgd .grad{height:9px;width:150px;border-radius:2px;background:linear-gradient(90deg,hsl(220,65%,45%),hsl(120,65%,45%),hsl(20,65%,45%))}
.leaflet-popup-content{font:13px/1.4 system-ui,sans-serif}.leaflet-popup-content a{color:var(--acc)}
@media(max-width:800px){body{grid-template-columns:1fr;grid-template-rows:auto auto 1fr}#side{max-height:40vh}}
</style></head><body data-serve="__SERVE__">
<header>__NAV__<h1>Geography</h1>
<input id="q" placeholder="Search person, place, volume…" size="28">
<span id="chips"></span>
<button id="reset" title="Back to the default view: ancestors, no other filters">↺ reset</button></header>
<aside id="side"></aside>
<div id="mainp"><div id="map"></div>
<div id="tbar"><span id="count"></span>
<button id="bbox" title="Count, list and facet only what is inside the map view; follows the map as you pan and zoom (the map keeps every point)"><svg viewBox="0 0 16 16"><rect x="2" y="3" width="12" height="10" rx="1" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="2.5 1.5"/></svg>only map view</button>
</div>
<div id="tablebox"><table id="tbl"></table></div></div>
<script type="text/plain" id="view-js">
const D=DATA;const T=D.tabs,P=D.people,R=D.rows;
// row fields
const RP=0,RT=1,RL=2,RY0=3,RY1=4,RD=5,RLAT=6,RLON=7,RLV=8,RNAME=9,RPAR=10,RPL=11,RDATE=12,RDET=13,RURL=14,RAGG=15,RN=16;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const BR={FF:'var(--FF)',FM:'var(--FM)',MF:'var(--MF)',MM:'var(--MM)'};
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v.replace(/^var\(|\)$/g,'')).trim()||v;
const PAL=['#2f6db5','#c0522b','#2f8f5b','#8a4fb0','#b08a1e','#1f8a96','#a8326b','#5d6b2f','#7a5c3e','#3e6f7a','#999'];
// facets: key, label, value of a row; in the order shown, the short lists first, people last (the longest)
const FACETS=[
 ['branch','Family branch',r=>P[r[RP]][4]||'none'],
 ['kin','Relationship',r=>P[r[RP]][3]],
 ['type','Event type',r=>T.t[r[RT]]],
 ['parish','Parish',r=>T.parish[r[RPAR]]||'(outside parishes)'],
 ['layer','Layer',r=>T.l[r[RL]]],
 ['surname','Surname',r=>P[r[RP]][2]||'(none)'],
 ['person','Person',r=>P[r[RP]][0]],
];
const PBY=Object.fromEntries(P.map(p=>[p[0],p]));
const LABEL={person:v=>{const p=PBY[v];return p?p[1]:v}};
// parishes and surnames read alphabetically; the rest (people too) by count, most first
const ALPHA=new Set(['parish','surname']);
// one family branch at a time (radio buttons); the others take several
const SINGLE=new Set(['branch']);
const SORTKEY={person:v=>{const p=PBY[v];return p?(p[2]+' '+p[1]):v}};
const EXTRA={person:v=>{const p=PBY[v];return p&&(p[6]||p[7])?`<span class="yrs">${p[6]||''}–${p[7]||''}</span>`:''}};
const coll=new Intl.Collator('sv');
// with no filter in the address, the view opens on the ancestors; kin=all lifts it
const DEFAULT={kin:['ancestor']};
let S={};const MULTI=FACETS.map(f=>f[0]);
function readHash(){S={};const h=new URLSearchParams(location.hash.slice(1));
 for(const [k,v] of h){S[k]=MULTI.includes(k)||k==='place'?(v==='all'?[]:v.split(',').filter(Boolean)):v}
 if(![...MULTI,'place','q','from','to'].some(k=>k in S))Object.assign(S,structuredClone(DEFAULT))}
function writeHash(){const h=new URLSearchParams();for(const [k,v] of Object.entries(S)){if(Array.isArray(v)?v.length:v!==undefined&&v!=='')h.set(k,Array.isArray(v)?v.join(','):v);else if(k in DEFAULT&&Array.isArray(v))h.set(k,'all')}
 history.replaceState(null,'','#'+h.toString().replace(/%2C/g,',').replace(/%3A/g,':').replace(/%2F/g,'/'))}
function yearOK(r){const a=+S.from||null,b=+S.to||null;if(!a&&!b)return true;const y0=r[RY0]??r[RY1],y1=r[RY1]??r[RY0];if(y0==null)return false;
 return (!a||y1>=a)&&(!b||y0<=b)}
let MAPB=null;
// dates as written, shortened: ~ about, < before, > after, a–b between; days as 1850-03-12
__DATEJS__
function base(r,skip){
 for(const [k,,fn] of FACETS){if(k===skip)continue;const sel=S[k];if(sel&&sel.length&&!sel.includes(fn(r)))return false}
 if(S.place&&S.place.length&&!S.place.includes(T.place[r[RPL]]))return false;
 if(skip!=='year'&&!yearOK(r))return false;
 if(S.q){const q=S.q.toLowerCase();const p=P[r[RP]];if(!(p[1]+' '+T.name[r[RNAME]]+' '+r[RDET]+' '+T.parish[r[RPAR]]+' '+p[0]).toLowerCase().includes(q))return false}
 if(skip!=='bbox'&&S.bbox==='1'&&MAPB&&!MAPB.contains([r[RLAT],r[RLON]]))return false;
 return true}
// facets UI
const OPEN=new Set(['kin','branch','person']);
function facetsUI(){const side=document.getElementById('side');let h='';
 // time
 const dec={};let n=0;R.forEach(r=>{if(!base(r,'year'))return;const y=r[RY0]??r[RY1];if(y==null)return;const d=Math.floor(y/10)*10;dec[d]=(dec[d]||0)+1});
 const dk=Object.keys(dec).map(Number);const ds=[];if(dk.length)for(let d=Math.min(...dk);d<=Math.max(...dk);d+=10)ds.push(d);
 const mx=Math.max(1,...Object.values(dec));
 h+=`<details open><summary>Time<span class="act" data-clear="year">${S.from||S.to?'clear':''}</span></summary>
 <div class="hist" title="Click a decade, or drag across several">${ds.map(d=>`<div data-dec="${d}" class="${S.from||S.to?(yearOK([0,0,0,d,d+9])?'in':''):'in'}" style="height:${100*(dec[d]||0)/mx}%" title="${d}s: ${dec[d]||0}"></div>`).join('')}</div>
 <div class="meta" style="display:flex;justify-content:space-between"><span>${ds[0]||''}</span><span>${ds.length?ds[ds.length-1]+9:''}</span></div>
 <div class="yr"><input id="from" placeholder="from" value="${esc(S.from||'')}"> – <input id="to" placeholder="to" value="${esc(S.to||'')}"></div></details>`;
 for(const [k,label,fn] of FACETS){const c={};R.forEach(r=>{if(base(r,k)){const v=fn(r);c[v]=(c[v]||0)+1}});
  const sel=S[k]||[];sel.forEach(v=>{if(!(v in c))c[v]=0});
  const sk=SORTKEY[k]||(v=>v);
  let keys=Object.keys(c).sort(ALPHA.has(k)?(a,b)=>coll.compare(sk(a),sk(b)):(a,b)=>c[b]-c[a]||coll.compare(sk(a),sk(b)));
  if(!SINGLE.has(k))keys=[...keys.filter(v=>sel.includes(v)),...keys.filter(v=>!sel.includes(v))];   // the chosen ones on top (radio lists stay put)
  const many=keys.length>12||k==='person';const fq=(document.getElementById('fs-'+k)||{}).value||'';
  if(fq)keys=keys.filter(v=>sel.includes(v)||(LABEL[k]?LABEL[k](v):v).toLowerCase().includes(fq.toLowerCase()));
  const show=keys.slice(0,many?300:keys.length);
  const rb=v=>SINGLE.has(k)?`<span class="rb${sel.includes(v)?' on':''}"></span>`:'';
  const sw=v=>k==='branch'?`<span class="sw" style="background:${BR[v]||'var(--none)'}"></span>`:(k===S.colorKey&&(k!=='person'||sel.includes(v))?`<span class="sw" style="background:${colorOf(v)}"></span>`:'');
  h+=`<details ${(S.open?S.open.split(',').includes(k):OPEN.has(k))||sel.length||fq?'open':''} data-k="${k}"><summary>${label} <span class="act" data-clear="${k}">${sel.length?'clear':''}</span></summary>
  ${many?`<input class="fsearch" id="fs-${k}" placeholder="filter ${label.toLowerCase()}…" value="${esc(fq)}">`:''}
  <div class="${many?'flist':''}">${show.map(v=>`<div class="f ${sel.includes(v)?'on':''} ${c[v]?'':'zero'}" data-k="${k}" data-v="${esc(v)}"><span>${rb(v)}${sw(v)}${esc(LABEL[k]?LABEL[k](v):v)}${EXTRA[k]?EXTRA[k](v):''}${k==='person'&&sel.includes(v)?spouseActs(v,sel):''}</span><span class="n">${c[v]}</span></div>`).join('')}</div>
  ${keys.length>show.length?`<div class="meta">… ${keys.length-show.length} more; type to narrow</div>`:''}</details>`}
 const act=document.activeElement&&document.activeElement.id;const pos=document.activeElement&&document.activeElement.selectionStart;
 side.innerHTML=h;if(act&&act.startsWith('fs-')){const e=document.getElementById(act);if(e){e.focus();e.setSelectionRange(pos,pos)}}fitLast()}
// the last facet (people) runs to the bottom of the sidebar when there is room
function fitLast(){const side=document.getElementById('side');const ls=side.querySelectorAll('details[open] .flist');const fl=ls[ls.length-1];
 if(!fl||fl.closest('details')!==side.lastElementChild)return;
 const top=fl.getBoundingClientRect().top-side.getBoundingClientRect().top+side.scrollTop;fl.style.maxHeight=Math.max(240,side.clientHeight-top-12)+'px'}
document.getElementById('side').addEventListener('toggle',fitLast,true);
const spousesOf=v=>{const p=PBY[v];return p?p[8].map(i=>P[i]):[]};
// a spouse joins the chosen people, the people filters widen to take them, paths on
// one spouse: "+ spouse"; several: one link each, by given name, to pick one
const given=s=>String(s[1]).split(' ')[0];
function spouseActs(v,sel){const sp=spousesOf(v).filter(s=>!sel.includes(s[0]));const swap=spousesOf(v).some(s=>sel.includes(s[0]));
 return sp.map(s=>`<span class="act" data-spouse="${esc(v)}" data-sid="${esc(s[0])}" title="${swap?'Show':'Add'} ${esc(s[1])} and draw both paths">${swap?'→':'+'} ${sp.length===1&&spousesOf(v).length===1?'spouse':esc(given(s))}</span>`).join('')}
function addSpouse(v,sid){S.person=S.person||[];
 if(sid){const others=spousesOf(v).map(s=>s[0]).filter(x=>x!==sid);S.person=S.person.filter(x=>!others.includes(x))}   // one spouse at a time
 for(const s of spousesOf(v).filter(s=>!sid||s[0]===sid)){if(!S.person.includes(s[0]))S.person.push(s[0]);
  if(S.kin&&S.kin.length&&!S.kin.includes(s[3]))S.kin.push(s[3]);
  if(S.surname&&S.surname.length&&!S.surname.includes(s[2]||'(none)'))S.surname.push(s[2]||'(none)');
  if(S.branch&&S.branch.length&&!S.branch.includes(s[4]||'none'))S.branch=[]}
 S.lines='1';update(true)}
document.getElementById('side').addEventListener('click',e=>{
 const sp=e.target.closest('[data-spouse]');if(sp){e.preventDefault();addSpouse(sp.dataset.spouse,sp.dataset.sid);return}
 const c=e.target.closest('[data-clear]');if(c&&c.textContent){e.preventDefault();const k=c.dataset.clear;if(k==='year'){delete S.from;delete S.to}else if(k in DEFAULT)S[k]=[];else delete S[k];update();return}
 const f=e.target.closest('.f');if(!f)return;const k=f.dataset.k,v=f.dataset.v;const sel=S[k]||[];
 S[k]=SINGLE.has(k)?(sel.length===1&&sel[0]===v?[]:[v]):e.metaKey||e.ctrlKey||e.shiftKey||sel.length?(sel.includes(v)?sel.filter(x=>x!==v):[...sel,v]):[v];update(k==='person'&&S[k].length>0)});
// years: press on a decade, drag across the histogram, release
let DRAG=null;
function decAt(e){const h=e.target.closest('.hist');if(!h)return null;const bars=[...h.children];if(!bars.length)return null;
 const b=h.getBoundingClientRect();const i=Math.max(0,Math.min(bars.length-1,Math.floor((e.clientX-b.left)/b.width*bars.length)));return +bars[i].dataset.dec}
function paint(a,b){const lo=Math.min(a,b),hi=Math.max(a,b);document.querySelectorAll('.hist [data-dec]').forEach(x=>x.classList.toggle('in',+x.dataset.dec>=lo&&+x.dataset.dec<=hi))}
document.getElementById('side').addEventListener('pointerdown',e=>{const d=decAt(e);if(d==null)return;e.preventDefault();DRAG={a:d,b:d,el:e.target.closest('.hist')};DRAG.el.setPointerCapture(e.pointerId);paint(d,d)});
document.getElementById('side').addEventListener('pointermove',e=>{if(!DRAG)return;const b=DRAG.el.getBoundingClientRect();const bars=DRAG.el.children;
 const i=Math.max(0,Math.min(bars.length-1,Math.floor((e.clientX-b.left)/b.width*bars.length)));DRAG.b=+bars[i].dataset.dec;paint(DRAG.a,DRAG.b)});
document.addEventListener('pointerup',()=>{if(!DRAG)return;const lo=Math.min(DRAG.a,DRAG.b),hi=Math.max(DRAG.a,DRAG.b);DRAG=null;
 if(S.from==lo&&S.to==hi+9){delete S.from;delete S.to}else{S.from=String(lo);S.to=String(hi+9)}update()});
document.getElementById('side').addEventListener('input',e=>{if(e.target.classList.contains('fsearch'))facetsUI()});
document.getElementById('side').addEventListener('change',e=>{if(e.target.id==='from'||e.target.id==='to'){S[e.target.id]=e.target.value.trim();update()}});
// colours
function colorOf(v){if(S.colorKey==='person'){const i=(S.person||[]).indexOf(v);return i<0?'#999':PAL[i%PAL.length]}
 if(S.colorKey==='branch')return css(BR[v]||'var(--none)');const keys=S.colorKeys||[];const i=keys.indexOf(v);return PAL[i<0?PAL.length-1:Math.min(i,PAL.length-1)]}
// auto: by person when one to six are chosen, by period within one branch, else by branch
function colorKey(){if(S.color)return S.color;const n=(S.person||[]).length;
 return n&&n<=6?'person':(S.branch||[]).length===1?'time':'branch'}
function rowColor(r){const ck=S.colorKey;if(ck==='person'){const i=(S.person||[]).indexOf(P[r[RP]][0]);return i<0?'#999':PAL[i%PAL.length]}
 if(ck==='branch')return css(BR[P[r[RP]][4]]||'var(--none)');
 if(ck==='time'){const y=r[RY0]??r[RY1];if(y==null)return '#999';const t=Math.max(0,Math.min(1,(y-1700)/300));return `hsl(${220-200*t},65%,45%)`}
 const v=ck==='type'?T.t[r[RT]]:T.l[r[RL]];return colorOf(v)}
// map
const map=L.map('map',{preferCanvas:true});L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:17,attribution:'© OpenStreetMap'}).addTo(map);
// a cluster shows the colour mix of its points as a ring, the count inside
// a place's own name: its first part ("Hagelstorp, Källeryd, Småland, ..." -> Hagelstorp)
const short=r=>String(T.name[r[RNAME]]||'').split(',')[0].trim();
// what a cluster's points have in common, shown beside it: one place, or the main one of a few
function common(ms){const c={};ms.forEach(m=>{const s=short(m._r);c[s]=(c[s]||0)+1});const ks=Object.keys(c).sort((a,b)=>c[b]-c[a]);
 if(ks.length===1)return ks[0];if(ks.length<=3)return `${ks[0]} +${ks.length-1}`;
 // many places on one parish point: farms with no point of their own
 const par=new Set(ms.map(m=>T.parish[m._r[RPAR]]));
 return par.size===1&&ms.filter(m=>T.lv[m._r[RLV]]==='parish').length>=.9*ms.length?`${[...par][0]} · parish centre, ${ks.length} places`:''}
function pie(cl){const ms=cl.getAllChildMarkers(),c={};ms.forEach(m=>{const f=m.options.fillColor;c[f]=(c[f]||0)+1});
 let a=0;const st=Object.entries(c).sort((x,y)=>y[1]-x[1]).map(([f,k])=>{const s=`${f} ${a}turn ${a+k/ms.length}turn`;a+=k/ms.length;return s});
 const n=ms.length,d=n<10?26:n<100?32:n<1000?38:44;
 return L.divIcon({html:`<div class="pie" style="width:${d}px;height:${d}px;position:relative;background:conic-gradient(${st.join(',')})"><b>${n}</b>${(lab=>lab?`<span class="clab">${esc(lab)}</span>`:'')(common(ms))}</div>`,className:'',iconSize:[d,d]})}
const cluster=L.markerClusterGroup({chunkedLoading:true,maxClusterRadius:38,zoomToBoundsOnClick:false,spiderfyOnMaxZoom:false,showCoverageOnHover:false,iconCreateFunction:pie});map.addLayer(cluster);
// a click zooms into a cluster that zooming can split; one at a single spot (a farm's
// events share its point) lists its events instead
cluster.on('clusterclick',e=>{const cl=e.layer,b=cl.getBounds();
 if(b.getNorthEast().distanceTo(b.getSouthWest())>30&&map.getZoom()<map.getMaxZoom()){cl.zoomToBounds({padding:[30,30]});return}
 L.popup({maxWidth:420,maxHeight:320}).setLatLng(cl.getLatLng()).setContent(here(cl.getAllChildMarkers().map(m=>m._r))).openOn(map)});
function here(rs){rs=[...rs].sort((a,b)=>((a[RY0]??a[RY1]??9999)-(b[RY0]??b[RY1]??9999)));
 const pls=[...new Set(rs.map(r=>T.place[r[RPL]]).filter(Boolean))];const h=new URLSearchParams(location.hash.slice(1));
 if(pls.length)h.set('place',pls.join(','));
 return `<b>${esc(common(rs.map(r=>({_r:r})))||T.name[rs[0][RNAME]])}</b> <span class="meta">${rs.length} events · ${new Set(rs.map(r=>r[RP])).size} people</span>`+
  (pls.length?` · <a href="#${h.toString().replace(/%2C/g,',').replace(/%3A/g,':').replace(/%2F/g,'/')}">only this place</a>`:'')+
  '<br>'+rs.slice(0,40).map(r=>`<span class="sw" style="background:${rowColor(r)}"></span>${esc(fmtDate(r[RDATE]))} · ${esc(T.t[r[RT]])} · ${esc(P[r[RP]][1])}${r[RDET]&&r[RDET]!==T.name[r[RNAME]]?` <span class="meta">${esc(r[RDET])}</span>`:''}`).join('<br>')+
  (rs.length>40?`<br><span class="meta">… ${rs.length-40} more in the table</span>`:'')}
// single points name their place once the map is close
map.on('zoomend',()=>document.getElementById('map').classList.toggle('close',map.getZoom()>=11));
const paths=L.layerGroup().addTo(map);
// what the map draws sits on the map: colour and paths
const Ctl=L.Control.extend({onAdd(){const d=L.DomUtil.create('div','ctl');
 d.innerHTML=`<label>Colour <select id="color"><option value="">auto</option><option value="branch">branch</option><option value="person">person</option><option value="type">event type</option><option value="layer">layer</option><option value="time">period</option></select></label>
 <button id="lines" title="Draw a path through each selected person's dated events (one or two people)"><svg viewBox="0 0 16 16"><polyline points="2,13 6,6 10,10 14,3" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="2" cy="13" r="1.6" fill="currentColor"/><circle cx="14" cy="3" r="1.6" fill="currentColor"/></svg>paths</button>`;
 L.DomEvent.disableClickPropagation(d);L.DomEvent.disableScrollPropagation(d);return d}});
new Ctl({position:'topright'}).addTo(map);
// the colour key, following the colouring
const Lgd=L.Control.extend({onAdd(){const d=L.DomUtil.create('div','ctl lgd');d.id='lgd';L.DomEvent.disableClickPropagation(d);return d}});
new Lgd({position:'bottomleft'}).addTo(map);
function legend(){const ck=S.colorKey,el=document.getElementById('lgd');const c={};let rows=[];
 const val={branch:r=>P[r[RP]][4]||'none',person:r=>P[r[RP]][0],type:r=>T.t[r[RT]],layer:r=>T.l[r[RL]]}[ck];
 if(ck==='time'){const ys=FILT.map(r=>r[RY0]??r[RY1]).filter(y=>y!=null);
  el.innerHTML=`<div><b>Period</b></div><div><span>≤1700</span><span class="grad"></span><span>2000</span></div>`+(ys.length?`<div class="meta">points here: ${Math.min(...ys)}–${Math.max(...ys)}</div>`:'');return}
 FILT.forEach(r=>{const v=val(r);c[v]=(c[v]||0)+1});
 const keys=ck==='person'?(S.person||[]).filter(v=>c[v]):ck==='branch'?['FF','FM','MF','MM','none'].filter(v=>c[v]):Object.keys(c).sort((a,b)=>c[b]-c[a]);
 const shown=keys.slice(0,10),rest=keys.slice(10).reduce((n,v)=>n+c[v],0);
 const col=v=>ck==='person'?colorOf(v):ck==='branch'?css(BR[v]||'var(--none)'):colorOf(v);
 el.innerHTML=`<div><b>${{branch:'Family branch',person:'Person',type:'Event type',layer:'Layer'}[ck]}</b></div>`+shown.map(v=>`<div><span class="sw" style="background:${col(v)}"></span>${esc(ck==='person'?LABEL.person(v):v)}<span class="n">${c[v]}</span></div>`).join('')+
  (rest?`<div><span class="sw" style="background:${PAL[PAL.length-1]}"></span>other<span class="n">${rest}</span></div>`:'')}
const LKM={farm:.3,village:1,parent:2,parish:6,town:5,region:60,country:300};
function popup(r){const p=P[r[RP]];const sp=new URLSearchParams({person:p[0],lines:'1'});
 return `<b>${esc(p[1])}</b> <span class="meta">${esc(p[3])} ${esc(p[5]||p[4]||'')}</span><br>${esc(T.t[r[RT]])} · ${esc(fmtDate(r[RDATE]))}<br>${esc(T.name[r[RNAME]])}${T.parish[r[RPAR]]?', '+esc(T.parish[r[RPAR]]):''} <span class="meta">(${esc(T.lv[r[RLV]])})</span>`+
 (r[RDET]&&r[RDET]!==T.name[r[RNAME]]?`<br><span class="meta">${esc(r[RDET])}</span>`:'')+
 `<br><a href="#${sp.toString().replace(/%3A/g,':')}">this person's path</a> · <a href="family.html#p=${encodeURIComponent(p[0]).replace(/%3A/g,':')}">family</a>`+
 p[8].map(i=>` · <a href="#${new URLSearchParams({person:[p[0],P[i][0]].join(','),lines:'1'}).toString().replace(/%3A/g,':').replace(/%2C/g,',')}">with ${p[8].length===1?'spouse':esc(given(P[i]))}</a>`).join('')+
 (T.parish[r[RPAR]]?` · <a href="#parish=${encodeURIComponent(T.parish[r[RPAR]])}">all in ${esc(T.parish[r[RPAR]])}</a>`+
  ` · <a href="archives.html#${new URLSearchParams(Object.assign({parish:T.parish[r[RPAR]]},T.l[r[RL]]==='record'?{q:r[RDET].split(' p. ')[0]}:{},{kin:'all'})).toString()}" target="archives">${T.l[r[RL]]==='record'?'this volume':'archives'}</a>`:'')+
 (r[RURL]?` · <a href="${esc(r[RURL])}" target="_blank" rel="noopener">record ↗</a>`:'')}
let FILT=[],ALL=[];
function drawMap(fit){cluster.clearLayers();paths.clearLayers();
 const ms=ALL.map(r=>{const m=L.circleMarker([r[RLAT],r[RLON]],{radius:6,weight:1,color:'#fff',fillColor:rowColor(r),fillOpacity:.9});m.bindPopup(()=>popup(r));m._r=r;if(ALL.length<=4000)m.bindTooltip(short(r),{permanent:true,direction:'right',offset:[5,0],className:'plab'});return m});
 cluster.addLayers(ms);
 const sel=S.person||[];
 if(S.lines==='1'&&sel.length&&sel.length<=2){sel.forEach((pid,k)=>{const pts=ALL.filter(r=>P[r[RP]][0]===pid&&T.l[r[RL]]==='tree'&&(r[RY0]??r[RY1])!=null)
   .sort((a,b)=>(a[RY0]??a[RY1])-(b[RY0]??b[RY1]));
   const dated=pts.filter(r=>T.d[r[RD]]==='day'||['birth','baptism','marriage','death','burial'].includes(T.t[r[RT]]));
   const use=dated.length>1?dated:pts;const c=PAL[k%PAL.length];
   if(use.length>1){L.polyline(use.map(r=>[r[RLAT],r[RLON]]),{color:c,weight:3,opacity:.85}).addTo(paths);
    use.forEach((r,i)=>L.circle([r[RLAT],r[RLON]],{radius:(LKM[T.lv[r[RLV]]]||5)*1000,color:c,weight:0,fillOpacity:.06,interactive:false}).addTo(paths));
    // the stops in date order, numbered; one number per run of events at one place
    const seq=[];use.forEach(r=>{const l=seq[seq.length-1];if(l&&l.lat===r[RLAT]&&l.lon===r[RLON])l.rs.push(r);else seq.push({lat:r[RLAT],lon:r[RLON],rs:[r]})});
    seq.forEach((s,i)=>L.marker([s.lat,s.lon],{zIndexOffset:1000+i,icon:L.divIcon({className:'',iconSize:[20,20],
      html:`<div class="seq" style="background:${c};width:20px;height:20px">${i+1}</div>`})})
     .bindPopup(`<b>${esc(P[s.rs[0][RP]][1])}</b> · stop ${i+1}<br>`+s.rs.map(r=>`${esc(fmtDate(r[RDATE]))} · ${esc(T.t[r[RT]])}: ${esc(T.name[r[RNAME]])}`).join('<br>')).addTo(paths))}})}
 if(fit&&ALL.length){const b=L.latLngBounds(ALL.map(r=>[r[RLAT],r[RLON]]));map.fitBounds(b.pad(.1),{maxZoom:12})}}
// table
let SORT={k:'year',d:1};
function drawTable(){const cols=[['year','Years'],['person','Person'],['type','Event'],['place','Place'],['parish','Parish'],['level','Precision'],['det','Detail']];
 const val={year:r=>r[RY0]??r[RY1]??9999,person:r=>P[r[RP]][1],type:r=>T.t[r[RT]],place:r=>T.name[r[RNAME]],parish:r=>T.parish[r[RPAR]],level:r=>T.lv[r[RLV]],det:r=>r[RDET]};
 const rows=[...FILT].sort((a,b)=>{const x=val[SORT.k](a),y=val[SORT.k](b);return (x>y?1:x<y?-1:0)*SORT.d}).slice(0,600);
 document.getElementById('tbl').innerHTML=`<tr>${cols.map(([k,l])=>`<th data-s="${k}">${l}${SORT.k===k?(SORT.d>0?' ▲':' ▼'):''}</th>`).join('')}</tr>`+
  rows.map((r,i)=>`<tr data-i="${R.indexOf(r)}"><td>${esc(fmtDate(r[RDATE]))}</td><td><span class="sw" style="background:${rowColor(r)}"></span>${esc(P[r[RP]][1])}</td><td>${esc(T.t[r[RT]])}</td><td>${esc(T.name[r[RNAME]])}</td><td>${esc(T.parish[r[RPAR]])}</td><td>${esc(T.lv[r[RLV]])}</td><td class="wrap meta">${esc(r[RDET])}</td></tr>`).join('')+
  (FILT.length>600?`<tr><td colspan="7" class="meta">Showing 600 of ${FILT.length}; filter or sort to see others.</td></tr>`:'')}
document.getElementById('tbl').addEventListener('click',e=>{const th=e.target.closest('th');if(th){const k=th.dataset.s;SORT=SORT.k===k?{k,d:-SORT.d}:{k,d:1};drawTable();return}
 const tr=e.target.closest('tr[data-i]');if(!tr)return;const r=R[+tr.dataset.i];map.setView([r[RLAT],r[RLON]],Math.max(map.getZoom(),12));
 let mk=null;cluster.eachLayer(m=>{if(m._r===r)mk=m});if(mk)cluster.zoomToShowLayer(mk,()=>mk.openPopup())});
// chips: active filters
function chips(){const out=[];for(const [k,label] of FACETS)(S[k]||[]).forEach(v=>out.push([k,v,`${label}: ${LABEL[k]?LABEL[k](v):v}`]));
 if(S.from||S.to)out.push(['year','',`${S.from||'…'}–${S.to||'…'}`]);(S.place||[]).forEach(v=>out.push(['place',v,`place: ${v}`]));if(S.q)out.push(['q','',`“${S.q}”`]);
 document.getElementById('chips').innerHTML=out.map(([k,v,t])=>`<span class="chip" data-k="${esc(k)}" data-v="${esc(v)}" title="remove">${esc(t)} ×</span>`).join('')}
document.getElementById('chips').addEventListener('click',e=>{const c=e.target.closest('.chip');if(!c)return;const k=c.dataset.k,v=c.dataset.v;
 if(k==='year'){delete S.from;delete S.to}else if(k==='q'){delete S.q;document.getElementById('q').value=''}else{S[k]=(S[k]||[]).filter(x=>x!==v)}update()});
// glue
function update(fit,pan){S.colorKey=colorKey();const ck=S.colorKey;
 ALL=R.filter(r=>base(r,'bbox'));FILT=S.bbox==='1'?ALL.filter(r=>base(r)):ALL;
 if(ck==='type'||ck==='layer'){const c={};FILT.forEach(r=>{const v=ck==='type'?T.t[r[RT]]:T.l[r[RL]];c[v]=(c[v]||0)+1});S.colorKeys=Object.keys(c).sort((a,b)=>c[b]-c[a])}
 const persons=new Set(FILT.map(r=>r[RP])).size;
 document.getElementById('count').textContent=(S.bbox==='1'?`${FILT.length} of ${ALL.length} point${ALL.length===1?'':'s'} in the map view`:`${FILT.length} point${FILT.length===1?'':'s'}`)+` · ${persons} ${persons===1?'person':'people'}`;
 document.getElementById('lines').classList.toggle('on',S.lines==='1');
 const nsel=(S.person||[]).length;document.getElementById('lines').disabled=!nsel||nsel>2;document.getElementById('bbox').classList.toggle('on',S.bbox==='1');
 document.getElementById('color').value=S.color||'';
 const keep={...S};delete keep.colorKey;delete keep.colorKeys;const save=S;S=keep;writeHash();S=save;
 facetsUI();chips();if(!pan)drawMap(fit);drawTable();legend()}
document.getElementById('q').addEventListener('input',e=>{S.q=e.target.value;clearTimeout(window._qt);window._qt=setTimeout(()=>update(),250)});
document.getElementById('color').onchange=e=>{S.color=e.target.value;update()};
document.getElementById('lines').onclick=()=>{S.lines=S.lines==='1'?'':'1';update()};
document.getElementById('bbox').onclick=()=>{S.bbox=S.bbox==='1'?'':'1';update()};
document.getElementById('reset').onclick=()=>{S=structuredClone(DEFAULT);document.getElementById('q').value='';update(true)};
map.on('moveend',()=>{MAPB=map.getBounds();const c=map.getCenter();S.view=`${c.lat.toFixed(4)},${c.lng.toFixed(4)},${map.getZoom()}`;
 if(S.bbox==='1')update(false,true);else{const keep={...S};delete keep.colorKey;delete keep.colorKeys;const save=S;S=keep;writeHash();S=save}});
window.addEventListener('hashchange',()=>{const v=S.view;readHash();document.getElementById('q').value=S.q||'';update(!S.view||S.view!==v)});
readHash();document.getElementById('q').value=S.q||'';
// no position in the address: fit to the points once the map is measured
// (setView fires moveend, which writes a view into S, so remember it first)
const FIT=!S.view;
if(S.view){const [a,b,z]=S.view.split(',').map(Number);map.setView([a,b],z)}else map.setView([58,14.5],7);
document.getElementById('map').classList.toggle('close',map.getZoom()>=11);
MAPB=map.getBounds();update(false);
// the grid sizes the map after Leaflet has measured it: measure again
setTimeout(()=>{map.invalidateSize();if(FIT)update(true)},0);   // not rAF: it waits while the tab is hidden
window.addEventListener('resize',()=>{map.invalidateSize();fitLast()});
</script>__DATA__</body></html>
"""
HTML = HTML.replace("__LINEAGE_DARK__", lineage.css_vars(dark=True)).replace("__LINEAGE__", lineage.css_vars())


def _main(argv):
    import config
    cfg = config.load()
    people, points = collect(cfg)
    data = pack(people, points)
    out = config.path(cfg, "geography.html")
    write(out, data)
    layers = Counter(p["l"] for p in points)
    print(f"geography: {len(points)} points ({', '.join(f'{k} {v}' for k, v in layers.items())}) "
          f"for {len(people)} people -> {out}")


if __name__ == "__main__":
    _main(sys.argv[1:])
