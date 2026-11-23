#!/usr/bin/env python3
"""Write this copy's figures.js after figures went up to the artifact's asset store.

After each upload (an Artifact publish with asset: true), paste the result's lines into
UPLOADS.txt as they are, one line per file:
  - "/…/lib/Proj/artifact/2026-11-16-ARSTAG/fig1.jpg" (209570 bytes, image/jpeg) → "/_blob/853e…" (id 853e…)
Such a line names the asset's id twice and the file's size. A line whose two ids differ,
or whose size is not the library file's, is reported as `bad` and left out, so a copying
slip cannot point a figure at the wrong asset. Plain "<path> <id>" lines work too,
unchecked.

Writes OUT: the copy's old map (--figures, read from the artifact), plus the uploads,
minus the figures no longer in the library. Then prints:
  bad <line>        an upload line that failed the checks: upload that file again
  missing <path>    a figure of a page here that the map does not cover: upload it and
                    run this again
  remove <path>     a figure file the artifact's version still holds, which the map now
                    covers: publish it as null to free the version's room
  stored <n>        figures the map covers

Usage: figures_map.py LIBRARY LISTING.txt --uploads UPLOADS.txt [--figures FIGURES.js] --out OUT.js
"""
import argparse
import json
import re
from pathlib import Path

from sync_plan import FIGURE, figures, listing, sha, stored

LINE = re.compile(r'"([^"]+)"\s*\((\d+) bytes.*?/_blob/([0-9a-f]{32})(?:.*?\(id ([0-9a-f]{32})\))?')
PLAIN = re.compile(r"^\s*(\S+)\s+([0-9a-f]{32})\s*$")
HEAD = ("/* This copy's figures in the artifact's asset store, by their path in the library.\n"
        "   Written by figures_map.py (paper-explain); library.js points each page's figures\n"
        "   at /_blob/<id>. Each account's copy has its own. */\n")


def library_path(path):
    """<Project>/artifact/<page>/<file> from an uploaded file's path, wherever it was staged."""
    head, sep, tail = path.rpartition("/artifact/")
    return head.rsplit("/", 1)[-1] + sep + tail if sep else path


def merge(root, store, lines):
    """Add the checked upload lines to `store`; return the lines that failed the checks."""
    bad = []
    for line in lines:
        m = LINE.search(line)
        if m:
            path, size, id1, id2 = m.groups()
        elif PLAIN.match(line):
            (path, id1), size, id2 = PLAIN.match(line).groups(), None, None
        else:
            continue  # not an upload line
        rel = library_path(path)
        f = root / rel
        if (id2 and id2 != id1) or not FIGURE.match(rel) or not f.is_file() \
                or (size and int(size) != f.stat().st_size):
            bad.append(line.strip())
            continue
        store[rel] = {"id": id1, "sha": sha(f.read_bytes())[:32]}
    return bad


def main():
    args = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    args.add_argument("library")
    args.add_argument("listing")
    args.add_argument("--uploads", help="the upload results' lines")
    args.add_argument("--figures", help="the copy's figures.js, read from the artifact")
    args.add_argument("--out", required=True)
    a = args.parse_args()
    root = Path(a.library).resolve()
    store = stored(a.figures)
    uploads = Path(a.uploads) if a.uploads else None
    bad = merge(root, store, uploads.read_text().splitlines() if uploads and uploads.is_file() else [])
    store = {p: v for p, v in sorted(store.items()) if (root / p).is_file()}
    Path(a.out).write_text(HEAD + "window.FIGURES = {\n" + ",\n".join(
        f"{json.dumps(p, ensure_ascii=False)}: {json.dumps(v)}" for p, v in store.items()) + "\n};\n")

    for line in bad:
        print("bad", line)
    for page in sorted(p.relative_to(root).as_posix() for p in root.glob("*/artifact/*.html")):
        for f in figures(root, page):
            if f not in store or not sha((root / f).read_bytes()).startswith(store[f]["sha"]):
                print("missing", f)
    for path in sorted(listing(Path(a.listing).read_text())):
        if FIGURE.match(path) and path in store:
            print("remove", path)
    print("stored", len(store))


if __name__ == "__main__":
    main()
