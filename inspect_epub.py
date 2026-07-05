#!/usr/bin/env python3
"""Report the structure of an EPUB: table of contents, documents in reading
order, and each document's title + approximate word count.

Structure only. This script does not extract, clean, summarize, or atomize
content, and it writes no files -- everything goes to stdout.

Usage:
    python inspect_epub.py <path-to-epub>
"""

import argparse
import os
import sys

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup


def strip_fragment(href):
    """Return the file portion of an href, dropping any #fragment."""
    return (href or "").split("#", 1)[0]


def text_of(item):
    """Approximate word count and parsed soup for a document item."""
    soup = BeautifulSoup(item.get_content(), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(" ")
    return len(text.split()), soup


def title_from_soup(soup):
    """Best-effort title from a document's own markup."""
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    for level in ("h1", "h2"):
        h = soup.find(level)
        if h and h.get_text(strip=True):
            return h.get_text(strip=True)
    return None


def walk_toc(entries, toc_map, depth=0, lines=None):
    """Recursively render book.toc and record the first label seen per file.

    Handles ebooklib's mixed structure: bare epub.Link / epub.Section nodes,
    and (Section, [children]) tuples.
    """
    if lines is None:
        lines = []
    for entry in entries:
        if isinstance(entry, tuple):
            section, children = entry[0], entry[1]
            title = getattr(section, "title", "") or "(section)"
            href = getattr(section, "href", "") or ""
            lines.append(("  " * depth) + f"- {title}" + (f"  [{href}]" if href else ""))
            _record(toc_map, href, title)
            walk_toc(children, toc_map, depth + 1, lines)
        else:  # epub.Link or epub.Section leaf
            title = getattr(entry, "title", "") or "(untitled)"
            href = getattr(entry, "href", "") or ""
            lines.append(("  " * depth) + f"- {title}" + (f"  [{href}]" if href else ""))
            _record(toc_map, href, title)
    return lines


def _record(toc_map, href, title):
    fname = strip_fragment(href)
    if fname and fname not in toc_map:
        toc_map[fname] = title


def main():
    parser = argparse.ArgumentParser(
        description="Report an EPUB's structure (ToC, reading order, word counts). Read-only."
    )
    parser.add_argument("epub_path", help="Path to the .epub file")
    args = parser.parse_args()

    if not os.path.isfile(args.epub_path):
        parser.error(f"not a file: {args.epub_path}")

    book = epub.read_epub(args.epub_path)

    # --- Header ---------------------------------------------------------
    def meta(field):
        vals = book.get_metadata("DC", field)
        return vals[0][0] if vals else "(none)"

    print("=" * 70)
    print(f"EPUB: {os.path.basename(args.epub_path)}")
    print(f"Title:      {meta('title')}")
    print(f"Identifier: {meta('identifier')}")
    print(f"Language:   {meta('language')}")
    print("=" * 70)

    # --- Table of contents ---------------------------------------------
    toc_map = {}  # filename -> first ToC label
    toc_lines = walk_toc(book.toc, toc_map)
    print("\nTABLE OF CONTENTS")
    print("-" * 70)
    if toc_lines:
        print("\n".join(toc_lines))
    else:
        print("(empty / unparseable ToC -- titles below fall back to document markup)")
    print(f"\nToC entries (files referenced): {len(toc_map)}")

    # --- Documents in reading order (spine) ----------------------------
    print("\nDOCUMENTS IN READING ORDER (spine)")
    print("-" * 70)
    print(f"{'#':>3}  {'words':>8}  {'file':<34}  title")
    print(f"{'-'*3}  {'-'*8}  {'-'*34}  {'-'*20}")

    total_words = 0
    count = 0
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None:
            print(f"{count:>3}  {'?':>8}  (unresolved idref: {idref})")
            count += 1
            continue

        fname = item.get_name()
        words = 0
        soup = None
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            words, soup = text_of(item)
            total_words += words

        title = toc_map.get(fname)
        if not title and soup is not None:
            title = title_from_soup(soup)
        if not title:
            title = "(untitled)"

        shown = fname if len(fname) <= 34 else "…" + fname[-33:]
        print(f"{count:>3}  {words:>8}  {shown:<34}  {title}")
        count += 1

    print("-" * 70)
    print(f"{count} spine documents,  ~{total_words} words total")
    print("\n(Structure only -- no content extracted, no files written.)")


if __name__ == "__main__":
    main()
