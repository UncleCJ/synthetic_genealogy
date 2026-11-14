"""
The genome lens, donor focus (docs/lenses.md): one donor's two copies of
each autosome, painted with the copy model's blocks in the lineage colours.
A block fades with its posterior, from its prior (a coin toss between the
codes on its copy) to sure. Under each copy, a lane of assertions (match
segments said to come down a code) as spans, by the model's leave-one-out
verdict: dissents by default (the work to do), or unclear or agreeing.

    python3 genomeview.py       # writes data/output/genome.html (private: names)

Counts first: per code, its share of its copy against the expected, how
much of it is sure (block posterior >= 0.9), and the verdicts on the
assertions under it. Hover a block or a span for what it is; click a block
to open the family page on that ancestor. Below, the assertions with the
chosen verdict, longest first. Column heads explain themselves on hover.

Link scheme (after #): d=<donor>&c=<code>&l=<2|3>&m=<siblings|single>&v=<verdict>.
A donor or a code (an ancestor held out, the rest dimmed; the family page
links here with it) adds a history step; level, model and verdict replace it.

Sketch: reads copy_model_blocks.csv and copy_model_verdicts.csv (rebuilt)
and the store for the ancestors' names. Codes are read from the proband,
as the copy model's are, which holds for the proband and full siblings.
Positions are in cM; an assertion's start (bp) is placed by interpolating
between the block ends of its copy, its end by its length in cM.
"""
import sys

import lineage

SURE = 0.9


def parents(db):
    """person -> (father, mother) from the store (the first family a child is in)."""
    par = {}
    fams = {fid: (h, w) for fid, h, w in db.execute("select id, husb, wife from family")}
    for fid, child in db.execute("select family, child from child order by rowid"):
        par.setdefault(child, fams.get(fid, (None, None)))
    return par


def fit(par, root, donors):
    """donor -> why the page leaves them out, or None: the codes run from
    the proband, so only the proband and full siblings (both parents
    recorded and shared) can be painted. donors: donor -> store id."""
    import familyview
    codes = familyview.lineage_codes(par, root, 12)
    mine = par.get(root, (None, None))
    out = {}
    for d, pid in donors.items():
        theirs = par.get(pid, (None, None))
        if not pid:
            out[d] = "not placed in the tree (no mh for them in family.toml)"
        elif pid == root or (all(mine) and theirs == mine):
            out[d] = None
        elif any(a and a == b for a, b in zip(theirs, mine)):
            out[d] = "a half-sibling: only the copy from the shared parent runs through the proband's codes"
        elif codes.get(pid):
            out[d] = f"the proband's {codes[pid][0]}: their own codes do not run from the proband"
        else:
            out[d] = "neither the proband nor a full sibling"
    return out


def ancestors(db, root, depth=3):
    """code -> [store id, name, birth, death] for root's ancestors to depth
    (pedigree collapse: one person under several codes)."""
    import familyview
    import tree_store
    from intervals import years
    codes = familyview.lineage_codes(parents(db), root, depth)
    life = {}
    for pid, tag, date in db.execute("select owner, tag, date from event where tag in ('BIRT','DEAT')"):
        life.setdefault(pid, {})[tag] = years(date)[0]
    out = {}
    for pid, g, s in db.execute("select id, given, surname from person"):
        for c in codes.get(pid, []):
            if c and c not in out:
                lf = life.get(pid, {})
                out[c] = [pid, " ".join(tree_store.name_parts(g, s)).replace("*", "").strip(), lf.get("BIRT"), lf.get("DEAT")]
    return out


def _claim(cid):
    """(source, match, start bp) from a claim id source:match:subject:chrom:start:code
    (a match name may hold colons)."""
    p = str(cid).split(":")
    try:
        return p[0], ":".join(p[1:-4]), int(float(p[-2]))
    except (ValueError, IndexError):
        return p[0], "", None


