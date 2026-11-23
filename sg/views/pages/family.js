const D=DATA;const P={};for(const r of D.people)P[r[0]]={id:r[0],nm:r[1],sex:r[2],b:r[3],d:r[4],codes:r[5],ev:r[6],cit:r[7],dna:r[8],lk:r[9],br:r[10],dr:r[11],dk:r[12],unk:r[13]||'',gl:r[14]??0};
// one union, or the same recorded couple twice: full siblings
const sameU=(F,G)=>!!(F&&G&&(F===G||F.h&&F.w&&F.h===G.h&&F.w===G.w));
const asChild={},asSpouse={};for(const [f,h,w,c,m,mr,dv] of D.fams){const F={id:f,h,w,c,m,mr,dv};for(const x of c)if(!asChild[x])asChild[x]=F;for(const x of [h,w])if(x)(asSpouse[x]=asSpouse[x]||[]).push(F)}
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// a person's name as drawn, the same in every view (viewkit.NAME_JS)
const pn=p=>pname(p.nm,p.unk);   // NAME_JS
// a life as ✻ born and † died, never a bare range (which reads like a
// stay); a death known without a date is a bare †
const yrs=p=>[p.b&&'✻ '+p.b,(p.d||p.dk)&&('† '+(p.d??'')).trim()].filter(Boolean).join(' ');
const DK=matchMedia('(prefers-color-scheme:dark)').matches;
// a lineage code's colour, from lineage.color (light, dark)
const BR=c=>c?(D.col?.[c]?.[+DK]||`var(--${c.slice(0,2)})`):'var(--line)';
const counts=p=>[p.ev&&`${p.ev} events`,p.cit&&`${p.cit} citations`,p.dna&&`${p.dna} matches on path`,p.lk&&`${p.lk} linked kit${p.lk>1?'s':''}`].filter(Boolean).join(' · ');
// a pedigree box: name, codes and years, counts on hover
// short: given names only (the full name on hover), where boxes are narrow
function box(id,slot,cls='',short=false){const p=P[id];if(!p)return `<div class="p slot">${esc(slot||'unknown')}</div>`;
 const c=p.codes,code=c.length?`<span class="code">${esc(c.slice(0,3).join(' '))}${c.length>3?' …':''}</span> `:'';
 const sh=short&&p.gl&&p.gl<p.nm.length,t=[sh&&p.nm.replace(/\*/g,''),counts(p)].filter(Boolean).join(' · ');
 return `<div class="p ${cls}${p.nm?'':' anon'}" data-id="${esc(id)}" style="border-left-color:${BR(c[0])}" title="${esc(t)}"><span class="nm">${sh?nm(p.nm.slice(0,p.gl)):pn(p)}</span><span class="yr">${code}${esc(yrs(p))}</span></div>`}
// a family row: role, a fold for the person's children (▸ as in the
// descendants), and a one-line box, indented with a guide per generation
const kidsOf=x=>[...new Set((asSpouse[x]||[]).flatMap(G=>G.c))];
const byB=(a,b)=>(P[a]?.b??9999)-(P[b]?.b??9999);
const guide=d=>`style="padding-left:${d*16}px;background:repeating-linear-gradient(to right,var(--line) 0 1px,transparent 1px 16px) 5px 0/${d*16}px 100% no-repeat"`;
const OPEN=new Set();let focus;
function row(id,role,depth=0,slot,G,U=G){const p=P[id];const start=`<div class="row"><span class="role">${role}</span><div class="dn" ${guide(depth)}>`;
 if(!p)return `${start}<span class="sym"></span><div class="p slot">${esc(slot)}</div></div><span class="ll"></span></div>`;
 const k=role==='child'||depth?kidsOf(id):[];const open=k.length&&OPEN.has(id);
 const sym=k.length?`<button class="sym tog" data-tog="${esc(id)}" title="${open?'fold':'unfold'} ${k.length} child${k.length>1?'ren':''}">${open?'▾':'▸'}</button>`:'<span class="sym"></span>';
 let h=`${start}${sym}<div class="p${id===focus?' focus':''}${p.nm?'':' anon'}" data-id="${esc(id)}" style="border-left-color:${BR(p.codes[0])}" title="${esc(counts(p))}"><span class="nm">${pn(p)}</span><span class="yr">${esc(yrs(p))}${flag(id,G)}</span></div></div>${life(id,U)}</div>`;
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
// what a person was called (viewkit.NAME_JS callName);
// a person whose given name is unknown is "an unknown man/woman"
const given=id=>{const p=P[id];if(!p)return '';if(p.unk.includes('g'))return kin(id,'an unknown man','an unknown woman','someone unknown');return callName(p.nm)};
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
 const lv=G.c.filter(c=>P[c]?.b&&NOW-P[c].b<LIVE),u=[union(G,head),lv.length?`${G.c.filter(c=>aliveAt(c,99999999)).length} of ${G.c.length} children living`:''].filter(Boolean).join(' · ');return (title?`<div class="hht">${esc(title)}</div>`:'')+(u?`<div class="uni">${esc(u)}</div>`:'')+(showHead?row(head,'head',0,'',null,G):'')+row(sp,showHead?'spouse':'partner',0,'not in tree',null,G)+[...G.c].sort(byB).map(x=>row(x,'child',0,'',G)).join('')}
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
 if(a===1&&b===1)return (sameU(asChild[s],asChild[e])?'':'half-')+K('brother','sister','sibling');
 if(b===1)return gr(a-2)+K('uncle','aunt','uncle or aunt');
 if(a===1)return gr(b-2)+K('nephew','niece','nephew or niece');
 const d=Math.min(a,b)-1,r=Math.abs(a-b);return `${d>1?ord(d)+' ':''}cousin${r?' '+(TIMES[r]||r+' times')+' removed':''}`}
