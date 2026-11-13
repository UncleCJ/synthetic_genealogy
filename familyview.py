"""
The family lens: one person in focus, their pedigree four generations up
and their close family around them, read from the tree store. Click anyone
to move the focus; the focus lives in the address, so a person's page can be
bookmarked or opened from another view.

    python3 familyview.py       # writes data/output/family.html (private: names)

Each person shows their years, their lineage codes from the proband (one
per path under pedigree collapse), and counts: tree events, source
citations, and tree-linked or documented matches whose path ends at them.
A parent the tree does not name is drawn as an empty parent slot.
A line on top says how the focus is related to the proband ("wife of
X's 2nd cousin"), by the shortest path that prefers blood to marriage,
with the people along it as links back. Each household row has a lifeline
on one time scale for the page (birth to death, fading where no death is
recorded, a tick for the marriage).

Link scheme (after #): p=<store person id>, e.g. #p=MH:I1. Without it the
page opens on the proband.

Sketch: reads the store only (no GEDCOM), except to find the proband's
store id; match counts come from the rebuilt assertion tables.
"""
import sys
from collections import defaultdict

import identity
import lineage
from intervals import years as _span


def lineage_codes(parents, root, depth=12):
    """person -> sorted lineage codes from root ('' for root itself).
    parents: person -> (father, mother), either may be None."""
    codes = defaultdict(list)
    todo = [(root, "")]
    while todo:
        p, c = todo.pop()
        codes[p].append(c)
        if len(c) < depth:
            f, m = parents.get(p, (None, None))
            if f:
                todo.append((f, c + "F"))
            if m:
                todo.append((m, c + "M"))
    return {p: sorted(cs, key=lambda c: (len(c), c)) for p, cs in codes.items()}


ARCHIVAL = ("ra-full", "ra-link", "mh-record", "mh-index", "other")


def references(rows):
    """volume_refs rows -> {store id: [[event, date, volume, years, page, url, tier]]},
    in the shared reference order; citations to other trees only counted."""
    import references as refs
    out, trees = defaultdict(list), defaultdict(int)
    for r in rows:
        pid, tier = r.get("mh_id"), r.get("tier")
        if not pid:
            continue
        if tier == "tree":
            trees[pid] += 1
        elif tier in ARCHIVAL:
            k = refs.order_key(r.get("years"), r.get("parish") or r.get("archive_code"), r.get("series"), r.get("vol"))
            vol = r.get("volume") or r.get("mh_volume") or r.get("source_title") or ""
            out[pid].append((k, [r.get("event", ""), r.get("event_date", ""), vol, r.get("years", ""),
                                 r.get("page", ""), r.get("url") or r.get("ra_viewer") or "", tier,
                                 r.get("parish", "")]))
    res = {}
    for p, v in out.items():
        rows, seen = [], {}
        for _, x in sorted(v, key=lambda t: t[0]):
            k = tuple(x[:5])
            if k in seen:
                seen[k][8] += 1          # the same reference again: counted, not repeated
            else:
                seen[k] = x + [1]
                rows.append(seen[k])
        res[p] = rows
    return res, dict(trees)


def person_fixes(fixes):
    """errata [[fix]] entries on a person's birth or death -> {store id: {field: entry}}."""
    out = defaultdict(dict)
    for f in fixes:
        k, field = f.get("key", ""), f.get("field", "")
        if k.startswith("person:") and field in ("birth", "death"):
            out[k[7:]][field] = f
    return out


def collect(db, root, ref_rows=(), fixes=()):
    """The lens's data from a store connection; root is the proband's store id;
    ref_rows: the volume_refs rows (volumes.py), for the references section;
    fixes: errata [[fix]] entries, of which a person's birth and death apply
    while the store still says what the erratum calls `was`."""
    people = {pid: dict(name=f"{g or ''} {s or ''}".strip() or "?", sex=sex or "")
              for pid, g, s, sex in db.execute("select id, given, surname, sex from person")}
    for pid, tag, date in db.execute("select owner, tag, date from event where tag in ('BIRT','DEAT')"):
        if pid in people:
            k = "b" if tag == "BIRT" else "d"
            people[pid][k], people[pid][k + "r"] = _span(date)[0], date or ""
    pfx = person_fixes(fixes)
    applied = defaultdict(list)
    for pid, fs in pfx.items():
        for field, f in fs.items():
            k = "b" if field == "birth" else "d"
            if pid in people and people[pid].get(k + "r", "") == (f.get("was") or ""):
                people[pid][k], people[pid][k + "r"] = _span(f["now"])[0], f["now"]
                applied[pid].append((field, f))
    fams = {fid: dict(h=h, w=w, c=[]) for fid, h, w in db.execute("select id, husb, wife from family")}
    for fid, child in db.execute("select family, child from child order by rowid"):
        if fid in fams:
            fams[fid]["c"].append(child)
    for owner, tag, date in db.execute("select owner, tag, date from event where tag in ('MARR', 'DIV')"):
        if owner in fams and date:
            if tag == "MARR" and "m" not in fams[owner]:
                fams[owner]["m"], fams[owner]["mr"] = _span(date)[0], date
            elif tag == "DIV":
                fams[owner].setdefault("dv", _span(date)[0])
    parents = {}
    for f in fams.values():
        for c in f["c"]:
            parents.setdefault(c, (f["h"], f["w"]))
    codes = lineage_codes(parents, root)
    nev = dict(db.execute("select owner, count(*) from event group by owner"))
    ncit = dict(db.execute("select owner, count(*) from citation group by owner"))
    # matches whose documented or tree path ends at this ancestor (one count per match)
    by_code = defaultdict(set)
    for t in ("out_assertions_tree", "out_assertions_documented"):
        try:
            for lin, mk in db.execute(f"select lineage, match_key from {t}"):
                by_code[lin].add(mk)
        except Exception:
            pass
    linked = defaultdict(int)
    for (pid,) in db.execute("select person from dna_match where person is not null and person != ''"):
        linked[pid] += 1
    out = []
    for pid, p in people.items():
        cs = codes.get(pid, [])
        dna = len(set().union(*(by_code.get(c, set()) for c in cs))) if cs else 0
        out.append([pid, p["name"], p["sex"], p.get("b"), p.get("d"), cs,
                    nev.get(pid, 0), ncit.get(pid, 0), dna, linked.get(pid, 0), p.get("br", ""), p.get("dr", "")])
    life = defaultdict(list)
    for owner, tag, date, place, value, parish in db.execute(
            # a place from the store alone (records placed it, the tree has no
            # text) is named with its parish: "Gyllenfors, Anderstorp"
            "select e.owner, e.tag, e.date, coalesce(nullif(e.place, ''), p.name ||"
            " case when p.parish is not null and p.parish != p.name then ', ' || p.parish else '' end), e.value,"
            " coalesce(p.parish, case when e.place_id like 'parish:%' then substr(e.place_id, 8) end)"
            " from event e left join place p on p.id = e.place_id order by e.owner, e.n"):
        if owner in people:
            life[owner].append([tag, date or "", place or "", value or "", None, parish or ""])
    for pid, fs in applied.items():
        for field, f in fs:
            tag = "BIRT" if field == "birth" else "DEAT"
            life[pid] = [e for e in life[pid] if e[0] != tag] + [
                [tag, f["now"], "", "erratum: " + f.get("source", ""), None, ""]]
    refs, trees = references(ref_rows)
    return dict(root=root, people=out, life=life, refs=refs, trees=trees,
                fams=[[fid, f["h"], f["w"], f["c"], f.get("m"), f.get("mr", ""), f.get("dv")] for fid, f in fams.items()])


