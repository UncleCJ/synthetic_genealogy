"""The view pages' templates and scripts (sg/views/pages): each page's
template takes its script once, and every script parses (node --check;
skipped without node). Placeholders such as __DATEJS__ are plain
identifiers, so the files parse as they are."""
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


if __name__ == "__main__":
    unittest.main()
