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
    "geography.html": "Map of every located event and record, with filters; links open it pre-filtered",
    "archives.html": "Archives: parishes, their volumes by series and page, farms on a map and across volumes",
    "report_malin.html": "Match-centred chromosome browser and research report",
    "revelations.md": "Placement of matches on grandparents, with cross-checks",
    "prospects.md": "Close matches not yet in the tree, with side and branch hints",
    "relationship_check.md": "Confirmed relatives: expected vs observed shared cM",
    "icw_report.md": "Shared-match (ICW) evidence against the placement",
    "places_rules.html": "Place recognition: how a place string becomes a parish, village or farm, and which rule resolved each",
    "gazetteer_todo.md": "Place-name variants to review, place strings with no parish",
    "errata_report.md": "Status of corrections and notes kept beside the MyHeritage tree",
    "pipeline_log.md": "What each pipeline step did, per run",
}
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
        group.sort(key=lambda p: (p.name not in KNOWN, -p.stat().st_mtime))
        rows = "".join(
            f'<tr><td><a href="{html.escape(str(p.relative_to(out)))}">{html.escape(str(p.relative_to(out)))}</a></td>'
            f'<td>{html.escape(KNOWN.get(p.name) or _title(p))}</td>'
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
Private: names and DNA results. <a href="#notes">Research notes</a></p>{''.join(sections)}</body></html>"""
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

    def translate_path(self, path):
        p = super().translate_path(path)
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