def proband_id(cfg):
    import gedcom_io
    tree, proband = gedcom_io.load(cfg)
    x = tree.id(proband)
    return identity.mh_id(tree.people[x]["facts"]) or "MH:" + x.strip("@")


def write(path, data):
    import geoview
    path.write_text(geoview.embed(HTML.replace("__NAV__", geoview.nav("family.html"))
                                  .replace("__DATEJS__", geoview.DATE_JS)
                                  .replace("__FOLDJS__", geoview.FOLD_JS), data),
                    encoding="utf-8")


HTML = r"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Family</title>
<style>
:root{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#6b6760;--line:#e2ded6;--card:#fff;--sel:#fff1bf;--acc:#2f6db5;
__LINEAGE__}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ece9e2;--mut:#9b968c;--line:#34312c;--card:#201f1c;--sel:#4a4220;--acc:#6ea4e6;
__LINEAGE_DARK__}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,-apple-system,sans-serif}
header{display:flex;gap:10px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:16px;margin:0 8px 0 0}
input{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
main{padding:12px 16px;display:grid;gap:16px}
#ped{display:grid;grid-template-columns:repeat(4,minmax(70px,.55fr)) minmax(150px,1.1fr);gap:3px 12px;overflow-x:auto}
/* the person, parents and grandparents never sit level with the next
   generation's boxes, so their columns overlap by half (two tracks each, one
   shared); the great-grandparents, packed, keep a column of their own */
#ped .col{grid-row:1;pointer-events:none}#ped .col>.p{pointer-events:auto}
#ped .g0{grid-column:1/3}#ped .g1{grid-column:2/4}#ped .g2{grid-column:3/5}#ped .g3{grid-column:5/6;gap:8px}
#fam{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:8px 24px;align-items:start}
.col{display:grid;gap:3px}.col>*{align-self:center}
.p{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:6px;padding:3px 7px;cursor:pointer;display:flex;flex-direction:column;justify-content:center;min-width:0}
#ped .p{min-height:40px}
.p:hover{border-color:var(--mut)}.p.focus{background:var(--sel);cursor:default}
.p.slot{border-style:dashed;color:var(--mut);cursor:default;background:transparent}
.p .nm u{text-decoration-thickness:1px;text-underline-offset:2px}.p .nm{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.p .yr,.meta{color:var(--mut);font-size:11px}
.row{display:flex;gap:6px;align-items:center;margin-bottom:3px}.row .p{flex:1;flex-direction:row;align-items:baseline;gap:8px}
.row .p .nm{flex:0 1 auto}.row .p .yr{margin-left:auto;white-space:nowrap}
.tog{font:inherit;font-size:11px;color:var(--acc);background:none;border:0;cursor:pointer;padding:0 2px;min-width:30px;text-align:left}
.code{font-family:ui-monospace,monospace;font-size:11px}
.n{font-variant-numeric:tabular-nums}
h2{font-size:13px;margin:0 0 6px;color:var(--mut);font-weight:600}h2 a.hl{font-weight:400;font-size:12px;color:var(--acc);margin-left:8px}
main>section+section{border-top:1px solid var(--line);padding-top:12px}
table{border-collapse:collapse;width:100%}td{padding:2px 8px 2px 0;border-bottom:1px solid var(--line);vertical-align:top}td.y{white-space:nowrap;color:var(--mut);font-variant-numeric:tabular-nums}
td a{color:var(--acc)}span.notice{color:var(--mut);font-size:12px;font-style:italic}tr.der td.ev{font-style:italic;color:var(--mut)}tr.der td .lk{opacity:.85}td a.pl{color:inherit;text-decoration:none;border-bottom:1px dotted var(--mut)}td a.pl:hover{color:var(--acc);border-bottom-color:var(--acc)}
td a.plain{font-size:11px;color:var(--mut);opacity:0;transition:opacity .15s}td:hover a.plain{opacity:1;transition-delay:.35s}td a.plain:hover{color:var(--acc)}
.hh{margin-bottom:10px}.hht{font-size:12px;font-weight:600;margin:2px 0 0}.uni{color:var(--mut);font-size:11px;margin:0 0 4px}
details.hh>summary{cursor:pointer;color:var(--mut);font-size:12px;list-style:none}details.hh>summary::before{content:'▸ '}details.hh[open]>summary::before{content:'▾ '}
.warn{color:#b8860b;cursor:help}td .lk{cursor:pointer;color:var(--acc)}
.role{font-size:10px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);width:44px;flex:none}
.links a{color:var(--acc);margin-right:10px}
#hits{position:absolute;background:var(--card);border:1px solid var(--line);border-radius:6px;max-height:300px;overflow:auto;z-index:2}
/* lifelines: birth to death on one time scale for every row on the page;
   a life with no recorded end fades out; the tick is the union's marriage */
.ll{position:relative;flex:none;width:150px;height:16px;align-self:center}.ll i{position:absolute;top:0;bottom:0}
.ll .gl{width:1px;background:var(--line)}.ll .bar{top:6px;bottom:6px;border-radius:2px}.ll .mk{width:2px;top:2px;bottom:2px;background:var(--fg)}
@media (max-width:560px){.ll{width:72px}}
#rel{font-size:13px}#rel .lk{cursor:pointer;color:var(--acc)}#rel .sep{color:var(--mut);margin:0 4px}
#hits div{padding:3px 8px;cursor:pointer}#hits div:hover,#hits div.at{background:var(--line)}
</style></head><body>
<header>__NAV__<h1>Family</h1>
<span style="position:relative"><input id="q" placeholder="Find a person…" size="26" autocomplete="off"><div id="hits"></div></span>
<span id="title"></span><span class="links" id="links"></span></header>
<main><div id="rel"></div><section id="ped"></section><section id="fam"></section><section id="life"></section><section id="refs"></section></main>
<script type="text/plain" id="view-js">
const D=DATA;const P={};for(const r of D.people)P[r[0]]={id:r[0],nm:r[1],sex:r[2],b:r[3],d:r[4],codes:r[5],ev:r[6],cit:r[7],dna:r[8],lk:r[9],br:r[10],dr:r[11]};
const asChild={},asSpouse={};for(const [f,h,w,c,m,mr,dv] of D.fams){const F={id:f,h,w,c,m,mr,dv};for(const x of c)if(!asChild[x])asChild[x]=F;for(const x of [h,w])if(x)(asSpouse[x]=asSpouse[x]||[]).push(F)}
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const nm=s=>esc(s).replace(/(\S+)\*/g,'<u>$1</u>');
const yrs=p=>p.b||p.d?`${p.b??''}–${p.d??''}`:'';
const BR=c=>c?`var(--${c.slice(0,2)})`:'var(--line)';
const counts=p=>[p.ev&&`${p.ev} events`,p.cit&&`${p.cit} citations`,p.dna&&`${p.dna} matches on path`,p.lk&&`${p.lk} linked kit${p.lk>1?'s':''}`].filter(Boolean).join(' · ');
// a pedigree box: name, codes and years, counts on hover
function box(id,slot,cls=''){const p=P[id];if(!p)return `<div class="p slot">${esc(slot||'unknown')}</div>`;
 const c=p.codes,code=c.length?`<span class="code">${esc(c.slice(0,3).join(' '))}${c.length>3?' …':''}</span> `:'';
 return `<div class="p ${cls}" data-id="${esc(id)}" style="border-left-color:${BR(c[0])}" title="${esc(counts(p))}"><span class="nm">${nm(p.nm)}</span><span class="yr">${code}${esc(yrs(p))}</span></div>`}
// a family row: role, one-line box, and a fold for the person's own descendants
const kidsOf=x=>[...new Set((asSpouse[x]||[]).flatMap(G=>G.c))];
const byB=(a,b)=>(P[a]?.b??9999)-(P[b]?.b??9999);
const OPEN=new Set();let focus;
function row(id,role,depth=0,slot,G,U=G){const p=P[id];const pad=`style="margin-left:${depth*16}px"`;
 if(!p)return `<div class="row" ${pad}><span class="role">${role}</span><div class="p slot">${esc(slot)}</div><span class="ll"></span><span class="tog"></span></div>`;
 const k=role==='child'||depth?kidsOf(id):[];const open=OPEN.has(id);
 let h=`<div class="row" ${pad}><span class="role">${role}</span><div class="p${id===focus?' focus':''}" data-id="${esc(id)}" style="border-left-color:${BR(p.codes[0])}" title="${esc(counts(p))}"><span class="nm">${nm(p.nm)}</span><span class="yr">${esc(yrs(p))}${flag(id,G)}</span></div>${life(id,U)}`+
  `<button class="tog" data-tog="${esc(id)}" title="${k.length?(open?'fold':'unfold')+' their children':''}">${k.length?(open?'▾ ':'▸ ')+k.length:''}</button></div>`;
 if(open)h+=k.sort(byB).map(x=>row(x,'',depth+1)).join('');return h}
const myr=G=>G.m??Math.min(9999,...G.c.map(x=>P[x]?.b??9999));
const fams=x=>[...(asSpouse[x]||[])].sort((a,b)=>myr(a)-myr(b));
// married: a marriage or divorce record, dated or not ("0", "Jun 0" when the year is unknown)
const wed=G=>!!(G.m||G.mr||G.dv);
// day keys: a union's first and last sign of life (dated marriage, children's
// births; old records often marry after the first child) and a person's death
const bk=G=>G.c.map(c=>P[c]?.b?dk(P[c].br||String(P[c].b)):0).filter(Boolean);
const sk=G=>Math.min(99999999,...(G.m?[dk(G.mr||String(G.m))]:[]),...bk(G));
const lk=G=>Math.max(sk(G),...bk(G));
const dd=id=>P[id]?.d?dk(P[id].dr||String(P[id].d)):99999999;
// a union still standing at a date: not divorced by then, and neither partner
// had begun another union (married or with a child) after this one's last
// child and before that date. Many couples have no marriage record, so a
// passing union shows only by what came after it. Undated unions stand.
const heldTo=(G,w)=>!(G.dv&&dk(String(G.dv))<=w)&&!(sk(G)<99999999&&[G.h,G.w].some(x=>x&&fams(x).some(H=>H!==G&&sk(H)>lk(G)&&sk(H)<w)));
// what a person was called: a starred name in brackets (a nickname, "(Betty*)"),
// else the starred given names, else all given names; other brackets are spellings
const given=id=>{const p=P[id];if(!p)return '';const nick=/\(([^)]*\*)\)/.exec(p.nm);if(nick)return nick[1].replace(/\*/g,'');
 const w=p.nm.replace(/\s*\([^)]*\)/g,'').split(' '),g=w.length>1?w.slice(0,-1):w,st=g.filter(x=>x.endsWith('*'));
 return (st.length?st:g).join(' ').replace(/\*/g,'')};
