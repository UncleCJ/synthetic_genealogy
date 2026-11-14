"""
The genome lens, donor focus (docs/lenses.md): one donor's two copies of
each autosome, painted with the copy model's blocks in the lineage colours.
A block fades with its posterior, from its prior (a coin toss between the
codes on its copy) to sure; a tick under a copy is an assertion the model
rejects without it (leave-one-out "conflicts"), the work to do.

    python3 genomeview.py       # writes data/output/genome.html (private: names)

Counts first: per code, its share of its copy against the expected, how
much of it is sure (block posterior >= 0.9), and the verdicts on the
assertions under it. Hover a block for its ancestor, span and the
assertions in it; click it to open the family page on that ancestor.
Below, the conflicting assertions, longest first.

Link scheme (after #): d=<donor>&l=<2|3>&m=<siblings|single>. A new donor
adds a history step; level and model replace it.

Sketch: reads copy_model_blocks.csv and copy_model_verdicts.csv (rebuilt)
and the store for the ancestors' names. Codes are read from the proband,
as the copy model's are, which holds for the proband and full siblings.
Positions are in cM; an assertion's start (bp) is placed by interpolating
between the block ends of its copy.
"""
import sys

import lineage

SURE = 0.9


def ancestors(db, root, depth=3):
    """code -> [store id, name, birth, death] for root's ancestors to depth
    (pedigree collapse: one person under several codes)."""
    import familyview
    import tree_store
    from intervals import years
    par = {}
    fams = {fid: (h, w) for fid, h, w in db.execute("select id, husb, wife from family")}
    for fid, child in db.execute("select family, child from child order by rowid"):
        par.setdefault(child, fams.get(fid, (None, None)))
    codes = familyview.lineage_codes(par, root, depth)
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


