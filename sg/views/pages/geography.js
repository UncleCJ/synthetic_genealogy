const D=DATA;const T=D.tabs,P=D.people,R=D.rows;
// row fields
const RP=0,RT=1,RL=2,RY0=3,RY1=4,RD=5,RLAT=6,RLON=7,RLV=8,RNAME=9,RPAR=10,RPL=11,RDATE=12,RDET=13,RURL=14,RAGG=15,RN=16;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const BR={F:'var(--F)',M:'var(--M)',FF:'var(--FF)',FM:'var(--FM)',MF:'var(--MF)',MM:'var(--MM)'};
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
// a person row's name as drawn (NAME_JS)
const PN=p=>pname(p[1],p[9]||'');
const LABEL={person:v=>{const p=PBY[v];return p?plainName(p[1]):v}};
// parishes and surnames read alphabetically; the rest (people too) by count, most first
const ALPHA=new Set(['parish','surname']);
// facets of a person count people; those that split a person's events (and
// the person list itself) count events, and say so
const BYPERSON=new Set(['branch','kin','surname']);
// one family branch at a time (radio buttons); the others take several
const SINGLE=new Set(['branch']);
const SORTKEY={person:v=>{const p=PBY[v];return p?(p[2]+' '+plainName(p[1])):v}};
const EXTRA={person:v=>{const p=PBY[v];if(!p||!(p[6]||p[7]))return '';const [b,d]=[p[6],p[7]];
 return `<span class="yrs">${[b&&'✻ '+b,d&&'† '+d].filter(Boolean).join(' ')}</span>`}};
const coll=new Intl.Collator('sv');
// with no filter in the address, the view opens on the ancestors; kin=all lifts it
const DEFAULT={kin:['ancestor']};
let S={};const MULTI=FACETS.map(f=>f[0]);
function readHash(){S={};const h=new URLSearchParams(location.hash.slice(1));
 for(const [k,v] of h){S[k]=MULTI.includes(k)||k==='place'?(v==='all'?[]:v.split(',').filter(Boolean)):v}
 if(![...MULTI,'place','q','from','to','sel'].some(k=>k in S))Object.assign(S,structuredClone(DEFAULT))}
function writeHash(){const h=new URLSearchParams();for(const [k,v] of Object.entries(S)){if(k==='colorKey')continue;if(Array.isArray(v)?v.length:v!==undefined&&v!=='')h.set(k,Array.isArray(v)?v.join(','):v);else if(k in DEFAULT&&Array.isArray(v))h.set(k,'all')}
 history.replaceState(null,'','#'+tidy(h));const one=a=>a&&a.length===1?a[0]:'';
 navFocus({person:one(S.person),parish:one(S.parish),sel:S.sel,mark:S.mark,code:(String((one(S.person)&&P.find(p=>p[0]===one(S.person))||[])[5]||'').split(' ')[0])})}
function yearOK(r){const a=+S.from||null,b=+S.to||null;if(!a&&!b)return true;const y0=r[RY0]??r[RY1],y1=r[RY1]??r[RY0];if(y0==null)return false;
 return (!a||y1>=a)&&(!b||y0<=b)}
let MAPB=null;
// the address readable: commas, colons, slashes, @, | and ! as typed
const tidy=h=>h.toString().replace(/%2C/g,',').replace(/%3A/g,':').replace(/%2F/g,'/').replace(/%40/g,'@').replace(/%7C/g,'|').replace(/%21/g,'!');
// dates as written, shortened: ~ about, < before, > after, a–b between; days as 1850-03-12
__DATEJS__
// selection rules (shared/rules.js): sel= narrows to people, mark= highlights them
const ST=D.steps||[],EN=D.ends||[];
// a person's steps in path order (they come so from geoview.trails), by person index
const STEPS_OF={};ST.forEach((s,j)=>(STEPS_OF[R[s[0]][RP]]=STEPS_OF[R[s[0]][RP]]||[]).push(j));
const PIX=Object.fromEntries(P.map((p,i)=>[p[0],i]));
const RU=makeRules(P,R,T,{RP,RT,RY0,RY1,RPAR,RPL,RNAME},ST,EN);let SELR=null,MARKR=null,SEL=null,MARK=null,SELX=null,MARKX=null;
// SEL, MARK: people; SELX, MARKX: the steps or loose ends a step:/end: rule picks
function rules(){SELR=S.sel?RU.parse(S.sel):null;MARKR=S.mark?RU.parse(S.mark):null;
 const own=(r,x)=>x&&r.kind!=='person'?new Set([...x].map(i=>RU.owner(r.kind,i))):x;
 SELX=RU.pick(SELR);MARKX=RU.pick(MARKR);SEL=own(SELR,SELX);MARK=own(MARKR,MARKX);
 if(SELR&&SELR.kind==='person')SELX=null;if(MARKR&&MARKR.kind==='person')MARKX=null}