const other=(G,x)=>G.h===x?G.w:G.h;
const exact=s=>/^\d{4}-\d{2}-\d{2}$/.test(s);
// age at a date: exact from two full dates, else ~ from the years
function ageAt(p,raw){if(!p||!p.b||!raw)return '';const e=fmtDate(String(raw)).split('–')[0],b=fmtDate(p.br||'');
 if(exact(e)&&exact(b)){const [y1,m1,d1]=b.split('-').map(Number),[y2,m2,d2]=e.split('-').map(Number);return String(y2-y1-((m2<m1||(m2===m1&&d2<d1))?1:0))}
 const y=yr(String(raw));return y<9999&&y>=p.b?'~'+(y-p.b):''}
// a union described: when it began, the ages then, how it ended
// with no dated marriage, a union says when its children came; how long it
// lasted only while it stood (heldTo)
function union(G,x){const o=other(G,x),a=P[x],b=P[o],t=[];
 if(G.m){t.push('married '+fmtDate(G.mr||String(G.m)));const ag=[ageAt(a,G.mr||G.m),ageAt(b,G.mr||G.m)];if(ag[0]&&ag[1])t.push(`ages ${ag[0]} and ${ag[1]}`)}
 else{if(G.mr)t.push('married, year unknown');const ys=G.c.map(c=>P[c]?.b).filter(Boolean),fb=Math.min(...ys),lb=Math.max(...ys);if(ys.length)t.push(lb>fb?`children ${fb}–${lb}`:(ys.length>1?'children ':'first child ')+fb)}
 let end=null,why='';if(G.dv){end=G.dv;why='divorce'}else{const ds=[[x,dd(x)],[o,dd(o)]].filter(d=>d[0]&&P[d[0]]?.d).sort((p,q)=>p[1]-q[1]);if(ds.length&&heldTo(G,ds[0][1])){end=P[ds[0][0]].d;why=`${given(ds[0][0])}'s death`}}
 const st=G.m??Math.min(9999,...G.c.map(c=>P[c]?.b??9999));
 if(end&&(G.dv||st<9999))t.push(st<9999&&end>st?`${end-st} years, until ${why} ${end}`:`until ${why} ${end}`);return t.join(' · ')}