def collect(blocks, verdicts, anc, names=None, matches=None):
    """The lens's data from the copy model's tables (DataFrames; verdicts may
    be None), the ancestors (ancestors()), the donors' display names and
    match key -> match name (keys in claim ids are vendor ids)."""
    lengths = blocks.groupby(blocks.chrom.astype(str)).end_cm.max().round(1).to_dict()
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
        V.append([r.subject, r.model, src, (matches or {}).get(match, match), str(r.chrom), bp, r.code, float(r.support),
                  r.verdict, None if r.cM != r.cM else round(float(r.cM), 1)])
    codes = {c for c in blocks.lineage.unique()} | {c[:k] for c in anc for k in range(1, len(c) + 1)}
    col = {c: [lineage.color(c), lineage.color(c, dark=True)] for c in sorted(codes)}
    return dict(blocks=B, names={d: (names or {}).get(d, d) for d in B}, verdicts=V, lengths=lengths, anc=anc, col=col, sure=SURE)


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
.seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.seg button{font:inherit;color:var(--fg);background:var(--card);border:0;border-left:1px solid var(--line);padding:3px 9px;cursor:pointer}
.seg button:first-child{border-left:0}.seg button.on{background:var(--sel);font-weight:600}.seg button:disabled{color:var(--mut);cursor:default}
main{padding:12px 16px;display:grid;gap:16px;max-width:1200px}main>section+section{border-top:1px solid var(--line);padding-top:12px}
table{border-collapse:collapse}td,th{padding:2px 12px 2px 0;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:12px}.n{text-align:right;font-variant-numeric:tabular-nums}
.chip{display:inline-block;width:12px;height:12px;border-radius:2px;vertical-align:-2px;margin-right:6px}
.code{font-family:ui-monospace,monospace;font-size:11px}.meta{color:var(--mut);font-size:11px}
a{color:var(--acc)}.bad{color:var(--bad)}
/* the counts: a bar for the share of the copy, a tick where the expected share falls */
.share{position:relative;width:120px;height:10px;background:var(--line);border-radius:2px}.share i{position:absolute;top:0;bottom:0;left:0;border-radius:2px}
.share b{position:absolute;top:-2px;bottom:-2px;width:2px;background:var(--fg)}
/* chromosomes: a row each, the paternal copy above the maternal, width by cM */
.cr{display:grid;grid-template-columns:28px 1fr;align-items:center;gap:6px;margin-bottom:5px}.cr>span{color:var(--mut);text-align:right;font-variant-numeric:tabular-nums}
.tr{position:relative;height:10px;background:var(--line);border-radius:2px;margin:1px 0}.tr i{position:absolute;top:0;bottom:0;cursor:pointer}
.tr i:hover{outline:1.5px solid var(--fg);z-index:1}.tr b{position:absolute;bottom:-4px;width:2px;height:6px;margin-left:-1px;background:var(--bad);z-index:2;cursor:help}
.legend{display:flex;gap:16px;flex-wrap:wrap;align-items:center;color:var(--mut);font-size:12px}
#tip{position:fixed;pointer-events:none;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:6px 8px;max-width:340px;font-size:12px;display:none;z-index:3;box-shadow:0 2px 8px #0002}
</style></head><body>
<header>__NAV__<h1>Genome</h1><span class="seg" id="donors"></span><span class="seg" id="levels"></span><span class="seg" id="models"></span></header>
<main><section id="counts"></section><section id="chroms"></section><section id="conf"></section></main><div id="tip"></div>
<script type="text/plain" id="view-js">
const D=DATA;const DARK=matchMedia('(prefers-color-scheme:dark)').matches;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const col=c=>(D.col[c]||['#8f8a80','#8f8a80'])[DARK?1:0];
const pct=x=>(100*x).toFixed(x<0.1?1:0)+'%';
const yrs=a=>a&&(a[2]||a[3])?`${a[2]??''}–${a[3]??''}`:'';
const who=c=>{const a=D.anc[c];return a?(a[1]||'<i>unnamed</i>'):'<i>no one in the tree</i>'};
const DONORS=Object.keys(D.blocks).sort();
function state(){const h=new URLSearchParams(location.hash.slice(1));let d=h.get('d');if(!D.blocks[d])d=DONORS[0];
 const ms=Object.keys(D.blocks[d]).sort((a,b)=>(b==='siblings')-(a==='siblings'));let m=h.get('m');if(!ms.includes(m))m=ms[0];
 let l=h.get('l');if(!D.blocks[d][m][l])l='2';return {d,m,l,ms}}
function go(k,v,push){const s=state(),h=new URLSearchParams({d:s.d,l:s.l,m:s.m});h.set(k,v);
 const u='#'+h.toString();if(push)location.hash=u;else{history.replaceState(null,'',u);render()}}
function seg(id,opts,cur,k,push,title){document.getElementById(id).innerHTML=opts.map(([v,t,dis])=>
 `<button data-v="${esc(v)}" class="${v===cur?'on':''}"${dis?' disabled':''} title="${esc(title||'')}">${esc(t)}</button>`).join('');
 document.getElementById(id).onclick=e=>{const b=e.target.closest('button');if(b&&!b.disabled)go(k,b.dataset.v,push)}}
// an assertion's start in cM, interpolated between the block ends of its copy
function toCm(bl,chrom,side,bp){const r=bl.filter(b=>b[0]===chrom&&b[1]===side);for(const b of r)if(bp>=b[4]&&bp<=b[5])
 return b[2]+(b[5]>b[4]?(bp-b[4])/(b[5]-b[4])*(b[3]-b[2]):0);for(let i=1;i<r.length;i++)if(bp<r[i][4])return (r[i-1][3]+r[i][2])/2;
 return bp<(r[0]||[0,0,0,0,0])[4]?0:(r[r.length-1]||[0,0,0,0])[3]}
