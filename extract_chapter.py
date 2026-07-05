#!/usr/bin/env python3
"""extract_chapter.py -- extract one chapter's clean text from an EPUB.

DOM-walking, alt-aware extraction validated in the step-0 sanity check:

  * walks the DOM (never bare get_text)
  * inlines each equation image's LaTeX from its alt attribute (alt starts with $)
  * marks figure images as [Figure: filename]
  * renders tables as structured `cell | cell` rows
  * reconstructs inline text without injected whitespace (beta0, H0, R2 stay tight)
  * cleanup pass: drops narrow spaces (U+2009/202F/200A) and zero-width U+200B,
    strips abstract wrapper comment nodes, drops margin-index paragraphs that just
    echo an adjacent emphasized term
  * strips Springer frontmatter (copyright, authors, affiliations)

Produces clean chapter TEXT only -- no atomization, no concept records.

Requires ebooklib + beautifulsoup4. These must NOT be installed into the repo or
system Python; run this with the throwaway scratchpad venv interpreter, e.g.:

    <scratchpad>/venv/Scripts/python.exe extract_chapter.py <epub> "<chapter_target>"

Usage:
    extract_chapter.py <epub_path> <chapter_target> [--book-id SLUG] [--out PATH]

<chapter_target> resolves a chapter by internal filename, ToC-title substring, or
chapter number. Output defaults to a deterministic path kb/<book-id>/chNN_extracted.txt
(overwritten, never appended).
"""

import argparse
import os
import re
import sys

try:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup, NavigableString, Tag, Comment
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    sys.exit(
        f"missing dependency: {exc.name!r}. Run this script with the scratchpad venv "
        f"python that has ebooklib + beautifulsoup4 installed (do not install into the "
        f"repo or system Python)."
    )

SENT = "\x01"  # sentinel marking a structural (block) break during rendering
BLOCK = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol",
         "section", "blockquote", "figure", "figcaption", "tr", "caption",
         "dt", "dd", "dl"}
# narrow + zero-width spaces to delete outright (typographic, not word separators)
_DROP_CHARS = {0x2009: None, 0x202F: None, 0x200A: None, 0x200B: None}


def norm(text):
    return re.sub(r"\s+", " ", text).strip().lower()


# --------------------------------------------------------------------------- #
# Chapter resolution
# --------------------------------------------------------------------------- #
def toc_title_map(book):
    """Map internal filename -> first ToC label seen for it."""
    out = {}

    def record(href, title):
        fname = (href or "").split("#", 1)[0]
        if fname and fname not in out:
            out[fname] = title or ""

    def walk(entries):
        for entry in entries:
            if isinstance(entry, tuple):
                section, children = entry[0], entry[1]
                record(getattr(section, "href", ""), getattr(section, "title", ""))
                walk(children)
            else:
                record(getattr(entry, "href", ""), getattr(entry, "title", ""))

    walk(book.toc)
    return out


def spine_docs(book):
    """List of (item, name, basename, title) for spine documents, in reading order."""
    titles = toc_title_map(book)
    docs = []
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        name = item.get_name()
        base = name.rsplit("/", 1)[-1]
        title = titles.get(name) or titles.get(base) or ""
        docs.append((item, name, base, title))
    return docs


def chapter_number(title, base):
    m = re.match(r"\s*(\d+)", title or "")
    if m:
        return int(m.group(1))
    m = re.search(r"_(\d+)_Chapter", base)
    if m:
        return int(m.group(1))
    return None


def resolve_chapter(book, target):
    """Resolve a chapter target to a single spine doc, or exit with candidates."""
    docs = spine_docs(book)
    t = target.strip()
    tl = t.lower()

    exact = [d for d in docs if t in (d[1], d[2])]
    if len(exact) == 1:
        return exact[0]
    if tl.isdigit():
        numbered = [d for d in docs if chapter_number(d[3], d[2]) == int(tl)]
        if len(numbered) == 1:
            return numbered[0]
    by_title = [d for d in docs if tl in (d[3] or "").lower()]
    if len(by_title) == 1:
        return by_title[0]
    by_file = [d for d in docs if tl in d[2].lower()]
    if len(by_file) == 1:
        return by_file[0]

    listing = "\n".join(f"    {d[2]:<40} | {d[3]}" for d in docs)
    hits = len(exact) or len(by_title) or len(by_file)
    reason = "no match" if hits == 0 else "ambiguous match"
    sys.exit(f"could not resolve chapter target {target!r} ({reason}). Available:\n{listing}")


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def _emphasized_terms(node):
    if not isinstance(node, Tag):
        return set()
    terms = set()
    for el in node.find_all(["b", "strong", "em", "i"]):
        terms.add(norm(el.get_text()))
    for el in node.find_all(class_=re.compile("Emphasis")):
        terms.add(norm(el.get_text()))
    return terms


