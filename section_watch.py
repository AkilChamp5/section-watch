"""Track changes to the text of one element in an HTML page."""

import argparse
import difflib
import sqlite3
import sys
from contextlib import closing
from html.parser import HTMLParser
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urldefrag, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_BYTES = 2 * 1024 * 1024
VOID_TAGS = set("area base br col embed hr img input link meta param source track wbr".split())
IGNORED_TAGS = {"script", "style", "template", "noscript"}
BLOCK_TAGS = set(
    "address article aside blockquote br dd details div dl dt figcaption figure "
    "footer form h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section "
    "summary table tbody td th thead tr ul".split()
)


class SectionParser(HTMLParser):
    """Extract text from the element with the given HTML id."""

    def __init__(self, element_id):
        super().__init__(convert_charrefs=True)
        self.element_id = element_id
        self.stack = []
        self.parts = []
        self.matches = 0
        self.target_depth = None
        self.ignored_depth = None

    def handle_starttag(self, tag, attrs):
        is_void = tag in VOID_TAGS
        if not is_void:
            self.stack.append(tag)
        if self.ignored_depth is not None:
            return
        if tag in IGNORED_TAGS:
            self.ignored_depth = len(self.stack)
            return
        if self.target_depth is not None and tag in BLOCK_TAGS:
            self.parts.append(None)
        if dict(attrs).get("id") == self.element_id:
            self.matches += 1
            if self.matches == 1 and not is_void:
                self.target_depth = len(self.stack)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index] == tag:
                break
        else:
            return
        del self.stack[index:]
        was_ignored = self.ignored_depth is not None
        if was_ignored and self.ignored_depth > index:
            self.ignored_depth = None
        if self.target_depth is not None:
            if self.target_depth > index:
                if self.target_depth != index + 1:
                    raise ValueError(f"Element {self.element_id!r} has no closing tag.")
                self.target_depth = None
            elif not was_ignored and tag in BLOCK_TAGS:
                self.parts.append(None)

    def handle_data(self, data):
        if self.target_depth is not None and self.ignored_depth is None:
            self.parts.append(data)

    def result(self):
        if self.matches == 0:
            raise ValueError(f"No element found with id {self.element_id!r}.")
        if self.matches > 1:
            raise ValueError(f"More than one element has id {self.element_id!r}.")
        if self.target_depth is not None:
            raise ValueError(f"Element {self.element_id!r} has no closing tag.")

        lines = []
        current = []
        for part in [*self.parts, None]:
            if part is None:
                line = " ".join("".join(current).split())
                if line:
                    lines.append(line)
                current.clear()
            else:
                current.append(part)
        if not lines:
            raise ValueError(f"Element {self.element_id!r} contains no text.")
        return "\n".join(lines)


def extract_section(html, element_id):
    parser = SectionParser(element_id)
    parser.feed(html)
    parser.close()
    return parser.result()


def validate_url(url):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Use an HTTP or HTTPS page URL.")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URLs containing login credentials are unsupported.")


class WebRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_html(stream, encoding):
    data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("The HTML exceeds the 2 MiB size limit.")
    return data.decode(encoding)


def read_source(source):
    if "://" not in source:
        path = Path(source).resolve()
        with path.open("rb") as stream:
            return path.as_uri(), read_html(stream, "utf-8-sig")

    url, _ = urldefrag(source)
    validate_url(url)
    request = Request(url, headers={"User-Agent": "SectionWatch/1.0", "Accept": "text/html"})
    opener = build_opener(WebRedirectHandler())
    with opener.open(request, timeout=10) as response:
        if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("The server did not return HTML.")
        encoding = response.headers.get_content_charset() or "utf-8-sig"
        return url, read_html(response, encoding)


def save_snapshot(database, source, element_id, current):
    # Serialize the read and write so concurrent checks each see the latest saved text.
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS snapshots ("
            "source TEXT NOT NULL, element_id TEXT NOT NULL, text TEXT NOT NULL, "
            "PRIMARY KEY (source, element_id))"
        )
        key = (source, element_id)
        row = connection.execute(
            "SELECT text FROM snapshots WHERE source = ? AND element_id = ?", key
        ).fetchone()
        if row is not None and row[0] == current:
            return row[0]
        connection.execute(
            "INSERT INTO snapshots (source, element_id, text) VALUES (?, ?, ?) "
            "ON CONFLICT (source, element_id) DO UPDATE SET text = excluded.text",
            (*key, current),
        )
        return None if row is None else row[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="HTTP(S) page URL or local HTML file")
    parser.add_argument("--id", required=True, help="HTML id of the element to track, without #")
    parser.add_argument(
        "--state", type=Path, default=Path(".section-watch.sqlite3"), help="snapshot database path"
    )
    args = parser.parse_args(argv)

    try:
        source, html = read_source(args.source)
        current = extract_section(html, args.id)
        previous = save_snapshot(args.state, source, args.id, current)
    except HTTPError as error:
        message = f"The server returned HTTP {error.code}."
        if error.code == 429:
            message += " The server is rate limiting requests. Wait before checking again."
        error.close()
        print(f"Check failed. {message} The saved snapshot was kept.", file=sys.stderr)
        return 1
    except (HTTPException, OSError, ValueError, LookupError, sqlite3.Error) as error:
        print(f"Check failed. {error} The saved snapshot was kept.", file=sys.stderr)
        return 1

    if previous is None:
        print(f"Saved first snapshot for {args.id!r}.")
    elif previous == current:
        print(f"No change in {args.id!r}.")
    else:
        difference = difflib.unified_diff(
            previous.splitlines(), current.splitlines(), "previous", "current", lineterm=""
        )
        print(f"Changed text in {args.id!r}.")
        print("\n".join(difference))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="backslashreplace")
    raise SystemExit(main())