function render(){const s=state(),bl=D.blocks[s.d][s.m][s.l],L=+s.l,prior=1/2**(L-1);
 seg('donors',DONORS.map(d=>[d,D.names[d]]),s.d,'d',true,'The donor in focus');
 seg('levels',[['2','grandparents',!D.blocks[s.d][s.m]['2']],['3','great-grandparents',!D.blocks[s.d][s.m]['3']]],s.l,'l',false,'How far back the codes go');
 seg('models',['siblings','single'].map(m=>[m,m==='siblings'?'siblings model':'single donor',!s.ms.includes(m)]),s.m,'m',false,'Which copy model painted the blocks');
 const V=D.verdicts.filter(v=>v[0]===s.d&&v[1]===s.m).map(v=>({src:v[2],match:v[3],chrom:v[4],bp:v[5],code:v[6],sup:v[7],ver:v[8],cM:v[9]}));
 for(const v of V)v.x=toCm(bl,v.chrom,v.code[0],v.bp);
 // counts first
 const tot={F:0,M:0},by={};for(const b of bl){const w=b[3]-b[2];tot[b[1]]+=w;const o=by[b[6]]??={cm:0,sure:0};o.cm+=w;if(b[7]>=D.sure)o.sure+=w}
 const codes=Object.keys(D.col).filter(c=>c.length===L).sort();
 document.getElementById('counts').innerHTML=`<h2>${esc(D.names[s.d])}: share of each copy by ${L===2?'grandparent':'great-grandparent'} (${s.m==='siblings'?'siblings model':'single donor'})</h2><table><tr><th>Code</th><th>Ancestor</th><th>Share of the copy</th><th class="n">Share</th><th class="n">Sure</th><th class="n">Assertions agree</th><th class="n">conflict</th></tr>`+
  codes.map(c=>{const o=by[c]||{cm:0,sure:0},t=tot[c[0]]||1,a=D.anc[c],vs=V.filter(v=>v.code.startsWith(c)),ag=vs.filter(v=>v.ver==='agrees').length,cf=vs.filter(v=>v.ver==='conflicts').length;
   return `<tr><td><span class="chip" style="background:${col(c)}"></span><span class="code">${c}</span></td><td>${a?`<a href="family.html#p=${encodeURIComponent(a[0])}">${who(c)}</a> <span class="meta">${esc(yrs(a))}</span>`:who(c)}</td>`+
    `<td><div class="share" title="Expected ${pct(prior)}"><i style="width:${100*o.cm/t}%;background:${col(c)}"></i><b style="left:${100*prior}%"></b></div></td>`+
    `<td class="n">${pct(o.cm/t)}</td><td class="n" title="Of the copy, in blocks with posterior ≥ ${D.sure}">${pct(o.sure/t)}</td><td class="n">${ag}</td><td class="n${cf?' bad':''}">${cf}</td></tr>`}).join('')+'</table>'+
  `<p class="legend"><span>Bar: the code's share of its copy; tick: the expected ${pct(prior)}.</span><span>A block fades from its prior (unsure) to sure.</span><span><span class="chip" style="background:var(--bad);width:3px"></span>an assertion the model rejects without it</span></p>`;
 // chromosomes
 const chroms=Object.keys(D.lengths).sort((a,b)=>(+a||99)-(+b||99)),mx=Math.max(...Object.values(D.lengths));
 const op=p=>(0.15+0.85*Math.max(0,Math.min(1,(p-prior)/(1-prior)))).toFixed(2);
 document.getElementById('chroms').innerHTML='<h2>Chromosomes <span class="meta">paternal copy above, maternal below; width by cM</span></h2>'+chroms.map(ch=>{
  const w=100*D.lengths[ch]/mx,len=D.lengths[ch];
  const track=side=>`<div class="tr" style="width:${w}%">`+bl.map((b,i)=>b[0]===ch&&b[1]===side?`<i data-i="${i}" style="left:${100*b[2]/len}%;width:${Math.max(0.3,100*(b[3]-b[2])/len)}%;background:${col(b[6])};opacity:${op(b[7])}"></i>`:'').join('')+
   V.map((v,i)=>v.chrom===ch&&v.code[0]===side&&v.ver==='conflicts'?`<b data-v="${i}" style="left:${100*v.x/len}%"></b>`:'').join('')+'</div>';
  return `<div class="cr"><span>${ch}</span><div>${track('F')}${track('M')}</div></div>`}).join('');
 // the conflicts, longest first
 const C=V.filter(v=>v.ver==='conflicts').sort((a,b)=>(b.cM||0)-(a.cM||0));
 document.getElementById('conf').innerHTML=`<h2>Conflicting assertions (${C.length}) <span class="meta">the model, without the assertion, doubts its copy is under its code</span></h2>`+(C.length?
  '<table><tr><th>Match</th><th>Source</th><th class="n">Chr</th><th class="n">Mb</th><th class="n">cM</th><th>Asserted</th><th class="n">Support</th></tr>'+C.map(v=>
  `<tr><td>${esc(v.match)}</td><td class="meta">${esc(v.src)}</td><td class="n">${esc(v.chrom)}</td><td class="n">${(v.bp/1e6).toFixed(1)}</td><td class="n">${v.cM??''}</td><td><span class="chip" style="background:${col(v.code.slice(0,L))}"></span><span class="code">${esc(v.code)}</span> ${who(v.code.slice(0,L))}</td><td class="n">${v.sup.toFixed(2)}</td></tr>`).join('')+'</table>':'<p class="meta">None.</p>');
 const tip=document.getElementById('tip'),ch=document.getElementById('chroms');
 ch.onmousemove=e=>{const t=e.target;let h='';
  if(t.dataset.i!=null){const b=bl[+t.dataset.i],a=D.anc[b[6]],in_=V.filter(v=>v.chrom===b[0]&&v.code[0]===b[1]&&v.bp>=b[4]&&v.bp<=b[5]),n=k=>in_.filter(v=>v.ver===k).length;
   h=`<b><span class="code">${b[6]}</span> ${who(b[6])}</b> <span class="meta">${esc(yrs(a))}</span><br>chr ${b[0]}, ${b[2]}–${b[3]} cM (${(b[4]/1e6).toFixed(1)}–${(b[5]/1e6).toFixed(1)} Mb)<br>posterior ${b[7].toFixed(2)} (prior ${prior.toFixed(2)})<br>assertions starting here: ${in_.length?`${n('agrees')} agree, ${n('unclear')} unclear, <span class="${n('conflicts')?'bad':''}">${n('conflicts')} conflict</span>`:'none'}`+(a?'<br><span class="meta">click: the family page on them</span>':'')}
  else if(t.dataset.v!=null){const v=V[+t.dataset.v];h=`<b>${esc(v.match)}</b> <span class="meta">${esc(v.src)}</span><br>asserted <span class="code">${esc(v.code)}</span> ${who(v.code.slice(0,L))}, ${v.cM??'?'} cM from ${(v.bp/1e6).toFixed(1)} Mb<br>support without it ${v.sup.toFixed(2)}`}
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
    if not outputs.has(D, "copy_model_blocks.csv"):
        print("no copy_model_blocks.csv: run copy_model.py first; skipped")
        return
    blocks = outputs.read(D, "copy_model_blocks.csv", dtype={"chrom": str})
    verdicts = (outputs.read(D, "copy_model_verdicts.csv", dtype={"chrom": str})
                if outputs.has(D, "copy_model_verdicts.csv") else None)
    anc = ancestors(tree_store.default_store().db, familyview.proband_id(cfg))
    matches = (dict(outputs.read(D, "copy_model_placed_matches.csv", usecols=["match_key", "match"]).values)
               if outputs.has(D, "copy_model_placed_matches.csv") else None)
    data = collect(blocks, verdicts, anc, {d: config.display_name(cfg, d) for d in blocks.subject.unique()}, matches)
    path = config.path(cfg, "genome.html")
    write(path, data)
    print(f"{len(data['blocks'])} donors, {len(blocks)} blocks, {len(data['verdicts'])} verdicts -> {path}")


if __name__ == "__main__":
    _main(sys.argv[1:])
