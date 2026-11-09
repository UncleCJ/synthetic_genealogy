"""
A geographic data view: every located event and record on one map, with
facet filters (as in Calibre's tag browser), a table, and a link scheme so
other views can open it already filtered.

    python3 geoview.py          # writes data/geography.html (private: names)

Points:
- tree events from the tree store (tree_store.py + place_store.py): births,
  baptisms, residences (incl. MyHeritage 2026 address residences),
  marriages, deaths, burials, emigration, ... located through their
  place_id; a place without its own point falls back to its parish;
- household-examination citations (volumes.py): one point per person,
  volume and page, at the farm or village of record (else the parish).

Each point carries: person, event type, layer (tree / record), years,
date precision (day / year / none), place, parish, place precision (farm,
village, parent, parish, town, region), relationship to the proband and
branch (FF/FM/MF/MM), surname.

Link scheme (the part after #, all optional, values comma-separated and
URL-encoded); the page keeps the address in step with the filters, so a
view can be bookmarked or opened from elsewhere:

    person=MH:I1,MH:I2       people (MyHeritage ids)
    lines=1                  draw each selected person's path
    type=residence,birth     event types        layer=tree,record
    kin=ancestor,relative    relationship       branch=FF,FM
    surname=Svenningsson     parish=Källeryd    place=Källeryd/Hagelstorp
    level=farm,village       precision of the place
    dated=day,year,none      precision of the date
    from=1850&to=1900        years (a point counts if its span overlaps)
    q=text                   free text over person, place, detail
    color=branch|type|layer|time
    raw=1                    MyHeritage's residence entries one by one
                             (default: aggregated into stays, stays.py)
    view=lat,lon,zoom        map position      bbox=1 (filter to the map view)

Sketch: kinship comes from the analysed GEDCOM (config), joined to store
people by MyHeritage id; people only in a newer export show as "unknown".
"""
import json
import re
import sys
from collections import Counter

YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
TAGS = {"BIRT": "birth", "CHR": "baptism", "BAPM": "baptism", "DEAT": "death", "BURI": "burial",
        "CREM": "burial", "MARR": "marriage", "DIV": "divorce", "ENGA": "engagement",
        "RESI": "residence", "OCCU": "occupation", "EDUC": "education", "EMIG": "emigration",
        "IMMI": "immigration", "CENS": "census", "CONF": "confirmation", "NATU": "naturalisation",
        "PROB": "probate", "_MILT": "military", "EVEN": "event", "FACT": "fact", "RETI": "retirement",
        "GRAD": "graduation", "RELI": "religion", "TITL": "title"}


def _span(date):
    ys = [int(y) for y in YEAR.findall(date or "")]
    if not ys:
        return None, None
    d = (date or "").upper()
    if d.startswith(("TO ", "BEF")):
        return None, max(ys)
    if d.startswith(("FROM ", "AFT")) and " TO " not in d:
        return min(ys), None
    return min(ys), max(ys)


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
    tree = gedcom_io.Tree(volumes.config.path(cfg, g["file"])) if hasattr(volumes, "config") else None
    if tree is None:
        import config
        tree = gedcom_io.Tree(config.path(cfg, g["file"]))
    kin = volumes.kinship(tree, g.get("proband"))
    by_mh = {}
    for i, p in tree.people.items():
        mh = next((f for f in p["facts"] if f.startswith("MH:")), None)
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
                               name=nm or text, parish=par or "", place=place_id or "",
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
                           date=f"{y0}–{y1}" if y0 else "", name=r.get("place") or r.get("farm") or r.get("parish"),
                           parish=r.get("parish", ""), place=r.get("place_id") or "",
                           lv=c[2], lat=round(c[0], 5), lon=round(c[1], 5),
                           det=f"{r['volume']} p. {r.get('page') or '?'}",
                           url=r.get("ra_viewer") or r.get("url") or ""))
    used = {pt["p"] for pt in points}
    ppl = {pid: dict(p, spouses=sorted(s for s in spouses.get(pid, ()) if s in used))
           for pid, p in people.items() if pid in used}
    return ppl, points