// a child born after a parent's death belongs, most likely, with another union
function flag(c,G){const p=P[c];if(!p||!p.b||!G)return '';const mo=P[G.w],fa=P[G.h],f=[];
 if(mo?.d&&p.b>mo.d)f.push(`born after ${given(G.w)}'s death (${mo.d})`);if(fa?.d&&p.b>fa.d+1)f.push(`born after ${given(G.h)}'s death (${fa.d})`);
 return f.length?` <span class="warn" title="${esc(f.join('; '))}">⚠</span>`:''}
// a family in the books' order: head, spouse, children by birth
function hh(G,head,title,showHead){const sp=other(G,head);
 const lv=G.c.filter(c=>P[c]?.b&&NOW-P[c].b<100),u=[union(G,head),lv.length?`${G.c.filter(c=>aliveAt(c,99999999)).length} of ${G.c.length} children living`:''].filter(Boolean).join(' · ');return (title?`<div class="hht">${esc(title)}</div>`:'')+(u?`<div class="uni">${esc(u)}</div>`:'')+(showHead?row(head,'head',0,'',null,G):'')+row(sp,showHead?'spouse':'partner',0,'not in tree',null,G)+[...G.c].sort(byB).map(x=>row(x,'child',0,'',G)).join('')}
// how the focus is related to the proband: the cheapest path through the
// tree, up to parents and down to children, where a step through a marriage
// costs as much as a hundred blood steps (so blood wins) and a path never
// climbs again after going down (a child's other parent is a spouse step)
const REL=(()=>{const dist=new Map(),prev=new Map(),B=[];
 const push=(k,c,from)=>{if(dist.has(k)&&dist.get(k)<=c)return;dist.set(k,c);prev.set(k,from);(B[c]=B[c]||[]).push(k)};
 push(D.root+'|0',0,null);
 for(let c=0;c<B.length;c++)for(const k of B[c]||[]){if(dist.get(k)!==c)continue;const i=k.lastIndexOf('|'),x=k.slice(0,i);
  if(k.endsWith('|0')){const F=asChild[x];if(F){if(F.h)push(F.h+'|0',c+1,[k,'F']);if(F.w)push(F.w+'|0',c+1,[k,'M'])}}
  for(const G of asSpouse[x]||[]){for(const ch of G.c)push(ch+'|1',c+1,[k,'c']);const o=other(G,x);if(o)push(o+'|0',c+100,[k,'s',G])}}
 return {dist,prev}})();
