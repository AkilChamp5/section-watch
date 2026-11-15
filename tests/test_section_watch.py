import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from section_watch import extract_section, main


class ExtractionTests(unittest.TestCase):
    def test_ignores_scripts_and_preserves_inline_words_and_block_boundaries(self):
        html = """
        <section id="watch">
            <p>Re<strong>lease</strong>&nbsp; 1</p>
            <template><p>Draft</p></template>
            <script>console.log("hello")</script>
            <p>Available now<br>Stable</p>
        </section>
        """
        self.assertEqual(extract_section(html, "watch"), "Release 1\nAvailable now\nStable")

    def test_rejects_duplicate_ids(self):
        html = '<p id="watch">One</p><p id="watch">Two</p>'
        with self.assertRaisesRegex(ValueError, "More than one"):
            extract_section(html, "watch")

    def test_rejects_unclosed_target_inside_a_closed_element(self):
        with self.assertRaisesRegex(ValueError, "no closing tag"):
            extract_section('<main><p id="watch">Broken</main>', "watch")


class SnapshotTests(unittest.TestCase):
    def test_failed_check_does_not_replace_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            page = Path(folder) / "page.html"
            state = Path(folder) / "state.sqlite3"

            def check(html):
                page.write_text(html, encoding="utf-8")
                output, errors = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    code = main([str(page), "--id", "watch", "--state", str(state)])
                return code, output.getvalue(), errors.getvalue()

            self.assertEqual(check('<p id="watch">Version 1</p>')[0], 0)
            code, _, errors = check("<p>Maintenance</p>")
            self.assertEqual(code, 1)
            self.assertIn("No element found", errors)
            code, output, _ = check('<p id="watch">Version 2</p>')
            self.assertEqual(code, 0)
            self.assertIn("-Version 1\n+Version 2", output)
            self.assertIn("No change", check('<p id="watch">Version 2</p>')[1])


if __name__ == "__main__":
    unittest.main()
