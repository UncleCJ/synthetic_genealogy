"""
The Archives view (archives.html), written from the volume rows that
volumes.py builds: parishes, their volumes by series, every volume as a
page strip with the people cited on it, and the farms most cited. Private
(holds names). The rows and their columns: docs/records.md, "Views".
"""
from sg.common import lineage
from sg.views import viewkit


def write(rows, parishes, path, proband_label):
    """The Archives view (archives.html), one self-contained page, private
    (holds names; keep it in data/): parishes with their archive codes on a
    map and in a list, each parish's volumes by series, every volume as a
    page strip with the people cited on each page, and the farms most cited
    across volumes. A chosen parish zooms the map onto its farms and
    villages; a volume's "map" button shows its farms coloured by page, so
    the order the book walks through the parish can be seen. Linked both
    ways with the geography view."""
    keep = ["person", "label", "kin", "branch", "lineage", "event", "event_date",
            "event_place", "tier", "resourced", "parish", "archive_code", "volume",
            "series", "vol", "years", "page", "row", "farm", "plac_detail", "image_id", "image_no",
            "url", "source_title", "mh_volume", "conflict", "ra_code", "code_from", "series_name",
            "place_id", "place", "village", "place_from", "notes", "errata", "mh_id",
            "ra_years", "ra_note", "ra_viewer", "ra_images", "ra_nad", "ra_pages", "ra_image_count", "ra_status", "cited_as", "lat", "lon", "lv"]
    data = [{k: r.get(k, "") or "" for k in keep} for r in rows if r["tier"] != "tree"]
    page = viewkit.embed(HTML.replace("__NAV__", viewkit.nav("archives.html")).replace("__FOLDJS__", viewkit.FOLD_JS + viewkit.OFFLINE_JS),
                         dict(rows=data, parishes=parishes, proband=proband_label))
    path.write_text(page, encoding="utf-8")


