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

Link scheme (after #): p=<store person id>, e.g. #p=MH:I1. Without it the
page opens on the proband.

Sketch: reads the store only (no GEDCOM), except to find the proband's
store id; match counts come from the rebuilt assertion tables.
"""
import json
import sys
from collections import defaultdict

import identity
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


def collect(db, root):
    """The lens's data from a store connection; root is the proband's store id."""
    people = {pid: dict(name=f"{g or ''} {s or ''}".strip() or "?", sex=sex or "")
              for pid, g, s, sex in db.execute("select id, given, surname, sex from person")}
    for pid, tag, date in db.execute("select owner, tag, date from event where tag in ('BIRT','DEAT')"):
        if pid in people:
            people[pid]["b" if tag == "BIRT" else "d"] = _span(date)[0]
    fams = {fid: dict(h=h, w=w, c=[]) for fid, h, w in db.execute("select id, husb, wife from family")}
    for fid, child in db.execute("select family, child from child order by rowid"):
        if fid in fams:
            fams[fid]["c"].append(child)
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
                    nev.get(pid, 0), ncit.get(pid, 0), dna, linked.get(pid, 0)])
    return dict(root=root, people=out,
                fams=[[fid, f["h"], f["w"], f["c"]] for fid, f in fams.items()])


def proband_id(cfg):
    import gedcom_io
    tree, proband = gedcom_io.load(cfg)
    x = tree.id(proband)
    return identity.mh_id(tree.people[x]["facts"]) or "MH:" + x.strip("@")


def write(path, data):
    import geoview
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    path.write_text(HTML.replace("__NAV__", geoview.nav("family.html")).replace("__DATA__", payload),
                    encoding="utf-8")


HTML = r"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Family</title>
<style>
:root{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#6b6760;--line:#e2ded6;--card:#fff;--sel:#fff1bf;--acc:#2f6db5;
--FF:#2f6db5;--FM:#c0522b;--MF:#2f8f5b;--MM:#8a4fb0}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ece9e2;--mut:#9b968c;--line:#34312c;--card:#201f1c;--sel:#4a4220;--acc:#6ea4e6;
--FF:#6ea4e6;--FM:#e8835c;--MF:#5fc38c;--MM:#b98ad8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,-apple-system,sans-serif}
header{display:flex;gap:10px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:16px;margin:0 8px 0 0}
input{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
main{padding:12px 16px;display:grid;gap:18px;grid-template-columns:minmax(0,1fr) 300px}
@media(max-width:900px){main{grid-template-columns:1fr}}
#ped{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:4px 14px;overflow-x:auto}
.col{display:grid;gap:4px}.col>*{align-self:center}
.p{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:6px;padding:4px 7px;cursor:pointer;min-height:44px;display:flex;flex-direction:column;justify-content:center}
.p:hover{border-color:var(--mut)}.p.focus{background:var(--sel);cursor:default}
.p.slot{border-style:dashed;color:var(--mut);cursor:default;background:transparent}
.p .nm u{text-decoration-thickness:1px;text-underline-offset:2px}.p .nm{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.p .yr,.p .meta{color:var(--mut);font-size:11px}
.code{font-family:ui-monospace,monospace;font-size:11px}
.n{font-variant-numeric:tabular-nums}
aside h2{font-size:13px;margin:12px 0 4px;color:var(--mut);font-weight:600}
aside .p{margin-bottom:4px}
.links a{color:var(--acc);margin-right:10px}
#hits{position:absolute;background:var(--card);border:1px solid var(--line);border-radius:6px;max-height:300px;overflow:auto;z-index:2}
#hits div{padding:3px 8px;cursor:pointer}#hits div:hover{background:var(--line)}
</style></head><body>
<header>__NAV__<h1>Family</h1>
<span style="position:relative"><input id="q" placeholder="Find a person…" size="26" autocomplete="off"><div id="hits"></div></span>
<span id="title"></span><span class="links" id="links"></span></header>
<main><section id="ped"></section><aside id="side"></aside></main>
<script>
const D=__DATA__;const P={};for(const r of D.people)P[r[0]]={id:r[0],nm:r[1],sex:r[2],b:r[3],d:r[4],codes:r[5],ev:r[6],cit:r[7],dna:r[8],lk:r[9]};
const asChild={},asSpouse={};for(const [f,h,w,c] of D.fams){const F={id:f,h,w,c};for(const x of c)if(!asChild[x])asChild[x]=F;for(const x of [h,w])if(x)(asSpouse[x]=asSpouse[x]||[]).push(F)}
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const nm=s=>esc(s).replace(/(\S+)\*/g,'<u>$1</u>');
const yrs=p=>p.b||p.d?`${p.b??''}–${p.d??''}`:'';
const BR=c=>c&&c.length>=2?`var(--${c.slice(0,2)})`:'var(--line)';
function box(id,slot,cls=''){const p=P[id];if(!p)return `<div class="p slot">${esc(slot||'unknown')}</div>`;
 const c=p.codes,code=c.length?`<span class="code">${esc(c.slice(0,3).join(' '))}${c.length>3?' …':''}</span> `:'';
 const m=[p.ev&&`${p.ev} events`,p.cit&&`${p.cit} citations`,p.dna&&`${p.dna} matches on path`,p.lk&&`${p.lk} linked kit${p.lk>1?'s':''}`].filter(Boolean).join(' · ');
 return `<div class="p ${cls}" data-id="${esc(id)}" style="border-left-color:${BR(c[0])}" title="${esc(m)}"><span class="nm">${nm(p.nm)}</span><span class="yr">${code}${esc(yrs(p))}</span>${cls.includes('focus')||!m?'':`<span class="meta n">${esc(m)}</span>`}</div>`}
const par=id=>{const F=asChild[id];return F?[F.h,F.w]:[null,null]};
function render(){const h=new URLSearchParams(location.hash.slice(1));let f=h.get('p');if(!P[f])f=D.root;const p=P[f];
 document.title=`Family · ${p.nm}`;
 // pedigree: generation g has 2^g slots
 let gen=[[f]],cols='';for(let g=1;g<4;g++)gen.push(gen[g-1].flatMap(x=>x?par(x):[null,null]));
 for(let g=0;g<4;g++){const n=gen[g].length;cols+=`<div class="col" style="grid-template-rows:repeat(${n},1fr)">`+gen[g].map((x,i)=>{
   const kid=gen[g-1]?.[i>>1];return x?box(x,'',g?'':'focus'):(g&&kid?box(null,i%2?'mother not in tree':'father not in tree'):'<div></div>')}).join('')+'</div>'}
 document.getElementById('ped').innerHTML=cols;
 // close family
 const F=asChild[f];let s='';
 const fp=box(f,'','focus');s+=`<h2>In focus</h2>${fp}<div class="meta n">${[p.ev&&p.ev+' events',p.cit&&p.cit+' citations',p.dna&&p.dna+' matches on path',p.lk&&p.lk+' linked kits'].filter(Boolean).join(' · ')}</div>`;
 if(F){const sib=F.c.filter(x=>x!==f);if(sib.length)s+=`<h2>Siblings (${sib.length})</h2>`+sib.map(x=>box(x)).join('')}
 const half=new Set();for(const x of par(f))if(x)for(const G of asSpouse[x]||[])if(G!==F)for(const c of G.c)half.add(c);
 if(half.size)s+=`<h2>Half-siblings (${half.size})</h2>`+[...half].map(x=>box(x)).join('');
 for(const G of asSpouse[f]||[]){const sp=G.h===f?G.w:G.h;s+=`<h2>Spouse${G.c.length?` and children (${G.c.length})`:''}</h2>`+box(sp,'spouse not in tree')+G.c.map(x=>box(x)).join('')}
 document.getElementById('side').innerHTML=s;
 document.getElementById('title').innerHTML=`<b>${nm(p.nm)}</b> <span class="meta">${esc(yrs(p))} ${p.codes.length?'· '+esc(p.codes.join(' ')):''}</span>`;
 const g=new URLSearchParams({person:f,lines:'1',kin:'all'}).toString().replace(/%3A/g,':');
 document.getElementById('links').innerHTML=`<a href="geography.html#${g}">on the map</a><a href="archives.html#${new URLSearchParams({q:p.nm,kin:'all'})}">in the archives</a>`}
document.addEventListener('click',e=>{const el=e.target.closest('[data-id]');if(el&&!el.classList.contains('focus')){location.hash='p='+el.dataset.id;document.getElementById('hits').innerHTML=''}});
const q=document.getElementById('q');q.addEventListener('input',()=>{const t=q.value.trim().toLowerCase();const hits=t.length<2?[]:D.people.filter(r=>r[1].toLowerCase().includes(t)).slice(0,30);
 document.getElementById('hits').innerHTML=hits.map(r=>`<div data-id="${esc(r[0])}">${nm(r[1])} <span class="meta">${esc(yrs(P[r[0]]))}</span></div>`).join('')});
window.addEventListener('hashchange',render);render();
</script></body></html>
"""


def _main(argv):
    import config
    import tree_store
    cfg = config.load()
    store = tree_store.default_store()
    data = collect(store.db, proband_id(cfg))
    path = config.path(cfg, "family.html")
    write(path, data)
    print(f"{len(data['people'])} people, {len(data['fams'])} families -> {path}")


if __name__ == "__main__":
    _main(sys.argv[1:])
