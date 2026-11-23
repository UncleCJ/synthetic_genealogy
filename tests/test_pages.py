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
                 "name@per": [1, 2], "born@A-by,!lived": [0], "foo@x": "error",
                 "born:18x": "error", "line": "error",
                 "step:km>30": [0], "step:km<30": [], "step:line@FMF": [0], "step:line@FM,to@Gården": [0],
                 "step:year:1800-1849": [], "end:open": [0], "end:age<20": [], "end:year:1850-1860": [0],
                 "end:at@Gården,!left": [0], "end:none": [], "end:household": [0], "end:cited": [], "end:km>3": "error", "step:age<3": "error",
                 "step:km=3": "error"}
        p = subprocess.run(["node", "-e", js, *cases], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr[:500])
        self.assertEqual(json.loads(p.stdout), cases)


class TestWorklist(unittest.TestCase):
    def test_tasks(self):
        """Loose ends become tasks by what to do (synthetic data)."""
        from sg.views import worklistview
        data = dict(tabs=dict(t=["birth", "residence"], name=["Gården, A-by"], parish=["A-by"]),
                    people=[["MH:I1", "Per*", "", "ancestor", "F", "FM", 1800, None, [], ""],
                            ["MH:I2", "Anna", "", "relative", "M", "MF", 1810, None, [], ""]],
                    rows=[[0, 0, 0, 1800, 1800, 0, 0, 0, 0, 0, 0, 0], [1, 1, 0, 1840, 1845, 0, 0, 0, 0, 0, 0, 0]],
                    ends=[[0, 1800, 0, "", "SE/X/A I/1 (1800–1810)", "v", "open", "household", "p. 3, father Nils"],
                          [1, 1845, 35, "emigrated", "", "", "?", "", ""]])
        t = worklistview.tasks(data)
        self.assertEqual([x[5] for x in t], ["page", "left"])
        self.assertEqual(t[0][8:], ["birth", "Gården, A-by", "A-by", "SE/X/A I/1 (1800–1810)", "v", "p. 3, father Nils"])
        self.assertEqual(t[1][8], "emigrated")

    def test_errata_tasks(self):
        """Errata by their state; a person's death fix read against the store."""
        from sg.views import worklistview
        people = {"MH:I1": dict(name="Per", kin="ancestor", lineage="FM", born=1800)}
        report = [(dict(key="person:MH:I1", field="death", was="1838", now="29 OCT 1838", date="2026-11-16"), "bad field 'death'", 0),
                  (dict(key="mh:9", field="page", was="35", now="36"), "applied", 1),
                  (dict(key="mh:8", field="page", was="1", now="2"), "retired", 1),
                  (dict(key="plac:X", text="two farms named X"), "orphan", 0),
                  (dict(key="mh:9", text="check the volume"), "attached", 1)]
        rows = [dict(mh_item="9", mh_id="MH:I1")]
        t = worklistview.errata_tasks(report, rows, people, {("MH:I1", "death"): "1838"})
        self.assertEqual([x[5] for x in t], ["upstream", "upstream", "retire", "orphan", "note"])
        self.assertEqual(t[1][0], "MH:I1")
        self.assertEqual(t[0][8], "death: 1838 → 29 OCT 1838")
        t = worklistview.errata_tasks(report[:1], rows, people, {("MH:I1", "death"): "29 OCT 1838"})
        self.assertEqual(t[0][5], "retire")

    def test_age_tasks(self):
        from sg.views import worklistview
        people = {"a": dict(name="A", born=1700, died=1810), "b": dict(name="B", born=1750, died=1800),
                  "c": dict(name="C", born=1790)}
        mis = [dict(xref="@I3@", union="@F1@", why="the mother over 50 at the birth", candidates=["@F2@ (X)"]),
               dict(xref="@I2@", union="@F1@", why="born after the mother's death", candidates=[])]
        t = worklistview.age_tasks(people, mis, {"@I3@": "c", "@I2@": "b"}, skip={"b"})
        self.assertEqual([(x[0], x[8], x[11]) for x in t],
                         [("c", "the mother over 50 at the birth", "other unions: @F2@ (X)"),
                          ("a", "a life of 110 years", "born 1700, died 1810")])

    def test_place_tasks(self):
        from sg.views import worklistview
        people = {"a": dict(name="A", kin="relative", lineage="FMF"), "b": dict(name="B", kin="ancestor", lineage="FM")}
        t = worklistview.place_tasks(people, [("Ekeby", "a"), ("Ekeby", "b"), ("Ekeby", "b")],
                                     [("X-by, Y län, Sverige", "a"), ("Chicago, Illinois", "a")])
        self.assertEqual([(x[0], x[8], x[9], x[11]) for x in t],
                         [("b", "Ekeby", "not on the map", "3 events, 2 people"),
                          ("a", "X-by, Y län, Sverige", "no parish known", "1 event, 1 person")])

    def test_parent_and_gap_tasks(self):
        import tempfile, pathlib
        from sg.views import worklistview
        people = {"a": dict(name="A", kin="ancestor", born=1800), "b": dict(name="B", kin="ancestor", born=1830),
                  "c": dict(name="C", kin="relative", born=1860), "d": dict(name="D", kin="relative")}
        fams = {"F1": ("a", None), "F2": ("b", "x")}
        kids = {"F1": ["b"], "F2": ["c"]}
        t = {x[0]: x[8] for x in worklistview.parent_tasks(people, fams, kids, {"a": "A-by"})}
        self.assertEqual(t, {"a": "both parents unknown", "b": "mother unknown"})
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "r.csv"
            f.write_text("mh_id,label,kin,kind,start,end,parish,place,detail\n"
                         "b,B,ancestor,gap,1841,1850,,A-by X → A-by Y,SE/X/A I/3 (1846–1850)\n"
                         "b,B,ancestor,record,1830,1840,A-by,X,v\n", encoding="utf-8")
            g = worklistview.gap_tasks(f, people)
        self.assertEqual([(x[5], x[6], x[11]) for x in g], [("gap", "1841–1850", "SE/X/A I/3 (1846–1850)")])

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_links(self):
        js = viewkit.LINKS_JS + r"""
console.log(JSON.stringify([linkTo('family.html',{person:'MH:I1'}),linkTo('geography.html',{person:'MH:I1',sel:'end:open'}),
 linkTo('archives.html',{parish:'A-by'}),linkTo('genome.html',{person:'MH:I1'}),linkTo('worklist.html',{person:'MH:I1'})]))"""
        p = subprocess.run(["node", "-e", js], capture_output=True, text=True)
        self.assertEqual(json.loads(p.stdout), ["family.html#p=MH:I1", "geography.html#sel=end:open",
                                                "archives.html#parish=A-by&kin=all", "genome.html",
                                                "worklist.html#person=MH:I1"])


if __name__ == "__main__":
    unittest.main()