const marked=r=>!MARK||MARK.has(r[RP]);
function base(r,skip){
 if(SEL&&!SEL.has(r[RP]))return false;
 for(const [k,,fn] of FACETS){if(k===skip)continue;const sel=S[k];if(sel&&sel.length&&!sel.includes(fn(r)))return false}
 if(S.place&&S.place.length&&!S.place.includes(T.place[r[RPL]]))return false;
 if(skip!=='year'&&!yearOK(r))return false;
 if(S.q){const q=S.q.toLowerCase();const p=P[r[RP]];if(!(plainName(p[1])+' '+T.name[r[RNAME]]+' '+r[RDET]+' '+T.parish[r[RPAR]]+' '+p[0]).toLowerCase().includes(q))return false}
 if(skip!=='bbox'&&S.bbox==='1'&&MAPB&&!MAPB.contains([r[RLAT],r[RLON]]))return false;
 return true}
// facets UI
const OPEN=new Set(['kin','branch','person']);
const EXAMPLES=['born@Källeryd','lived@Hagelstorp,!died','line@FM,born:1800-1850','step:km>30','end:open,kin@ancestor'];
function ruleBox(){const msg=(r,set,x)=>r?(r.error?`<span class="err">${esc(r.error)}</span>`:x?`${x.size} ${r.kind==='step'?'step':'loose end'}${x.size===1?'':'s'}, ${set.size} ${set.size===1?'person':'people'}`:set?`${set.size} ${set.size===1?'person':'people'}`:''):'';
 return `<details open class="rules"><summary>People by rule</summary>
  <div class="rl"><label>select <input id="sel" value="${esc(S.sel||'')}" placeholder="born@Hagelstorp" title="Only these people (Enter applies)"></label><span class="meta">${msg(SELR,SEL,SELX)}</span></div>
  <div class="rl"><label>mark <input id="mark" value="${esc(S.mark||'')}" placeholder="line@FM" title="Highlight these people, the rest faded (Enter applies)"></label><span class="meta">${msg(MARKR,MARK,MARKX)}</span></div>
  <div class="meta">born, died, married, lived, at <b>@place</b> or <b>:1800-1850</b>; line@FMF, kin@ancestor, surname@…, name@…; commas join, ! negates, a|b either. <b>step:</b> km&gt;30, year:, from@, to@, approx; <b>end:</b> (no death recorded) year:, age&lt;40, at@, open, none, left. E.g. ${EXAMPLES.map(x=>`<a href="#sel=${esc(encodeURIComponent(x))}">${esc(x)}</a>`).join(' · ')}</div></details>`}
