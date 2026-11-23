#!/usr/bin/env python3
"""Compare the library with this account's copy of the artifact, for the two-way sync of step 0.

A page made in a claude.ai chat reaches the artifact but often not the GitHub repo, and
a page made here reaches the repo but sometimes not the artifact. This script says, page
by page, which way each one goes so that each side ends up with what the other has.

The artifact holds the pages as files and their figures in its asset store: a version
holds at most 511 files, the store 5000. The copy's figures.js maps each stored figure to
its asset, {"<path in the library>": {"id": <asset id>, "sha": <sha256 prefix>}}, and
library.js points each page's figures at their stored copies through it.

LISTING is the artifact's file listing as the Artifact tool prints it (scope "files"), or
plain "path sha" lines. FIGURES is the copy's figures.js, read from the artifact; leave
it out when the artifact has none.

Prints one line per move, then a summary:
  download <path>   only in the artifact, or newer there: read it and every listed file
                    under its folder (<path> without .html) into the library
  upload <path>     only here, or newer here: publish it (library.js too, when the
                    copy's differs from the library's)
  conflict <path>   changed on both sides: keep the repo's, and ask the user
  skip <path>       not a library page (<Project>/artifact/<name>.html)
  asset <path>      a figure of a page here that the copy does not store, or stores an
                    older version of: upload it to the asset store
  same <n>          pages already alike on both sides

A page that differs is newer here when the artifact holds a version this repo committed
before; it is newer in the artifact when the repo never had that version and the page
here has no uncommitted change; otherwise both changed.

Usage: sync_plan.py LIBRARY LISTING.txt [--figures FIGURES.js]
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

PAGE = re.compile(r"^[^/]+/artifact/[^/]+\.html$")
FIGURE = re.compile(r"^[^/]+/artifact/[^/]+/.+")  # a file in a page's folder


def listing(text):
    """{path: sha256 prefix} from the listing's lines (or plain "path sha" lines)."""
    files = {}
    for line in text.splitlines():
        m = re.search(r'"([^"]+)".*?sha256\s+([0-9a-f]+)', line) or \
            re.match(r"\s*([^\s\"]+)\s+([0-9a-f]{8,})\s*$", line)
        if m:
            files[m.group(1)] = m.group(2)
    return files


def stored(path):
    """The copy's figure map from its figures.js (a plain JSON object works too); none
    when the copy has no figures.js yet."""
    if not path or not Path(path).is_file():
        return {}
    text = Path(path).read_text()
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


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


def figures(root, page):
    """The files of a page's figure folder, as paths relative to the library."""
    folder = root / page[:-len(".html")]
    return [f.relative_to(root).as_posix() for f in sorted(folder.rglob("*")) if f.is_file()] \
        if folder.is_dir() else []


def plan(root, remote, store):
    """The moves, as (action, path) pairs, and the number of pages already alike."""
    moves, same = [], 0
    local = {p.relative_to(root).as_posix() for p in root.glob("*/artifact/*.html")}
    for path, there in sorted(remote.items()):
        if not PAGE.match(path):
            if path.endswith(".html") and path != "index.html" and not FIGURE.match(path):
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
    for path in sorted(local - set(remote)):
        moves.append(("upload", path))
    script = root / "library.js"  # build_index.py copies it from this skill
    if script.is_file() and not sha(script.read_bytes()).startswith(remote.get("library.js") or "-"):
        moves.append(("upload", "library.js"))
    for page in sorted(local):
        for f in figures(root, page):
            known = store.get(f, {}).get("sha")
            if not known or not sha((root / f).read_bytes()).startswith(known):
                moves.append(("asset", f))
    return moves, same


def main():
    args = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    args.add_argument("library")
    args.add_argument("listing")
    args.add_argument("--figures", help="the copy's figures.js, read from the artifact")
    a = args.parse_args()
    root = Path(a.library).resolve()
    moves, same = plan(root, listing(Path(a.listing).read_text()), stored(a.figures))
    for action, path in moves:
        print(action, path)
    print("same", same)


if __name__ == "__main__":
    main()