HTML = r"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Archives</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#6b6760;--line:#e2ded6;--card:#fff;--sel:#fff1bf;--acc:#2f6db5;
__LINEAGE__;--anc:#111;--sp:#b9a76a;--un:#b8b4ac}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ece9e2;--mut:#9b968c;--line:#34312c;--card:#201f1c;--sel:#4a4220;--acc:#6ea4e6;
__LINEAGE_DARK__;--anc:#fff;--sp:#9c8d58;--un:#5d5a54}}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.45 system-ui,-apple-system,sans-serif;display:grid;grid-template-columns:300px 1fr;grid-template-rows:auto 1fr}
header{grid-column:1/-1;display:flex;gap:10px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:16px;margin:0 8px 0 0}h2{font-size:15px;margin:14px 0 6px}h3{font-size:13px;margin:0}
h4{font-size:13px;margin:16px 0 4px;color:var(--mut);border-bottom:1px solid var(--line);padding-bottom:2px}
input,select{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
aside{border-right:1px solid var(--line);padding:8px 10px;overflow:auto;min-height:0;display:flex;flex-direction:column;gap:6px}
#main{padding:8px 18px 24px;overflow:auto;min-height:0}
#map{height:240px;flex:none;border:1px solid var(--line);border-radius:6px}body.inparish #map{height:340px}
#mapnote{font-size:12px;color:var(--mut)}#mapnote .grad{display:inline-block;width:90px;height:8px;border-radius:2px;vertical-align:0;background:linear-gradient(90deg,hsl(220,70%,45%),hsl(120,70%,40%),hsl(20,80%,48%))}
.vol.on{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc)}
#pq{width:100%}
.par{padding:4px 6px;border-radius:4px;cursor:pointer;display:flex;justify-content:space-between;gap:8px}
.par:hover{background:var(--line)}.par.on{background:var(--sel)}
.par small,.meta{color:var(--mut)}.par .n{color:var(--mut);font-variant-numeric:tabular-nums}
.bar{display:flex;height:5px;border-radius:3px;overflow:hidden;margin-top:3px;width:120px}
.t-ra-full{background:#2a7d4f}.t-ra-link{background:#7fbf8f}.t-mh-record{background:#d49a2a}.t-mh-index{background:#e7cf8a}.t-plac-only{background:#bbb}.t-other{background:#ddd}
.legend{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:var(--mut)}
.legend span::before{content:"";display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;vertical-align:-1px;background:var(--c)}
.vol{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin:8px 0}
.vol .meta{font-size:12px;margin:2px 0}
.volno{font-family:ui-monospace,Menlo,monospace;background:var(--line);padding:0 4px;border-radius:4px}
svg text{fill:var(--fg);font-size:10px}
a.pay{opacity:.55}
.pages{width:100%;border-collapse:collapse;margin-top:4px}
.pages td{border-top:1px solid var(--line);padding:3px 6px;vertical-align:top}
.pages td:first-child{white-space:nowrap;color:var(--mut);width:70px}
.vol details summary{cursor:pointer;color:var(--mut);font-size:12px}
.who{display:inline-block;margin:0 8px 2px 0}.who a.fam{color:inherit;text-decoration:none}.who a.fam:hover{text-decoration:underline}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:0}
.k-ancestor,.k-self{font-weight:600}.k-unlinked{color:var(--mut)}
.tag{font-size:11px;padding:0 5px;border-radius:4px;border:1px solid var(--line);color:var(--mut);margin-left:4px;text-decoration:none}
.tag.note{border-color:var(--FM);color:var(--FM)}
a{color:inherit}a.btn{font-size:12px;font-weight:400;margin-left:6px;padding:1px 8px;border:1px solid var(--line);border-radius:5px;background:var(--card);text-decoration:none}
a.btn:hover{border-color:var(--mut)}
.sum{display:flex;gap:18px;flex-wrap:wrap;margin:6px 0 4px}.sum b{font-size:18px;display:block}
.farms{border-collapse:collapse}.farms td{padding:3px 8px;border-top:1px solid var(--line);vertical-align:top}.farms td.n{color:var(--mut);text-align:right}
@media(max-width:800px){body{grid-template-columns:1fr;grid-template-rows:auto auto 1fr}aside{max-height:45vh;border-right:0;border-bottom:1px solid var(--line)}}
</style></head><body>
<header>__NAV__<h1>Archives</h1>
<input id="q" placeholder="Filter: farm, person, volume…" size="28"><span id="pchip"></span>
<select id="kin"><option value="">all people</option><option value="family">relatives & ancestors</option><option value="ancestor">ancestors only</option></select>
<label><input type="checkbox" id="noplac" checked> hide uncited places</label>
<div class="legend" id="legend"></div></header>
<aside><div id="map"></div><div id="mapnote"></div>
<input id="pq" placeholder="filter parishes…">
<div class="legend"><span style="--c:#2a7d4f" title="Riksarkivet citation with archive, volume and page">RA full</span><span style="--c:#7fbf8f" title="only a Riksarkivet image link">RA link</span><span style="--c:#d49a2a" title="MyHeritage household-examination record">MH record</span><span style="--c:#e7cf8a" title="other MyHeritage record collections: no volume">MH index</span><span style="--c:#bbb" title="a place with no citation">place only</span></div>
<div id="plist"></div></aside>
<section id="main"></section>
<script type="text/plain" id="view-js">
const D=DATA;
const BR={FF:'var(--FF)',FM:'var(--FM)',MF:'var(--MF)',MM:'var(--MM)'};
const TIERS=['ra-full','ra-link','mh-record','mh-index','plac-only','other'];
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const enc=s=>encodeURIComponent(s).replace(/%2C/g,',').replace(/%3A/g,':');
const coll=new Intl.Collator('sv');
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
function color(r){if(r.kin==='self')return 'var(--anc)';if(r.kin==='unlinked')return 'var(--un)';
 if(r.kin==='spouse of relative')return 'var(--sp)';const b=(r.branch||'').split(' ')[0];return BR[b]||'var(--anc)'}
document.getElementById('legend').innerHTML=['FF','FM','MF','MM'].map(k=>`<span style="--c:var(--${k})">${k}</span>`).join('')+'<span style="--c:var(--sp)">spouse of relative</span><span style="--c:var(--un)">unlinked</span>';
// series in the order the books were kept, with plain names where Riksarkivet gives none
const SERIES=['A I','A II a','A II','B','B I','B II','C','C I','E','E I','F','F I'];
const SNAME={'A I':'Household examinations','A II a':'Parish books','A II':'Parish books','B':'Moving in and out','B I':'Moving in','B II':'Moving out',
 'C':'Births and baptisms','C I':'Births and baptisms','E':'Marriages','E I':'Marriages','F':'Deaths and burials','F I':'Deaths and burials'};