// the path root → id as [[person, step, family]], or null
function relPath(id){const ks=[id+'|0',id+'|1'].filter(k=>REL.dist.has(k)).sort((a,b)=>REL.dist.get(a)-REL.dist.get(b));if(!ks.length)return null;
 const out=[];for(let k=ks[0];k;){const pv=REL.prev.get(k);out.push([k.slice(0,k.lastIndexOf('|')),pv?.[1],pv?.[2]]);k=pv?.[0]}return out.reverse()}
const gr=n=>n<1?'':n===1?'great-':`${n}× great-`;
const ORD=['','','2nd','3rd'];const ord=n=>ORD[n]||n+'th';
const TIMES=['','once','twice','three times'];
// a blood relation from a steps up and b down, named for the one at the end
function term(a,b,e,s){const K=(m,f,x)=>kin(e,m,f,x);
 if(!b)return gr(a-2)+(a>1?'grand':'')+K('father','mother','parent');
 if(!a)return gr(b-2)+(b>1?'grand':'')+K('son','daughter','child');
 if(a===1&&b===1)return (asChild[s]===asChild[e]?'':'half-')+K('brother','sister','sibling');
 if(b===1)return gr(a-2)+K('uncle','aunt','uncle or aunt');
 if(a===1)return gr(b-2)+K('nephew','niece','nephew or niece');
 const d=Math.min(a,b)-1,r=Math.abs(a-b);return `${d>1?ord(d)+' ':''}cousin${r?' '+(TIMES[r]||r+' times')+' removed':''}`}
function relLine(f){if(f===D.root)return '';const path=relPath(f),R=P[D.root];
 const lk=id=>`<span class="lk" data-id="${esc(id)}">${nm(P[id].nm)}</span>`;
 if(!path)return `<span class="meta">Not connected to ${esc(given(D.root))} in the tree ·</span> ${lk(D.root)}`;
 // segments of blood steps between marriages
 const words=[],crumbs=[D.root];let s=D.root,a=0,b=0,top=null,code='',anc=null,first=true;
 const close=end=>{if(a||b){words.push(term(a,b,end,s));if(a&&b)crumbs.push(top)}if(end!==crumbs[crumbs.length-1])crumbs.push(end)};
 for(let i=1;i<path.length;i++){const [x,t,G]=path[i],y=path[i-1][0];
  if(t==='s'){close(y);words.push(wed(G)?kin(x,'husband','wife','spouse'):'partner');crumbs.push(x);s=x;a=b=0;first=false;continue}
  if(t==='c')b++;else{a++;top=x;if(first){code+=t;anc=x}}}
 close(path[path.length-1][0]);
 let ph=`${esc(given(D.root))}'s ${words[0]}`;for(let i=1;i<words.length;i++)ph=`${words[i]} of ${i>1?'the ':''}${ph}`;
 const cr=[...new Set(crumbs)].map(x=>lk(x)+(x===anc?` <span class="code meta">${esc(code)}</span>`:'')).join('<span class="sep">›</span>');
 return `<b>${ph}</b><span class="sep">·</span>${cr}`}
// a lifeline on the page's shared scale (LL): birth to death; living
// (born under 100 years ago) runs to now; no recorded end fades out over
// seventy years; U's marriage as a tick on its partners' rows
let LL=null;
function life(id,U){if(!LL)return '<span class="ll"></span>';const p=P[id],W=LL.hi-LL.lo||1,x=y=>Math.max(0,Math.min(100,(y-LL.lo)/W*100));
 let h='';for(let y=Math.ceil(LL.lo/50)*50;y<=LL.hi;y+=50)h+=`<i class="gl" style="left:${x(y)}%"></i>`;let t='';
 if(p?.b){const live=!p.d&&NOW-p.b<100,open=!p.d&&!live,e=p.d??(live?NOW:p.b+70),c=p.codes[0]?BR(p.codes[0]):'var(--mut)';
  h+=`<i class="bar" style="left:${x(p.b)}%;width:${x(e)-x(p.b)}%;background:${open?`linear-gradient(to right,${c},transparent)`:c}"></i>`;
  t=`${p.b}–${p.d??(live?'':'?')}${p.d?' ('+(p.d-p.b)+' years)':''}`}
 if(U&&(U.h===id||U.w===id)&&U.m){h+=`<i class="mk" style="left:${x(U.m)}%"></i>`;t+=` · married ${U.m}`}
 return `<span class="ll" title="${esc(t)}">${h}</span>`}
// the scale: everyone in the households shown, to the decade
function lifeScale(f){const ids=[f,...par(f)];for(const x of par(f))if(x)for(const G of fams(x))ids.push(G.h,G.w,...G.c);for(const G of fams(f))ids.push(G.h,G.w,...G.c);
 const ps=ids.map(x=>P[x]).filter(p=>p?.b);if(!ps.length)return null;
 const lo=Math.min(...ps.map(p=>p.b)),hi=Math.max(...ps.map(p=>p.d??Math.min(NOW,p.b+70)));return {lo:Math.floor(lo/10)*10,hi:Math.ceil(hi/10)*10}}
