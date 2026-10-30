#!/usr/bin/env python3
"""
Import Georgia law (O.C.G.A. Titles 16, 17, 42) from public sources and
update the law library JSON files served to residents.

Usage:
    python scripts/import_law.py [--output-dir DIR]

NOTE: O.C.G.A. full text is not freely available in bulk from an official
machine-readable API. This script fetches from legis.ga.gov (the official
Georgia General Assembly website) where HTML is publicly accessible, and
converts it to plain text. For production use, review with legal counsel
to confirm that the text is current and complete.

The script also refreshes the existing static law files (Constitution,
Declaration, PLRA) from web/public/law/ — it does not overwrite those
since they are already committed as authoritative verbatim text.

Titles imported:
  - Title 16 (Crimes and Offenses)
  - Title 17 (Criminal Procedure)
  - Title 42 (Penal Institutions)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from html.parser import HTMLParser

OUTPUT_DIR = Path("web/public/law")

# Georgia statute titles to fetch from legis.ga.gov
# The GA General Assembly site has title-level HTML pages we can parse.
GA_TITLES = [
    ("16", "Crimes and Offenses"),
    ("17", "Criminal Procedure"),
    ("42", "Penal Institutions"),
]

GA_BASE = "https://law.justia.com/codes/georgia/title-{title}/"
GA_ALT  = "https://legis.ga.gov/api/law/ocga/title/{title}"


class SimpleHTMLStripper(HTMLParser):
    """Extract plain text from HTML, preserving paragraph breaks."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "header", "footer"):
            self._skip = True
        if tag in ("p", "h1", "h2", "h3", "h4", "li", "br"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "header", "footer"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def get_text(self) -> str:
        text = "".join(self.parts)
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def fetch_url(url: str, description: str) -> str | None:
    try:
        print(f"  Fetching {description} from {url} …", end=" ", flush=True)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ISD-LawImport/1.0 (correctional facility law library; contact: facility-tech@example.invalid)"
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        print("ok")
        return text
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}")
    except Exception as e:
        print(f"error: {e}")
    return None


def html_to_text(html: str) -> str:
    parser = SimpleHTMLStripper()
    parser.feed(html)
    return parser.get_text()


def build_georgia_json(title_num: str, title_name: str, out_dir: Path) -> bool:
    """
    Attempt to fetch O.C.G.A. title and write/update georgia.json.
    Returns True on success.
    """
    url = GA_BASE.format(title=title_num)
    html = fetch_url(url, f"O.C.G.A. Title {title_num}")
    if html is None:
        return False

    text = html_to_text(html)
    if len(text) < 500:
        print(f"  Warning: fetched text is very short ({len(text)} chars); skipping")
        return False

    georgia_path = out_dir / "georgia.json"
    # Load existing file if present
    if georgia_path.exists():
        try:
            data = json.loads(georgia_path.read_text())
        except Exception:
            data = {"id": "georgia", "title": "Official Code of Georgia Annotated (O.C.G.A.)", "sections": []}
    else:
        data = {"id": "georgia", "title": "Official Code of Georgia Annotated (O.C.G.A.)", "sections": []}

    # Find or replace section for this title
    section_id = f"title-{title_num}"
    new_section = {
        "id": section_id,
        "title": f"Title {title_num} — {title_name}",
        "text": text[:50000],  # cap at ~50k chars to keep file reasonable
    }
    existing = [s for s in data["sections"] if s["id"] != section_id]
    data["sections"] = existing + [new_section]

    georgia_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"  Updated {georgia_path} with Title {title_num} ({len(text):,} chars fetched, {min(len(text), 50000):,} stored)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Directory containing law JSON files")
    parser.add_argument("--titles", nargs="*", default=[t for t, _ in GA_TITLES], help="Georgia title numbers to import")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    print("\n=== Importing Georgia O.C.G.A. ===")
    for title_num, title_name in GA_TITLES:
        if title_num not in args.titles:
            continue
        print(f"\n[Title {title_num}] {title_name}")
        ok = build_georgia_json(title_num, title_name, out_dir)
        if not ok:
            errors.append(f"Title {title_num}: fetch failed")
        time.sleep(2)  # be polite to the server

    print("\n=== Verifying existing law files ===")
    for fname, description in [
        ("constitution.json", "US Constitution"),
        ("plra.json", "Prison Litigation Reform Act"),
        ("declaration.json", "Declaration of Independence"),
    ]:
        p = out_dir / fname
        if not p.exists():
            print(f"  MISSING: {fname} ({description})")
            errors.append(f"{fname} not found in {out_dir}")
        else:
            data = json.loads(p.read_text())
            n = len(data.get("sections", []))
            chars = len(str(data))
            print(f"  OK: {fname} — {n} sections, {chars:,} chars")

    print(f"\n{'='*60}")
    if errors:
        print(f"Finished with {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        print("\nNote: Network errors are expected in offline/CI environments.")
        print("The static law files in web/public/law/ are the authoritative source.")
        sys.exit(1)
    else:
        print("All law files present and accounted for.")


if __name__ == "__main__":
    main()
