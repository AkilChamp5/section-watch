# Section Watch

Section Watch compares the text of one element on a webpage between runs.
Use it to follow release notes, a public status notice, or another specific
section without flagging edits to the rest of the page.

## Try it offline

Run this from the project folder with Python 3.10 or newer. There are no packages to install.

```sh
python examples/demo.py
```

On Windows, use `py` if that is how you launch Python.
The demo uses three sample pages and cleans up its files automatically.

```text
First check
Saved first snapshot for 'release-notes'.

Only the navigation and formatting changed
No change in 'release-notes'.

The release notes changed
Changed text in 'release-notes'.
--- previous
+++ current
@@ -1,3 +1,3 @@
 Release notes
-Current version: 1.0
-Includes CSV export.
+Current version: 1.1
+Includes CSV and JSON export.
```

## Watch a page

Choose a page you have permission to check. Find the section's `id` in the
page source. For example, `<section id="release-notes">` uses the ID
`release-notes`. Replace the example URL and ID below with yours.

```sh
python section_watch.py "https://your-site.example/releases" --id release-notes
```

You can pass a local HTML file in place of the URL. Run the same command
again later. The first successful check saves a baseline. Subsequent checks
print either “No change” or a line-by-line diff. Lines beginning with `-` came
from the previous check and lines beginning with `+` came from the new one.

Snapshots are stored locally in `.section-watch.sqlite3`, with a separate
record for each source and element ID. Use `--state PATH` to choose another
database file. A failed fetch or a missing, empty, or duplicated section
returns exit code 1 and preserves the previous snapshot. A successful check
returns 0, whether or not the section changed.

Section Watch reads the HTML the server sends. It ignores scripts, styles,
templates, and whitespace-only edits within a block. Choose an element with
an explicit closing tag. The tool reads static HTML without running
JavaScript or applying CSS. Local files should be UTF-8. Web pages use the
encoding specified in the response header or UTF-8 by default. The tool
accepts up to 2 MiB of HTML, checks on demand, and reports rate limits
without retrying.

## Test

```sh
python -m unittest discover -s tests
```

Released under the [MIT License](LICENSE).