let cur=null;
const $=id=>document.getElementById(id);
let PERSON=null;   // person=<store id>: one person's citations (names are not identities)
function chip(){const r=PERSON&&D.rows.find(x=>x.mh_id===PERSON);$('pchip').innerHTML=PERSON?` <span class="tag" style="cursor:pointer" title="Show everyone again">${(r?r.label:PERSON).replace(/[&<>]/g,'')} ×</span>`:''}
// the search folds accents and spelling variants (viewkit.name_fold): Qvarnby = Kvarnby, Oscar = Oskar
__FOLDJS__
function filtered(){const q=fold($('q').value),k=$('kin').value,np=$('noplac').checked;
 return D.rows.filter(r=>(!PERSON||r.mh_id===PERSON)&&(!np||r.tier!=='plac-only')&&(!k||(k==='ancestor'?['ancestor','self'].includes(r.kin):['ancestor','self','relative'].includes(r.kin)))
  &&(!q||(r._k??=fold([r.farm,r.place,r.label,r.volume,r.event_place,r.parish,r.notes,r.ra_code].join(' '))).includes(q)))}
function byParish(rows){const by={};rows.forEach(r=>{if(r.parish)(by[r.parish]=by[r.parish]||[]).push(r)});return by}
function plist(by){const pq=$('pq').value.toLowerCase();
 const names=Object.keys(by).filter(n=>!pq||n.toLowerCase().includes(pq)||n===cur).sort((a,b)=>by[b].length-by[a].length||coll.compare(a,b));
 $('plist').innerHTML=names.map(n=>{const c={};by[n].forEach(r=>c[r.tier]=(c[r.tier]||0)+1);const tot=by[n].length;const p=D.parishes[n]||{};
  return `<div class="par ${n===cur?'on':''}" data-p="${esc(n)}"><div><b>${esc(n)}</b> <small>${esc(p.code||'')}</small>
  <div class="bar">${TIERS.filter(t=>c[t]).map(t=>`<div class="t-${t}" style="width:${100*c[t]/tot}%" title="${t}: ${c[t]}"></div>`).join('')}</div></div><span class="n">${tot}</span></div>`}).join('')||'<p class="meta">No parish matches.</p>'}
$('plist').addEventListener('click',e=>{const p=e.target.closest('.par');if(p)pick(p.dataset.p===cur?null:p.dataset.p)});
// map: one circle per parish, sized by its citations
const map=L.map('map',{zoomControl:false,attributionControl:false});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:15}).addTo(map);
if(location.protocol==='file:'){const c=L.control({position:'bottomleft'});c.onAdd=()=>{const d=L.DomUtil.create('div','meta');
 d.style.cssText='background:var(--card);padding:3px 8px;border-radius:6px';d.textContent='No map tiles when opened as a file: run python3 serve.py';return d};c.addTo(map)}
