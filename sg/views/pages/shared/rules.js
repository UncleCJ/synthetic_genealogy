// Selection rules (roadmap, "Focus selection"): which people a page selects
// (sel=) or marks (mark=). Kind people only so far; written against the
// geography page's data (people P, event rows R, lookup tables T), needs fold
// (FOLD_JS). A rule is clauses joined by commas, all of which must hold:
//   born@Hagelstorp     an event of the kind at a place (any level: farm,
//                       village, parish, county; "Källeryd/Hagelstorp" too);
//                       a|b for either
//   born:1800-1850      the event's year in a span (1800- or -1850 open)
//   died                has such an event at all; !died has none
//   line@FMF            lineage code under FMF (ancestors there, and
//                       relatives whose shared ancestors are there)
//   kin@ancestor        relationship (ancestor, relative, spouse of relative, ...)
//   surname@Svensson    surname, spellings folded; name@anna: part of the name
// Event kinds: born, died, married, lived (residences, household books,
// moves, census), at (any event). An optional "person:" in front names the kind.
// Steps (moves between places on a life path, lifepath.py), "step:" in front:
//   km>30, km<5   distance; approx / !approx: an end on a parish point
//   year:1850-1900  the year of arrival; from@place, to@place
// Loose ends (a path that stops with no death), "end:" in front:
//   year:-1900    last seen; age<40, age>60; at@place (last seen there)
//   open          a later household volume exists; none: the inventory has
//                 none; left: emigrated or moved out
// Person clauses work for steps and ends too (step:km>30,line@FM).
function makeRules(P,R,T,ix,ST=[],EN=[]){
 const RP=ix.RP,RT=ix.RT,RY0=ix.RY0,RY1=ix.RY1,RPAR=ix.RPAR,RPL=ix.RPL,RNAME=ix.RNAME;
 const EV={born:['birth','baptism','birth record'],died:['death','burial','death record'],
  married:['marriage','marriage record'],
  lived:['residence','household examination','census','moving','moving in','moving out','record'],at:null};
 const PEOPLE=['line','kin','surname','name'];
 // clauses of their own for steps and loose ends (person clauses apply too)
 const OWN={step:['km','year','approx','from','to'],end:['year','age','at','open','none','left']};
 const byP=P.map(()=>[]);R.forEach(r=>byP[r[RP]].push(r));
 const f=s=>fold(String(s||'').trim());
 // a row is at place v: its place key, a key under it, its parish, or a part of its name
 const at=(r,v)=>{const pl=f(T.place[r[RPL]]),par=f(T.parish[r[RPAR]]);
  return pl===v||pl===f('parish:')+v||pl.startsWith(v+'/')||par===v||String(T.name[r[RNAME]]||'').split(',').some(x=>f(x)===v)};
 function parse(s){
  s=String(s||'').trim();const m=/^(person|step|end):/.exec(s);const kind=m?m[1]:'person';if(m)s=s.slice(m[0].length);
  const clauses=[];
  for(let c of s.split(',').map(x=>x.trim()).filter(Boolean)){
   const neg=c.startsWith('!');if(neg)c=c.slice(1);
   const k=/^[a-z]+/.exec(c);const key=k&&k[0];
   if(!key||!(key in EV||PEOPLE.includes(key)||(OWN[kind]||[]).includes(key)))return {kind,clauses,error:`unknown: ${c}`};
   const rest=c.slice(key.length);let cl={key,neg};
   if(/^[<>]/.test(rest)){const n=/^([<>])(\d+(?:\.\d+)?)$/.exec(rest);if(!n||!['km','age'].includes(key))return {kind,clauses,error:`compare as km>30 or age<40: ${c}`};
    cl.op=n[1];cl.n=+n[2];clauses.push(cl);continue}
   // codes and relationships as written; places and names with spellings folded
   if(rest[0]==='@'){const vs=rest.slice(1).split('|').map(x=>x.trim()).filter(Boolean);
    cl.vals=key==='line'?vs.map(x=>x.toUpperCase()):key==='kin'?vs.map(x=>x.toLowerCase()):vs.map(f)}
   else if(rest[0]===':'){const y=/^:(\d{3,4})?-(\d{3,4})?$|^:(\d{3,4})$/.exec(rest);
    if(!y)return {kind,clauses,error:`years as 1800-1850: ${c}`};
    cl.y0=+(y[1]||y[3]||0)||null;cl.y1=+(y[2]||y[3]||0)||null}
   else if(rest)return {kind,clauses,error:`after ${key}: @place or :years`};
   if((PEOPLE.includes(key)||['from','to'].includes(key)||(key==='at'&&kind==='end'))&&!cl.vals)return {kind,clauses,error:`${key} needs @value`};
   if(['km','age'].includes(key))return {kind,clauses,error:`${key} needs < or >`};
   clauses.push(cl)}
  return {kind,clauses,error:''}}
 function one(cl,i){const p=P[i];
  if(cl.key==='line')return String(p[5]||'').split(' ').some(c=>c&&cl.vals.some(v=>c.startsWith(v)));
  if(cl.key==='kin')return cl.vals.includes(String(p[3]).toLowerCase());
  if(cl.key==='surname')return cl.vals.includes(f(p[2]));
  if(cl.key==='name')return cl.vals.some(v=>f(p[1]).includes(v));
  const ts=EV[cl.key];
  return byP[i].some(r=>(!ts||ts.includes(T.t[r[RT]]))&&(!cl.vals||cl.vals.some(v=>at(r,v)))&&
   (cl.y0==null&&cl.y1==null||(()=>{const a=r[RY0]??r[RY1],b=r[RY1]??r[RY0];return a!=null&&(cl.y0==null||b>=cl.y0)&&(cl.y1==null||a<=cl.y1)})()))}
 const yr=(cl,y)=>y!=null&&(cl.y0==null||y>=cl.y0)&&(cl.y1==null||y<=cl.y1);
 const cmp=(cl,x)=>x!=null&&(cl.op==='>'?x>cl.n:x<cl.n);
 // a step [from row, to row, km, approx]: its own clauses, else its person's
 function oneStep(cl,s){const a=R[s[0]],b=R[s[1]];
  if(cl.key==='km')return cmp(cl,s[2]);if(cl.key==='approx')return !!s[3];
  if(cl.key==='year')return yr(cl,b[RY0]??b[RY1]);
  if(cl.key==='from')return cl.vals.some(v=>at(a,v));if(cl.key==='to')return cl.vals.some(v=>at(b,v));
  return one(cl,a[RP])}
 // a loose end [row, year, age, left, next volume, viewer, status]
 function oneEnd(cl,e){const r=R[e[0]];
  if(cl.key==='year')return yr(cl,e[1]);if(cl.key==='age')return cmp(cl,e[2]);
  if(cl.key==='at')return cl.vals.some(v=>at(r,v));
  if(cl.key==='open')return e[6]==='open';if(cl.key==='none')return e[6]==='none';if(cl.key==='left')return !!e[3];
  return one(cl,r[RP])}
 // person index (or step, or loose end) -> holds (an empty rule holds for everyone)
 const test=(rule,i)=>rule.clauses.every(cl=>(rule.kind==='step'?oneStep(cl,ST[i]):rule.kind==='end'?oneEnd(cl,EN[i]):one(cl,i))!==cl.neg);
 // the indexes a rule picks (people, steps or ends by its kind), or null for no rule (or a broken one)
 const pick=rule=>{if(!rule||rule.error||!rule.clauses.length&&rule.kind==='person')return null;
  const all=rule.kind==='step'?ST:rule.kind==='end'?EN:P;return new Set(all.map((_,i)=>i).filter(i=>test(rule,i)))};
 // the people behind a step or loose end
 const owner=(kind,i)=>kind==='step'?R[ST[i][0]][RP]:kind==='end'?R[EN[i][0]][RP]:i;
 return {parse,test,pick,owner}}