def pack(people, points):
    """Strings into lookup tables, points as arrays: a smaller page."""
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


VIEWS = [("people.html", "People"), ("volumes.html", "Volumes"), ("geography.html", "Geography")]
NAV_CSS = ("nav.views{display:flex;gap:2px;margin-right:6px}nav.views a{padding:3px 10px;border:1px solid var(--line);"
           "border-radius:6px;text-decoration:none;color:var(--fg);background:var(--card);font-size:13px}"
           "nav.views a.on{background:var(--sel);font-weight:600}nav.views a:hover{border-color:var(--mut)}"
           "nav.views a.home{color:var(--mut)}")


def nav(current):
    """The row of links between the views, the same on each page."""
    links = "".join(f'<a href="{f}"' + (' class="on"' if f == current else "") + f">{t}</a>"
                    for f, t in VIEWS)
    return f'<style>{NAV_CSS}</style><nav class="views"><a class="home" href="index.html" title="All outputs">⌂</a>{links}</nav>'


def write(path, data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    path.write_text(HTML.replace("__NAV__", nav("geography.html")).replace("__DATA__", payload),
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
--FF:#2f6db5;--FM:#c0522b;--MF:#2f8f5b;--MM:#8a4fb0;--none:#8f8a80}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ece9e2;--mut:#9b968c;--line:#34312c;--card:#201f1c;--sel:#4a4220;--acc:#6ea4e6;
--FF:#6ea4e6;--FM:#e8835c;--MF:#5fc38c;--MM:#b98ad8;--none:#777}}
*{box-sizing:border-box}html,body{height:100%}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,-apple-system,sans-serif;display:grid;grid-template-columns:290px 1fr;grid-template-rows:auto 1fr}
header{grid-column:1/-1;display:flex;gap:10px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:16px;margin:0 8px 0 0}
input,select,button{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
button{cursor:pointer}button.on{background:var(--sel)}
#side{overflow:auto;border-right:1px solid var(--line);padding:6px 10px 40px}
#mainp{display:grid;grid-template-rows:minmax(300px,62%) 1fr;min-height:0}
#map{min-height:0}
#tablebox{overflow:auto;border-top:1px solid var(--line)}
details{border-bottom:1px solid var(--line);padding:4px 0}summary{cursor:pointer;font-weight:600;padding:3px 0;list-style:none;display:flex;justify-content:space-between}
summary::-webkit-details-marker{display:none}summary .act{font-weight:400;color:var(--acc);font-size:12px}
.f{display:flex;justify-content:space-between;gap:6px;padding:1px 4px;border-radius:4px;cursor:pointer;user-select:none}
.f:hover{background:var(--line)}.f.on{background:var(--sel);font-weight:600}.f.zero{opacity:.4}
.f .n{color:var(--mut);font-variant-numeric:tabular-nums}
.sw{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:0}
.fsearch{width:100%;margin:3px 0}
.hist{display:flex;align-items:flex-end;height:46px;gap:1px;margin:4px 0}
.hist div{flex:1;background:var(--acc);opacity:.55;cursor:pointer;min-height:1px}.hist div.in{opacity:.95}
.yr{display:flex;gap:6px}.yr input{width:70px}
table{border-collapse:collapse;width:100%}th,td{padding:3px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{position:sticky;top:0;background:var(--card);cursor:pointer;font-weight:600}tr:hover td{background:var(--line);cursor:pointer}
td.wrap{white-space:normal}
.meta{color:var(--mut)}.chip{display:inline-block;border:1px solid var(--line);border-radius:10px;padding:0 7px;margin:2px;cursor:pointer}
.chip:hover{text-decoration:line-through}
.leaflet-popup-content{font:13px/1.4 system-ui,sans-serif}.leaflet-popup-content a{color:var(--acc)}
@media(max-width:800px){body{grid-template-columns:1fr;grid-template-rows:auto auto 1fr}#side{max-height:40vh}}
</style></head><body>
<header>__NAV__<h1>Geography</h1>
<input id="q" placeholder="Search person, place, volume…" size="28">
<label>Colour <select id="color"><option value="branch">branch</option><option value="type">event type</option><option value="layer">layer</option><option value="time">period</option></select></label>
<button id="lines" title="Draw a path for each selected person">paths</button>
<button id="bbox" title="Count and list only what is in the map view">only map view</button>
<button id="raw" title="Show MyHeritage's residence entries one by one instead of aggregated stays">raw entries</button>
<span id="chips"></span><span class="meta" id="count"></span>
<button id="reset">reset</button></header>
<aside id="side"></aside>
<div id="mainp"><div id="map"></div><div id="tablebox"><table id="tbl"></table></div></div>
<script>
const D=__DATA__;const T=D.tabs,P=D.people,R=D.rows;
// row fields
const RP=0,RT=1,RL=2,RY0=3,RY1=4,RD=5,RLAT=6,RLON=7,RLV=8,RNAME=9,RPAR=10,RPL=11,RDATE=12,RDET=13,RURL=14,RAGG=15,RN=16;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const BR={FF:'var(--FF)',FM:'var(--FM)',MF:'var(--MF)',MM:'var(--MM)'};
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v.replace(/^var\(|\)$/g,'')).trim()||v;
const PAL=['#2f6db5','#c0522b','#2f8f5b','#8a4fb0','#b08a1e','#1f8a96','#a8326b','#5d6b2f','#7a5c3e','#3e6f7a','#999'];
// facets: key, label, value of a row
const FACETS=[
 ['layer','Layer',r=>T.l[r[RL]]],
 ['type','Event type',r=>T.t[r[RT]]],
 ['dated','Date precision',r=>T.d[r[RD]]],
 ['kin','Relationship',r=>P[r[RP]][3]],
 ['branch','Branch',r=>P[r[RP]][4]||'none'],
 ['level','Place precision',r=>T.lv[r[RLV]]],
 ['parish','Parish',r=>T.parish[r[RPAR]]||'(outside parishes)'],
 ['surname','Surname',r=>P[r[RP]][2]||'(none)'],
 ['person','Person',r=>P[r[RP]][0]],
];
const LABEL={person:v=>{const p=P.find(x=>x[0]===v);return p?p[1]:v}};
let S={};const MULTI=FACETS.map(f=>f[0]);
function readHash(){S={};const h=new URLSearchParams(location.hash.slice(1));
 for(const [k,v] of h){S[k]=MULTI.includes(k)||k==='place'?v.split(',').filter(Boolean):v}}
function writeHash(){const h=new URLSearchParams();for(const [k,v] of Object.entries(S)){if(Array.isArray(v)?v.length:v!==undefined&&v!=='')h.set(k,Array.isArray(v)?v.join(','):v)}
 history.replaceState(null,'','#'+h.toString().replace(/%2C/g,',').replace(/%3A/g,':').replace(/%2F/g,'/'))}
function yearOK(r){const a=+S.from||null,b=+S.to||null;if(!a&&!b)return true;const y0=r[RY0]??r[RY1],y1=r[RY1]??r[RY0];if(y0==null)return false;
 return (!a||y1>=a)&&(!b||y0<=b)}
let MAPB=null;
function base(r,skip){
 if(r[RAGG]===(S.raw==='1'?1:0))return false;   // stays by default, raw entries on request
 for(const [k,,fn] of FACETS){if(k===skip)continue;const sel=S[k];if(sel&&sel.length&&!sel.includes(fn(r)))return false}
 if(S.place&&S.place.length&&!S.place.includes(T.place[r[RPL]]))return false;
 if(skip!=='year'&&!yearOK(r))return false;
 if(S.q){const q=S.q.toLowerCase();const p=P[r[RP]];if(!(p[1]+' '+T.name[r[RNAME]]+' '+r[RDET]+' '+T.parish[r[RPAR]]+' '+p[0]).toLowerCase().includes(q))return false}
 if(S.bbox==='1'&&MAPB&&!MAPB.contains([r[RLAT],r[RLON]]))return false;
 return true}
// facets UI
const OPEN=new Set(['layer','type','kin','branch','level']);
function facetsUI(){const side=document.getElementById('side');let h='';
 // time
 const dec={};let n=0;R.forEach(r=>{if(!base(r,'year'))return;const y=r[RY0]??r[RY1];if(y==null)return;const d=Math.floor(y/10)*10;dec[d]=(dec[d]||0)+1});
 const ds=Object.keys(dec).map(Number).sort((a,b)=>a-b);const mx=Math.max(1,...Object.values(dec));
 h+=`<details open><summary>Time<span class="act" data-clear="year">${S.from||S.to?'clear':''}</span></summary>
 <div class="hist">${ds.map(d=>`<div data-dec="${d}" class="${yearOK([0,0,0,d,d+9])?'in':''}" style="height:${100*dec[d]/mx}%" title="${d}s: ${dec[d]}"></div>`).join('')}</div>
 <div class="meta" style="display:flex;justify-content:space-between"><span>${ds[0]||''}</span><span>${ds.length?ds[ds.length-1]+9:''}</span></div>
 <div class="yr"><input id="from" placeholder="from" value="${esc(S.from||'')}"> – <input id="to" placeholder="to" value="${esc(S.to||'')}"></div></details>`;
 for(const [k,label,fn] of FACETS){const c={};R.forEach(r=>{if(base(r,k)){const v=fn(r);c[v]=(c[v]||0)+1}});
  const sel=S[k]||[];sel.forEach(v=>{if(!(v in c))c[v]=0});
  let keys=Object.keys(c).sort((a,b)=>c[b]-c[a]||a.localeCompare(b));
  const many=keys.length>12;const fq=(document.getElementById('fs-'+k)||{}).value||'';
  if(fq)keys=keys.filter(v=>(LABEL[k]?LABEL[k](v):v).toLowerCase().includes(fq.toLowerCase()));
  const show=keys.slice(0,many?40:keys.length);
  const sw=v=>k==='branch'?`<span class="sw" style="background:${BR[v]||'var(--none)'}"></span>`:(k===S.colorKey?`<span class="sw" style="background:${colorOf(v)}"></span>`:'');
  h+=`<details ${OPEN.has(k)||sel.length||fq?'open':''} data-k="${k}"><summary>${label} <span class="act" data-clear="${k}">${sel.length?'clear':''}</span></summary>
  ${many?`<input class="fsearch" id="fs-${k}" placeholder="filter ${label.toLowerCase()}…" value="${esc(fq)}">`:''}
  ${show.map(v=>`<div class="f ${sel.includes(v)?'on':''} ${c[v]?'':'zero'}" data-k="${k}" data-v="${esc(v)}"><span>${sw(v)}${esc(LABEL[k]?LABEL[k](v):v)}</span><span class="n">${c[v]}</span></div>`).join('')}
  ${keys.length>show.length?`<div class="meta">… ${keys.length-show.length} more; type to narrow</div>`:''}</details>`}
 const act=document.activeElement&&document.activeElement.id;const pos=document.activeElement&&document.activeElement.selectionStart;
 side.innerHTML=h;if(act&&act.startsWith('fs-')){const e=document.getElementById(act);if(e){e.focus();e.setSelectionRange(pos,pos)}}}
document.getElementById('side').addEventListener('click',e=>{
 const c=e.target.closest('[data-clear]');if(c&&c.textContent){e.preventDefault();const k=c.dataset.clear;if(k==='year'){delete S.from;delete S.to}else delete S[k];update();return}
 const d=e.target.closest('[data-dec]');if(d){const y=+d.dataset.dec;if(S.from==y&&S.to==y+9){delete S.from;delete S.to}else{S.from=String(y);S.to=String(y+9)}update();return}
 const f=e.target.closest('.f');if(!f)return;const k=f.dataset.k,v=f.dataset.v;const sel=S[k]||[];
 S[k]=e.metaKey||e.ctrlKey||e.shiftKey||sel.length?(sel.includes(v)?sel.filter(x=>x!==v):[...sel,v]):[v];update()});
document.getElementById('side').addEventListener('input',e=>{if(e.target.classList.contains('fsearch'))facetsUI()});
document.getElementById('side').addEventListener('change',e=>{if(e.target.id==='from'||e.target.id==='to'){S[e.target.id]=e.target.value.trim();update()}});
// colours
function colorOf(v){if(S.colorKey==='branch')return css(BR[v]||'var(--none)');const keys=S.colorKeys||[];const i=keys.indexOf(v);return PAL[i<0?PAL.length-1:Math.min(i,PAL.length-1)]}
function rowColor(r){const ck=S.color||'branch';if(ck==='branch')return css(BR[P[r[RP]][4]]||'var(--none)');
 if(ck==='time'){const y=r[RY0]??r[RY1];if(y==null)return '#999';const t=Math.max(0,Math.min(1,(y-1700)/300));return `hsl(${220-200*t},65%,45%)`}
 const v=ck==='type'?T.t[r[RT]]:T.l[r[RL]];return colorOf(v)}
// map
const map=L.map('map',{preferCanvas:true});L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:17,attribution:'© OpenStreetMap'}).addTo(map);
const cluster=L.markerClusterGroup({chunkedLoading:true,maxClusterRadius:38,spiderfyOnMaxZoom:true,showCoverageOnHover:false});map.addLayer(cluster);
const paths=L.layerGroup().addTo(map);
const LKM={farm:.3,village:1,parent:2,parish:6,town:5,region:60,country:300};
function popup(r){const p=P[r[RP]];const sp=new URLSearchParams({person:p[0],lines:'1'});
 return `<b>${esc(p[1])}</b> <span class="meta">${esc(p[3])} ${esc(p[5]||p[4]||'')}</span><br>${esc(T.t[r[RT]])} · ${esc(r[RDATE])}<br>${esc(T.name[r[RNAME]])}${T.parish[r[RPAR]]?', '+esc(T.parish[r[RPAR]]):''} <span class="meta">(${esc(T.lv[r[RLV]])})</span>`+
 (r[RDET]&&r[RDET]!==T.name[r[RNAME]]?`<br><span class="meta">${esc(r[RDET])}</span>`:'')+
 `<br><a href="#${sp.toString().replace(/%3A/g,':')}">this person's path</a> · <a href="people.html#q=${encodeURIComponent(p[0])}" target="people">people view</a>`+
 (T.parish[r[RPAR]]?` · <a href="#parish=${encodeURIComponent(T.parish[r[RPAR]])}">all in ${esc(T.parish[r[RPAR]])}</a>`:'')+
 (r[RURL]?` · <a href="${esc(r[RURL])}" target="_blank" rel="noopener">record ↗</a>`:'')}
let FILT=[];
function drawMap(fit){cluster.clearLayers();paths.clearLayers();
 const ms=FILT.map(r=>{const m=L.circleMarker([r[RLAT],r[RLON]],{radius:6,weight:1,color:'#fff',fillColor:rowColor(r),fillOpacity:.9});m.bindPopup(()=>popup(r));m._r=r;return m});
 cluster.addLayers(ms);
 const sel=S.person||[];
 if(S.lines==='1'&&sel.length&&sel.length<=6){sel.forEach((pid,k)=>{const pts=FILT.filter(r=>P[r[RP]][0]===pid&&T.l[r[RL]]==='tree'&&(r[RY0]??r[RY1])!=null)
   .sort((a,b)=>(a[RY0]??a[RY1])-(b[RY0]??b[RY1]));
   const dated=pts.filter(r=>T.d[r[RD]]==='day'||['birth','baptism','marriage','death','burial'].includes(T.t[r[RT]]));
   const use=dated.length>1?dated:pts;const c=PAL[k%PAL.length];
   if(use.length>1){L.polyline(use.map(r=>[r[RLAT],r[RLON]]),{color:c,weight:3,opacity:.85}).addTo(paths);
    use.forEach((r,i)=>L.circle([r[RLAT],r[RLON]],{radius:(LKM[T.lv[r[RLV]]]||5)*1000,color:c,weight:0,fillOpacity:.06}).addTo(paths))}})}
 if(fit&&FILT.length){const b=L.latLngBounds(FILT.map(r=>[r[RLAT],r[RLON]]));map.fitBounds(b.pad(.1),{maxZoom:12})}}
// table
let SORT={k:'year',d:1};
function drawTable(){const cols=[['year','Years'],['person','Person'],['type','Event'],['place','Place'],['parish','Parish'],['level','Precision'],['det','Detail']];
 const val={year:r=>r[RY0]??r[RY1]??9999,person:r=>P[r[RP]][1],type:r=>T.t[r[RT]],place:r=>T.name[r[RNAME]],parish:r=>T.parish[r[RPAR]],level:r=>T.lv[r[RLV]],det:r=>r[RDET]};
 const rows=[...FILT].sort((a,b)=>{const x=val[SORT.k](a),y=val[SORT.k](b);return (x>y?1:x<y?-1:0)*SORT.d}).slice(0,600);
 document.getElementById('tbl').innerHTML=`<tr>${cols.map(([k,l])=>`<th data-s="${k}">${l}${SORT.k===k?(SORT.d>0?' ▲':' ▼'):''}</th>`).join('')}</tr>`+
  rows.map((r,i)=>`<tr data-i="${R.indexOf(r)}"><td>${esc(r[RDATE]||'')}</td><td><span class="sw" style="background:${rowColor(r)}"></span>${esc(P[r[RP]][1])}</td><td>${esc(T.t[r[RT]])}</td><td>${esc(T.name[r[RNAME]])}</td><td>${esc(T.parish[r[RPAR]])}</td><td>${esc(T.lv[r[RLV]])}</td><td class="wrap meta">${esc(r[RDET])}</td></tr>`).join('')+
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
function update(fit){S.colorKey=S.color||'branch';const ck=S.colorKey;
 FILT=R.filter(r=>base(r));
 if(ck==='type'||ck==='layer'){const c={};FILT.forEach(r=>{const v=ck==='type'?T.t[r[RT]]:T.l[r[RL]];c[v]=(c[v]||0)+1});S.colorKeys=Object.keys(c).sort((a,b)=>c[b]-c[a])}
 const persons=new Set(FILT.map(r=>r[RP])).size;
 document.getElementById('count').textContent=`${FILT.length} points · ${persons} people`;
 document.getElementById('lines').classList.toggle('on',S.lines==='1');document.getElementById('raw').classList.toggle('on',S.raw==='1');document.getElementById('bbox').classList.toggle('on',S.bbox==='1');
 document.getElementById('color').value=S.color||'branch';
 const keep={...S};delete keep.colorKey;delete keep.colorKeys;const save=S;S=keep;writeHash();S=save;
 facetsUI();chips();drawMap(fit);drawTable()}
document.getElementById('q').addEventListener('input',e=>{S.q=e.target.value;clearTimeout(window._qt);window._qt=setTimeout(()=>update(),250)});
document.getElementById('color').onchange=e=>{S.color=e.target.value;update()};
document.getElementById('lines').onclick=()=>{S.lines=S.lines==='1'?'':'1';update()};
document.getElementById('bbox').onclick=()=>{S.bbox=S.bbox==='1'?'':'1';update()};
document.getElementById('raw').onclick=()=>{S.raw=S.raw==='1'?'':'1';update()};
document.getElementById('reset').onclick=()=>{S={};document.getElementById('q').value='';update(true)};
map.on('moveend',()=>{MAPB=map.getBounds();const c=map.getCenter();S.view=`${c.lat.toFixed(4)},${c.lng.toFixed(4)},${map.getZoom()}`;
 if(S.bbox==='1')update();else{const keep={...S};delete keep.colorKey;delete keep.colorKeys;const save=S;S=keep;writeHash();S=save}});
window.addEventListener('hashchange',()=>{const v=S.view;readHash();document.getElementById('q').value=S.q||'';update(!S.view||S.view!==v)});
readHash();document.getElementById('q').value=S.q||'';
if(S.view){const [a,b,z]=S.view.split(',').map(Number);map.setView([a,b],z)}else map.setView([58,14.5],7);
MAPB=map.getBounds();update(false);
// the grid sizes the map after Leaflet has measured it: measure again
requestAnimationFrame(()=>{map.invalidateSize();if(!S.view)update(true)});
window.addEventListener('resize',()=>map.invalidateSize());
</script></body></html>
"""


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
