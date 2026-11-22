#!/usr/bin/env python3
"""Compare the library's pages with the artifact's, for the two-way sync of step 0.

A page made in a claude.ai chat reaches the artifact but often not the GitHub repo, and
a page made here reaches the repo but sometimes not the artifact. This script says, page
by page, which way each one goes so that each side ends up with what the other has.

PAGES is a text file of the artifact's pages, one per line: its path and its sha256 (the
prefix the Artifact tool's file listing prints is enough). The listing's own lines work
as they are:  - "Proj/artifact/2026-10-15-DexAgent.html"  text/html  54008 bytes  sha256 f4e8…
Only pages count (*/artifact/*.html); index.html and library.js are rebuilt, not synced.

Prints one line per page that needs a move, then a summary:
  download <path>   only in the artifact, or newer there: read it and every listed file
                    under its folder (<path> without .html) into the library
  upload <path>     only here, or newer here: publish it; the lines after it name its
                    figure files, which go with it
  conflict <path>   changed on both sides: keep the repo's, and ask the user
  skip <path>       not a library page (<Project>/artifact/<name>.html)
  wontfit <path>    only here, but its files would pass the artifact's file cap: tell
                    the user it stays in the repo only
  same <n>          pages already alike on both sides
  room <n>          files the artifact can still take after these uploads

The artifact holds at most CAP files (511 per version); FILES is how many it holds now,
the count its listing starts with. Pages only here go up newest first while their files
fit and RESERVE files stay free for the papers still to come (a page with its figures
takes 10 to 40); a page newer here replaces its old copy and takes no new room.

A page that differs is newer here when the artifact holds a version this repo committed
before; it is newer in the artifact when the repo never had that version and the page
here has no uncommitted change; otherwise both changed.

Usage: sync_plan.py LIBRARY PAGES.txt --files N [--cap 511] [--reserve 40]
"""
import argparse
import hashlib
import re
import subprocess
from pathlib import Path

PAGE = re.compile(r"^[^/]+/artifact/[^/]+\.html$")


def artifact_pages(text):
    """{path: sha256 prefix} from the listing's lines (or plain "path sha" lines)."""
    pages = {}
    for line in text.splitlines():
        m = re.search(r'"([^"]+\.html)".*?sha256\s+([0-9a-f]+)', line) or \
            re.match(r"\s*([^\s\"]+\.html)\s+([0-9a-f]{8,})", line)
        if m:
            pages[m.group(1)] = m.group(2)
    return pages


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True).stdout


def committed_shas(root, path):
    """The sha256 of every version of `path` the repo ever committed."""
    shas = set()
    for commit in git(root, "log", "--format=%H", "--", path).decode().split():
        shas.add(sha(git(root, "show", f"{commit}:{path}")))
    return shas


def figures(root, path):
    """The files of a page's figure folder, as paths relative to the library."""
    folder = root / path[:-len(".html")]
    return [f.relative_to(root).as_posix() for f in sorted(folder.rglob("*")) if f.is_file()] \
        if folder.is_dir() else []


def plan(root, remote, room):
    """The moves, as (action, path) pairs, the number of pages already alike, and the
    room left in the artifact after the uploads."""
    moves, same = [], 0
    local = {p.relative_to(root).as_posix() for p in root.glob("*/artifact/*.html")}
    for path, there in sorted(remote.items()):
        if not PAGE.match(path):
            moves.append(("skip", path))
        elif path not in local:
            moves.append(("download", path))
        elif sha((root / path).read_bytes()).startswith(there):
            same += 1
        elif any(old.startswith(there) for old in committed_shas(root, path)):
            moves.append(("upload", path))
        elif not git(root, "status", "--porcelain", "--", path).strip():
            moves.append(("download", path))
        else:
            moves.append(("conflict", path))
    # pages only here, newest first (by the date their names start with), while they fit
    for path in sorted(local - set(remote), key=lambda p: (Path(p).name, p), reverse=True):
        need = 1 + len(figures(root, path))
        if need <= room:
            moves.append(("upload", path))
            room -= need
        else:
            moves.append(("wontfit", path))
    return moves, same, room


def main():
    args = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    args.add_argument("library")
    args.add_argument("pages")
    args.add_argument("--files", type=int, required=True, help="files the artifact holds now")
    args.add_argument("--cap", type=int, default=511, help="files the artifact can hold")
    args.add_argument("--reserve", type=int, default=40, help="files kept free for new papers")
    a = args.parse_args()
    root = Path(a.library).resolve()
    room = max(0, a.cap - a.files - a.reserve)
    moves, same, room = plan(root, artifact_pages(Path(a.pages).read_text()), room)
    for action, path in moves:
        print(action, path)
        if action == "upload":  # its figures go with it
            for f in figures(root, path):
                print("upload", f)
    print("same", same)
    print("room", room)


if __name__ == "__main__":
    main()