def drop_margin_terms(body):
    """Drop bare short paragraphs that echo an emphasized term in an adjacent sibling.

    These are Springer margin/index keyword paragraphs (e.g. `least squares`) that
    duplicate an italicized term nearby. R lab code (class ParaTypeProgramcode) and
    anything without an adjacent emphasized echo is preserved.
    """
    targets = []
    for p in body.find_all("div", class_="Para"):
        if "ParaTypeProgramcode" in p.get("class", []):
            continue
        if any(isinstance(c, Tag) for c in p.children):  # real paras carry inline tags
            continue
        term = norm(p.get_text())
        if not term or len(term.split()) > 6:
            continue
        prev = p.find_previous_sibling("div")
        nxt = p.find_next_sibling("div")
        if term in _emphasized_terms(prev) or term in _emphasized_terms(nxt):
            targets.append(p)
    for p in targets:
        p.decompose()
    return len(targets)


def render_table(table):
    rows = []
    for tr in table.find_all("tr"):
        cells = [_clean_inline(render(c)) for c in tr.find_all(["th", "td"], recursive=False)]
        if any(cells):
            rows.append(" | ".join(cells))
    return SENT + "[TABLE]" + SENT + SENT.join(rows) + SENT + "[/TABLE]" + SENT


def render(node):
    if isinstance(node, Comment):
        return ""
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    if node.name == "table":
        return render_table(node)
    if node.name == "br":
        return SENT
    inner = "".join(render(child) for child in node.children)
    if node.name in BLOCK:
        return SENT + inner + SENT
    return inner


def _clean_inline(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ").replace(SENT, " ")).strip()


def extract_chapter_text(item):
    """Return (clean_text, stats) for one chapter document item."""
    html = item.get_content().decode("utf-8", "replace").translate(_DROP_CHARS)
    soup = BeautifulSoup(html, "html.parser")
    body = soup.body or soup

    # 1) strip Springer frontmatter (copyright, authors, affiliations) + non-content
    for cls in ("ChapterContextInformation", "AuthorGroup"):
        for el in body.find_all(class_=cls):
            el.decompose()
    for el in body(["style", "script"]):
        el.decompose()

    # 2) strip abstract wrapper (and any other) HTML comment nodes
    for c in body.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()

    # 3) drop margin-index paragraphs that echo an adjacent emphasized term
    dropped = drop_margin_terms(body)

    # 4) tighten sub/sup: remove formatting whitespace before them, flatten to text
    for tag in body.find_all(["sub", "sup"]):
        prev = tag.previous_sibling
        if isinstance(prev, NavigableString) and not prev.strip():
            prev.extract()
        tag.replace_with(NavigableString(tag.get_text().strip()))

    # 5) replace images: equations -> LaTeX alt; figures -> placeholder
    n_eq = n_fig = 0
    for im in body.find_all("img"):
        alt = (im.get("alt") or "").strip()
        if alt.startswith("$"):
            n_eq += 1
            im.replace_with(NavigableString(" " + re.sub(r"\s+", " ", alt).strip() + " "))
        else:
            n_fig += 1
            name = (im.get("src") or alt).rsplit("/", 1)[-1]
            im.replace_with(NavigableString(SENT + f"[Figure: {name}]" + SENT))

    n_tab = len(body.find_all("table"))

    # 6) render, then normalize whitespace and structural breaks
    raw = render(body).replace("\xa0", " ")
    raw = re.sub(r"\s+", " ", raw)                  # collapse whitespace; sentinels survive
    raw = re.sub(r"(?:\s*\x01\s*)+", "\n", raw)     # each structural break -> one newline
    text = "\n".join(ln.strip() for ln in raw.split("\n") if ln.strip()).strip()

    stats = {"equations": n_eq, "figures": n_fig, "tables": n_tab, "dropped_terms": dropped}
    return text, stats


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Extract one chapter's clean text from an EPUB.")
    ap.add_argument("epub_path", help="Path to the .epub file")
    ap.add_argument("chapter_target", help="Chapter filename, ToC-title substring, or number")
    ap.add_argument("--book-id", default="islr-1e", help="Book slug for the output dir (default: islr-1e)")
    ap.add_argument("--out", default=None, help="Explicit output path (overrides the derived path)")
    args = ap.parse_args()

    if not os.path.isfile(args.epub_path):
        ap.error(f"not a file: {args.epub_path}")

    book = epub.read_epub(args.epub_path)
    item, name, base, title = resolve_chapter(book, args.chapter_target)
    num = chapter_number(title, base)

    text, stats = extract_chapter_text(item)

    if args.out:
        out_path = args.out
    else:
        tag = f"ch{num:02d}" if num is not None else "ch_" + re.sub(r"\W+", "_", base).strip("_")[:24]
        out_path = os.path.join("kb", args.book_id, f"{tag}_extracted.txt")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")

    print(f"wrote: {out_path}")
    print(f"  source file  : {name}")
    print(f"  chapter      : {title or '(untitled)'}  (#{num})")
    print(f"  words        : {len(text.split())}")
    print(f"  equations    : {stats['equations']}  (LaTeX inlined)")
    print(f"  tables       : {stats['tables']}  (rendered as rows)")
    print(f"  figures      : {stats['figures']}  (marked [Figure: ...])")
    print(f"  margin terms dropped : {stats['dropped_terms']}")


if __name__ == "__main__":
    main()