def collect(blocks, verdicts, anc, names=None, matches=None, left=()):
    """The lens's data from the copy model's tables (DataFrames; verdicts may
    be None), the ancestors (ancestors()), the donors' display names and
    match key -> match name (keys in claim ids are vendor ids); left: (name,
    reason) for subjects with blocks the page does not paint (fit())."""
    lengths = blocks.groupby(blocks.chrom.astype(str)).end_cm.max().round(1).to_dict()
    mb = (blocks.groupby(blocks.chrom.astype(str)).end.max() / 1e6).round(0).to_dict()
    B = {}
    for (subj, model, level), g in blocks.groupby(["subject", "model", "level"]):
        B.setdefault(subj, {}).setdefault(model, {})[str(level)] = [
            [str(r.chrom), r.side, round(r.start_cm, 1), round(r.end_cm, 1), int(r.start), int(r.end),
             r.lineage, round(float(r.posterior), 3)] for r in g.itertuples()]
    V = []
    for r in (verdicts.itertuples() if verdicts is not None else ()):
        src, match, bp = _claim(r.claim_id)
        if bp is None:
            continue
        V.append([r.subject, r.model, getattr(r, "source_kind", None) or src, (matches or {}).get(match, match), str(r.chrom), bp, r.code, float(r.support),
                  r.verdict, None if r.cM != r.cM else round(float(r.cM), 1)])
    codes = {c for c in blocks.lineage.unique()} | {c[:k] for c in anc for k in range(1, len(c) + 1)}
    col = {c: [lineage.color(c), lineage.color(c, dark=True)] for c in sorted(codes)}
    return dict(left=[list(x) for x in left], mb=mb, blocks=B, names={d: (names or {}).get(d, d) for d in B}, verdicts=V, lengths=lengths, anc=anc, col=col, sure=SURE)


def write(path, data):
    import geoview
    path.write_text(geoview.embed(HTML.replace("__NAV__", geoview.nav("genome.html")), data), encoding="utf-8")


HTML = r"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Genome</title>
<style>
:root{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#6b6760;--line:#e2ded6;--card:#fff;--sel:#fff1bf;--acc:#2f6db5;--bad:#c0392b}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ece9e2;--mut:#9b968c;--line:#34312c;--card:#201f1c;--sel:#4a4220;--acc:#6ea4e6;--bad:#e8705f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,-apple-system,sans-serif}
header{display:flex;gap:10px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:16px;margin:0 8px 0 0}h2{font-size:13px;margin:0 0 6px;color:var(--mut);font-weight:600}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden;vertical-align:middle}
.seg button{font:inherit;font-weight:400;color:var(--fg);background:var(--card);border:0;border-left:1px solid var(--line);padding:3px 9px;cursor:pointer}
.seg button:first-child{border-left:0}.seg button.on{background:var(--sel);font-weight:600}.seg button:disabled{color:var(--mut);cursor:not-allowed;opacity:.5;text-decoration:line-through}
main{padding:12px 16px;display:grid;gap:16px;max-width:1200px}main>section+section{border-top:1px solid var(--line);padding-top:12px}
table{border-collapse:collapse}td,th{padding:2px 12px 2px 0;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:12px}[title].help{cursor:help;text-decoration:underline dotted;text-underline-offset:3px}
.n{text-align:right;font-variant-numeric:tabular-nums}
.chip{display:inline-block;width:12px;height:12px;border-radius:2px;vertical-align:-2px;margin-right:6px}
.code{font-family:ui-monospace,monospace;font-size:11px}.meta{color:var(--mut);font-size:11px;font-weight:400}
a{color:var(--acc)}.bad{color:var(--bad)}tr.on td{background:var(--sel)}
#focus{display:flex;gap:4px;align-items:center}#focus a{cursor:pointer;margin-left:6px}
/* the counts: a bar for the share of the copy, a tick where the expected share falls */
.share{position:relative;width:120px;height:10px;background:var(--line);border-radius:2px}.share i{position:absolute;top:0;bottom:0;left:0;border-radius:2px}
.share b{position:absolute;top:-2px;bottom:-2px;width:2px;background:var(--fg)}
/* chromosomes: a row each, the paternal copy above the maternal, width by cM;
   under each copy a lane with the assertions of the chosen verdict as spans */