const par=id=>{const F=asChild[id];return F?[F.h,F.w]:[null,null]};
function render(){const h=new URLSearchParams(location.hash.slice(1));let f=h.get('p');if(!P[f])f=D.root;focus=f;const p=P[f];
 document.title=`Family · ${p.nm}`;
 let gen=[[f]],cols='';for(let g=1;g<4;g++)gen.push(gen[g-1].flatMap(x=>x?par(x):[null,null]));
 for(let g=0;g<4;g++){const n=gen[g].length;cols+=`<div class="col g${g}" style="grid-template-rows:repeat(${n},1fr)">`+gen[g].map((x,i)=>{
   const kid=gen[g-1]?.[i>>1];return x?box(x,'',g?'':'focus'):(g&&kid?box(null,i%2?'mother not in tree':'father not in tree'):'<div></div>')}).join('')+'</div>'}
 document.getElementById('ped').innerHTML=cols;document.getElementById('rel').innerHTML=relLine(f);
 LL=lifeScale(f);const F=asChild[f];let a='',b='';
 if(F){const fa=F.h,mo=F.w,head=fa||mo;
  a+=`<div class="hh">${hh(F,head,[given(fa),given(mo)].filter(Boolean).join(' and '),true)}</div>`;
  for(const [x,who] of [[fa,'Father'],[mo,'Mother']])if(x)for(const G of fams(x))if(G!==F){const o=other(G,x);
   a+=`<details class="hh"><summary>${who} with ${esc(o?given(o):'a partner not in tree')}${G.m?' · married '+G.m:''} (${G.c.length} child${G.c.length===1?'':'ren'})</summary>${hh(G,x,'',false)}</details>`}}
 const own=fams(f);for(const G of own){const o=other(G,f);b+=`<div class="hh">${hh(G,f,o?'With '+given(o):'Partner not in tree',false)}</div>`}
 document.getElementById('fam').innerHTML=(a?`<div><h2>Parents and siblings</h2>${a}</div>`:'')+(b?`<div><h2>Partners and children</h2>${b}</div>`:'');
 document.getElementById('title').innerHTML=`<b>${nm(p.nm)}</b> <span class="meta">${esc(yrs(p))}${p.codes.length?' · '+esc(p.codes.join(' ')):''}${counts(p)?' · '+esc(counts(p)):''}</span>`;
 const g=new URLSearchParams({person:f,lines:'1',kin:'all'}).toString().replace(/%3A/g,':');
 document.getElementById('links').innerHTML=`<a href="geography.html#${g}">on the map</a><a href="archives.html#${enc(new URLSearchParams({person:f,kin:'all'}))}">in the archives</a>`}
