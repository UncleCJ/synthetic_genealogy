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


if __name__ == "__main__":
    unittest.main()