.cr{display:grid;grid-template-columns:28px 1fr;align-items:center;gap:6px;margin-bottom:6px}.cr>span{color:var(--mut);text-align:right;font-variant-numeric:tabular-nums}
.tr{position:relative;height:10px;background:var(--line);border-radius:2px;margin-top:1px}.tr i{position:absolute;top:0;bottom:0;cursor:pointer}
.tr i:hover{outline:1.5px solid var(--fg);z-index:1}
.ln{position:relative;height:6px;margin:1px 0 2px}.ln b{position:absolute;top:0;bottom:0;border-radius:1px;cursor:help;min-width:3px;opacity:.85}
.ln b:hover{outline:1.5px solid var(--fg);opacity:1}.ln b.dissents{background:var(--bad)}.ln b.unclear{background:var(--mut)}
.legend{display:flex;gap:16px;flex-wrap:wrap;align-items:center;color:var(--mut);font-size:12px}
#tip{position:fixed;pointer-events:none;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:6px 8px;max-width:340px;font-size:12px;display:none;z-index:3;box-shadow:0 2px 8px #0002}
</style></head><body>
<header>__NAV__<h1>Genome</h1><span class="seg" id="donors"></span><span class="seg" id="levels"></span><span class="seg" id="models"></span><span id="focus"></span></header>
<main><section id="counts"></section><section id="chroms"></section><section id="list"></section></main><div id="tip"></div>
<script type="text/plain" id="view-js">
const D=DATA;const DARK=matchMedia('(prefers-color-scheme:dark)').matches;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const col=c=>(D.col[c]||['#8f8a80','#8f8a80'])[DARK?1:0];
const pct=x=>(100*x).toFixed(x<0.1?1:0)+'%';
// a life as ✻ born and † died, as on the family page
const yrs=a=>a?[a[2]&&'✻ '+a[2],a[3]&&'† '+a[3]].filter(Boolean).join(' '):'';
const who=c=>{const a=D.anc[c];return a?(esc(a[1])||'<i>unnamed</i>'):'<i>no one in the tree</i>'};
const VER={dissents:'dissent',unclear:'unclear',agrees:'agree'};
const SRC={documented:'a relative documented by hand (assertions.toml, [[anchors]]): the path is researched, the segment read against a parent\'s or the siblings\' matches',
 tree:'a match linked to a person in the tree (a confirmed identity, or a name join): the path is the tree\'s'};
const TH={code:'Lineage code: the path from the proband up to an ancestor, F for father and M for mother, read left to right (FM is the father\'s mother). Its first letter names the copy. Click one to hold that ancestor out.',
 anc:'The person the tree has at that code; the name opens the family page.',
 bar:'How much of this copy (in cM) the model paints with this code; the tick marks the average share inheritance gives.',
 share:'Share of the copy, in cM, painted with this code.',
 sure:'Share of the copy in blocks the model is at least 90% sure of (posterior ≥ 0.9).',
 agree:'Assertions under this code (match segments said to come down from this ancestor) that the model, judged without each one, places under it.',
 conf:'Assertions under this code that the model, judged without each one, places under another code. The rest are unclear.',
 match:'The DNA match whose shared segment makes the assertion.',
 src:'Where the assertion\'s path comes from. documented: '+SRC.documented+'. tree: '+SRC.tree+'.',
 chr:(()=>{const c=Object.keys(D.lengths).sort((a,b)=>D.lengths[a]-D.lengths[b]),f=k=>`${k} (${D.mb[k]} Mb, ${Math.round(D.lengths[k])} cM)`;
  return c.length?`Chromosome. Numbered roughly by decreasing size (21, not 22, is in fact the smallest); here from ${f(c[0])} to ${f(c[c.length-1])}, as far as the genetic map reaches.`:'Chromosome.'})(),
 mb:'Where the segment starts, in megabases (million base pairs): a physical position along the chromosome\'s DNA sequence.',
 cm:'Length in centimorgans: genetic distance, measured by how often crossovers fall in a stretch (1 cM is about a 1% chance of one per generation). It measures the same stretch as Mb, but by recombination rather than by letters of DNA, which is what says how much a shared segment means for relationship. On average about 1 Mb per cM, varying along the chromosome.',
 as:'The code the assertion names; it can go deeper than the level shown.',
 sup:'The model\'s belief, computed without this assertion, that the segment\'s copy is under its code. Against the prior (a coin toss between the codes): well above it agrees, well below it dissents.'};
const th=(k,t,n)=>`<th class="help${n?' n':''}" title="${esc(TH[k])}">${t}</th>`;
const DONORS=Object.keys(D.blocks).sort();
const LEFT=(D.left||[]).length?`<p class="meta">Not painted: ${D.left.map(([n,w])=>`${esc(n)} (${esc(w)})`).join('; ')}.</p>`:'';
function state(){const h=new URLSearchParams(location.hash.slice(1));let d=h.get('d');if(!D.blocks[d])d=DONORS[0];
 const ms=Object.keys(D.blocks[d]).sort((a,b)=>(b==='siblings')-(a==='siblings'));let m=h.get('m');if(!ms.includes(m))m=ms[0];
 const c=(h.get('c')||'').replace(/[^FM]/g,'');let l=h.get('l')||String(Math.max(2,Math.min(3,c.length)));if(!D.blocks[d][m][l])l='2';
 let v=h.get('v');if(!VER[v]&&v!=='all')v='dissents';return {d,m,l,ms,c,v}}
