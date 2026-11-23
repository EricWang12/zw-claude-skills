#!/usr/bin/env python3
"""Merge this account's stars with the library's, so every account shows the same stars.

Each Claude account has its own copy of the library artifact, and stars live in a copy's
database, so a star made in one account would stay there. The library's repo holds the
shared set, LIBRARY/stars.json. Each copy keeps, in its doc "config/sync", the stars it
had when it last synced, so this script can tell what the user starred and unstarred in
this account since then, and apply just that to the shared set:

  shared := (shared + starred here since the last sync) - unstarred here since then

A first sync (no base) only adds: nothing this account never saw is taken away.

DB.txt holds this copy's star ids (the doc ids of its collection "stars"), BASE.txt the
"stars" list of its doc "config/sync", one id per line; leave --base out when that doc
does not exist. An id is "<Project>" (a whole folder) or "<Project>:<name>" (one paper).

Writes LIBRARY/stars.json when the shared set changes, and prints this copy's writes:
  set <id> <path>   set the doc stars/<id> to {"path": <path>}
  delete <id>       delete the doc stars/<id>
  stars <n> <json>  the shared set; set the doc config/sync to {"stars": <json>}

Usage: stars_sync.py LIBRARY --db DB.txt [--base BASE.txt]
"""
import argparse
import json
from pathlib import Path


def ids(path):
    return {line.strip() for line in Path(path).read_text().splitlines() if line.strip()}


def star_path(key):
    """The path a star doc records, as library.js writes it."""
    return key.replace(":", "/artifact/", 1) + ".html" if ":" in key else key + "/"


def merge(shared, here, base):
    """The new shared set: this account's changes since its last sync, applied to it."""
    if base is None:
        return shared | here
    return (shared | (here - base)) - (base - here)


def main():
    args = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    args.add_argument("library")
    args.add_argument("--db", required=True, help="this copy's star ids, one per line")
    args.add_argument("--base", help="this copy's stars at its last sync, one per line")
    a = args.parse_args()
    store = Path(a.library) / "stars.json"
    shared = set(json.loads(store.read_text())["stars"]) if store.exists() else set()
    here = ids(a.db)
    new = merge(shared, here, ids(a.base) if a.base else None)
    if new != shared or not store.exists():
        store.write_text(json.dumps({"stars": sorted(new)}, ensure_ascii=False, indent=1) + "\n")
    for key in sorted(new - here):
        print("set", key, star_path(key))
    for key in sorted(here - new):
        print("delete", key)
    print("stars", len(new), json.dumps(sorted(new), ensure_ascii=False))


if __name__ == "__main__":
    main()
