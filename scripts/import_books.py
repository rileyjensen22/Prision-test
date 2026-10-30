#!/usr/bin/env python3
"""
Import public-domain books from Project Gutenberg into the reading library.

Usage:
    python scripts/import_books.py [--db-url DATABASE_URL] [--output-dir DIR]

Downloads 20 classic public-domain texts, stores them in the database as
LibraryItem records, and writes JSON files to web/public/books/ for the
resident reader. Uses only non-copyrighted material (pre-1928 or donated
to the public domain).

Requires: requests, sqlalchemy (already in requirements.txt)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Books to import: (gutenberg_id, title, author, approximate_year)
BOOKS = [
    (11, "Alice's Adventures in Wonderland", "Lewis Carroll", 1865),
    (1342, "Pride and Prejudice", "Jane Austen", 1813),
    (84, "Frankenstein", "Mary Shelley", 1818),
    (1661, "The Adventures of Sherlock Holmes", "Arthur Conan Doyle", 1892),
    (2701, "Moby Dick", "Herman Melville", 1851),
    (98, "A Tale of Two Cities", "Charles Dickens", 1859),
    (1232, "The Prince", "Niccolò Machiavelli", 1532),
    (2591, "Grimms' Fairy Tales", "Brothers Grimm", 1812),
    (174, "The Picture of Dorian Gray", "Oscar Wilde", 1890),
    (1080, "A Modest Proposal", "Jonathan Swift", 1729),
    (46, "A Christmas Carol", "Charles Dickens", 1843),
    (1400, "Great Expectations", "Charles Dickens", 1861),
    (345, "Dracula", "Bram Stoker", 1897),
    (514, "Little Women", "Louisa May Alcott", 1868),
    (2554, "Crime and Punishment", "Fyodor Dostoevsky", 1866),
    (1260, "Jane Eyre", "Charlotte Brontë", 1847),
    (768, "Wuthering Heights", "Emily Brontë", 1847),
    (2600, "War and Peace", "Leo Tolstoy", 1869),
    (4300, "Ulysses", "James Joyce", 1922),
    (5200, "Metamorphosis", "Franz Kafka", 1915),
]

GUTENBERG_BASE = "https://www.gutenberg.org/files/{id}/{id}-0.txt"
GUTENBERG_ALT  = "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt"

PREVIEW_CHARS = 2000  # characters to store as preview text


def fetch_text(book_id: int, title: str) -> str | None:
    import urllib.request
    import urllib.error

    urls = [
        GUTENBERG_BASE.format(id=book_id),
        GUTENBERG_ALT.format(id=book_id),
        f"https://www.gutenberg.org/files/{book_id}/{book_id}.txt",
    ]
    for url in urls:
        try:
            print(f"  Fetching {title} from {url} …", end=" ", flush=True)
            req = urllib.request.Request(url, headers={"User-Agent": "ISD-LibraryImport/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
            # Gutenberg files are UTF-8 or Latin-1
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


def strip_gutenberg_header(text: str) -> str:
    """Remove the Project Gutenberg header/footer boilerplate."""
    start_markers = [
        "*** START OF THE PROJECT GUTENBERG",
        "***START OF THE PROJECT GUTENBERG",
        "*** START OF THIS PROJECT GUTENBERG",
    ]
    end_markers = [
        "*** END OF THE PROJECT GUTENBERG",
        "***END OF THE PROJECT GUTENBERG",
        "*** END OF THIS PROJECT GUTENBERG",
    ]
    for m in start_markers:
        idx = text.find(m)
        if idx != -1:
            text = text[idx:]
            text = text[text.find("\n") + 1:]
            break
    for m in end_markers:
        idx = text.find(m)
        if idx != -1:
            text = text[:idx]
            break
    return text.strip()


def write_json(out_dir: Path, book_id: int, title: str, author: str, year: int, text: str) -> None:
    slug = f"book-{book_id}"
    data = {
        "id": slug,
        "title": title,
        "author": author,
        "year": year,
        "source": "Project Gutenberg (public domain)",
        "preview": text[:PREVIEW_CHARS],
        "full_text": text,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"  Wrote {out_path} ({len(text):,} chars)")


def insert_db(db_url: str, book_id: int, title: str, author: str, year: int, text: str) -> None:
    from sqlalchemy import create_engine, text as sa_text

    engine = create_engine(db_url)
    slug = f"book-{book_id}"
    with engine.begin() as conn:
        conn.execute(
            sa_text(
                """
                INSERT INTO library_items (slug, title, author, published_year, source, preview_text, full_text, approved, min_tier)
                VALUES (:slug, :title, :author, :year, :source, :preview, :full, true, 1)
                ON CONFLICT (slug) DO UPDATE
                  SET title = EXCLUDED.title,
                      full_text = EXCLUDED.full_text,
                      preview_text = EXCLUDED.preview_text
                """
            ),
            {
                "slug": slug,
                "title": title,
                "author": author,
                "year": year,
                "source": "Project Gutenberg (public domain)",
                "preview": text[:PREVIEW_CHARS],
                "full": text,
            },
        )
    print(f"  Inserted/updated DB record for {title}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL"), help="PostgreSQL connection URL")
    parser.add_argument("--output-dir", default="web/public/books", help="Directory for JSON output files")
    parser.add_argument("--json-only", action="store_true", help="Write JSON files only, skip DB insert")
    parser.add_argument("--limit", type=int, default=len(BOOKS), help="Import only the first N books")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    errors: list[str] = []

    for book_id, title, author, year in BOOKS[: args.limit]:
        print(f"\n[{book_id}] {title} — {author} ({year})")
        text = fetch_text(book_id, title)
        if text is None:
            errors.append(f"{title} (id {book_id}): all download attempts failed")
            continue

        text = strip_gutenberg_header(text)

        write_json(out_dir, book_id, title, author, year, text)

        if not args.json_only and args.db_url:
            try:
                insert_db(args.db_url, book_id, title, author, year, text)
            except Exception as e:
                print(f"  DB insert failed: {e} (JSON file still written)")
                errors.append(f"{title}: DB insert failed — {e}")

        time.sleep(1)  # be polite to Gutenberg's servers

    print(f"\n{'='*60}")
    print(f"Done. {len(BOOKS[:args.limit]) - len(errors)} succeeded, {len(errors)} failed.")
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