function link(s,k,v){const h=new URLSearchParams({d:s.d,l:s.l,m:s.m,v:s.v});if(s.c)h.set('c',s.c);if(v==null)h.delete(k);else h.set(k,v);return '#'+h}
function go(k,v,push){const u=link(state(),k,v);if(push)location.hash=u;else{history.replaceState(null,'',u);render()}}
function seg(id,opts,cur,k,push,title){document.getElementById(id).innerHTML=opts.map(([v,t,dis])=>
 `<button data-v="${esc(v)}" class="${v===cur?'on':''}"${dis?' disabled':''} title="${esc(title||'')}">${esc(t)}</button>`).join('');
 document.getElementById(id).onclick=e=>{const b=e.target.closest('button');if(b&&!b.disabled)go(k,b.dataset.v,push)}}
// a position in cM, interpolated between the block ends of its copy
function toCm(bl,chrom,side,bp){const r=bl.filter(b=>b[0]===chrom&&b[1]===side);for(const b of r)if(bp>=b[4]&&bp<=b[5])
 return b[2]+(b[5]>b[4]?(bp-b[4])/(b[5]-b[4])*(b[3]-b[2]):0);for(let i=1;i<r.length;i++)if(bp<r[i][4])return (r[i-1][3]+r[i][2])/2;
 return bp<(r[0]||[0,0,0,0,0])[4]?0:(r[r.length-1]||[0,0,0,0])[3]}
