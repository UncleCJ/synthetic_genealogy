"""The view pages' templates and scripts (sg/views/pages): each page's
template takes its script once, and every script parses (node --check;
skipped without node). Placeholders such as __DATEJS__ are plain
identifiers, so the files parse as they are."""
import json
import shutil
import subprocess
import unittest

from sg.views import viewkit


class TestPages(unittest.TestCase):
    def test_each_template_takes_its_script_once(self):
        for html in viewkit.PAGES.glob("*.html"):
            self.assertEqual(html.read_text(encoding="utf-8").count("__JS__"), 1, html.name)
            self.assertTrue(html.with_suffix(".js").exists(), html.name)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_scripts_parse(self):
        for js in sorted(viewkit.PAGES.rglob("*.js")):
            p = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, f"{js.name}: {p.stderr[:300]}")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_selection_rules(self):
        """rules.js on three synthetic people (no real names)."""
        js = viewkit.FOLD_JS + "\n" + viewkit.RULES_JS + r"""
const T={t:['birth','death','household examination'],place:['A-by/Gården','parish:A-by','parish:B-by',''],
 parish:['A-by','B-by',''],name:['Gården, A-by, Landskap','A-by','B-by, Landskap','']};
// id, name, surname, kin, branch, lineage, born, died, spouses, unk
const P=[['p0','Anna Svensdotter','Svensdotter','ancestor','F','FM',1820,null,[],''],
 ['p1','Per Svensson','Svensson','relative','F','FMF',1830,null,[],''],
 ['p2','Lisa Persdotter','Persdotter','spouse of relative','','',1850,1900,[],'']];
// person, type, layer, y0, y1, precision, lat, lon, level, name, parish, place
const R=[[0,0,0,1820,1820,0,0,0,0,0,0,0],[1,0,0,1830,1830,0,0,0,0,1,0,1],[1,2,0,1850,1855,0,0,0,0,0,0,0],
 [2,0,0,1850,1850,0,0,0,0,2,1,2],[2,1,0,1900,1900,0,0,0,0,2,1,2]];
// a step [from row, to row, km, approx]; a loose end [row, year, age, left, volume, viewer, status, lead, page]
const ST=[[1,2,220,0]],EN=[[2,1855,25,'','SE/X/A I/3 (1856–1860)','v','open','household','p. 5, Anna']];
const RU=makeRules(P,R,T,{RP:0,RT:1,RY0:3,RY1:4,RNAME:9,RPAR:10,RPL:11},ST,EN);
const out={};for(const q of process.argv.slice(1)){const r=RU.parse(q);out[q]=r.error?'error':[...(RU.pick(r)||[])].sort()}
console.log(JSON.stringify(out))"""
        cases = {"born@Gården": [0], "born@A-by": [0, 1], "born@a-by/gården": [0], "person:born@Landskap": [0, 2],
                 "line@FM": [0, 1], "line@FMF": [1], "!died": [0, 1], "born:1840-1860": [2],
                 "kin@ancestor|relative": [0, 1], "lived@Gården": [1], "surname@Svenson": [1],
                 "name@per": [1, 2], "born@A-by,!lived": [0], "foo@x": "error", "step:km>30": "error",
                 "born:18x": "error", "line": "error",
                 "step:km>30": [0], "step:km<30": [], "step:line@FMF": [0], "step:line@FM,to@Gården": [0],
                 "step:year:1800-1849": [], "end:open": [0], "end:age<20": [], "end:year:1850-1860": [0],
                 "end:at@Gården,!left": [0], "end:none": [], "end:household": [0], "end:cited": [], "end:km>3": "error", "step:age<3": "error",
                 "step:km=3": "error"}
        p = subprocess.run(["node", "-e", js, *cases], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr[:500])
        self.assertEqual(json.loads(p.stdout), cases)


if __name__ == "__main__":
    unittest.main()