function relLine(f){if(f===D.root)return '';const path=relPath(f),R=P[D.root];
 const lk=id=>`<span class="lk" data-id="${esc(id)}">${pn(P[id])}</span>`;
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
// (born under LIVE years ago) runs to now; no recorded end fades out over
// seventy years; the marriage of U (a union or several) as a tick on its partners' rows
let LL=null;
function life(id,U){if(!LL)return '<span class="ll"></span>';const p=P[id],W=LL.hi-LL.lo||1,x=y=>Math.max(0,Math.min(100,(y-LL.lo)/W*100));
 let h='';for(let y=Math.ceil(LL.lo/10)*10;y<=LL.hi;y+=10)if(y%50===0||LL.sub)h+=`<i class="gl${y%50?' s':''}" style="left:${x(y)}%"></i>`;let t='';
 if(p?.b){const live=!p.d&&!p.dk&&NOW-p.b<LIVE,open=!p.d&&!live,e=p.d??(live?NOW:p.b+70),c=p.codes[0]?BR(p.codes[0]):'var(--mut)';
  h+=`<i class="bar" style="left:${x(p.b)}%;width:${x(e)-x(p.b)}%;background:${open?`linear-gradient(to right,${c},transparent)`:c}"></i>`;
  t=yrs(p)+(p.d?` (${p.d-p.b} years)`:'')}
 for(const G of [].concat(U||[]))if((G.h===id||G.w===id)&&G.m){h+=`<i class="mk" style="left:${x(G.m)}%"></i>`;t+=` · married ${G.m}`}
 return `<span class="ll" title="${esc(t)}">${h}</span>`}
// the scale: everyone in the households shown, to the decade
function lifeScale(f){const ids=[f,...par(f)];for(const x of par(f))if(x)for(const G of fams(x))ids.push(G.h,G.w,...G.c);for(const G of fams(f))ids.push(G.h,G.w,...G.c);
 const ps=ids.map(x=>P[x]).filter(p=>p?.b);if(!ps.length)return null;
 const lo=Math.min(...ps.map(p=>p.b)),hi=Math.max(...ps.map(p=>p.d??Math.min(NOW,p.b+70)));return {lo:Math.floor(lo/10)*10,hi:Math.ceil(hi/10)*10}}
const par=id=>{const F=asChild[id];return F?[F.h,F.w]:[null,null]};
function render(){const h=new URLSearchParams(location.hash.slice(1));let f=h.get('p');if(!P[f])f=D.root;focus=f;const p=P[f];
 navFocus({person:f,code:p.codes.find(c=>c.length<=3)});
 document.title=`Family · ${p.nm||'name unknown'}`;
 let gen=[[f]],cols='';for(let g=1;g<4;g++)gen.push(gen[g-1].flatMap(x=>x?par(x):[null,null]));
 const cell=(g,x,i)=>{const kid=gen[g-1]?.[i>>1];return x?box(x,'',g?'':'focus',g===3):(g&&kid?box(null,i%2?'mother not in tree':'father not in tree'):'<div></div>')};
 const lc=x=>P[x]?BR(P[x].codes[0]):'var(--line)';
 const conn=x=>{if(!x)return '<div></div>';const [fa,mo]=par(x);
  return `<div class="cn"><i style="left:25%;top:0;bottom:50%;background:${lc(fa)}"></i><i class="h" style="left:25%;right:50%;background:${lc(fa)}"></i>`+
   `<i class="h" style="left:50%;right:25%;background:${lc(mo)}"></i><i style="left:75%;top:0;bottom:50%;background:${lc(mo)}"></i><i style="left:50%;top:50%;bottom:0;background:${lc(x)}"></i></div>`};
 const row=(g,xs)=>`<div class="gen" style="grid-template-columns:repeat(${gen[g].length},1fr)">${xs}</div>`;
 for(let g=3;g>=0;g--){cols+=row(g,gen[g].map((x,i)=>cell(g,x,i)).join(''));if(g)cols+=row(g-1,gen[g-1].map(conn).join(''))}
 document.getElementById('ped').innerHTML=cols;document.getElementById('rel').innerHTML=relLine(f);
 LL=lifeScale(f);const F=asChild[f];let a='',b='';
 if(F){const fa=F.h,mo=F.w,head=fa||mo;
  a+=`<div class="hh">${hh(F,head,[given(fa),given(mo)].filter(Boolean).join(' and '),true)}</div>`;
  for(const [x,who] of [[fa,'Father'],[mo,'Mother']])if(x)for(const G of fams(x))if(G!==F){const o=other(G,x);
   a+=`<details class="hh"><summary>${who} with ${esc(o?given(o):'a partner not in tree')}${G.m?' · married '+G.m:''} (${G.c.length} child${G.c.length===1?'':'ren'})</summary>${hh(G,x,'',false)}</details>`}}
 const own=fams(f);for(const G of own){const o=other(G,f);b+=`<div class="hh">${hh(G,f,o?'With '+given(o):'Partner not in tree',false)}</div>`}
 document.getElementById('fam').innerHTML=(a?`<div><h2>Parents and siblings</h2>${a}</div>`:'')+(b?`<div><h2>Partners and children</h2>${b}</div>`:'');
 document.getElementById('title').innerHTML=`<b>${pn(p)}</b> <span class="meta">${esc(yrs(p))}${p.codes.length?' · '+esc(p.codes.join(' ')):''}${counts(p)?' · '+esc(counts(p)):''}</span>`;
 const g=new URLSearchParams({person:f,lines:'1',kin:'all'}).toString().replace(/%3A/g,':');
 document.getElementById('links').innerHTML=`<a href="geography.html#${g}">on the map</a><a href="archives.html#${enc(new URLSearchParams({person:f,kin:'all'}))}">in the archives</a>`+
  // the genome page holds an ancestor out down to great-grandparents, where the copy model's blocks reach
  (gc=>gc!=null?`<a href="genome.html${gc?'#c='+gc:''}" title="${gc?'Where this ancestor\'s DNA lies in the donors\' genomes':'The donors\' genomes'}">in the genome</a>`:'')(p.codes.find(c=>c.length<=3))}
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
// born less than LIVE years before (presumed living; anyone older is
// quietly presumed dead)
const NOW=new Date().getFullYear(),LIVE=120;
const aliveAt=(id,w)=>{const p=P[id];if(!p||!p.b||dk(p.br||String(p.b))>w)return false;return p.d?dk(p.dr||String(p.d))>w:!p.dk&&NOW-p.b<LIVE&&(w>=99999999||Math.floor(w/1e4)-p.b<LIVE)};
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
 const aged=id=>{const s=shortSpan(P[id]?.br,P[id]?.dr),a=ageAt(P[id],P[id]?.dr);return s?s+' old':a?'aged '+a:''};
 for(const x of par(f))if(x)add(kin(x,'father died','mother died','parent died'),P[x].dr,x,aged(x));
 const F=asChild[f],sibs=new Set();if(F)F.c.forEach(c=>c!==f&&sibs.add(c));
 for(const x of par(f))if(x)for(const G of fams(x))if(G!==F)G.c.forEach(c=>sibs.add(c));
 const full=new Set(F?F.c:[]);for(const x of par(f))if(x)for(const G of fams(x))if(G!==F&&sameU(F,G))G.c.forEach(c=>full.add(c));
 for(const s of sibs){let x=aged(s);if(full.has(s)&&P[s]?.d){const w=dk(P[s].dr||String(P[s].d)),left=[...full].filter(c=>c!==s&&aliveAt(c,w)).length;const fu=sibs.size>=full.size?'full ':'';x=[x,left===1&&aliveAt(f,w)?`the last ${fu}sibling left`:`${left} of ${full.size}${fu?" full siblings":""} left`].filter(Boolean).join(' · ')}
  add(full.has(s)?kin(s,'brother died','sister died','sibling died'):kin(s,'half-brother died','half-sister died','half-sibling died'),P[s]?.dr,s,x)}
 // moves, from Geography's steps (life_steps.json): each labelled by where
 // the family was (lifepath.labels): back home, to a parent, to a relative's
 // farm, with or after a relative; the person's own as events, the
 // parents' moves, and when siblings and children first moved out
 const ST=D.steps||{},pr=kin(f,'him','her','them'),mv=ST[f]||[];
 const lab=(L,mover,y)=>{const g={},old=P[mover]?.b&&y-P[mover].b>=55,nm1=([r,,w])=>r===f?pr:`${w} ${given(r)}`,who=xs=>xs.map(nm1).join(', ');
  for(const [k,r,yy,w] of L)(g[k]=g[k]||[]).push([r,yy,w]);
  return Object.entries(g).map(([k,xs])=>k==='born'?'back where born':k==='back'?`back (there in ${xs[0][1]})`:k==='parents'?`to ${who(xs)}`:
   k==='ageing'?'back to '+xs.map(x=>nm1(x)+(P[x[0]]?.b?`, ${y-P[x[0]].b}`:'')).join(', '):
   k==='kin'?(old&&xs.every(x=>/^(son|daughter|child)$/.test(x[2]))?`in with ${who(xs)}`:`where ${who(xs)} lived`):
   k==='near'?`near ${who(xs)}`:k==='together'?`with ${who(xs)}`:k==='following'?'after '+xs.map(x=>`${nm1(x)} (there ${x[1]})`).join(', '):k).join(' · ')};
 const kmT=km=>km>=1?`${Math.round(km)} km`:'';
 for(const [y,d,fr,to,km,ap,L] of mv)if(dw(String(y)))ex.push(['moved',String(y),to,'',null,'',false,[lab(L,f,y),kmT(km)].filter(Boolean).join(' · ')]);
 const pm={};
 for(const x of par(f))if(x)for(const [y,d,fr,to,km,ap,L] of ST[x]||[]){if(!dw(String(y)))continue;const k=y+'|'+to;
  if(pm[k]){pm[k][0]='parents moved';pm[k][3]='';pm[k][4]=null;continue}
  const with_=mv.some(m=>Math.abs(m[0]-y)<=1&&m[3]===to);
  ex.push(pm[k]=[kin(x,'father moved','mother moved','parent moved'),String(y),to,given(x),x,'',true,[lab(L,x,y),with_?`${pr} too`:''].filter(Boolean).join(' · ')])}
 const firstOut=(id,t)=>{const s0=(ST[id]||[]).find(s=>!(P[id]?.b&&s[0]-P[id].b<15)&&!s[6].some(l=>['parents','ageing','born'].includes(l[0])||l[0]==='together'&&/^(father|mother|parent)$/.test(l[3])));if(s0&&dw(String(s0[0])))ex.push([t,String(s0[0]),s0[3],given(id),id,'',true,[P[id]?.b?`at ${s0[0]-P[id].b}`:'',lab(s0[6],id,s0[0])].filter(Boolean).join(' · ')])};
 for(const s of sibs)firstOut(s,kin(s,'brother moved out','sister moved out','sibling moved out'));
 for(const c of kidsOf(f))firstOut(c,kin(c,'son moved out','daughter moved out','child moved out'));
 // the tree's own: siblings' marriages, a parent's new marriage, grandparents'
 // deaths, and a wedding on the same day as a sibling's or cousin's
 const ageOn=(id,raw)=>P[id]?.b&&yr(raw)<9999?`at ${yr(raw)-P[id].b}`:'';
 const day=d=>/\b\d{1,2} [A-Z]{3} \d{4}\b|\d{4}-\d{2}-\d{2}/.test(d||'')?d:'',myDays=new Set(fams(f).map(G=>day(G.mr)).filter(Boolean));
 for(const s of sibs)for(const H of fams(s)){const o=other(H,s);if(H.m||H.mr)add(kin(s,'brother married','sister married','sibling married'),H.mr||String(H.m),s,[o&&P[o]?'to '+given(o):'',ageOn(s,H.mr||String(H.m)),myDays.has(day(H.mr))?`the same day as ${pr}`:''].filter(Boolean).join(' · '))}
 for(const x of par(f))if(x)for(const G of fams(x))if(G!==F&&wed(G)&&(G.m||G.mr)&&me.b&&yr(G.mr||String(G.m))>=me.b){const o=other(G,x);add(kin(x,'father remarried','mother remarried','parent remarried'),G.mr||String(G.m),x,o&&P[o]?'to '+given(o):'')}
 // grandparents: how many were living at the birth, and at each death how
 // many are left ("the last grandparent")
 const gps=par(f).filter(Boolean).flatMap(par).filter(g=>g&&P[g]);
 if(gps.length&&me.b){const wb=dk(me.br||String(me.b)),n=gps.filter(g=>aliveAt(g,wb)).length;
  ex.push([n?`born with ${n} grandparent${n>1?'s':''} living`:'born with no grandparent living',me.br||String(me.b),'','',null,'',true,gps.length<4?`${gps.length} of 4 in the tree`:''])}
 for(const g of gps)if(P[g].d){const w=dk(P[g].dr||String(P[g].d)),left=gps.filter(o=>o!==g&&aliveAt(o,w)).length;
  add(kin(g,'grandfather died','grandmother died','grandparent died'),P[g].dr,g,[aged(g),left?`${left} grandparent${left>1?'s':''} left`:aliveAt(f,w)?(gps.length<4?'the last grandparent in the tree':'the last grandparent'):''].filter(Boolean).join(' · '))}
 const cous=par(f).filter(Boolean).flatMap(x=>siblingsOf(x)).flatMap(kidsOf).filter(c=>c!==f&&!sibs.has(c));
 for(const G of fams(f)){const w=day(G.mr);if(!w)continue;
  for(const [r,t] of cous.map(r=>[r,'cousin']))for(const H of fams(r))if(H!==G&&day(H.mr)===w){const o=other(H,r);
   ex.push([`${t} married the same day`,w,'',given(r),r,'',true,o&&P[o]?'to '+given(o):''])}}
 const nieces=[...sibs].flatMap(kidsOf).filter(c=>P[c]?.b).sort(byB);
 const before=nieces.filter(c=>me.b&&dk(P[c].br||String(P[c].b))<dk(me.br||String(me.b)));
 if(before.length)ex.push([kin(f,'born an uncle','born an aunt','born an uncle or aunt'),me.br||String(me.b),'','',null,'',true,`${before.length} nephew${before.length>1?'s and nieces':' or niece'} already · ${nieces.length} in all`]);
 else if(nieces[0])add(kin(nieces[0],'first nephew','first niece','first nephew or niece'),P[nieces[0]].br||String(P[nieces[0]].b),nieces[0],nieces.length>1?`${nieces.length} in all`:'');
 const grand=[];
 for(const G of fams(f)){const o=other(G,f);if(G.m||G.mr)ex.push(['MARR',G.mr||String(G.m),'',o?'with '+(P[o].nm||'an unknown '+kin(o,'husband','wife','partner')):'',o,'',false,'']);
  for(const c of G.c){if(P[c]?.b)add(kin(c,'son born','daughter born','child born'),P[c].br||String(P[c].b),c);
   for(const H of fams(c)){const sp=other(H,c);if(sp&&(H.m||H.mr))add(kin(c,'gained a daughter-in-law','gained a son-in-law','child married'),H.mr||String(H.m),sp,'married '+given(c));
    H.c.forEach(g=>P[g]?.b&&grand.push(g))}
   add(kin(c,'son died','daughter died','child died'),P[c]?.dr,c,aged(c))}
  // a former spouse is named so; an unmarried partner who was left is named
  // only after a lasting union (two children or more), not a passing one
  if(o&&P[o]?.d){const w=dd(o),h=heldTo(G,w);
   if(wed(G))add(h?kin(o,'husband died','wife died','spouse died'):kin(o,'former husband died','former wife died','former spouse died'),P[o].dr,o,aged(o));
   else if(h||G.c.length>1)add(h?'partner died':'former partner died',P[o].dr,o,aged(o))}}
 grand.sort(byB);if(grand[0])add('first grandchild',P[grand[0]].br||String(P[grand[0]].b),grand[0],grand.length>1?`${grand.length} in all`:'');
 const L=[...(D.life[f]||[]),...ex].map((e,i)=>[e,i]).sort((a,b)=>dk(a[0][1])-dk(b[0][1])||a[1]-b[1]).map(x=>x[0]);
 document.getElementById('life').innerHTML=L.length?`<h2>Life events (${L.length})</h2><table>`+L.map(([t,d,pl,v,id,par,der,extra])=>(extra=t==='DEAT'?notice(f):extra,`<tr${der?' class="der" title="Derived from the family: no source of its own"':''}><td class="y">${esc(fmtDate(d))}</td><td class="y">${(t==='BIRT'?'':shortSpan(me.br,d)?shortSpan(me.br,d)+' old':(a=>a&&!/^~?0$/.test(a)?'age '+a:'')(ageAt(me,d)))}</td><td class="ev">${esc(TAG[t]||t.toLowerCase())}</td><td>${[pl&&placeLink(pl,par),v&&(id?`<span class="lk" data-id="${esc(id)}">${nm(v)}</span>`:`<span class="meta">${esc(v)}</span>`),extra&&`<span class="${t==='DEAT'?'notice':'meta'}">${esc(extra)}</span>`].filter(Boolean).join(t==='DEAT'?'<br>':' · ')}</td></tr>`)).join('')+'</table>':'';
 const A=(D.added||{})[f]||[],KIND={fix:'correction',src:'source',note:'note'};
 document.getElementById('added').innerHTML=A.length?`<h2>Notes and added sources (${A.length}) <span class="meta" style="font-weight:400">kept beside MyHeritage</span></h2><table>`+A.map(([k,d,head,text,img])=>`<tr><td class="y">${esc(d)}</td><td class="ev">${KIND[k]||k}</td><td>${head?`${esc(head)}${img?` <a href="https://sok.riksarkivet.se/bildvisning/${esc(img)}" target="_blank" rel="noopener">↗</a>${(m=>m?OFF(m[1],+m[2]):'')(/^([A-Za-z]?\d+)_(\d+)$/.exec(img))}`:''}<br>`:''}<span class="meta">${esc(text)}</span></td></tr>`).join('')+'</table>':'';
 const R=D.refs[f]||[],n=D.trees[f]||0,MV=(D.moves||{})[f]||[],RM=((D.remarks||{})[f]||[]).slice().sort((a,b)=>!a[1]-!b[1]);
 document.getElementById('refs').innerHTML=R.length||n?`<h2>References (${R.reduce((a,r)=>a+r[8],0)}) <a class="hl" href="archives.html#${enc(new URLSearchParams({person:f,kin:'all'}))}" title="In the archives: ${esc(given(f))}'s citations in every parish">in the archives</a></h2>`+(R.length?'<table>'+R.map(([ev,d,vol,y,pg,url,tier,par,k,more,urls,hint])=>
  `<tr><td class="y">${esc(y)}</td><td>${esc(vol)}${pg?' p. '+esc(pg):''}${k>1?` <span class="meta">×${k}</span>`:''}${[url,...(urls||[])].filter(Boolean).map(u=>` <a href="${esc(u)}" target="_blank" rel="noopener" title="${/myheritage/.test(u)?'MyHeritage':/riksarkivet/.test(u)?'Riksarkivet':'source'}">↗</a>`).join('')}${(m=>m?OFF(m[1],m[2]&&+m[2]):'')(/bildvisning\/([A-Za-z]?\d+)(?:_(\d+))?/.exec([url,...(urls||[])].find(u=>/bildvisning/.test(u||''))||''))}${par&&/\//.test(vol)?` <a class="plain" href="archives.html#${enc(new URLSearchParams({parish:par,q:vol.replace(par+' ',''),kin:'all'}))}" title="In the archives: everyone in ${esc(vol)}">everyone in this volume</a>`:''}</td><td class="meta">${[[ev,d],...(more||[])].filter(e=>e[0]!=='person').map(([e,d])=>esc(e+(d?' '+fmtDate(d):''))).join(', ')}${hint?`<br><span class="hint" title="Read from the page on the archive shelf: a hint, not a correction">⚑ ${esc(hint)}</span>`:''}</td></tr>`).join('')+'</table>':'')+
  (MV.length?`<h3>Moves read from the pages <span class="meta" style="font-weight:400">hints from the archive shelf, not in the tree</span></h3><table>`+MV.map(([dir,yr,pl,t,vol,pg,v])=>`<tr><td class="y">${esc(yr||'')}</td><td>${dir==='in'?'moved in from':'moved out to'} ${pl?esc(pl.replace(/s? (församling|socken)$/,'')):'<i>unread place</i>'} <span class="meta">'${esc(t)}'</span></td><td class="meta">${esc(vol)}${pg?' p. '+esc(pg):''}${v==='new'?' · <b>not among the tree\'s parishes</b>':v==='within the book'?' · within the book':''}</td></tr>`).join('')+'</table>':'')+
  (RM.length?`<h3>Remarks read from the pages <span class="meta" style="font-weight:400">the person's row beyond name, birth and moves (lyte, frejd, notes, …), hints from the archive shelf; ⚑ a word worth a look</span></h3><table>`+RM.map(([col,fl,t,vol,pg])=>`<tr><td class="y">${esc(col)}</td><td>${fl?`<b>⚑ ${esc(fl)}</b> `:''}<span class="meta">'${esc(t)}'</span></td><td class="meta">${esc(vol)}${pg?' p. '+esc(pg):''}</td></tr>`).join('')+'</table>':'')+
  (n?`<p class="meta">Also cited by ${n} other tree${n>1?'s':''} (MyHeritage matches, not sources).</p>`:''):''}
