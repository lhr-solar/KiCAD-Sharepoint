#!/usr/bin/env python3
"""
generate_toc.py

Usage:
  python3 scripts/generate_toc.py path/to/file.md [--max-level 3] [--dry-run]

This script finds the first occurrence of a heading named "Table of Contents"
and replaces the following section up to the next heading of the same level with
a generated Table of Contents built from the file's headings.

It uses a GitHub-style slug for anchors (lowercase, spaces -> '-', strips
punctuation) and appends numeric suffixes for duplicate anchors to avoid
collisions (like GitHub's behavior).

Options:
  --max-level N  Include headings up to level N (default: 3)
  --dry-run      Print the modified file to stdout instead of writing
  --backup       Save an original backup as <file>.bak before writing

"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from typing import List, Tuple


def slugify(text: str) -> str:
    """Create a GitHub-style slug for a heading.

    This is a practical approximation: lowercase, strip HTML/markdown inline
    code/links, replace non-alphanum with '-', collapse hyphens, strip '-'.
    Duplicate handling is done separately by the caller.
    """
    # remove inline code `code`
    text = re.sub(r"`([^`]*)`", r"\1", text)
    # remove links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # remove any remaining markup characters
    text = re.sub(r"[\*\_\~\#\>\[\]\(\)]", "", text)
    text = text.strip().lower()
    # replace non-alphanumeric with hyphen
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def parse_headings(lines: List[str]) -> List[Tuple[int, str, int]]:
    """Return list of (level, text, line_index) for markdown headings.

    Recognizes ATX-style headings: #, ##, ### ...
    """
    headings: List[Tuple[int, str, int]] = []
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            headings.append((level, text, i))
    return headings


def generate_toc(headings: List[Tuple[int, str, int]], min_level: int = 2, max_level: int = 3, indent_size: int = 4) -> List[str]:
    """Generate markdown list lines for headings between min_level..max_level.

    Returns the list of TOC lines (without surrounding heading line).
    """
    toc_lines: List[str] = []
    counts = defaultdict(int)
    for level, text, _ in headings:
        if level < min_level or level > max_level:
            continue
        slug_base = slugify(text)
        counts[slug_base] += 1
        slug = slug_base
        if counts[slug_base] > 1:
            slug = f"{slug_base}-{counts[slug_base]-1}"
        indent = " " * (indent_size * (level - min_level))
        toc_lines.append(f"{indent}- [{text}](#{slug})")
    return toc_lines


def find_toc_section(lines: List[str]) -> Tuple[int, int]:
    """Find the start and end indexes (inclusive start, exclusive end) of the
    contents belonging to the first '## Table of Contents' section.

    Returns (insert_at, end_at) where insert_at is the line index after the
    '## Table of Contents' heading and end_at is the line index of the next
    heading with the same or higher level (i.e., another H2 or H1) or EOF.
    If no 'Table of Contents' heading found, returns (-1, -1).
    """
    headings = parse_headings(lines)
    target_idx = None
    for level, text, i in headings:
        if text.lower() == "table of contents":
            target_idx = (level, i)
            break
    if target_idx is None:
        return -1, -1
    level, idx = target_idx
    insert_at = idx + 1
    # find next heading with level <= level
    end_at = len(lines)
    for lvl, _, j in headings:
        if j <= idx:
            continue
        if lvl <= level:
            end_at = j
            break
    return insert_at, end_at


def update_file(path: str, max_level: int = 3, dry_run: bool = False, backup: bool = True) -> int:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    insert_at, end_at = find_toc_section(lines)
    if insert_at == -1:
        print("No 'Table of Contents' heading found. No changes made.")
        return 1

    headings = parse_headings(lines)
    # Use a 4-space indent by default for nested list items. Many Markdown
    # renderers (including the one MkDocs uses) require 4 spaces to render
    # nested lists correctly, otherwise subitems may appear at the same level.
    toc_lines = generate_toc(headings, min_level=2, max_level=max_level, indent_size=opts_indent_size)

    new_lines = list(lines[:insert_at])
    # ensure a blank line after the heading
    if not new_lines or new_lines[-1].strip() != "":
        new_lines.append("")
    if toc_lines:
        new_lines.extend(toc_lines)
        new_lines.append("")
    else:
        new_lines.append("_No headings found to populate TOC._")
        new_lines.append("")
    new_lines.extend(lines[end_at:])

    out = "\n".join(new_lines) + "\n"

    if dry_run:
        print(out)
        return 0

    if backup:
        bak = path + ".bak"
        with open(bak, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Backup written to: {bak}")

    with open(path, "w", encoding="utf-8") as f:
        f.write(out)

    print(f"Updated TOC in {path}")
    return 0


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate/update Table of Contents for a Markdown file")
    p.add_argument("file", help="Path to the markdown file to update")
    p.add_argument("--max-level", type=int, default=3, help="Maximum heading level to include (default: 3)")
    p.add_argument("--indent-size", type=int, default=4, help="Number of spaces per indent level (default: 4)")
    p.add_argument("--dry-run", action="store_true", help="Print results to stdout instead of writing")
    p.add_argument("--no-backup", dest="backup", action="store_false", help="Don't write a .bak backup")
    args = p.parse_args(argv)

    if not os.path.isfile(args.file):
        print(f"File not found: {args.file}")
        return 2

    # pass indent size through to the updater
    global opts_indent_size
    opts_indent_size = args.indent_size
    return update_file(args.file, max_level=args.max_level, dry_run=args.dry_run, backup=args.backup)


if __name__ == "__main__":
    raise SystemExit(main())
