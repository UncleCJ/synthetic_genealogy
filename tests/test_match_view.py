"""match_view's small Markdown renderer (kept-report summaries, research entries)."""
import unittest

import match_view


class Markdown(unittest.TestCase):
    def test_wrapped_lines_join(self):
        h = match_view.md_to_html("Para one\ncontinues.\n\n- item\n  wraps\n- two\n\n## Head\ntext")
        self.assertIn("<p>Para one continues.</p>", h)
        self.assertIn("<li>item wraps</li>", h)
        self.assertIn("<li>two</li>", h)
        self.assertIn("<h4>Head</h4>", h)
        self.assertIn("<p>text</p>", h)

    def test_table(self):
        h = match_view.md_to_html("| a | b |\n|---|---|\n| 1 | 2 |")
        self.assertIn("<th>a</th>", h)
        self.assertIn("<td>2</td>", h)



class References(unittest.TestCase):
    def test_hide_and_volume_codes(self):
        import tempfile
        from pathlib import Path
        import config
        root = Path(tempfile.mkdtemp())
        (root / "output").mkdir()
        (root / "output" / "volume_refs.csv").write_text(
            "person,tier,volume,years,page,archive_code,ra_code,ra_status,source_title,ref_text,"
            "ra_images,ra_pages,ra_image_count\n"
            "@I1@,mh-record,Ryd A I/2,1800-1810,5,SE/XA/001,SE/XA/001/A I/2,found,,,00001,1-101,51\n"
            "@I1@,mh-record,Ryd A I/3,1811-1820,7,SE/XA/001,SE/XA/001/A I/3,no such volume at Riksarkivet,,,,,\n"
            "@I1@,tree,,,,,,,Example Web Site,,,,\n"
            "@I1@,tree,,,,,,,Geni World Family Tree,,,,\n"
            "@I1@,tree,,,,,,,Household records,vol 2,,,\n"
            "@I1@,plac-only,Ryd A I/4,,,,,,,,,,\n", encoding="utf-8")
        cfg = {"data_dir": config.DataDir(root),
               "reports": {"hide_references": ["^Geni\\b", " Web Site$"]}}
        none = ("", "")
        self.assertEqual(match_view.references(cfg, ["@I1@"])["@I1@"], [
            # confirmed: the volume's own code, and the image page 5 is likely on
            ("Ryd A I/2 (1800-1810) p. 5 · SE/XA/001/A I/2",
             ("https://sok.riksarkivet.se/bildvisning/00001_00003", "≈image")),
            ("Ryd A I/3 (1811-1820) p. 7 · SE/XA/001", none),     # not confirmed: the archive's
            ("Household records: vol 2", none)])


class Riksarkivet(unittest.TestCase):
    def test_page_span(self):
        import riksarkivet as ra
        self.assertEqual(ra.page_span("I. 1 - 275. Södra delen."), (1, 275, "page"))
        self.assertEqual(ra.page_span("Volym 1. Uppslag 1-350. Höganäs"), (1, 350, "uppslag"))
        self.assertEqual(ra.page_span("I. Fol. 1-200."), (1, 200, "folio"))
        for note in ("1918-1938", "Rote 14-19.", "B 1 - B 200.", ""):
            self.assertIsNone(ra.page_span(note))

    def test_compact_and_link(self):
        import riksarkivet as ra
        self.assertEqual(ra.compact("SE/VALA/00100/A ll a/3"), ra.compact("SE/VALA/00100/AIIa/3"))
        self.assertEqual(ra.link({"image_id": "00042", "image_no": "7"}),
                         ("https://sok.riksarkivet.se/bildvisning/00042_00007", "image"))
        self.assertEqual(ra.link({"ra_status": "found", "ra_nad": "https://x/arkiv/abc"}),
                         ("https://x/arkiv/abc", "catalogue"))


if __name__ == "__main__":
    unittest.main()