const dots=L.layerGroup().addTo(map);let FITKEY='',VOL=null;
// page position in a volume as a colour: first page blue, last red
const pageCol=f=>`hsl(${220-200*f},70%,${45-5*Math.sin(Math.PI*f)}%)`;
function drawMap(by){dots.clearLayers();const pts=[];const acc=css('--acc')||'#2f6db5';document.body.classList.toggle('inparish',!!cur);
 Object.entries(by).forEach(([n,rs])=>{const p=D.parishes[n];if(!p||p.lat==null)return;if(!cur)pts.push([p.lat,p.lon]);
  L.circleMarker([p.lat,p.lon],{radius:cur?(n===cur?6:3):3+Math.sqrt(rs.length)/1.5,weight:n===cur?2.5:1,color:n===cur?'#d49a2a':'#fff',fillColor:n===cur?'#d49a2a':acc,fillOpacity:cur&&n!==cur?.35:.75})
   .bindTooltip(`${esc(n)} · ${rs.length}`).on('click',()=>pick(n===cur?null:n)).addTo(dots)});
 let note='';
 if(cur){// the chosen parish's farms and villages; with a volume chosen, only its own, coloured by page
  const rs=(by[cur]||[]).filter(r=>!VOL||r.volume===VOL);const F={};let centre=0;
  rs.forEach(r=>{if(r.lat===''||r.lat==null){centre++;return}const k=r.place_id;(F[k]=F[k]||[]).push(r)});
  const mx=VOL?Math.max(1,...rs.map(r=>+r.page||0)):0;
  Object.values(F).sort((a,b)=>b.length-a.length).forEach(fr=>{const r0=fr[0];const pg=fr.map(r=>+r.page).filter(x=>x>0);
   const lo=pg.length?Math.min(...pg):null,hi=pg.length?Math.max(...pg):null;
   const fill=VOL?(lo!=null?pageCol(((lo+hi)/2)/mx):'#999'):acc;pts.push([r0.lat,r0.lon]);
   const vols=[...new Set(fr.map(r=>r.volume).filter(Boolean))];
   L.circleMarker([r0.lat,r0.lon],{radius:4+Math.sqrt(fr.length),weight:1,color:'#fff',fillColor:fill,fillOpacity:.9})
    .bindTooltip(`<b>${esc(r0.place||r0.farm)}</b> <span style="opacity:.7">(${esc(r0.lv)})</span><br>${fr.length} citation${fr.length===1?'':'s'}`+
     (VOL?(lo!=null?`, ${lo===hi?'p. '+lo:'pp. '+lo+'–'+hi}`:''):(vols.length?`<br>${vols.length} volume${vols.length===1?'':'s'}`:'')))
    .on('click',()=>{$('q').value=r0.place||r0.farm;VOL=null;go()}).addTo(dots)});
  if(!pts.length){const p=D.parishes[cur];if(p&&p.lat!=null)pts.push([p.lat,p.lon])}
  note=(VOL?`<b>${esc(VOL)}</b>: page <span class="grad"></span> first → last · <a href="#" id="novol">all volumes</a>`:`Farms and villages of ${esc(cur)}, sized by citations; click one to filter`)+
   (centre?`<br>${centre} without a point of their own (at the parish only)`:'')}
 $('mapnote').innerHTML=note;const nv=$('novol');if(nv)nv.onclick=e=>{e.preventDefault();VOL=null;go()};
 const key=cur+'|'+VOL+'|'+pts.map(String).join(';');
 if(key!==FITKEY&&pts.length){FITKEY=key;map.invalidateSize();map.fitBounds(pts,{padding:[18,18],maxZoom:cur?13:10})}}
function who(r){return `<span class="who k-${r.kin.replace(/ /g,'-')}" title="${esc(r.kin)} ${esc(r.lineage||r.branch)} · ${esc(r.event)} ${esc(r.event_date)} · ${esc(r.tier)}${r.resourced?' (re-sourced)':''}"><span class="dot" style="background:${color(r)}"></span>${r.mh_id?`<a class="fam" href="family.html#p=${esc(r.mh_id)}" title="family">${esc(r.label)}</a>`:esc(r.label)}${r.row?` <span class="tag">rad ${esc(r.row)}</span>`:''}${imglink(r)}${r.url?` <a class="${/riksarkivet\.se/.test(r.url)?'':'pay'}" href="${esc(r.url)}" target="_blank" rel="noopener" title="${/riksarkivet\.se/.test(r.url)?'Riksarkivet':/myheritage/i.test(r.url)?'MyHeritage (subscription)':/arkivdigital/i.test(r.url)?'Arkiv Digital (subscription)':'the citation\'s link'}">↗</a>`:''}${r.notes?` <span class="tag note" title="${esc(r.notes)}">note</span>`:''}${r.errata?` <span class="tag note" title="${esc(r.errata)}">corrected</span>`:''}</span>`}
const BILD=(id,n)=>`https://sok.riksarkivet.se/bildvisning/${id}_${String(n).padStart(5,'0')}`;
function span(r){const m=/^(\d+)-(\d+)(?: (\w+))?/.exec(r.ra_pages||'');return m?{a:+m[1],b:+m[2],unit:m[3]||'page'}:null}
// the image a page is likely on, from its place in the page span: a guess, shown with ≈
function guess(r){const s=span(r),n=+r.ra_image_count,p=+r.page;if(!s||!n||!r.ra_images||!(p>=s.a&&p<=s.b))return 0;
 return Math.min(n,Math.max(1,Math.round(1+(n-1)*(p-s.a)/Math.max(1,s.b-s.a))))}
function imglink(r){if(r.image_id&&r.image_no)return ` <a class="tag" href="${BILD(esc(r.image_id),r.image_no)}" target="_blank" rel="noopener">bild ${esc(r.image_no)}</a>`+OFF(esc(r.image_id),r.image_no);
 const g=guess(r);return g?` <a class="tag" href="${BILD(esc(r.ra_images),g)}" target="_blank" rel="noopener" title="estimated from the page's place in the volume (${esc(r.ra_pages)}, ${esc(r.ra_image_count)} images): look a few images either side">≈ bild ${g}</a>`+OFF(esc(r.ra_images),g):''}
