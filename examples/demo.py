"""Show all three tracker outcomes using a temporary HTML page."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    examples = Path(__file__).resolve().parent
    tracker = examples.parent / "section_watch.py"
    steps = [
        ("release-1.html", "First check"),
        ("release-1-edited.html", "Only the navigation and formatting changed"),
        ("release-2.html", "The release notes changed"),
    ]

    with tempfile.TemporaryDirectory(prefix="section-watch-") as folder:
        page = Path(folder) / "release-notes.html"
        state = Path(folder) / "snapshots.sqlite3"
        command = [
            sys.executable, str(tracker), str(page),
            "--id", "release-notes", "--state", str(state),
        ]
        for fixture, label in steps:
            shutil.copyfile(examples / fixture, page)
            print(f"\n{label}", flush=True)
            subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
