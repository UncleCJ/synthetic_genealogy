"""Browse the pipeline's results without Claude: an index page and a small
web server for data/output (docs/data.md), with the hand-kept notes
(data/notes: research entries, errata) read-only under /notes/.

    python3 serve.py                 # http://127.0.0.1:8000, opens the browser
    python3 serve.py --port 8765 --no-browser
    python3 serve.py --lan           # also reachable from the local network
    python3 serve.py --index         # only (re)write output/index.html
    python3 serve.py --dir FOLDER    # an unzipped snapshot (backup.py snapshot),
                                     # without family.toml or the rest of the repo

Markdown files open as formatted pages that follow changes, CSV files as
sortable, filterable tables; add ?raw=1 for the file itself. It listens on
127.0.0.1 only (the pages hold names and DNA results); --lan has no password,
so use it on a home network only. Any static server works too, e.g.
`python -m http.server 8000 --directory data/output`.
"""
import os
import argparse
import html
import http.server
import re
import threading
import webbrowser
from datetime import datetime
from functools import partial
from pathlib import Path

# What each known output is, for the index page (others are listed by name).
KNOWN = {
    "family.html": "One person in focus: pedigree four generations up, close family, counts; click to move",
    "genome.html": "One donor's matches, filterable, and their segments on the donor's copies, painted by the copy model where it applies",
    "geography.html": "Map of every located event and record, with filters; links open it pre-filtered",
    "archives.html": "Archives: parishes, their volumes by series and page, farms on a map and across volumes",
    "revelations.md": "Placement of matches on grandparents, with cross-checks",
    "prospects.md": "Close matches not yet in the tree, with side and branch hints",
    "relationship_check.md": "Confirmed relatives: expected vs observed shared cM",
    "icw_report.md": "Shared-match (ICW) evidence against the placement",
    "places_rules.html": "Place recognition: how a place string becomes a parish, village or farm, and which rule resolved each",
    "gazetteer_todo.md": "Place-name variants to review, place strings with no parish",
    "errata_report.md": "Status of corrections and notes kept beside the MyHeritage tree",
    "pipeline_log.md": "What each pipeline step did, per run",
}


def _known(name):
    """What a known output is; a kept report (match_view.py --report) by its prefix."""
    if name.startswith("report_") and name.endswith(".html"):
        return "Match-centred chromosome browser and research report"
    return KNOWN.get(name)
GROUPS = [("Views", (".html",)), ("Reports", (".md",)), ("Tables", (".csv", ".gexf")),
          ("Images", (".png", ".svg")), ("Other", ())]


def _title(path):
    if path.suffix == ".html":
        m = re.search(r"<title>(.*?)</title>", path.read_text(encoding="utf-8", errors="ignore")[:4000], re.S)
        if m:
            return m.group(1).strip()
    if path.suffix == ".md":
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[:5]:
            if line.startswith("#"):
                return line.lstrip("# ").strip()
    return ""


def _notes_section(notes):
    """The hand-kept notes (not outputs, but read alongside them): the
    research log's index first, then each entry by title."""
    if not notes or not notes.is_dir():
        return ""
    files = [p for p in notes.rglob("*") if p.is_file() and p.suffix in (".md", ".toml", ".csv")]
    files.sort(key=lambda p: (p.name != "INDEX.md", p.parent != notes, str(p.relative_to(notes))))
    rows = "".join(
        f'<tr><td><a href="notes/{html.escape(str(p.relative_to(notes)))}">{html.escape(str(p.relative_to(notes)))}</a></td>'
        f'<td>{html.escape(_title(p))}</td>'
        f'<td class="m">{datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M}</td></tr>'
        for p in files)
    return (f'<h2 id="notes">Research notes</h2><p class="m">Kept by hand in data/notes (edit the files, '
            f'or through research_log.py); shown read-only.</p><table>{rows}</table>')