// held out: the code in focus, its line above it, or its line below it
const held=(s,code)=>!s.c||code.startsWith(s.c)||s.c.startsWith(code);
function render(){if(!DONORS.length){document.querySelector('main').innerHTML=`<section><h2>No donor to paint</h2><p>${esc(D.none||'No donor here is the proband or a full sibling, whose copies the lineage codes describe.')}</p>${LEFT}</section>`;return}
 const s=state(),bl=D.blocks[s.d][s.m][s.l],L=+s.l,prior=1/2**(L-1);
 seg('donors',DONORS.map(d=>[d,D.names[d]]),s.d,'d',true,'The donor in focus');
 seg('levels',[['2','grandparents',!D.blocks[s.d][s.m]['2']],['3','great-grandparents',!D.blocks[s.d][s.m]['3']]],s.l,'l',false,'How far back the codes go');
 // single donor always applies; the siblings model only with phased full siblings, and is then the default
 seg('models',['single','siblings'].map(m=>[m,m==='siblings'?'siblings model':'single donor',!s.ms.includes(m)]),s.m,'m',false,'Which copy model painted the blocks: this donor alone, or the siblings modelled together through their shared phasing (needs raw kits for full siblings; preferred when there)');
 const F=document.getElementById('focus');F.innerHTML=s.c?`<span class="chip" style="background:${col(s.c)}"></span><span class="code">${s.c}</span> ${who(s.c)} <span class="meta">${esc(yrs(D.anc[s.c]))}</span><a title="Show every ancestor">✕</a>`:'';
 if(s.c)F.querySelector('a').onclick=()=>go('c',null,true);
 const V=D.verdicts.filter(v=>v[0]===s.d&&v[1]===s.m).map(v=>({src:v[2],match:v[3],chrom:v[4],bp:v[5],code:v[6],sup:v[7],ver:v[8],cM:v[9]}));
 for(const v of V){v.x=toCm(bl,v.chrom,v.code[0],v.bp);v.x2=v.x+(v.cM||0)}
 const shown=v=>(s.v==='all'||v.ver===s.v)&&held(s,v.code.slice(0,L));
 // counts first
 const tot={F:0,M:0},by={};for(const b of bl){const w=b[3]-b[2];tot[b[1]]+=w;const o=by[b[6]]??={cm:0,sure:0};o.cm+=w;if(b[7]>=D.sure)o.sure+=w}
 const codes=Object.keys(D.col).filter(c=>c.length===L).sort();
 document.getElementById('counts').innerHTML=`<h2>${esc(D.names[s.d])}: share of each copy by ${L===2?'grandparent':'great-grandparent'} (${s.m==='siblings'?'siblings model':'single donor'})</h2><table><tr>${th('code','Code')}${th('anc','Ancestor')}${th('bar','Share of the copy')}${th('share','Share',1)}${th('sure','Sure',1)}${th('agree','Assertions agree',1)}${th('conf','dissent',1)}</tr>`+
  codes.map(c=>{const o=by[c]||{cm:0,sure:0},t=tot[c[0]]||1,a=D.anc[c],vs=V.filter(v=>v.code.startsWith(c)),ag=vs.filter(v=>v.ver==='agrees').length,cf=vs.filter(v=>v.ver==='dissents').length;
   return `<tr${s.c&&c.startsWith(s.c)?' class="on"':''}><td><span class="chip" style="background:${col(c)}"></span><a class="code" href="${link(s,'c',c)}" title="Hold out this ancestor">${c}</a></td><td>${a?`<a href="family.html#p=${encodeURIComponent(a[0])}">${who(c)}</a> <span class="meta">${esc(yrs(a))}</span>`:who(c)}</td>`+
    `<td><div class="share" title="Expected ${pct(prior)}"><i style="width:${100*o.cm/t}%;background:${col(c)}"></i><b style="left:${100*prior}%"></b></div></td>`+
    `<td class="n">${pct(o.cm/t)}</td><td class="n">${pct(o.sure/t)}</td><td class="n">${ag}</td><td class="n${cf?' bad':''}">${cf}</td></tr>`}).join('')+'</table>'+
  `<p class="legend"><span>Bar: the code's share of its copy; tick: the expected ${pct(prior)}.</span><span>A block fades from its prior (unsure) to sure.</span><span>Under each copy: the assertions listed below, as spans.</span></p>`+LEFT;
 // chromosomes
 const chroms=Object.keys(D.lengths).sort((a,b)=>(+a||99)-(+b||99)),mx=Math.max(...Object.values(D.lengths));
 const op=(p,code)=>((0.15+0.85*Math.max(0,Math.min(1,(p-prior)/(1-prior))))*(held(s,code)?1:0.2)).toFixed(2);
 const vc=v=>v.ver==='agrees'?';background:'+col(v.code.slice(0,L)):'';
 document.getElementById('chroms').innerHTML=`<h2>Chromosomes <span class="meta">paternal copy above, maternal below, each with its assertions under it; width by <span class="help" title="${esc(TH.cm)}">cM</span></span></h2>`+chroms.map(ch=>{
  const w=100*D.lengths[ch]/mx,len=D.lengths[ch];
  const track=side=>`<div class="tr" style="width:${w}%">`+bl.map((b,i)=>b[0]===ch&&b[1]===side?`<i data-i="${i}" style="left:${100*b[2]/len}%;width:${Math.max(0.3,100*(b[3]-b[2])/len)}%;background:${col(b[6])};opacity:${op(b[7],b[6])}"></i>`:'').join('')+'</div>'+
   `<div class="ln" style="width:${w}%">`+V.map((v,i)=>v.chrom===ch&&v.code[0]===side&&shown(v)?`<b data-v="${i}" class="${v.ver}" style="left:${100*v.x/len}%;width:${100*(v.x2-v.x)/len}%${vc(v)}"></b>`:'').join('')+'</div>';
  return `<div class="cr"><span>${ch}</span><div>${track('F')}${track('M')}</div></div>`}).join('');
 // the assertions with the chosen verdict, longest first
 const C=V.filter(shown).sort((a,b)=>(b.cM||0)-(a.cM||0)),n=k=>V.filter(v=>(k==='all'||v.ver===k)&&held(s,v.code.slice(0,L))).length;
 const WHY={dissents:'the model, judged without each one, places its segment under another code: the work to do',agrees:'the model, judged without each one, places its segment under its code',unclear:'the model cannot tell without them',all:'every verdict'};
 document.getElementById('list').innerHTML=`<h2>Assertions <span class="seg" id="vers"></span> <span class="meta">${WHY[s.v]}</span></h2>`+(C.length?
  `<table><tr>${th('match','Match')}${th('src','Source')}${th('chr','Chr',1)}${th('mb','Mb',1)}${th('cm','cM',1)}${th('as','Asserted')}${th('sup','Support',1)}</tr>`+C.map(v=>
  `<tr><td>${esc(v.match)}</td><td class="meta" title="${esc(SRC[v.src]||'')}">${esc(v.src)}</td><td class="n">${esc(v.chrom)}</td><td class="n">${(v.bp/1e6).toFixed(1)}</td><td class="n">${v.cM??''}</td><td><span class="chip" style="background:${col(v.code.slice(0,L))}"></span><span class="code">${esc(v.code)}</span> ${who(v.code.slice(0,L))}</td><td class="n${v.ver==='dissents'?' bad':''}">${v.sup.toFixed(2)}</td></tr>`).join('')+'</table>':'<p class="meta">None.</p>');
 seg('vers',[...Object.keys(VER),'all'].map(k=>[k,`${k} (${n(k)})`]),s.v,'v',false,'Which verdicts to list and draw under the copies');
 const tip=document.getElementById('tip'),ch=document.getElementById('chroms');
 ch.onmousemove=e=>{const t=e.target;let h='';
  if(t.dataset.i!=null){const b=bl[+t.dataset.i],a=D.anc[b[6]],in_=V.filter(v=>v.chrom===b[0]&&v.code[0]===b[1]&&v.bp>=b[4]&&v.bp<=b[5]),k=x=>in_.filter(v=>v.ver===x).length;
   h=`<b><span class="code">${b[6]}</span> ${who(b[6])}</b> <span class="meta">${esc(yrs(a))}</span><br>chr ${b[0]}, ${b[2]}–${b[3]} cM (${(b[4]/1e6).toFixed(1)}–${(b[5]/1e6).toFixed(1)} Mb)<br>posterior ${b[7].toFixed(2)} (prior ${prior.toFixed(2)})<br>assertions starting here: ${in_.length?`${k('agrees')} agree, ${k('unclear')} unclear, <span class="${k('dissents')?'bad':''}">${k('dissents')} dissent</span>`:'none'}`+(a?'<br><span class="meta">click: the family page on them</span>':'')}
  else if(t.dataset.v!=null){const v=V[+t.dataset.v];h=`<b>${esc(v.match)}</b> <span class="meta">${esc(v.src)}</span><br>asserted <span class="code">${esc(v.code)}</span> ${who(v.code.slice(0,L))}<br>${v.cM??'?'} cM from ${(v.bp/1e6).toFixed(1)} Mb<br>verdict: <span class="${v.ver==='dissents'?'bad':''}">${v.ver}</span>, support without it ${v.sup.toFixed(2)}`}
  tip.style.display=h?'block':'none';if(h){tip.innerHTML=h;tip.style.left=Math.min(e.clientX+12,innerWidth-350)+'px';tip.style.top=(e.clientY+14)+'px'}};
 ch.onmouseleave=()=>tip.style.display='none';
 ch.onclick=e=>{const i=e.target.dataset.i;if(i==null)return;const a=D.anc[bl[+i][6]];if(a)location.href='family.html#p='+encodeURIComponent(a[0])};
}
window.addEventListener('hashchange',render);render();
</script>__DATA__</body></html>
"""


def _main(argv):
    import config
    import familyview
    import outputs
    import tree_store
    cfg = config.load()
    D = cfg["data_dir"]
    path = config.path(cfg, "genome.html")
    if not outputs.has(D, "copy_model_blocks.csv"):
        write(path, dict(blocks={}, left=[], none="The copy model has not run: it needs segment lists "
                         "for the proband or a full sibling, and lineage assertions (tree links or "
                         "documented relatives) to anchor them."))
        print(f"no copy_model_blocks.csv: an empty page saying so -> {path}")
        return
    blocks = outputs.read(D, "copy_model_blocks.csv", dtype={"chrom": str})
    verdicts = (outputs.read(D, "copy_model_verdicts.csv", dtype={"chrom": str})
                if outputs.has(D, "copy_model_verdicts.csv") else None)
    db, root = tree_store.default_store().db, familyview.proband_id(cfg)
    anc = ancestors(db, root)
    subj = sorted(blocks.subject.unique())
    why = fit(parents(db), root, {d: (cfg.get("people", {}).get(d) or {}).get("mh") for d in subj})
    left = [(config.display_name(cfg, d), why[d]) for d in subj if why[d]]
    blocks = blocks[blocks.subject.map(lambda d: why[d] is None)]
    if verdicts is not None:
        verdicts = verdicts[verdicts.subject.map(lambda d: why.get(d, "") is None)]
    matches = (dict(outputs.read(D, "copy_model_placed_matches.csv", usecols=["match_key", "match"]).values)
               if outputs.has(D, "copy_model_placed_matches.csv") else None)
    data = collect(blocks, verdicts, anc, {d: config.display_name(cfg, d) for d in blocks.subject.unique()},
                   matches, left)
    write(path, data)
    print(f"{len(data['blocks'])} donors ({len(left)} left out), {len(blocks)} blocks, {len(data['verdicts'])} verdicts -> {path}")


if __name__ == "__main__":
    _main(sys.argv[1:])