// the page strip runs over the volume's page span where Riksarkivet's note gives
// it, else to the highest cited page (or the image count, when larger): an estimate
function strip(rows){const pg=rows.map(r=>+r.page).filter(x=>x>0);if(!pg.length)return '';const hi=Math.max(...pg),W=900,H=46;
 const ra=rows.find(r=>r.ra_status==='found')||{},s=span(ra),n=+ra.ra_image_count||0;
 const lo=s&&s.a<=Math.min(...pg)?s.a:1,mx=s&&s.b>=hi?s.b:Math.max(hi,n);
 const end=s&&s.b>=hi?`${mx}${s.unit==='page'?'':' ('+s.unit+')'}`:n>hi?`~${n} images`:`≥ ${hi} (highest cited)`;
 const farms={};rows.forEach(r=>{const fn=r.place||r.farm;if(+r.page>0&&fn){const f=farms[fn]=farms[fn]||[1e9,0];f[0]=Math.min(f[0],+r.page);f[1]=Math.max(f[1],+r.page)}});
 const x=p=>8+(W-16)*(p-lo)/Math.max(1,mx-lo);
 return `<svg viewBox="0 0 ${W} ${H+14*Object.keys(farms).length}" width="100%"><line x1="8" x2="${W-8}" y1="20" y2="20" stroke="var(--line)" stroke-width="6"/>
 ${rows.filter(r=>+r.page>0).map(r=>`<line x1="${x(+r.page)}" x2="${x(+r.page)}" y1="10" y2="30" stroke="${color(r)}" stroke-width="2"><title>p. ${esc(r.page)}: ${esc(r.label)} (${esc(r.place||r.farm)})</title></line>`).join('')}
 <text x="8" y="44">${lo}</text><text x="${W-8}" y="44" text-anchor="end">${esc(end)}</text>
 ${Object.entries(farms).sort((a,b)=>a[1][0]-b[1][0]).map(([f,[a,b]],i)=>`<rect x="${x(a)-2}" y="${50+14*i}" width="${Math.max(4,x(b)-x(a)+4)}" height="9" rx="2" fill="#7a8fa8" fill-opacity=".45"/><text x="${x(b)+6}" y="${58+14*i}">${esc(f)} ${a===b?'p. '+a:'pp. '+a+'–'+b}</text>`).join('')}</svg>`}
function volhead(v,rs,yrs){const r=rs.find(x=>x.ra_code)||rs[0];
 if(!r.series||v.startsWith('—'))return `<h3>${esc(v)}</h3>`;
 const ra=rs.find(x=>x.ra_status==='found');const ry=ra?ra.ra_years:'';
 const mhy=[...new Set(rs.filter(x=>x.tier==='mh-record'&&x.years).map(x=>x.years.replace('-','–')))];
 const conf=[...new Set(rs.map(x=>x.conflict).filter(Boolean))];const vn=[...new Set(rs.map(x=>x.notes).filter(Boolean))];
 return `<h3><span class="volno">${esc(r.series)}/${esc(r.vol)}</span> · ${esc(ry||yrs.replace('-','–'))}${cur?`<a class="btn" href="#" data-vol="${esc(v)}" title="Its farms on the map beside, coloured by page">map</a>`:''}<a class="btn" href="geography.html#q=${enc(v)}&layer=record&kin=all" target="geography">geography</a></h3>
 <div class="meta">${r.ra_code?(ra&&ra.ra_viewer?`<a href="${esc(ra.ra_viewer)}" target="_blank" rel="noopener">${esc(r.ra_code)}</a> (opens the volume at Riksarkivet; code from ${esc(r.code_from)})${OFF(esc(ra.ra_images||''))}`:esc(r.ra_code)+' · '+esc(r.ra_status||'not looked up'))+(ra&&ra.ra_nad?` · <a href="${esc(ra.ra_nad)}" target="_blank" rel="noopener" title="the volume's page in Riksarkivet's catalogue (NAD)">catalogue</a>`:'')+(ra&&(ra.ra_pages||ra.ra_image_count)?` · ${ra.ra_pages?(span(ra).unit==='page'?'pp. ':span(ra).unit+' ')+esc(ra.ra_pages.split(' ')[0].replace('-','–')):''}${ra.ra_pages&&ra.ra_image_count?', ':''}${ra.ra_image_count?esc(ra.ra_image_count)+' images':''}`:''):'archive code unknown: no tidied citation or unique Wikidata match for this parish'}
 ${ra&&ra.ra_note?`<br>Riksarkivet note: <i>${esc(ra.ra_note)}</i>`:''}
 ${mhy.length&&ry&&mhy.some(y=>y!==ry)?`<br>MyHeritage label years: ${esc(mhy.join(', '))}`:''}
 ${conf.length?`<br><b style="color:var(--FM)">Check: ${esc(conf.join('; '))}</b>`:''}${vn.length?`<br>Notes: ${esc(vn.join(' | '))}`:''}</div>`}