// descendants: everyone down from the focus with their partners, children
// under the union they came from; generations step right as indents and
// down the page by birth, years run right on the bars. Children are open
// down to DGEN generations (the grandchildren, folded), fewer
// past DROWS rows; below that a person shows folded, and ▸ left of the
// name unfolds their partners and children. Someone reached twice
// (cousins who married) is drawn once, then marked ↺.
const DGEN=2,DROWS=250,DOPEN=new Set();
const dkids=G=>G.c.filter(c=>P[c]).sort(byB);
function descendants(f){const per=[],all=new Set([f]);let lvl=[f],rows=[1];
 while(lvl.length&&per.length<20){const nx=[];let sp=0;for(const x of lvl)for(const G of fams(x)){if(other(G,x))sp++;for(const c of dkids(G))if(!all.has(c)){all.add(c);nx.push(c)}}
  rows[rows.length-1]+=sp;if(!nx.length)break;per.push(nx.length);rows.push(rows[rows.length-1]+nx.length);lvl=nx}
 let depth=1;while(depth<Math.min(DGEN,per.length)&&rows[depth]<=DROWS)depth++;
 return {per,all,depth}}
const below=(x,seen=new Set())=>{for(const G of fams(x))for(const c of dkids(G))if(!seen.has(c)){seen.add(c);below(c,seen)}return seen};
function descSection(f){const T=descendants(f);if(!T.per.length)return '';
 const shown=[],seen=new Set();
 const box1=(id,cls)=>{const p=P[id];return `<div class="p${id===focus?' focus':''}${cls||''}${p.nm?'':' anon'}" data-id="${esc(id)}" style="border-left-color:${BR(p.codes[0])}" title="${esc(counts(p))}"><span class="nm">${pn(p)}</span><span class="yr">${esc(yrs(p))}</span></div>`};
 const out=[];
 function walk(id,d){const rep=seen.has(id);seen.add(id);shown.push(id);
  // open shows the person's unions: partners and children, whichever
  // partner the descendant is; folded, neither
  const fs=rep?[]:fams(id),np=fs.filter(G=>P[other(G,id)]).length,n=rep?0:below(id).size;
  const open=(np||n)&&(d<T.depth)!==DOPEN.has(id),what=[np&&`${np} partner${np>1?'s':''}`,n&&`${n} descendant${n>1?'s':''}`].filter(Boolean).join(', ');
  const sym=rep?'<span class="sym" title="also above: reached twice">↺</span>':np||n?`<button class="sym tog" data-dtog="${esc(id)}" title="${open?'fold':'unfold'} ${what}">${open?'▾':'▸'}</button>`:'<span class="sym"></span>';
  out.push([`<div class="dr"><div class="dn" ${guide(d)}>${sym}${box1(id)}</div>`,id,fams(id)]);
  if(!open)return;
  for(const G of fs){const o=other(G,id),w=wed(G),mark=`<span class="sym${w?'':' unw'}" title="${w?'married':'partner, not married'}">⚭</span>`;
   if(o&&P[o]){shown.push(o);out.push([`<div class="dr sp"><div class="dn" ${guide(d)}>${mark}${box1(o,' sp')}${T.all.has(o)?'<span class="meta" title="also a descendant">↺</span>':''}</div>`,o,G])}
   else if(fs.length>1)out.push([`<div class="dr sp"><div class="dn" ${guide(d)}>${mark}<div class="p slot">partner not in tree</div></div>`,null,null]);
   for(const c of dkids(G))walk(c,d+1)}}
 walk(f,0);
 const ps=shown.map(x=>P[x]).filter(p=>p?.b),keep=LL;
 LL=ps.length?{lo:Math.floor(Math.min(...ps.map(p=>p.b))/10)*10,hi:Math.ceil(Math.max(...ps.map(p=>p.d??Math.min(NOW,p.b+70)))/10)*10}:null;if(LL)LL.sub=1;
 let ax='';if(LL){const W=LL.hi-LL.lo||1;for(let y=Math.ceil(LL.lo/10)*10;y<=LL.hi;y+=10){const l=(y-LL.lo)/W*100;ax+=`<i class="tk${y%50?'':' M'}" style="left:${l}%"></i>`+(y%50?'':`<b style="left:${l}%">${y}</b>`)}}
 const body=out.map(([a,id,G])=>a+(id?life(id,G):'<span class="ll"></span>')+'</div>').join('');LL=keep;
 const gname=g=>g===0?'children':g===1?'grandchildren':gr(g-1)+'grandchildren';
 const sum=T.per.map((n,g)=>`${n} ${n===1?gname(g).replace(/ren$/,''):gname(g)}`).join(' · ');
 return `<h2>Descendants (${T.all.size-1}) <span class="meta" style="font-weight:400">${esc(sum)}${T.depth<T.per.length?` · ${T.depth} generations open, ▸ unfolds a branch`:''}</span></h2>`+
  `<div class="dr ax"><div></div><span class="ll">${ax}</span></div>`+body}
