"""
Smoke tests on synthetic data only (no family data needed):

    python3 -m unittest discover -s tests -v

They check that the core pieces still fit together after edits by any of
the sessions working in this repository: the GEDCOM reader (including
MyHeritage's quirks), kinship with pedigree collapse and identical twins,
the tree store's round trip and edit persistence, the AutoCluster reader,
the sibling-consistency pairs, and the phasing model on simulated siblings.
"""
import gzip
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

# A tiny tree: grandparents G1 x G2 have children P1 and P2 (identical twins,
# written as such only in the test) and P3; P1 x M1 have children C1, C2;
# P2 x M2 have C3; P3 x M3 have C4 (adopted: PEDI adopted). C1's record has a
# CONC that splits the two bytes of "ö", as MyHeritage does, and a citation
# repeated twice.
GED = """0 HEAD
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Gustav /Example/
1 SEX M
1 RIN MH:I1
1 FAMS @F1@
0 @I2@ INDI
1 NAME Gerd /Sample/
1 SEX F
1 RIN MH:I2
1 FAMS @F1@
0 @I3@ INDI
1 NAME Per /Example/
1 SEX M
1 RIN MH:I3
1 FAMC @F1@
1 FAMS @F2@
0 @I4@ INDI
1 NAME Pål /Example/
1 SEX M
1 RIN MH:I4
1 FAMC @F1@
1 FAMS @F3@
0 @I5@ INDI
1 NAME Mia /Other/
2 _MARNM Example
1 SEX F
1 RIN MH:I5
1 FAMS @F2@
0 @I6@ INDI
1 NAME Cid /Example/
1 SEX M
1 RIN MH:I6
1 BIRT
2 DATE 1 JAN 1990
2 PLAC J\xc3
3 CONC \xb6nköping
1 SOUR @S1@
2 PAGE p. 1
1 SOUR @S1@
2 PAGE p. 1
1 FAMC @F2@
0 @I7@ INDI
1 NAME Cia /Example/
1 SEX F
1 RIN MH:I7
1 FAMC @F2@
0 @I8@ INDI
1 NAME Mona /Third/
1 SEX F
1 RIN MH:I8
1 FAMS @F3@
0 @I9@ INDI
1 NAME Kim /Example/
1 SEX M
1 RIN MH:I9
1 FAMC @F3@
0 @I10@ INDI
1 NAME Olle /Example/
1 SEX M
1 RIN MH:I10
1 FAMC @F1@
1 FAMS @F4@
0 @I11@ INDI
1 NAME Ada /Fourth/
1 SEX F
1 RIN MH:I11
1 FAMS @F4@
0 @I12@ INDI
1 NAME Ture /Example/
1 SEX M
1 RIN MH:I12
1 FAMC @F4@
2 PEDI adopted
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
1 CHIL @I10@
0 @F2@ FAM
1 HUSB @I3@
1 WIFE @I5@
1 CHIL @I6@
1 CHIL @I7@
0 @F3@ FAM
1 HUSB @I4@
1 WIFE @I8@
1 CHIL @I9@
0 @F4@ FAM
1 HUSB @I10@
1 WIFE @I11@
1 CHIL @I12@
0 @S1@ SOUR
1 TITL Example parish register
0 TRLR
"""


def write_ged(dirpath):
    p = Path(dirpath) / "tree.ged"
    raw = GED.encode("utf-8")
    # turn the escaped split "\\xc3 / \\xb6" into raw bytes split across lines
    raw = raw.replace(b"J\\xc3\n3 CONC \\xb6", b"J\xc3\n3 CONC \xb6")
    p.write_bytes(b"\xef\xbb\xbf" + raw)
    return p


class TreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ged = write_ged(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reader_quirks(self):
        import gedcom_io
        t = gedcom_io.Tree(self.ged)
        self.assertEqual(len(t.people), 12)
        c1 = t.id("MH:I6")                       # RIN alias
        self.assertEqual(t.people[c1]["birth"]["place"], "Jönköping")   # CONC inside a character
        self.assertEqual(t.people[t.id("MH:I5")]["married"], ["Example"])
        self.assertEqual(t.lineage("MH:I6", "MH:I1"), ["FF"])
        self.assertEqual({(x[0], x[2]) for x in t.nonbio}, {(t.id("MH:I12"), "adopted")})   # one link per adoptive parent
        self.assertNotIn(t.id("MH:I10"), t.parents(t.id("MH:I12")))   # adopted: no genetic path

    def test_kinship(self):
        import gedcom_io
        t = gedcom_io.Tree(self.ged)
        k = lambda a, b, tw=None: gedcom_io.kinship(t, a, b, twins=tw)
        self.assertAlmostEqual(k("MH:I6", "MH:I6"), 0.5)
        self.assertAlmostEqual(k("MH:I6", "MH:I7"), 0.25)      # full siblings
        self.assertAlmostEqual(k("MH:I6", "MH:I9"), 1 / 16)    # first cousins
        self.assertAlmostEqual(k("MH:I6", "MH:I9", {"MH:I4": "MH:I3"}), 1 / 8)   # fathers identical twins
        self.assertAlmostEqual(k("MH:I6", "MH:I12"), 0.0)      # adopted cousin

    def test_store_round_trip_and_edits(self):
        import gedcom_io
        import tree_store
        db = Path(self.tmp.name) / "tree.sqlite"
        s = tree_store.Store(db)
        s.import_gedcom(self.ged, "test export")
        out = Path(self.tmp.name) / "out.ged"
        r = s.export_gedcom(out)
        self.assertEqual(r["citations_dropped"], 1)            # the repeated citation
        a, b = gedcom_io.Tree(self.ged), gedcom_io.Tree(out)
        self.assertEqual(len(a.people), len(b.people))
        for mh in ("MH:I6", "MH:I9", "MH:I12"):
            pa = sorted(a.label(x) for x in a.parents(a.id(mh)))
            pb = sorted(b.label(x) for x in b.parents(b.id(mh)))
            self.assertEqual(pa, pb)
        self.assertEqual(b.people[b.id("MH:I6")]["birth"]["place"], "Jönköping")
        # an edit survives a re-import, and a rebuild from tree_edits.json
        s.add_event("MH:I6", "EVEN", "donor", "test", type="Note", date="2000", value="edited")
        s.import_gedcom(self.ged, "test export again")
        self.assertEqual(len([e for e in s.events("MH:I6") if e[6].startswith("edit:")]), 1)
        s.db.close()
        db.unlink()
        s2 = tree_store.Store(db)
        s2.import_gedcom(self.ged, "rebuild")
        self.assertGreaterEqual(s2.load_edits(), 1)
        self.assertEqual(len([e for e in s2.events("MH:I6") if e[6].startswith("edit:")]), 1)

    def test_tree_replaced_in_place(self):
        """import_tree: who left the tree goes, an edit stays once, other tables stay."""
        import tree_store
        db = Path(self.tmp.name) / "replace.sqlite"
        s = tree_store.Store(db)
        text = Path(self.ged).read_text(encoding="utf-8")
        extra = Path(self.tmp.name) / "extra.ged"
        extra.write_text(text.replace("0 TRLR", "0 @I99@ INDI\n1 NAME Extra /Person/\n0 TRLR"), encoding="utf-8")
        s.import_gedcom(extra, "older export", keep_unlinked=True)
        s.db.execute("create table if not exists step_table (x)")
        s.db.execute("insert into step_table values (1)")
        s.add_event("MH:I6", "EVEN", "donor", "test", type="Note", date="2000", value="edited")
        people = lambda: {r[0] for r in s.db.execute("select id from person")}
        self.assertIn("@I99@", people())
        r = s.import_tree(self.ged, "newer export", keep_unlinked=True)
        self.assertNotIn("@I99@", people())
        self.assertEqual(r["edits_replayed"], 1)
        self.assertEqual(len([e for e in s.events("MH:I6") if e[6].startswith("edit:")]), 1)
        self.assertEqual(s.db.execute("select count(*) from step_table").fetchone()[0], 1)
        # an edit the json lacks stops it
        s.db.execute("update person set origin='edit:unsaved' where id='MH:I7'")
        with self.assertRaises(RuntimeError):
            s.import_tree(self.ged, "again", keep_unlinked=True)

    def test_audit(self):
        import gedcom_audit
        a = gedcom_audit.audit(self.ged)
        self.assertTrue(a["citations repeated on one person or event (same source and page)"].startswith("1 of"))


class GeneticsTests(unittest.TestCase):
    def test_autocluster_reader(self):
        import icw_io
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "run.csv"
            p.write_text("Identifier,Name,total shared cM,Tree,Tree Person Count,Notes,Cluster,1_Ann A,2_Bo B,3_Cy C\n"
                         "AAAA-1,Ann A,50,,,,1,1,2,\n"
                         "BBBB-2,Bo B,45,,,,1,1,2,\n"
                         "CCCC-3,Cy C,40,,,,2,,,3\n"
                         "\n# The following matches have been removed:\nDee D, Eve E\n", encoding="utf-8")
            Path(d, "run.html").write_text("globalInfo = {min_cm: 35, max_cm: 400}", encoding="utf-8")
            nodes, edges = icw_io.autocluster_matrix(p, "x")
            self.assertEqual(len(nodes), 3)
            self.assertEqual(len(edges), 1)                  # Ann - Bo
            ids, names, lo, hi = icw_io.autocluster_window(p)
            self.assertEqual((lo, hi), (35.0, 400.0))
            self.assertIn("eve e", names)
            self.assertIn("D-AAAA-1", ids)

    def test_sibling_pairs(self):
        import sibling_consistency as sc
        segs = pd.DataFrame([
            dict(platform="P", subject="a", match_key="m1", match="M1", chrom="1", start=1_000_000, end=20_000_000, cM=20, parent="F"),
            dict(platform="P", subject="b", match_key="m1", match="M1", chrom="1", start=1_100_000, end=20_000_000, cM=20, parent="F"),
            dict(platform="P", subject="c", match_key="m1", match="M1", chrom="1", start=10_000_000, end=40_000_000, cM=30, parent="F"),
        ])
        pairs = sc.shared_pairs(segs, ["a", "b", "c"])
        self.assertEqual(len(pairs), 1)                        # only a-b share end to end
        iv = sc.ibd_intervals(pairs)
        self.assertEqual(iv.side.tolist(), ["A"])

    def test_phasing_on_simulated_siblings(self):
        """Three siblings and their mother on one simulated chromosome with
        known crossovers: the decoded sibling-pair states must match the truth."""
        import visual_phasing as vp
        rnd = random.Random(1)
        n = 4000
        pos = [i * 25_000 + 10_000 for i in range(n)]          # 100 Mb at 1 cM/Mb
        hap = [[rnd.randint(0, 1) for _ in range(n)] for _ in range(4)]   # F0 F1 M0 M1

        def child(fx, mx):          # copy index along the chromosome, switching at crossovers
            return [(0 if p < fx else 1) for p in pos], [(1 if p < mx else 0) for p in pos]
        kids = {"a": child(30e6, 70e6), "b": child(60e6, 20e6), "c": child(90e6, 50e6)}
        with tempfile.TemporaryDirectory() as d:
            files = {}

            def write(name, g):
                f = Path(d) / f"{name}.csv.gz"
                with gzip.open(f, "wt") as fh:
                    fh.write("RSID,CHROMOSOME,POSITION,RESULT\n")
                    for i, p in enumerate(pos):
                        fh.write(f"rs{i},1,{p},{g[i]}\n")
                return f
            al = "AG"
            for k, (fc, mc) in kids.items():
                g = [al[hap[fc[i]][i]] + al[hap[2 + mc[i]][i]] for i in range(n)]
                files[k] = write(k, g)
            mum = vp.load_raw(write("mum", [al[hap[2][i]] + al[hap[3][i]] for i in range(n)]), "mum")
            res = vp.run(files, parent=mum)["1"]
        S = [vp.STATES[s] for s in res["path"]]
        p = list(res["pos"])
        idx = {k: i for i, k in enumerate(vp.SIBS)}
        ok = tot = 0
        for j, x in enumerate(p):
            i = pos.index(x)
            for a, b in (("a", "b"), ("a", "c"), ("b", "c")):
                truth = (kids[a][0][i] == kids[b][0][i]) + (kids[a][1][i] == kids[b][1][i])
                st = S[j]
                cA, cB = (0, st[0], st[1]), (0, st[2], st[3])
                model = (cA[idx[a]] == cA[idx[b]]) + (cB[idx[a]] == cB[idx[b]])
                ok += truth == model
                tot += 1
        self.assertGreater(ok / tot, 0.95)

    def test_parent_side_containment(self):
        """A child's segment reaching well beyond the mother's segments with
        the same match is paternal; one inside hers stays maternal."""
        import match_placement as mp

        def kit(rows, date):
            s = pd.DataFrame(rows, columns=["match_key", "chrom", "start", "end", "cM"])
            return dict(segs=s.assign(match=s.match_key), keys=set(s.match_key),
                        date=pd.Timestamp(date))
        # mother: a long segment with "cousin", one stray 8 cM piece with "uncle"
        mum = kit([("cousin", "20", 11_000_000, 58_000_000, 64.0),
                   ("uncle", "14", 26_500_000, 33_000_000, 8.0)], "2026-01-01")
        child = kit([("cousin", "20", 45_000_000, 56_500_000, 23.4),    # inside hers
                     ("uncle", "14", 21_200_000, 34_000_000, 24.7),     # half outside
                     ("uncle", "4", 44_000_000, 86_600_000, 35.0)],     # none of hers
                    "2026-01-02")
        side = list(mp.phase_child(child, mum).parent)
        self.assertEqual(side, ["M", "F", "F"])
        # years apart, vendors recompute segments: no containment calls
        child["date"] = pd.Timestamp("2028-01-01")
        self.assertEqual(list(mp.phase_child(child, mum).parent), ["M", "M", ""])

    def test_parent_side_selection(self):
        """Absence from a mother's selection says nothing, unless the same
        matches were looked up for her."""
        import match_placement as mp

        def kit(rows, date, **kw):
            s = pd.DataFrame(rows, columns=["match_key", "chrom", "start", "end", "cM"])
            return dict(segs=s.assign(match=s.match_key), keys=set(s.match_key),
                        date=pd.Timestamp(date), **kw)
        mum = kit([("cousin", "20", 11_000_000, 58_000_000, 64.0)], "2026-01-01", partial=True)
        child = kit([("cousin", "20", 45_000_000, 56_500_000, 23.4),
                     ("stranger", "4", 44_000_000, 86_600_000, 35.0)], "2025-12-01")
        self.assertEqual(list(mp.phase_child(child, mum).parent), ["M", ""])
        mum["same_selection"] = True
        self.assertEqual(list(mp.phase_child(child, mum).parent), ["M", "F"])
        mum["partial"] = False
        self.assertEqual(list(mp.phase_child(child, mum).parent), ["M", "F"])

    def test_parent_side_absence_floor(self):
        """Absence from the mother's list is not read below ABSENCE_MIN_CM."""
        import match_placement as mp
        s = pd.DataFrame([("stranger", "4", 44_000_000, 86_600_000, 35.0),
                          ("stranger", "7", 10_000_000, 12_000_000, 7.5)],
                         columns=["match_key", "chrom", "start", "end", "cM"])
        mum = dict(segs=s.iloc[:0].assign(match=[]), keys=set(), date=pd.Timestamp("2026-01-01"))
        child = dict(segs=s.assign(match=s.match_key), keys={"stranger"},
                     date=pd.Timestamp("2025-12-01"))
        out = mp.phase_child(child, mum)
        self.assertEqual(list(out.parent), ["F", ""])
        self.assertIn("absence not read", out.parent_reason.iloc[1])

    def test_parent_side_first_seen(self):
        """Absence counts when any donor's accession saw the match on or
        before the mother's list, whatever the child's own export date."""
        import match_placement as mp

        def kit(rows, date, **kw):
            s = pd.DataFrame(rows, columns=["match_key", "chrom", "start", "end", "cM"])
            return dict(segs=s.assign(match=s.match_key), keys=set(s.match_key),
                        date=pd.Timestamp(date), **kw)
        mum = kit([("cousin", "20", 11_000_000, 58_000_000, 64.0)], "2025-01-01")
        rows = [("old", "4", 44_000_000, 86_600_000, 35.0),
                ("new", "5", 44_000_000, 86_600_000, 35.0)]
        child = kit(rows, "2026-06-01")       # newer than the mother's list
        sib = kit(rows[:1], "2024-06-01")      # a sibling saw "old" before it
        self.assertEqual(list(mp.phase_child(child, mum).parent), ["", ""])
        seen = mp.first_seen([child, sib, mum])
        self.assertEqual(list(mp.phase_child(child, mum, seen).parent), ["F", ""])
        # the child's own earlier accession (kits.py first_seen) does the same
        child["first_seen"] = {"old": pd.Timestamp("2024-12-01"), "new": pd.Timestamp("2026-06-01")}
        self.assertEqual(list(mp.phase_child(child, mum).parent), ["F", ""])


if __name__ == "__main__":
    unittest.main()