function volume(v,rs){const pages={};rs.forEach(r=>{const k=r.page||'';(pages[k]=pages[k]||[]).push(r)});
 const keys=Object.keys(pages).sort((a,b)=>(+a||1e9)-(+b||1e9));const yrs=(rs.find(r=>r.years)||{}).years||'';
 const fam=rs.filter(r=>['ancestor','relative','self'].includes(r.kin)).length;const people=new Set(rs.map(r=>r.person)).size;
 const table=`<table class="pages">${keys.map(k=>{const fs=[...new Set(pages[k].map(r=>r.place&&r.place!==r.farm?r.place+(r.farm?' ('+r.farm+')':''):r.farm).filter(Boolean))];const seen=new Set();
  return `<tr><td>${k?'p. '+esc(k):(pages[k][0].image_no?'img '+esc(pages[k][0].image_no):'')}</td><td>${fs.length?`<b>${esc(fs.join(' / '))}</b><br>`:''}${pages[k].filter(r=>{const s=r.person+r.event;if(seen.has(s))return false;seen.add(s);return true}).map(who).join('')}</td></tr>`}).join('')}</table>`;
 const open=keys.length<=12||$('q').value;
 return `<div class="vol${v===VOL?' on':''}">${volhead(v,rs,yrs)}<div class="meta">${rs.length} citation${rs.length===1?'':'s'} of ${people} ${people===1?'person':'people'}, ${fam} of the family</div>${strip(rs)}
 <details ${open?'open':''}><summary>${keys.length} page${keys.length===1?'':'s'}</summary>${table}</details></div>`}
function render(){const rows=filtered(),by=byParish(rows);plist(by);drawMap(by);const M=$('main');
 if(!cur&&!$('q').value){M.innerHTML=overview(rows,by);return}
 const sel=rows.filter(r=>!cur||r.parish===cur);
 const vols={};sel.forEach(r=>{const v=r.volume||(r.tier==='plac-only'?'— places without a citation':'— records without a volume');(vols[v]=vols[v]||[]).push(r)});
 const yr=v=>+((vols[v].find(r=>r.years)||{}).years||'9999').slice(0,4);
 const ser=v=>{const s=(vols[v][0]||{}).series||'';const i=SERIES.indexOf(s);return v.startsWith('—')?999:i<0?500:i};
 const order=Object.keys(vols).sort((a,b)=>ser(a)-ser(b)||coll.compare(vols[a][0].parish||'',vols[b][0].parish||'')||yr(a)-yr(b)||coll.compare(a,b));
 const p=D.parishes[cur]||{};let h='',last=null;
 if(cur)h+=`<h2>${esc(cur)}<a class="btn" href="geography.html#parish=${enc(cur)}&kin=all" target="geography">geography</a> <small class="meta" style="font-weight:400">${esc(p.code||'')} ${p.qid?`<a href="https://www.wikidata.org/wiki/${p.qid}" target="_blank" rel="noopener">${p.qid}</a> ${esc(p.label)}`:''} ${esc(p.harad||'')} ${p.status?'· '+esc(p.status):''}</small></h2>`;
 else h+=`<h2>Filtered: “${esc($('q').value)}”</h2>`;
 h+=`<p class="meta">${Object.keys(vols).filter(v=>!v.startsWith('—')).length} volumes, ${sel.length} citations.</p>`;
 order.forEach(v=>{const rs=vols[v];const s=v.startsWith('—')?'—':(rs[0].series||'');const g=cur?s:s+'|'+rs[0].parish;
  if(g!==last){last=g;h+=v.startsWith('—')?'<h4>Without a volume</h4>':`<h4>${cur?'':esc(rs[0].parish)+' · '}${esc(s)} · ${esc(rs[0].series_name||SNAME[s]||'')}</h4>`}
  h+=volume(v,rs)});
 M.innerHTML=h}