document.addEventListener('click',e=>{const t=e.target.closest('[data-tog]');if(t){const x=t.dataset.tog;OPEN.has(x)?OPEN.delete(x):OPEN.add(x);render();return}
 const dt=e.target.closest('[data-dtog]');if(dt){const x=dt.dataset.dtog;DOPEN.has(x)?DOPEN.delete(x):DOPEN.add(x);document.getElementById('desc').innerHTML=descSection(focus);return}
 const el=e.target.closest('[data-id]');if(el&&!el.classList.contains('focus')){OPEN.clear();DOPEN.clear();location.hash='p='+el.dataset.id;if(el.parentElement.id==='hits'){q.value='';HITS=[];showHits()}}});
// a search box, not a filter: every word must match (any order, accents and
// spelling variants ignored: viewkit.name_fold); arrows move through the hits,
// Enter goes to the marked one, Escape or leaving clears
__FOLDJS__
const KEY=D.people.map(r=>fold(r[1]));
const q=document.getElementById('q'),hl=document.getElementById('hits');let HITS=[],AT=0;
function showHits(){hl.innerHTML=HITS.map((r,i)=>`<div data-id="${esc(r[0])}" class="${i===AT?'at':''}">${pn(P[r[0]])} <span class="meta">${esc(yrs(P[r[0]]))}</span></div>`).join('');hl.querySelector('.at')?.scrollIntoView({block:'nearest'})}
q.addEventListener('input',()=>{const ws=fold(q.value).split(/\s+/).filter(Boolean);
 HITS=ws.join('').length<2?[]:D.people.filter((r,i)=>ws.every(w=>KEY[i].includes(w))).sort((a,b)=>(P[a[0]].b??9999)-(P[b[0]].b??9999)).slice(0,30);AT=0;showHits()});
q.addEventListener('keydown',e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){if(!HITS.length)return;e.preventDefault();AT=(AT+(e.key==='ArrowDown'?1:-1)+HITS.length)%HITS.length;showHits()}
 else if(e.key==='Enter'&&HITS[AT]){OPEN.clear();DOPEN.clear();location.hash='p='+HITS[AT][0];q.value='';HITS=[];showHits();q.blur()}
 else if(e.key==='Escape'){q.value='';HITS=[];showHits();q.blur()}});
q.addEventListener('blur',()=>setTimeout(()=>{HITS=[];showHits()},150));
q.addEventListener('focus',()=>{if(q.value.trim())q.dispatchEvent(new Event('input'))});
const _r=render;render=function(){_r();sections(focus);document.getElementById('desc').innerHTML=descSection(focus)};
window.addEventListener('hashchange',render);render();
