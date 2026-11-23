"""
What every view page shares: the nav row between the views, the data
embedding (gzipped JSON the page unpacks), and the JS used on several
pages: GEDCOM dates shortened (DATE_JS), names drawn (NAME_JS), search
folding of Swedish spellings (FOLD_JS, with name_fold its tested Python
reference), and the offline-copy links (OFFLINE_JS).

Imported by the page writers (geoview, familyview, volumes, genomeview)
and by showcase; it imports none of them.
"""
import base64
import gzip
import json
import re
import unicodedata
from pathlib import Path

PAGES = Path(__file__).resolve().parent / "pages"   # templates and scripts


def _read(name):
    return (PAGES / name).read_text(encoding="utf-8")


def template(page):
    """pages/<page>.html with pages/<page>.js as its main script (__JS__); the
    writer fills the other placeholders (__NAV__, __DATA__, ...)."""
    return _read(f"{page}.html").replace("__JS__", _read(f"{page}.js"))


DATE_JS = _read("shared/date.js")   # GEDCOM dates shortened, the same in every view

# A person's name, the same in every view (needs esc and the CSS i.unk):
# the call name (starred in the store, "Anna* Lisa") underlined, an unknown
# part (absent in the data, tree_store.name_parts) as a pale gap, a wholly
# unknown name said so. plainName is the text for titles, search and sorting.
NAME_JS = _read("shared/name.js")

# Search folding for names and places: historical Swedish spellings meet
# ("Oscar" finds "Oskar", "Gustaf" "Gustav", "Christina" "Kristina"). Accents
# go, plain substring pairs apply in order, then doubled letters inside a word
# become single (Svenning = Svening; "A II" stays apart from "A I"). Applied to
# query and text alike, so a key needn't be a real spelling; it overmatches a
# little (f = v everywhere), which a search box can afford. FOLD_JS is the same
# fold for the pages (fold(x)); name_fold is the tested reference.
NAME_FOLD = (("ph", "f"), ("th", "t"), ("ch", "k"), ("ck", "k"), ("c", "k"),
             ("q", "k"), ("x", "ks"), ("z", "s"), ("w", "v"), ("f", "v"))


def name_fold(s):
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    s = re.sub(r"[*()]", "", s).lower()
    for a, b in NAME_FOLD:
        s = s.replace(a, b)
    return re.sub(r"(?<=[a-z])([a-z])\1+", r"\1", s)


FOLD_JS = ("const NF=" + json.dumps(NAME_FOLD) + r",fold=x=>NF.reduce((s,[a,b])=>s.split(a).join(b),"
           r"x.normalize('NFD').replace(/[\u0300-\u036f*()]/g,'').toLowerCase()).replace(/(?<=[a-z])([a-z])\1+/g,'$1');")

# Offline copies of archive images (data/archive, served by serve.py under
# archive/): a ⌂ link per image or volume, hidden until archive/held.json
# says the copy is there. Opened as a file, the fetch fails and none show.
OFFLINE_JS = _read("shared/offline.js")

# Selection rules (sel=, mark=) over a page's people and events; needs FOLD_JS.
RULES_JS = _read("shared/rules.js")

VIEWS = [("family.html", "Family"), ("geography.html", "Geography"), ("archives.html", "Archives"), ("genome.html", "Genome"),
         ("worklist.html", "Work list")]
NAV_CSS = ("nav.views{display:flex;gap:2px;margin-right:6px}nav.views a{padding:3px 10px;border:1px solid var(--line);"
           "border-radius:6px;text-decoration:none;color:var(--fg);background:var(--card);font-size:13px}"
           "nav.views a.on{background:var(--sel);font-weight:600}nav.views a:hover{border-color:var(--mut)}"
           "nav.views a.home{color:var(--mut)}")


LINKS_JS = _read("shared/links.js")   # the nav bar carries the focus: navFocus, linkTo


def nav(current):
    """The row of links between the views, the same on each page."""
    links = "".join(f'<a href="{f}"' + (' class="on"' if f == current else "") + f">{t}</a>"
                    for f, t in VIEWS)
    return (f'<style>{NAV_CSS}</style><nav class="views"><a class="home" href="index.html" title="All outputs">⌂</a>{links}</nav>'
            f"<script>{LINKS_JS}</script>")


# The data a view carries, gzipped and base64-encoded (about 18 times smaller
# than the JSON). A template marks its main script <script type="text/plain"
# id="view-js"> starting `const D=DATA;` and puts __DATA__ after it; the loader
# unpacks the data, then runs the main script as an ordinary one. Views work
# opened as files; one that needs a web server says why in <body
# data-serve="...">, and opened as a file shows that and a link instead.
DATA_TAG = '<script id="view-data" type="application/octet-stream">'
LOAD_JS = ("<script>(async()=>{const n=document.body.dataset.serve;if(n&&location.protocol==='file:'){"
           "const u='http://127.0.0.1:8000/'+location.pathname.split('/').pop()+location.hash;"
           "document.body.innerHTML=`<p style=\"max-width:40em;margin:3em auto;font:15px/1.5 system-ui,sans-serif\">${n} "
           "Run <code>python3 serve.py</code> in the project (in an unzipped snapshot, <code>python3 serve.py --dir FOLDER</code>), "
           "then <a href=\"${u}\">open this view there</a>.</p>`;return}"
           "const b=Uint8Array.from(atob(document.getElementById('view-data').textContent),c=>c.charCodeAt(0));"
           "window.DATA=await new Response(new Blob([b]).stream().pipeThrough(new DecompressionStream('gzip'))).json();"
           "const s=document.createElement('script');s.textContent=document.getElementById('view-js').textContent;"
           "document.body.append(s)})()</script>")


def pack_data(data):
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    return base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode("ascii")


def embed(page, data):
    """The template with its data in place of __DATA__."""
    return page.replace("__DATA__", DATA_TAG + pack_data(data) + "</script>" + LOAD_JS)


def embedded(page):
    """(head, data, tail) of a written view; head + pack_data(data) + tail
    writes it back."""
    i = page.index(DATA_TAG) + len(DATA_TAG)
    j = page.index("</script>", i)
    return page[:i], json.loads(gzip.decompress(base64.b64decode(page[i:j]))), page[j:]