function overview(rows,by){const vols=new Set(rows.filter(r=>r.volume).map(r=>r.volume));const t={};rows.forEach(r=>t[r.tier]=(t[r.tier]||0)+1);
 const coded=Object.keys(by).filter(n=>(D.parishes[n]||{}).code).length;
 return `<div class="sum"><div><b>${Object.keys(by).length}</b>parishes (${coded} with an archive code)</div><div><b>${vols.size}</b>volumes cited</div><div><b>${rows.length}</b>citations and places</div>
 <div><b>${t['ra-full']||0}</b>tidy Riksarkivet citations</div></div>
 <p class="meta">Pick a parish on the map or in the list for its volumes by series, page by page. Filter by a farm, a person or a volume to see it across every parish.</p>`+farmsAll(rows)}
function farmsAll(rows){const F={};rows.forEach(r=>{const fn=r.place||r.farm;if(!fn||!r.parish||r.cited_as)return;const k=fn+'\u0000'+r.parish;(F[k]=F[k]||[]).push(r)});
 const ks=Object.keys(F).sort((a,b)=>F[b].length-F[a].length).slice(0,80);
 return `<h2>Farms and villages, most cited first</h2><table class="farms">${ks.map(k=>{const [fn,par]=k.split('\u0000');const vs={};F[k].forEach(r=>{const v=r.volume||'(no volume)';(vs[v]=vs[v]||new Set()).add(r.page)});
 const yr=v=>+((F[k].find(r=>(r.volume||'(no volume)')===v&&r.years)||{}).years||'9999').slice(0,4);
 return `<tr><td><b>${esc(fn)}</b>, <a href="#parish=${enc(par)}" data-p="${esc(par)}">${esc(par)}</a></td><td class="n">${F[k].length}</td><td>${Object.entries(vs).sort((a,b)=>yr(a[0])-yr(b[0])).map(([v,s])=>esc(v)+(([...s].filter(Boolean).length)?' p. '+[...s].filter(Boolean).sort((a,b)=>a-b).join(', '):'')).join('<br>')}</td></tr>`}).join('')}</table>`}
$('main').addEventListener('click',e=>{const a=e.target.closest('a[data-p]');if(a){e.preventDefault();pick(a.dataset.p);return}
 const b=e.target.closest('a[data-vol]');if(b){e.preventDefault();VOL=VOL===b.dataset.vol?null:b.dataset.vol;const y=$('main').scrollTop;go();$('main').scrollTop=y}});
function pick(p){cur=p;VOL=null;go();$('main').scrollTop=0}
function go(){render();hash()}
function hash(){const h=new URLSearchParams();const q=$('q').value,k=$('kin').value;
 if(PERSON)h.set('person',PERSON);if(cur)h.set('parish',cur);if(q)h.set('q',q);h.set('kin',k||'all');if(!$('noplac').checked)h.set('uncited','1');
 history.replaceState(null,'','#'+h.toString().replace(/%3A/g,':').replace(/%2C/g,','))}
['q','kin','noplac'].forEach(id=>$(id).oninput=go);$('pchip').onclick=()=>{PERSON=null;chip();go()};$('pq').oninput=()=>plist(byParish(filtered()));
// link scheme: archives.html#parish=Källeryd&q=Hagelstorp&kin=all (uncited=1 shows places without a citation;
// person=MH:I123 one person's citations)
// (an address with no filter opens on the ancestors; kin=all for everyone)
function readHash(){const h=new URLSearchParams(location.hash.slice(1));$('q').value=h.get('q')||'';PERSON=h.get('person');chip();
 const k=h.get('kin');$('kin').value=k?(k==='all'?'':k):(h.get('q')||h.get('parish')||PERSON?'':'ancestor');cur=h.get('parish')||null;$('noplac').checked=h.get('uncited')!=='1'}
window.addEventListener('hashchange',()=>{readHash();render()});
readHash();go();setTimeout(()=>{map.invalidateSize();FITKEY='';render()},0);
</script>__DATA__</body></html>
"""
HTML = HTML.replace("__LINEAGE_DARK__", lineage.css_vars(dark=True)).replace("__LINEAGE__", lineage.css_vars())
