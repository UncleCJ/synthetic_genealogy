const D=DATA;const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
__NAMEJS__
// a task [person, name, kin, lineage, born, kind, year, age, event, place, parish, volume, viewer, page and who];
// an erratum fills the same columns (worklistview.errata_tasks): date entered, what, key, text
const ERR=new Set(['conflict','orphan','upstream','retire','note','parent','gap','age','place']);   // tasks written as what and a text
const K=Object.fromEntries(D.kinds.map(([k,w],i)=>[k,{why:w,i}]));
const KC={place:'#5a6b2f',age:'#a0306b',parent:'#7a5c3a',gap:'#3a8a8a',conflict:'#c0392b',orphan:'#d4762a',upstream:'#2f6db5',retire:'#9aa5b1',note:'#b08a1e',cited:'#8a3fb8',page:'#1f7a48',search:'#6fb88f',left:'#5b8fd0',none:'#8a857c',unknown:'#c9b071'};
const KIN=['ancestor','relative','spouse of relative','unlinked','unknown'];
const kinRank=k=>{const i=KIN.indexOf(k);return i<0?KIN.length:i};
const $=id=>document.getElementById(id);
// state in the address: kind, kin, q, sort, person (the focus, from another view)
let S={};
function readHash(){const h=new URLSearchParams(location.hash.slice(1));S=Object.fromEntries(h);$('q').value=S.q||'';$('kin').value=S.kin||''}
function writeHash(){const h=new URLSearchParams();for(const [k,v] of Object.entries(S))if(v)h.set(k,v);
 history.replaceState(null,'','#'+h.toString().replace(/%3A/g,':').replace(/%2C/g,','));
 navFocus({person:S.person})}
const kins=[...new Set(D.tasks.map(t=>t[2]))].sort((a,b)=>kinRank(a)-kinRank(b));
$('kin').innerHTML='<option value="">everyone</option>'+kins.map(k=>`<option>${esc(k)}</option>`).join('');
const COLS=[['kind','',t=>K[t[5]].i],['person','person',t=>plainName(t[1])],['kin','kin',t=>kinRank(t[2])*100+String(t[3]).split(' ')[0].length],
 ['year','when',t=>String(t[6]??'')],['place','what',t=>t[9]],['volume','next',t=>t[11]]];
// default order: what to do, then nearest the proband, then the year
const order=(a,b)=>K[a[5]].i-K[b[5]].i||kinRank(a[2])-kinRank(b[2])||String(a[3]).split(' ')[0].length-String(b[3]).split(' ')[0].length||(a[6]??0)-(b[6]??0);
function render(){
 const q=fold(S.q||''),kin=S.kin||'',kind=S.kind||'';
 const base=D.tasks.filter(t=>(!kin||t[2]===kin)&&(!S.person||t[0]===S.person)&&(!q||fold([t[1],t[8],t[9],t[10],t[11],t[13],t[3]].join(' ')).includes(q)));
 const n={};base.forEach(t=>n[t[5]]=(n[t[5]]||0)+1);
 $('kinds').innerHTML=`<button data-k="" class="${kind?'':'on'}">all <span class="n">${base.length}</span></button>`+
  D.kinds.filter(([k])=>n[k]).map(([k])=>`<button data-k="${k}" class="${kind===k?'on':''}" title="${esc(K[k].why)}"><span class="k" style="--c:${KC[k]}"></span>${k} <span class="n">${n[k]}</span></button>`).join('')+
  (S.person?` <button data-clear="person" title="Show everyone">× ${esc(S.person)}</button>`:'');
 $('why').textContent=kind?K[kind].why:'Errata against the current export, age checks, unresolved places, empty parent slots, gaps between record stays, and loose ends (where a life path stops with no death recorded); ordered by what to do, then nearest the proband.';
 let ts=base.filter(t=>!kind||t[5]===kind);
 const sk=(S.sort||'').replace(/^-/,''),c=COLS.find(c=>c[0]===sk);
 ts=ts.sort(c?(a,b)=>{const x=c[2](a),y=c[2](b);return (x>y)-(x<y)||order(a,b)}:order);if(S.sort?.[0]==='-')ts.reverse();
 $('count').textContent=`${ts.length} task${ts.length===1?'':'s'}`;
 const fam=id=>'family.html#p='+encodeURIComponent(id).replace(/%3A/g,':');
 $('tbl').innerHTML='<tr>'+COLS.map(([k,l])=>`<th data-s="${k}">${l}${sk===k?(S.sort[0]==='-'?' ▾':' ▴'):''}</th>`).join('')+'</tr>'+
  ts.slice(0,2000).map(t=>`<tr><td title="${esc(K[t[5]].why)}"><span class="k" style="--c:${KC[t[5]]}"></span>${t[5]}</td>`+
   `<td>${t[0]?(t[1]?`<a href="${fam(t[0])}">${pname(t[1])}</a> <span class="meta">${t[4]?'✻ '+t[4]:''}</span>`:`<span class="meta" title="Not in the tree any more">${esc(t[0])}</span>`):'<span class="meta">—</span>'}</td>`+
   `<td>${esc(t[2])} <span class="meta">${esc(String(t[3]).split(' ')[0])}</span></td>`+
   `<td class="n">${t[6]??''}${t[7]!=null?` <span class="meta">aged ${t[7]}</span>`:''}</td>`+
   (ERR.has(t[5])?`<td>${esc(t[8])} <span class="meta">${esc(t[9])}</span></td><td title="${esc(t[11])}">${esc(t[11].length>160?t[11].slice(0,160)+'…':t[11])}</td></tr>`:
   `<td>${esc(t[8])}: <a href="${linkTo('geography.html',{person:t[0]})}" title="This person's path on the map">${esc(t[9])}</a></td>`+
   `<td>${t[11]?(t[12]?`<a href="${esc(t[12])}" target="_blank" rel="noopener">${esc(t[11])} ↗</a>`:esc(t[11])):''}${t[13]?` <span class="meta">${esc(t[13])}</span>`:''}`+
   `${t[10]?` · <a href="${linkTo('archives.html',{parish:t[10]})}" class="meta">archives</a>`:''}</td></tr>`)).join('');
 writeHash()}
$('kinds').onclick=e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.clear)delete S[b.dataset.clear];else S.kind=b.dataset.k;render()};
$('tbl').onclick=e=>{const th=e.target.closest('th');if(!th)return;const k=th.dataset.s;S.sort=S.sort===k?'-'+k:S.sort==='-'+k?'':k;render()};
$('q').oninput=()=>{S.q=$('q').value;render()};$('kin').onchange=()=>{S.kin=$('kin').value;render()};
window.addEventListener('hashchange',()=>{readHash();render()});readHash();render();