function facetsUI(){const side=document.getElementById('side');let h=ruleBox();
 // time
 const dec={};let n=0;R.forEach(r=>{if(!base(r,'year'))return;const y=r[RY0]??r[RY1];if(y==null)return;const d=Math.floor(y/10)*10;dec[d]=(dec[d]||0)+1});
 const dk=Object.keys(dec).map(Number);const ds=[];if(dk.length)for(let d=Math.min(...dk);d<=Math.max(...dk);d+=10)ds.push(d);
 const mx=Math.max(1,...Object.values(dec));
 h+=`<details open><summary>Time<span class="act" data-clear="year">${S.from||S.to?'clear':''}</span></summary>
 <div class="hist" title="Click a decade, or drag across several">${ds.map(d=>`<div data-dec="${d}" class="${S.from||S.to?(yearOK([0,0,0,d,d+9])?'in':''):'in'}" style="height:${100*(dec[d]||0)/mx}%" title="${d}s: ${dec[d]||0}"></div>`).join('')}</div>
 <div class="meta" style="display:flex;justify-content:space-between"><span>${ds[0]||''}</span><span>${ds.length?ds[ds.length-1]+9:''}</span></div>
 <div class="yr"><input id="from" placeholder="from" value="${esc(S.from||'')}"> – <input id="to" placeholder="to" value="${esc(S.to||'')}"></div></details>`;
 for(const [k,label,fn] of FACETS){let c={};const pp=BYPERSON.has(k);
  R.forEach(r=>{if(base(r,k)){const v=fn(r);if(pp)(c[v]=c[v]||new Set()).add(r[RP]);else c[v]=(c[v]||0)+1}});
  if(pp)c=Object.fromEntries(Object.entries(c).map(([v,x])=>[v,x.size]));
  const cnt=v=>pp?c[v]:`${c[v]} event${c[v]===1?'':'s'}`;
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
  <div class="${many?'flist':''}">${show.map(v=>`<div class="f ${sel.includes(v)?'on':''} ${c[v]?'':'zero'}" data-k="${k}" data-v="${esc(v)}"><span>${rb(v)}${sw(v)}${esc(LABEL[k]?LABEL[k](v):v)}${EXTRA[k]?EXTRA[k](v):''}${k==='person'&&sel.includes(v)?spouseActs(v,sel):''}</span><span class="n">${cnt(v)}</span></div>`).join('')}</div>
  ${keys.length>show.length?`<div class="meta">… ${keys.length-show.length} more; type to narrow</div>`:''}</details>`}
 const act=document.activeElement&&document.activeElement.id;const pos=document.activeElement&&document.activeElement.selectionStart;
 side.innerHTML=h;if(act&&(act.startsWith('fs-')||act==='sel'||act==='mark')){const e=document.getElementById(act);if(e){e.focus();e.setSelectionRange(pos,pos)}}fitLast()}
// the last facet (people) runs to the bottom of the sidebar when there is room
function fitLast(){const side=document.getElementById('side');const ls=side.querySelectorAll('details[open] .flist');const fl=ls[ls.length-1];
 if(!fl||fl.closest('details')!==side.lastElementChild)return;
 const top=fl.getBoundingClientRect().top-side.getBoundingClientRect().top+side.scrollTop;fl.style.maxHeight=Math.max(240,side.clientHeight-top-12)+'px'}
document.getElementById('side').addEventListener('toggle',fitLast,true);
const spousesOf=v=>{const p=PBY[v];return p?p[8].map(i=>P[i]):[]};
// a spouse joins the chosen people, the people filters widen to take them, paths on
// one spouse: "+ spouse"; several: one link each, by given name, to pick one
function spouseActs(v,sel){const sp=spousesOf(v).filter(s=>!sel.includes(s[0]));const swap=spousesOf(v).some(s=>sel.includes(s[0]));
 return sp.map(s=>`<span class="act" data-spouse="${esc(v)}" data-sid="${esc(s[0])}" title="${swap?'Show':'Add'} ${esc(plainName(s[1]))} and draw both paths">${swap?'→':'+'} ${sp.length===1&&spousesOf(v).length===1?'spouse':esc(callName(s[1]))}</span>`).join('')}
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
document.getElementById('side').addEventListener('change',e=>{if(['from','to','sel','mark'].includes(e.target.id)){S[e.target.id]=e.target.value.trim();if(!S[e.target.id])delete S[e.target.id];update(e.target.id==='sel')}});
// colours
function colorOf(v){if(S.colorKey==='person'){const i=(S.person||[]).indexOf(v);return i<0?'#999':PAL[i%PAL.length]}
 if(S.colorKey==='branch')return css(BR[v]||'var(--none)');const keys=S.colorKeys||[];const i=keys.indexOf(v);return PAL[i<0?PAL.length-1:Math.min(i,PAL.length-1)]}
// auto: by person when one to six are chosen, else by branch
function colorKey(){if(S.color)return S.color;const n=(S.person||[]).length;
 return n&&n<=6?'person':'branch'}
// by branch, an ancestor takes their own lineage shade (the family page's), others their branch's
const DARK=matchMedia('(prefers-color-scheme:dark)').matches;
const shade=p=>{const c=p[3]==='ancestor'?(p[5]||'').split(' ')[0]:'',x=(D.col||{})[c];return x?x[DARK?1:0]:css(BR[p[4]]||'var(--none)')};
function rowColor(r){const ck=S.colorKey;if(ck==='person'){const i=(S.person||[]).indexOf(P[r[RP]][0]);return i<0?'#999':PAL[i%PAL.length]}
 if(ck==='branch')return shade(P[r[RP]]);
 if(ck==='time'){const y=r[RY0]??r[RY1];if(y==null)return '#999';const t=Math.max(0,Math.min(1,(y-1700)/300));return `hsl(${220-200*t},65%,45%)`}
 const v=ck==='type'?T.t[r[RT]]:T.l[r[RL]];return colorOf(v)}
// map
const map=L.map('map',{preferCanvas:true});L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:17,attribution:'© OpenStreetMap'}).addTo(map);
// dated map layers under the events (maplayers.py; served by serve.py under maps/, optional):
// one image per layer, placed by three corners with an affine transform; hidden while zooming
map.createPane('hist').style.zIndex=250;let HOP=.7;
const Hist=L.Layer.extend({initialize(m){this.m=m},
 onAdd(mp){const i=this._i=L.DomUtil.create('img','',mp.getPane('hist'));i.src='maps/'+encodeURIComponent(this.m.img);
  i.style.cssText=`position:absolute;left:0;top:0;transform-origin:0 0;pointer-events:none;max-width:none;opacity:${HOP}`;i.onload=()=>this._put();
  mp.on('zoomend viewreset',this._put,this);mp.on('zoomstart',this._hide,this)},
 onRemove(mp){this._i.remove();mp.off('zoomend viewreset',this._put,this);mp.off('zoomstart',this._hide,this)},
 _hide(){this._i.style.visibility='hidden'},
 _put(){const i=this._i,w=i.naturalWidth,h=i.naturalHeight;if(!w)return;const p=k=>this._map.latLngToLayerPoint(this.m[k]),a=p('nw'),b=p('ne'),c=p('sw');
  i.style.transform=`matrix(${(b.x-a.x)/w},${(b.y-a.y)/w},${(c.x-a.x)/h},${(c.y-a.y)/h},${a.x},${a.y})`;i.style.visibility=''}});
fetch('maps/maps.json').then(r=>r.ok?r.json():null).then(ms=>{if(!ms||!ms.length)return;const o={},on=[];
 ms.forEach(m=>{const l=new Hist(m);o[`${esc(m.label)} <span class="meta">${m.year??''}</span>`]=l;on.push(l)});
 const c=L.control.layers(null,o,{position:'topright'}).addTo(map),d=L.DomUtil.create('label','',c.getContainer().querySelector('.leaflet-control-layers-list'));
 d.innerHTML='Opacity <input type="range" min="0" max="1" step="0.05">';const r=d.querySelector('input');r.value=HOP;
 r.addEventListener('input',()=>{HOP=+r.value;on.forEach(l=>l._i&&(l._i.style.opacity=HOP))})}).catch(()=>{});
// a cluster shows the colour mix of its points as a ring, the count inside
// a place's own name: its first part ("Hagelstorp, Källeryd, Småland, ..." -> Hagelstorp)
const short=r=>String(T.name[r[RNAME]]||'').split(',')[0].trim();
// what a cluster's points have in common, shown beside it: one place, else
// the place with the most events and how many more places
function common(ms){const c={};ms.forEach(m=>{const s=short(m._r)||T.parish[m._r[RPAR]];if(s)c[s]=(c[s]||0)+1});const ks=Object.keys(c).sort((a,b)=>c[b]-c[a]);
 if(ks.length<=1)return ks[0]||'';
 // many places on one parish point: farms with no point of their own
 const par=new Set(ms.map(m=>T.parish[m._r[RPAR]]));
 if(ks.length>3&&par.size===1&&ms.filter(m=>T.lv[m._r[RLV]]==='parish').length>=.9*ms.length)return `${[...par][0]} · parish centre: ${ms.length} events in ${ks.length} places`;
 return `${ks[0]} +${ks.length-1}`}
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
  (pls.length?` · <a href="#${tidy(h)}">only this place</a>`:'')+(pls.length===1?peopleHere(placeKey(rs[0])):'')+
  '<br>'+rs.slice(0,40).map(r=>`<span class="sw" style="background:${rowColor(r)}"></span>${esc(fmtDate(r[RDATE]))} · ${esc(T.t[r[RT]])} · ${PN(P[r[RP]])}${r[RDET]&&r[RDET]!==T.name[r[RNAME]]?` <span class="meta">${esc(r[RDET])}</span>`:''}`).join('<br>')+
  (rs.length>40?`<br><span class="meta">… ${rs.length-40} more in the table</span>`:'')}
// single points name their place once the map is close
map.on('zoomend',()=>document.getElementById('map').classList.toggle('close',map.getZoom()>=11));
const paths=L.layerGroup().addTo(map);
// what the map draws sits on the map: colour and paths
const Ctl=L.Control.extend({onAdd(){const d=L.DomUtil.create('div','ctl');
 d.innerHTML=`<label>Colour <select id="color"><option value="">auto</option><option value="branch">branch</option><option value="person">person</option><option value="type">event type</option><option value="layer">layer</option><option value="time">period</option></select></label>
 <button id="lines" title="Draw each selected person's life path: the places moved between, in order, numbered (one or two people)"><svg viewBox="0 0 16 16"><polyline points="2,13 6,6 10,10 14,3" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="2" cy="13" r="1.6" fill="currentColor"/><circle cx="14" cy="3" r="1.6" fill="currentColor"/></svg>paths</button>`;
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
 const keys=ck==='person'?(S.person||[]).filter(v=>c[v]):ck==='branch'?['F','M','FF','FM','MF','MM','none'].filter(v=>c[v]):Object.keys(c).sort((a,b)=>c[b]-c[a]);
 const shown=keys.slice(0,10),rest=keys.slice(10).reduce((n,v)=>n+c[v],0);
 const col=v=>ck==='person'?colorOf(v):ck==='branch'?css(BR[v]||'var(--none)'):colorOf(v);
 el.innerHTML=`<div><b>${{branch:'Family branch',person:'Person',type:'Event type',layer:'Layer'}[ck]}</b></div>`+shown.map(v=>`<div><span class="sw" style="background:${col(v)}"></span>${esc(ck==='person'?LABEL.person(v):v)}<span class="n">${c[v]}</span></div>`).join('')+
  (rest?`<div><span class="sw" style="background:${PAL[PAL.length-1]}"></span>other<span class="n">${rest}</span></div>`:'')}
const LKM={farm:.3,village:1,parent:2,parish:6,town:5,region:60,country:300};
// links that select the people with an event at a place (rules.js)
const placeKey=r=>{const k=T.place[r[RPL]]||'';return k.startsWith('parish:')?k.slice(7):k||T.parish[r[RPAR]]||''};
const peopleHere=k=>k?` · people <a href="#sel=${esc(encodeURIComponent('born@'+k))}">born</a> / <a href="#sel=${esc(encodeURIComponent('lived@'+k))}">living</a> / <a href="#sel=${esc(encodeURIComponent('at@'+k))}">with any event</a> here`:'';
function popup(r){const p=P[r[RP]];const sp=new URLSearchParams({person:p[0],lines:'1'});
 return `<b>${PN(p)}</b> <span class="meta">${esc(p[3])} ${esc(p[5]||p[4]||'')}</span><br>${esc(T.t[r[RT]])} · ${esc(fmtDate(r[RDATE]))}<br>${esc(T.name[r[RNAME]])}${T.parish[r[RPAR]]?', '+esc(T.parish[r[RPAR]]):''} <span class="meta">(${esc(T.lv[r[RLV]])})</span>`+
 (r[RDET]&&r[RDET]!==T.name[r[RNAME]]?`<br><span class="meta">${esc(r[RDET])}</span>`:'')+
 `<br><a href="#${sp.toString().replace(/%3A/g,':')}">this person's path</a> · <a href="family.html#p=${encodeURIComponent(p[0]).replace(/%3A/g,':')}">family</a>`+
 p[8].map(i=>` · <a href="#${new URLSearchParams({person:[p[0],P[i][0]].join(','),lines:'1'}).toString().replace(/%3A/g,':').replace(/%2C/g,',')}">with ${p[8].length===1?'spouse':esc(given(P[i]))}</a>`).join('')+
 (T.parish[r[RPAR]]?` · <a href="#parish=${encodeURIComponent(T.parish[r[RPAR]])}">all in ${esc(T.parish[r[RPAR]])}</a>`+
  ` · <a href="archives.html#${new URLSearchParams(Object.assign({parish:T.parish[r[RPAR]]},T.l[r[RL]]==='record'?{q:r[RDET].split(' p. ')[0]}:{},{kin:'all'})).toString()}" target="archives">${T.l[r[RL]]==='record'?'this volume':'archives'}</a>`:'')+
 (r[RURL]?` · <a href="${esc(r[RURL])}" target="_blank" rel="noopener">record ↗</a>`:'')+`<br>${peopleHere(placeKey(r)).slice(3)}`}
let FILT=[],ALL=[];const FADED='#c9c5bd';
function drawMap(fit){cluster.clearLayers();paths.clearLayers();
 const ms=ALL.map(r=>{const on=marked(r);const m=L.circleMarker([r[RLAT],r[RLON]],{radius:on&&MARK?7:6,weight:1,color:'#fff',fillColor:on?rowColor(r):FADED,fillOpacity:on?.9:.5});m.bindPopup(()=>popup(r));m._r=r;if(ALL.length<=4000)m.bindTooltip(short(r),{permanent:true,direction:'right',offset:[5,0],className:'plab'});return m});
 cluster.addLayers(ms);
 const sel=S.person||[];
 if(S.lines==='1'&&sel.length&&sel.length<=2){sel.forEach((pid,k)=>{const i=PIX[pid];const st=STEPS_OF[i]||[];if(!st.length)return;
   // the life path (lifepath.py): where it starts, then each step's destination
   const use=[R[ST[st[0]][0]],...st.map(j=>R[ST[j][1]])];const c=PAL[k%PAL.length];
   L.polyline(use.map(r=>[r[RLAT],r[RLON]]),{color:c,weight:3,opacity:.85}).addTo(paths);
   use.forEach(r=>L.circle([r[RLAT],r[RLON]],{radius:(LKM[T.lv[r[RLV]]]||5)*1000,color:c,weight:0,fillOpacity:.06,interactive:false}).addTo(paths));
   // the stops numbered in order; a stop lists the person's events at that point until the next step
   const mine=R.filter(r=>r[RP]===i);
   use.forEach((s,n)=>{const y0=s[RY0]??s[RY1],nx=use[n+1],y1=nx?(nx[RY0]??nx[RY1]):Infinity;
    const here=mine.filter(r=>r[RLAT]===s[RLAT]&&r[RLON]===s[RLON]&&((r[RY0]??r[RY1])==null||(r[RY0]??r[RY1])>=y0&&(r[RY0]??r[RY1])<=y1))
     .sort((a,b)=>(a[RY0]??a[RY1]??9999)-(b[RY0]??b[RY1]??9999));
    L.marker([s[RLAT],s[RLON]],{zIndexOffset:1000+n,icon:L.divIcon({className:'',iconSize:[20,20],
      html:`<div class="seq" style="background:${c};width:20px;height:20px">${n+1}</div>`})})
     .bindPopup(`<b>${PN(P[i])}</b> · stop ${n+1}${n?` · ${ST[st[n-1]][2]} km${ST[st[n-1]][3]?' (about)':''}`:''}<br>`+(here.length?here:[s]).map(r=>`${esc(fmtDate(r[RDATE]))} · ${esc(T.t[r[RT]])}: ${esc(T.name[r[RNAME]])}`).join('<br>')).addTo(paths)})})}
 trailsDraw();
 if(fit&&ALL.length){const b=L.latLngBounds(ALL.map(r=>[r[RLAT],r[RLON]]));map.fitBounds(b.pad(.1),{maxZoom:12})}}
// steps as lines from the earlier place to a dot at the later (dashed when an
// end is only a parish point); loose ends as open rings, ranked by how
// answerable: purple the person is cited in a later household volume already
// (the citation has no place or years: a fix), thick green their household
// is (a page to open), thin green a later volume exists, grey none in the
// inventory, blue left (emigrated, moved out), amber not known. Only those of
// people the filters keep.
const ENDC={cited:'#8a3fb8',household:'#1f7a48',open:'#6fb88f',none:'#8a857c','?':'#b08a1e',left:'#2f6db5'};
function trailsDraw(){const inView=new Set(ALL.map(r=>r[RP]));let n=0;
 for(const X of [SELX,MARKX]){if(!X)continue;const kind=X===SELX?SELR.kind:MARKR.kind;
  for(const i of X){if(n>4000)break;
   if(kind==='step'){const s=ST[i],a=R[s[0]],b=R[s[1]];if(!inView.has(a[RP]))continue;n++;const c=rowColor(b);
    const pop=()=>`<b>${PN(P[a[RP]])}</b> · ${s[2]} km${s[3]?' (about: a parish point)':''}<br>${esc(fmtDate(a[RDATE]))} ${esc(T.t[a[RT]])}: ${esc(T.name[a[RNAME]])}<br>→ ${esc(fmtDate(b[RDATE]))} ${esc(T.t[b[RT]])}: ${esc(T.name[b[RNAME]])}`;
    L.polyline([[a[RLAT],a[RLON]],[b[RLAT],b[RLON]]],{color:c,weight:2.5,opacity:.8,dashArray:s[3]?'5 5':null}).bindPopup(pop).addTo(paths);
    L.circleMarker([b[RLAT],b[RLON]],{radius:3.5,weight:0,fillColor:c,fillOpacity:1}).bindPopup(pop).addTo(paths)}
   else if(kind==='end'){const e=EN[i],r=R[e[0]];if(!inView.has(r[RP]))continue;n++;const st=e[3]?'left':e[7]||e[6];
    L.circleMarker([r[RLAT],r[RLON]],{radius:10,weight:e[7]?4:2,color:ENDC[st],fill:false}).bindPopup(()=>endPopup(e)).addTo(paths)}}}}
function endPopup(e){const r=R[e[0]],p=P[r[RP]];const par=T.parish[r[RPAR]];
 return `<b>${PN(p)}</b> <span class="meta">last seen</span><br>${esc(String(e[1]))}${e[2]!=null?`, aged about ${e[2]}`:''} · ${esc(T.t[r[RT]])}: ${esc(T.name[r[RNAME]])}`+
  (e[3]?`<br>${esc(e[3])}`:'')+
  (e[6]==='open'?`<br>${e[7]==='cited'?'cited in a later household volume, not on the path':e[7]==='household'?'household cited in':'next household volume'}: ${e[5]?`<a href="${esc(e[5])}" target="_blank" rel="noopener">${esc(e[4])} ↗</a>`:esc(e[4])}${e[8]?` ${esc(e[8])}`:''}`:e[6]==='none'?'<br>no later household volume in the inventory':e[3]?'':'<br>the parish archive is not in the inventory cache')+
  `<br><a href="#${tidy(new URLSearchParams({person:p[0],lines:'1'}))}">this person's path</a> · <a href="family.html#p=${encodeURIComponent(p[0]).replace(/%3A/g,':')}">family</a>`+
  (par?` · <a href="archives.html#${new URLSearchParams({parish:par,kin:'all'})}" target="archives">archives</a>`:'')}
// table
// the table's order lives in the address (sort=person, sort=-person), kept like the map view
function drawTable(){const SORT=(v=>v[0]==='-'?{k:v.slice(1),d:-1}:{k:v,d:1})(S.sort||'year');const cols=[['year','Years'],['person','Person'],['type','Event'],['place','Place'],['parish','Parish'],['level','Precision'],['det','Detail']];
 const val={year:r=>r[RY0]??r[RY1],person:r=>plainName(P[r[RP]][1]),type:r=>T.t[r[RT]],place:r=>T.name[r[RNAME]],parish:r=>T.parish[r[RPAR]],level:r=>T.lv[r[RLV]],det:r=>r[RDET]};
 // a missing value (no year, no place) stays last in either direction
 const no=v=>v==null||v==='';
 const rows=[...FILT].sort((a,b)=>{const x=val[SORT.k](a),y=val[SORT.k](b);return no(x)||no(y)?no(x)-no(y):(x>y?1:x<y?-1:0)*SORT.d}).slice(0,600);
 document.getElementById('tbl').innerHTML=`<tr>${cols.map(([k,l])=>`<th data-s="${k}">${l}${SORT.k===k?(SORT.d>0?' ▲':' ▼'):''}</th>`).join('')}</tr>`+
  rows.map((r,i)=>`<tr data-i="${R.indexOf(r)}"${marked(r)?'':' class="dim"'}><td>${esc(fmtDate(r[RDATE]))}</td><td><span class="sw" style="background:${rowColor(r)}"></span>${PN(P[r[RP]])}</td><td>${esc(T.t[r[RT]])}</td><td>${esc(T.name[r[RNAME]])}</td><td>${esc(T.parish[r[RPAR]])}</td><td>${esc(T.lv[r[RLV]])}</td><td class="wrap meta">${esc(r[RDET])}</td></tr>`).join('')+
  (FILT.length>600?`<tr><td colspan="7" class="meta">Showing 600 of ${FILT.length}; filter or sort to see others.</td></tr>`:'')}
document.getElementById('tbl').addEventListener('click',e=>{const th=e.target.closest('th');if(th){const k=th.dataset.s;S.sort=(S.sort||'year')===k?'-'+k:k;if(S.sort==='year')delete S.sort;writeHash();drawTable();return}
 const tr=e.target.closest('tr[data-i]');if(!tr)return;const r=R[+tr.dataset.i];map.setView([r[RLAT],r[RLON]],Math.max(map.getZoom(),12));
 let mk=null;cluster.eachLayer(m=>{if(m._r===r)mk=m});if(mk)cluster.zoomToShowLayer(mk,()=>mk.openPopup())});
// chips: active filters
function chips(){const out=[];for(const [k,label] of FACETS)(S[k]||[]).forEach(v=>out.push([k,v,`${label}: ${LABEL[k]?LABEL[k](v):v}`]));
 if(S.from||S.to)out.push(['year','',`${S.from||'…'}–${S.to||'…'}`]);(S.place||[]).forEach(v=>out.push(['place',v,`place: ${v}`]));if(S.q)out.push(['q','',`“${S.q}”`]);if(S.sel)out.push(['sel','',`select: ${S.sel}`]);if(S.mark)out.push(['mark','',`mark: ${S.mark}`]);
 document.getElementById('chips').innerHTML=out.map(([k,v,t])=>`<span class="chip" data-k="${esc(k)}" data-v="${esc(v)}" title="remove">${esc(t)} ×</span>`).join('')}
document.getElementById('chips').addEventListener('click',e=>{const c=e.target.closest('.chip');if(!c)return;const k=c.dataset.k,v=c.dataset.v;
 if(k==='year'){delete S.from;delete S.to}else if(k==='q'){delete S.q;document.getElementById('q').value=''}else if(k==='sel'||k==='mark'){delete S[k]}else{S[k]=(S[k]||[]).filter(x=>x!==v)}update()});
// glue
function update(fit,pan){rules();S.colorKey=colorKey();const ck=S.colorKey;
 ALL=R.filter(r=>base(r,'bbox'));FILT=S.bbox==='1'?ALL.filter(r=>base(r)):ALL;
 if(ck==='type'||ck==='layer'){const c={};FILT.forEach(r=>{const v=ck==='type'?T.t[r[RT]]:T.l[r[RL]];c[v]=(c[v]||0)+1});S.colorKeys=Object.keys(c).sort((a,b)=>c[b]-c[a])}
 const persons=new Set(FILT.map(r=>r[RP])).size;const nmark=MARK?new Set(FILT.filter(marked).map(r=>r[RP])).size:0;
 document.getElementById('count').textContent=(S.bbox==='1'?`${FILT.length} of ${ALL.length} point${ALL.length===1?'':'s'} in the map view`:`${FILT.length} point${FILT.length===1?'':'s'}`)+` · ${persons} ${persons===1?'person':'people'}`+(MARK?`, ${nmark} marked`:'');
 document.getElementById('lines').classList.toggle('on',S.lines==='1');
 const nsel=(S.person||[]).length;document.getElementById('lines').disabled=!nsel||nsel>2;document.getElementById('bbox').classList.toggle('on',S.bbox==='1');
 document.getElementById('color').value=S.color||'';
 const keep={...S};delete keep.colorKey;delete keep.colorKeys;const save=S;S=keep;writeHash();S=save;
 facetsUI();chips();if(!pan)drawMap(fit);drawTable();legend()}
document.getElementById('q').addEventListener('input',e=>{S.q=e.target.value;clearTimeout(window._qt);window._qt=setTimeout(()=>update(),250)});
document.getElementById('color').onchange=e=>{S.color=e.target.value;update()};
document.getElementById('lines').onclick=()=>{S.lines=S.lines==='1'?'':'1';update()};
document.getElementById('bbox').onclick=()=>{S.bbox=S.bbox==='1'?'':'1';update()};
document.getElementById('reset').onclick=()=>{S=Object.assign(structuredClone(DEFAULT),S.sort?{sort:S.sort}:{});document.getElementById('q').value='';update(true)};
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