def write_index(out, notes=None):
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "index.html"
                   and p.relative_to(out).parts[0] not in ("notes", "input", "serve.py"))
    sections = []
    used = set()
    for name, exts in GROUPS:
        group = [p for p in files if p not in used and (not exts or p.suffix in exts)]
        used.update(group)
        if not group:
            continue
        group.sort(key=lambda p: (not _known(p.name), -p.stat().st_mtime))
        rows = "".join(
            f'<tr><td><a href="{html.escape(str(p.relative_to(out)))}">{html.escape(str(p.relative_to(out)))}</a></td>'
            f'<td>{html.escape(_known(p.name) or _title(p))}</td>'
            f'<td class="m">{datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M}</td></tr>'
            for p in group)
        sections.append(f"<h2>{name}</h2><table>{rows}</table>")
        if name == "Views":
            sections.append(_notes_section(notes))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Genealogy outputs</title>
<style>
:root{{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#6b6760;--line:#e2ded6;--acc:#2f6db5}}
@media (prefers-color-scheme:dark){{:root{{--bg:#171614;--fg:#ece9e2;--mut:#9b968c;--line:#34312c;--acc:#6ea4e6}}}}
body{{margin:0 auto;max-width:980px;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}}
h1{{font-size:20px}}h2{{font-size:15px;margin-top:22px}}a{{color:var(--acc)}}
table{{border-collapse:collapse;width:100%}}td{{border-top:1px solid var(--line);padding:4px 8px;vertical-align:top}}
td.m,.m{{color:var(--mut);white-space:nowrap}}
</style></head><body><h1>Genealogy outputs</h1>
<p class="m">Generated by the pipeline into data/output; this page by serve.py, {datetime.now():%Y-%m-%d %H:%M}.
Private: names and DNA results. <a href="#notes">Research notes</a></p>
<p class="m" id="asfile" hidden>Opened as a file: the views work, but the Geography map, formatted reports and tables,
and the research notes need the server (<code>python3 serve.py</code>).</p>
<script>if(location.protocol==='file:')document.getElementById('asfile').hidden=false</script>{''.join(sections)}</body></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")


STYLE = """:root{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#6b6760;--line:#e2ded6;--acc:#2f6db5;--code:#f1eee8;--sel:#fff1bf}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ece9e2;--mut:#9b968c;--line:#34312c;--acc:#6ea4e6;--code:#24221f;--sel:#4a4220}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,sans-serif}
.top{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:8px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;z-index:2}
.top a{color:var(--acc)}.m{color:var(--mut);font-size:13px}
main{max-width:980px;margin:0 auto;padding:8px 20px 60px}
a{color:var(--acc)}h1{font-size:24px}h2{font-size:19px;margin-top:28px}h3{font-size:16px}
code{background:var(--code);padding:1px 4px;border-radius:4px;font-size:90%}
pre{background:var(--code);padding:10px 12px;border-radius:6px;overflow:auto;font-size:13px;line-height:1.4}pre code{background:none;padding:0}
table{border-collapse:collapse;margin:10px 0;font-size:14px}th,td{border:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}
th{background:var(--code)}blockquote{border-left:3px solid var(--line);margin:0;padding:0 12px;color:var(--mut)}
.badge{border:1px solid var(--line);border-radius:10px;padding:1px 8px;font-size:12px}.badge.run{border-color:#d49a2a;color:#d49a2a}
input{font:inherit;border:1px solid var(--line);border-radius:6px;padding:4px 8px;background:var(--bg);color:var(--fg)}
.csv{max-width:none}.csv table{font-size:13px}.csv th{position:sticky;top:44px;cursor:pointer;white-space:nowrap}
.csv td{white-space:nowrap;max-width:420px;overflow:hidden;text-overflow:ellipsis}.csv tr:hover td{background:var(--sel)}
.num{text-align:right;font-variant-numeric:tabular-nums}"""

MD_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>{style}</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/4.3.0/marked.min.js"></script></head><body>
<div class="top"><a href="/">← outputs</a><b>{title}</b><span id="st" class="m"></span>
<label class="m"><input type="checkbox" id="live" {live}> follow changes</label><a class="m" href="?raw=1">raw</a></div>
<main id="doc"><p class="m">Loading…</p></main>
<script>
let last=null;
async function load(){{
  const r=await fetch(location.pathname+'?raw=1',{{cache:'no-store'}});const t=await r.text();
  const st=document.getElementById('st');
  const running=/[*][*]Status: running[*][*]/.test(t);
  st.innerHTML=(running?'<span class="badge run">running</span> ':'')+'updated '+new Date().toLocaleTimeString();
  if(t===last)return;last=t;
  const atEnd=window.innerHeight+window.scrollY>=document.body.scrollHeight-40;
  document.getElementById('doc').innerHTML=window.marked?marked.parse(t):'<pre>'+t.replace(/[&<]/g,c=>c=='&'?'&amp;':'&lt;')+'</pre>';
  if(atEnd&&running)window.scrollTo(0,document.body.scrollHeight);
}}
load();setInterval(()=>{{if(document.getElementById('live').checked)load()}},3000);
</script></body></html>"""

CSV_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>{style}</style></head><body>
<div class="top"><a href="/">← outputs</a><b>{title}</b><span class="m" id="n"></span>
<input id="q" placeholder="filter rows…" size="28"><a class="m" href="?raw=1">raw</a></div>
<main class="csv"><table id="t"></table><p class="m" id="more"></p></main>
<script>
const H={header},R={rows};let S={{k:-1,d:1}};const LIMIT=2000;
const isnum=R.length?H.map((_,i)=>R.slice(0,200).every(r=>r[i]===''||!isNaN(+r[i]))):[];
const esc=s=>String(s).replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
function draw(){{const q=document.getElementById('q').value.toLowerCase();
 let rows=q?R.filter(r=>r.join(' ').toLowerCase().includes(q)):R.slice();
 if(S.k>=0)rows.sort((a,b)=>{{const x=a[S.k],y=b[S.k];return (isnum[S.k]?(+x)-(+y):String(x).localeCompare(String(y)))*S.d}});
 document.getElementById('n').textContent=rows.length+' of '+R.length+' rows'+({truncated}?' (file has more; see raw)':'');
 document.getElementById('t').innerHTML='<tr>'+H.map((h,i)=>`<th data-i="${{i}}">${{esc(h)}}${{S.k==i?(S.d>0?' ▲':' ▼'):''}}</th>`).join('')+'</tr>'+
  rows.slice(0,LIMIT).map(r=>'<tr>'+r.map((c,i)=>`<td class="${{isnum[i]?'num':''}}" title="${{esc(c)}}">${{esc(c)}}</td>`).join('')+'</tr>').join('');
 document.getElementById('more').textContent=rows.length>LIMIT?`Showing ${{LIMIT}} of ${{rows.length}}; filter or sort to see others.`:'';}}
document.getElementById('t').addEventListener('click',e=>{{const th=e.target.closest('th');if(!th)return;const i=+th.dataset.i;S=S.k==i?{{k:i,d:-S.d}}:{{k:i,d:1}};draw()}});
document.getElementById('q').addEventListener('input',draw);draw();
</script></body></html>"""

CSV_MAX_ROWS = 50000


class Handler(http.server.SimpleHTTPRequestHandler):
    """Static files, plus readable pages for Markdown (rendered, following
    changes, e.g. the pipeline log during a run) and CSV (a sortable,
    filterable table). Add ?raw=1 for the file itself."""
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".md": "text/plain; charset=utf-8", ".csv": "text/plain; charset=utf-8",
                      ".gexf": "text/plain; charset=utf-8", ".toml": "text/plain; charset=utf-8", ".html": "text/html; charset=utf-8"}

    notes = None            # data/notes, served read-only at /notes/
    archive = None          # data/archive (shelf(1)), served read-only at /archive/

    def _archived(self, p):
        """data/archive path for a request under archive/, or None. Only
        volume folders and the shelf's index files: never cookie.txt,
        login/ or the logs."""
        base = os.path.join(self.directory, "archive")
        if not self.archive or not (p == base or p.startswith(base + os.sep)):
            return None
        rel = Path(p[len(base):].lstrip(os.sep))
        ok = len(rel.parts) >= 3 or str(rel) in ("README.md", "structure.tsv")
        return self.archive / rel if ok and not rel.name.startswith(".") else Path(os.devnull + "-denied")

    def translate_path(self, path):
        p = super().translate_path(path)
        a = self._archived(p)
        if a is not None:
            return str(a)
        base = os.path.join(self.directory, "notes")
        if self.notes and (p == base or p.startswith(base + os.sep)):
            return str(self.notes) + p[len(base):]
        return p

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")    # outputs change under us
        super().end_headers()

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if self.archive and path in ("/archive/held.json", "/archive/view.html"):
            page = held(self.archive) if path.endswith(".json") else VIEW_PAGE.replace("__STYLE__", STYLE)
            data = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if path.endswith(".json") else "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if "raw=1" not in query and path.endswith((".md", ".csv")):
            f = Path(self.translate_path(path))
            if f.is_file():
                page = self._md(f) if f.suffix == ".md" else self._csv(f)
                data = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
        super().do_GET()

    def _md(self, f):
        live = "checked" if ("log" in f.name.lower() or "logs" in f.parts) else ""
        return MD_PAGE.format(title=html.escape(f.name), style=STYLE, live=live)

    def _csv(self, f):
        import csv
        import json
        text = f.read_text(encoding="utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(text.splitlines(), dialect))
        header, body = (rows[0], rows[1:]) if rows else ([], [])
        truncated = len(body) > CSV_MAX_ROWS
        width = len(header)
        body = [(r + [""] * width)[:width] for r in body[:CSV_MAX_ROWS]]
        js = lambda x: json.dumps(x, ensure_ascii=False).replace("</", "<\\/")
        return CSV_PAGE.format(title=html.escape(f.name), style=STYLE, header=js(header), rows=js(body),
                               truncated="true" if truncated else "false")


def held(root):
    """{volume id: {d: folder, n: images, f: {n: file}, t: {n: thumbnail}}}
    for the shelf in data/archive (shelf(1)), as JSON."""
    import json
    import re
    out = {}
    for vol in root.glob("*/*/volume.md"):
        d = vol.parent
        m = re.search(r"^- Bilder: (\d+)", vol.read_text(encoding="utf-8"), re.M)
        num = lambda f: str(int(f.name[5:9]))
        out[d.name.rsplit(" ", 1)[-1]] = {
            "d": str(d.relative_to(root)), "n": int(m.group(1)) if m else 0,
            "f": {num(f): f.name for f in d.glob("Bild *.jpg")},
            "t": {num(f): f"{f.parent.name}/{f.name}"     # stand-ins: thumbnail, or 1000 px scout
                  for sub in ("thumbs", "scout") for f in (d / sub).glob("Bild *.jpg")}}
    return json.dumps(out, ensure_ascii=False)


VIEW_PAGE = r"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Archive volume</title><style>__STYLE__
#strip{display:flex;flex-wrap:wrap;gap:1px;margin:8px 0}#strip a{width:7px;height:14px;background:var(--line,#ddd);display:block}
#strip a.t{background:#9ab}#strip a.f{background:#357}#strip a.on{outline:2px solid #c33}
#pic{position:relative}#pic img{max-width:100%;display:block}#pic img.t{width:100%;filter:blur(1.5px);opacity:.75}
#pic .b{position:absolute;border:1px solid rgba(200,40,40,.55);background:rgba(255,230,120,.12);cursor:help}
#pic .b:hover,#pic .b.on{background:rgba(255,230,120,.45)}#pic.nobox .b{display:none}
#lines{font:13px/1.5 ui-monospace,monospace;max-height:40vh;overflow:auto;border:1px solid var(--line,#ddd);padding:4px 8px;margin-top:8px}
#lines div{cursor:default}#lines div:hover,#lines div.on{background:#ffe9a8}#lines .c{color:#999}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.m{color:#777;font-size:13px}</style>
<p class="bar"><a href="../archives.html">Archives</a> · <b id="title"></b></p>
<p class="bar"><button id="pf" title="previous kept image">⇤</button><button id="p" title="previous image (←)">←</button>
<span id="pos"></span><button id="n" title="next image (→)">→</button><button id="nf" title="next kept image">⇥</button>
<a id="ra" target="_blank" rel="noopener">at Riksarkivet ↗</a><a id="md">volume.md</a>
<label title="raw OCR kept beside the image (shelf(1)); untuned">OCR <select id="ocr"><option value="trocr">TrOCR (handwriting)</option><option value="vision">Apple Vision</option><option value="">off</option></select></label>
<label><input type="checkbox" id="box" checked> boxes</label></p>
<div id="strip" title="dark: kept at full size, light: thumbnail stand-in, grey: not here"></div>
<p class="m" id="what"></p><div id="pic"></div><div id="lines" hidden></div>
<script>
const q=()=>Object.fromEntries(new URLSearchParams(location.hash.slice(1)));let H,V,N;
const go=n=>{location.hash='v='+V+'&n='+n};
function show(){const a=q();V=a.v;const h=H[V];if(!h){document.getElementById('title').textContent='Volume '+V+' is not on the shelf';return}
 const fs=Object.keys(h.f).map(Number).sort((x,y)=>x-y);N=+a.n||fs[0]||1;
 document.getElementById('title').textContent=h.d;document.getElementById('pos').textContent='Bild '+N+' / '+h.n;
 document.getElementById('ra').href='https://sok.riksarkivet.se/bildvisning/'+V+'_'+String(N).padStart(5,'0');
 document.getElementById('md').href=encodeURI(h.d)+'/volume.md';
 const base=encodeURI(h.d)+'/',pic=document.getElementById('pic'),w=document.getElementById('what');
 if(h.f[N]){w.textContent=h.f[N];pic.innerHTML=`<img src="${base+encodeURIComponent(h.f[N])}">`}
 else if(h.t[N]){const sc=h.t[N].startsWith('scout/');w.textContent=h.t[N]+(sc?' (1000 px copy; the full page is at Riksarkivet)':' (thumbnail stand-in; the full page is at Riksarkivet)');pic.innerHTML=`<img class="${sc?'':'t'}" src="${base+h.t[N].split('/').map(encodeURIComponent).join('/')}">`;ocr(sc?base+'scout/ocr/'+encodeURIComponent(h.t[N].slice(6).replace(/\.jpg$/,'')):null)}
 else{w.textContent='Not on the shelf: open it at Riksarkivet.';pic.innerHTML=''}
 if(!(h.t[N]&&!h.f[N]))ocr(h.f[N]?base+'ocr/'+encodeURIComponent(h.f[N].replace(/\.jpg$/,'')):null)
 const s=document.getElementById('strip');if(s.dataset.v!==V){s.dataset.v=V;let x='';for(let i=1;i<=h.n;i++)x+=`<a href="#v=${V}&n=${i}" class="${h.f[i]?'f':h.t[i]?'t':''}" title="Bild ${i}"></a>`;s.innerHTML=x}
 s.querySelectorAll('a.on').forEach(e=>e.classList.remove('on'));if(s.children[N-1])s.children[N-1].classList.add('on');
 document.getElementById('pf').onclick=()=>{const k=fs.filter(x=>x<N).pop();if(k)go(k)};
 document.getElementById('nf').onclick=()=>{const k=fs.find(x=>x>N);if(k)go(k)}}
// OCR lines: "x y w h<TAB>text|conf  text|conf ...", boxes as page fractions from top left
async function ocr(stem){const L=document.getElementById('lines'),pic=document.getElementById('pic'),kind=document.getElementById('ocr').value;
 pic.querySelectorAll('.b').forEach(e=>e.remove());L.hidden=true;L.innerHTML='';if(!stem||!kind)return;
 let r=await fetch(stem+'.'+kind+'.tsv'),note='';if(!r.ok&&kind==='trocr'){r=await fetch(stem+'.vision.tsv');note='<div class="c">No TrOCR text yet: Apple Vision shown.</div>'}
 if(!r.ok){L.hidden=false;L.innerHTML='<span class="c">No OCR text for this image yet.</span>';return}
 const rows=(await r.text()).split('\n').filter(Boolean).map((l,i)=>{const [b,c]=l.split('\t');const [x,y,w,h]=b.split(' ').map(Number);
  const cands=(c||'').split('  ').map(s=>{const k=s.lastIndexOf('|');return [s.slice(0,k),s.slice(k+1)]});return {i,x,y,w,h,cands}}).sort((a,b)=>a.y-b.y||a.x-b.x);
 const esc=s=>s.replace(/[&<>"]/g,ch=>'&#'+ch.charCodeAt(0)+';');
 for(const o of rows){const d=document.createElement('div');d.className='b';d.dataset.i=o.i;Object.assign(d.style,{left:o.x*100+'%',top:o.y*100+'%',width:o.w*100+'%',height:o.h*100+'%'});d.title=o.cands.map(c=>c.join(' ')).join('\n');pic.appendChild(d)}
 L.innerHTML=note+rows.map(o=>`<div data-i="${o.i}">${esc(o.cands[0][0])}${o.cands.length>1?` <span class="c">${o.cands.slice(1).map(c=>esc(c[0])).join(' · ')}</span>`:''}</div>`).join('');L.hidden=false;
 const hl=(i,on)=>document.querySelectorAll(`[data-i="${i}"]`).forEach(e=>e.classList.toggle('on',on));
 for(const e of [...pic.querySelectorAll('.b'),...L.children]){e.onmouseenter=()=>hl(e.dataset.i,true);e.onmouseleave=()=>hl(e.dataset.i,false)}}
document.getElementById('ocr').onchange=show;document.getElementById('box').onchange=e=>document.getElementById('pic').classList.toggle('nobox',!e.target.checked);
document.getElementById('p').onclick=()=>N>1&&go(N-1);document.getElementById('n').onclick=()=>H[V]&&N<H[V].n&&go(N+1);
addEventListener('keydown',e=>{if(e.key==='ArrowLeft')document.getElementById('p').click();if(e.key==='ArrowRight')document.getElementById('n').click()});
addEventListener('hashchange',show);fetch('held.json').then(r=>r.json()).then(j=>{H=j;show()});
</script>"""


def _lan_urls(port):
    """This machine's addresses as others on the network see it: the IP of
    the interface that routes outward (a UDP connect sends nothing), and the
    Bonjour name (<host>.local), which macOS and most phones resolve."""
    import socket
    urls = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.254.254.254", 1))
        urls.append(f"http://{s.getsockname()[0]}:{port}/")
    except OSError:
        pass
    finally:
        s.close()
    name = socket.gethostname()
    if name:
        urls.append(f"http://{name if name.endswith('.local') else name.split('.')[0] + '.local'}:{port}/")
    return urls


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--index", action="store_true", help="only write output/index.html")
    ap.add_argument("--dir", help="serve an unzipped snapshot folder (notes in its notes/)")
    ap.add_argument("--lan", action="store_true",
                    help="listen on all interfaces, so others on the local network can browse "
                         "(no password: home networks only)")
    a = ap.parse_args()
    if a.dir:
        out = Path(a.dir).expanduser().resolve()
        notes = out / "notes"
    else:
        import config
        data = config.load()["data_dir"]
        out, notes = data.layer("output"), data.layer("notes")
    out.mkdir(parents=True, exist_ok=True)
    write_index(out, notes)
    Handler.notes = notes if notes.is_dir() else None
    archive = out.parent / "archive" if not a.dir else out / "archive"
    Handler.archive = archive if archive.is_dir() else None
    if a.index:
        print(f"wrote {out / 'index.html'}")
        return
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    srv = http.server.ThreadingHTTPServer((host, a.port), partial(Handler, directory=str(out)))
    url = f"http://127.0.0.1:{a.port}/"
    print(f"serving {out} at {url} (Ctrl-C to stop)")
    if a.lan:
        for lan in _lan_urls(a.port):
            print(f"  on the local network: {lan}")
        print("  no password: anyone on this network can read these pages")
    if not a.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