__DATEJS__
const TAG={BIRT:'birth',CHR:'baptism',BAPM:'baptism',DEAT:'death',BURI:'burial',MARR:'marriage',RESI:'residence',OCCU:'occupation',EMIG:'emigration',IMMI:'immigration',CENS:'census',CONF:'confirmation',EDUC:'education',EVEN:'event'};
// a sortable day number: full dates exactly, a year or month at its start
const dk=d=>{const m=/(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?/.exec(fmtDate(String(d||'')));return m?+(m[1]+(m[2]||'00')+(m[3]||'00')):99999999};
// the last day a date can mean: a year to its 31 December, a month to its end
const endK=d=>{const k=dk(d);return k%100?k:k%10000?k+99:k+1299};
const yr=d=>{const m=/\d{4}/.exec(d||'');return m?+m[0]:9999};
// a place link carries the focus (this person's points in that parish);
// the plain link beside it drops it (the whole parish), shown on hover
const enc=h=>h.toString().replace(/%3A/g,':');
function placeLink(pl,par){const where=par?{parish:par}:{q:pl.split(',')[0].trim()},name=par?`${par} parish`:pl.split(',')[0].trim();
 const ctx=enc(new URLSearchParams({person:focus,lines:'1',kin:'all',...where})),all=enc(new URLSearchParams({kin:'all',...where}));
 return `<a class="pl" href="geography.html#${ctx}" title="On the map: ${esc(given(focus))} in ${esc(name)}">${esc(pl)}</a>`+
  ` <a class="plain" href="geography.html#${all}" title="On the map: everyone in ${esc(name)}">all in ${esc(name)}</a>`}
// life events: the person's own, then derived ones (computed from the family,
// no source of their own, drawn lighter), kept within the person's lifetime
const kin=(id,m,f,x)=>P[id]?.sex==='M'?m:P[id]?.sex==='F'?f:x;
// alive at a year: born by then, and dead later, or no death recorded and
// born less than 100 years before (presumed living)
const NOW=new Date().getFullYear();
const aliveAt=(id,w)=>{const p=P[id];if(!p||!p.b||dk(p.br||String(p.b))>w)return false;return p.d?dk(p.dr||String(p.d))>w:NOW-p.b<100&&(w>=99999999||Math.floor(w/1e4)-p.b<100)};
const siblingsOf=f=>{const F=asChild[f];return F?F.c.filter(c=>c!==f&&P[c]):[]};
// a death notice: who the person leaves, or the partner they joined, and
// the children and grandchildren the tree knows of at that date
// (the marriage standing at death only: not a former spouse or partner)
function notice(f){const me=P[f];if(!me.d)return '';const out=[],end=dd(f),last=endK(me.dr||String(me.d));
 const cur=fams(f).filter(G=>heldTo(G,end)).pop(),o=cur&&other(cur,f);
 const role=G=>wed(G)?kin(other(G,f),'husband ','wife ','spouse '):'partner ';
 if(o&&P[o]){if(!P[o].d)out.push(wed(cur)?`married to ${given(o)}${cur.m?' since '+cur.m:''}`:'partner '+given(o));
  else out.push(dd(o)>end?'leaves '+role(cur)+given(o):`joined ${given(o)} (${P[o].d})`)}
 // and the marriages left behind: divorced or moved on, the other one still
// alive ("former"), or with no death recorded ("earlier": may have died first)
 const ex=fams(f).filter(G=>G!==cur&&wed(G)&&P[other(G,f)]&&!(P[other(G,f)].d&&dd(other(G,f))<=end)).map(G=>(G.dv||P[other(G,f)].d?'former ':'earlier ')+role(G)+given(other(G,f)));
 if(ex.length)out.push(ex.join(', '));
 // children, and by which union when there were several families
 const kids=fams(f).flatMap(G=>G.c).filter(c=>P[c]),pro=kin(f,'him','her','them');
 const by=fams(f).filter(G=>G.c.some(c=>P[c])).map(G=>{const n=G.c.filter(c=>P[c]).length,x=other(G,f);return `${n} with ${x&&P[x]?given(x):'a partner not in tree'}`});
 if(kids.length){const b=kids.filter(c=>P[c].d&&dd(c)<end).length;out.push(`${kids.length} child${kids.length>1?'ren':''}${by.length>1?` (${by.join(', ')})`:''}${b?`, ${b} died before ${pro}`:''}`)}
 const gr=kids.flatMap(kidsOf).filter(g=>P[g]?.b&&dk(P[g].br||String(P[g].b))<=last).length;if(gr)out.push(`${gr} grandchild${gr>1?'ren':''}`);
 const sb=siblingsOf(f);if(sb.length){const k=sb.filter(x=>aliveAt(x,dk(me.dr||String(me.d)))).length;out.push(k?`survived by ${k} of ${sb.length} sibling${sb.length>1?'s':''}`:`the last of ${sb.length+1} siblings`)}
 return out.join(' · ')}
function sections(f){const me=P[f],ex=[];
 // within the lifetime: from the birth year (a father who died before the
 // birth still shows), to the death day as precisely as both dates allow
 const dw=(raw)=>{const y=yr(raw);return y<9999&&(!me.b||y>=me.b)&&(me.d?dk(raw)<=endK(me.dr||String(me.d)):!me.b||y<=me.b+110)};
 // derived facts name people by what they were called, without surnames
 const add=(t,raw,id,extra,der=true)=>{if(raw&&(!der||dw(raw)))ex.push([t,raw,'',given(id),id,'',der,extra||''])};
 const aged=id=>{const a=ageAt(P[id],P[id]?.dr);return a?'aged '+a:''};
 for(const x of par(f))if(x)add(kin(x,'father died','mother died','parent died'),P[x].dr,x);
 const F=asChild[f],sibs=new Set();if(F)F.c.forEach(c=>c!==f&&sibs.add(c));
 for(const x of par(f))if(x)for(const G of fams(x))if(G!==F)G.c.forEach(c=>sibs.add(c));
 const full=new Set(F?F.c:[]);
 for(const s of sibs){let x=aged(s);if(full.has(s)&&P[s]?.d){const w=dk(P[s].dr||String(P[s].d)),left=[...full].filter(c=>c!==s&&aliveAt(c,w)).length;const fu=sibs.size>=full.size?'full ':'';x=[x,left===1&&aliveAt(f,w)?`the last ${fu}sibling left`:`${left} of ${full.size}${fu?" full siblings":""} left`].filter(Boolean).join(' · ')}
  add(full.has(s)?kin(s,'brother died','sister died','sibling died'):kin(s,'half-brother died','half-sister died','half-sibling died'),P[s]?.dr,s,x)}
 const nieces=[...sibs].flatMap(kidsOf).filter(c=>P[c]?.b).sort(byB);
 const before=nieces.filter(c=>me.b&&dk(P[c].br||String(P[c].b))<dk(me.br||String(me.b)));
 if(before.length)ex.push([kin(f,'born an uncle','born an aunt','born an uncle or aunt'),me.br||String(me.b),'','',null,'',true,`${before.length} nephew${before.length>1?'s and nieces':' or niece'} already · ${nieces.length} in all`]);
 else if(nieces[0])add(kin(nieces[0],'first nephew','first niece','first nephew or niece'),P[nieces[0]].br||String(P[nieces[0]].b),nieces[0],nieces.length>1?`${nieces.length} in all`:'');
 const grand=[];
 for(const G of fams(f)){const o=other(G,f);if(G.m||G.mr)ex.push(['MARR',G.mr||String(G.m),'',o?'with '+P[o].nm:'',o,'',false,'']);
  for(const c of G.c){if(P[c]?.b)add(kin(c,'son born','daughter born','child born'),P[c].br||String(P[c].b),c);
   for(const H of fams(c)){const sp=other(H,c);if(sp&&(H.m||H.mr))add(kin(c,'gained a daughter-in-law','gained a son-in-law','child married'),H.mr||String(H.m),sp,'married '+given(c));
    H.c.forEach(g=>P[g]?.b&&grand.push(g))}
   add(kin(c,'son died','daughter died','child died'),P[c]?.dr,c,aged(c))}
  // a former spouse is named so; an unmarried partner who was left is named
  // only after a lasting union (two children or more), not a passing one
  if(o&&P[o]?.d){const w=dd(o),h=heldTo(G,w);
   if(wed(G))add(h?kin(o,'husband died','wife died','spouse died'):kin(o,'former husband died','former wife died','former spouse died'),P[o].dr,o);
   else if(h||G.c.length>1)add(h?'partner died':'former partner died',P[o].dr,o)}}
 grand.sort(byB);if(grand[0])add('first grandchild',P[grand[0]].br||String(P[grand[0]].b),grand[0],grand.length>1?`${grand.length} in all`:'');
 const L=[...(D.life[f]||[]),...ex].map((e,i)=>[e,i]).sort((a,b)=>dk(a[0][1])-dk(b[0][1])||a[1]-b[1]).map(x=>x[0]);
 document.getElementById('life').innerHTML=L.length?`<h2>Life events (${L.length})</h2><table>`+L.map(([t,d,pl,v,id,par,der,extra])=>(extra=t==='DEAT'?notice(f):extra,`<tr${der?' class="der" title="Derived from the family: no source of its own"':''}><td class="y">${esc(fmtDate(d))}</td><td class="y">${(a=>a&&!/^~?0$/.test(a)&&t!=='BIRT'?'age '+a:'')(ageAt(me,d))}</td><td class="ev">${esc(TAG[t]||t.toLowerCase())}</td><td>${[pl&&placeLink(pl,par),v&&(id?`<span class="lk" data-id="${esc(id)}">${nm(v)}</span>`:`<span class="meta">${esc(v)}</span>`),extra&&`<span class="${t==='DEAT'?'notice':'meta'}">${esc(extra)}</span>`].filter(Boolean).join(t==='DEAT'?'<br>':' · ')}</td></tr>`)).join('')+'</table>':'';
 const R=D.refs[f]||[],n=D.trees[f]||0;
 document.getElementById('refs').innerHTML=R.length||n?`<h2>References (${R.reduce((a,r)=>a+r[8],0)}) <a class="hl" href="archives.html#${enc(new URLSearchParams({person:f,kin:'all'}))}" title="In the archives: ${esc(given(f))}'s citations in every parish">in the archives</a></h2>`+(R.length?'<table>'+R.map(([ev,d,vol,y,pg,url,tier,par,k])=>
  `<tr><td class="y">${esc(y)}</td><td>${esc(vol)}${pg?' p. '+esc(pg):''}${k>1?` <span class="meta">×${k}</span>`:''}${url?` <a href="${esc(url)}" target="_blank" rel="noopener">↗</a>`:''}${par&&/\//.test(vol)?` <a class="plain" href="archives.html#${enc(new URLSearchParams({parish:par,q:vol.replace(par+' ',''),kin:'all'}))}" title="In the archives: everyone in ${esc(vol)}">everyone in this volume</a>`:''}</td><td class="meta">${ev==='person'?'':esc(ev+(d?' '+fmtDate(d):''))}</td></tr>`).join('')+'</table>':'')+
  (n?`<p class="meta">Also cited by ${n} other tree${n>1?'s':''} (MyHeritage matches, not sources).</p>`:''):''}
document.addEventListener('click',e=>{const t=e.target.closest('[data-tog]');if(t){const x=t.dataset.tog;OPEN.has(x)?OPEN.delete(x):OPEN.add(x);render();return}
 const el=e.target.closest('[data-id]');if(el&&!el.classList.contains('focus')){OPEN.clear();location.hash='p='+el.dataset.id;if(el.parentElement.id==='hits'){q.value='';HITS=[];showHits()}}});
// a search box, not a filter: every word must match (any order, accents and
// spelling variants ignored: geoview.name_fold); arrows move through the hits,
// Enter goes to the marked one, Escape or leaving clears
__FOLDJS__
const KEY=D.people.map(r=>fold(r[1]));
const q=document.getElementById('q'),hl=document.getElementById('hits');let HITS=[],AT=0;
function showHits(){hl.innerHTML=HITS.map((r,i)=>`<div data-id="${esc(r[0])}" class="${i===AT?'at':''}">${nm(r[1])} <span class="meta">${esc(yrs(P[r[0]]))}</span></div>`).join('');hl.querySelector('.at')?.scrollIntoView({block:'nearest'})}
q.addEventListener('input',()=>{const ws=fold(q.value).split(/\s+/).filter(Boolean);
 HITS=ws.join('').length<2?[]:D.people.filter((r,i)=>ws.every(w=>KEY[i].includes(w))).sort((a,b)=>(P[a[0]].b??9999)-(P[b[0]].b??9999)).slice(0,30);AT=0;showHits()});
q.addEventListener('keydown',e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){if(!HITS.length)return;e.preventDefault();AT=(AT+(e.key==='ArrowDown'?1:-1)+HITS.length)%HITS.length;showHits()}
 else if(e.key==='Enter'&&HITS[AT]){OPEN.clear();location.hash='p='+HITS[AT][0];q.value='';HITS=[];showHits();q.blur()}
 else if(e.key==='Escape'){q.value='';HITS=[];showHits();q.blur()}});
q.addEventListener('blur',()=>setTimeout(()=>{HITS=[];showHits()},150));
q.addEventListener('focus',()=>{if(q.value.trim())q.dispatchEvent(new Event('input'))});
const _r=render;render=function(){_r();sections(focus)};
window.addEventListener('hashchange',render);render();
</script>__DATA__</body></html>
"""
HTML = HTML.replace("__LINEAGE_DARK__", lineage.css_vars(dark=True)).replace("__LINEAGE__", lineage.css_vars())


def _main(argv):
    import config
    import tree_store
    cfg = config.load()
    store = tree_store.default_store()
    import csv
    vr = config.path(cfg, "volume_refs.csv")
    rows = list(csv.DictReader(open(vr, encoding="utf-8"))) if vr.exists() else []
    import errata
    data = collect(store.db, proband_id(cfg), rows, errata.load(config.path(cfg, "errata.toml"))["fix"])
    path = config.path(cfg, "family.html")
    write(path, data)
    print(f"{len(data['people'])} people, {len(data['fams'])} families -> {path}")


if __name__ == "__main__":
    _main(sys.argv[1:])
