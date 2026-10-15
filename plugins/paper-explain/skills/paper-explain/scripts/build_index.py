#!/usr/bin/env python3
"""Rebuild LIBRARY/index.html, the artifact's home page, from the folder tree.

Layout it reads:  LIBRARY/<Project>/artifact/<YYYY-MM-DD>-<Short>.html
The page title is the "Artifact title:" line of LIBRARY/preferences.md.
From each page it takes <title>, <meta name="description"> (the TL;DR line) and
<meta name="paper:title">/<meta name="paper:venue">. Every project folder is
listed, newest paper first; an empty project shows as empty.

index.html is written without <!doctype>/<head>/<body> because the Artifact tool
wraps the main page in its own skeleton. Colors and fonts come from the
tokens block of the paper template, so both pages always match.

Prints the paths (relative to LIBRARY) of every file under */artifact/, one per
line, which is the `files` list for a full publish.

Usage: build_index.py LIBRARY
"""
import html
import re
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "paper-template.html"
FONTS = TEMPLATE.read_text().split('<link rel="stylesheet" href="')[1].split('"')[0]
TOKENS = re.search(r"/\* tokens:start \*/(.*?)/\* tokens:end \*/", TEMPLATE.read_text(), re.S).group(1)

CSS = TOKENS + """
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.6 var(--f-body);
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.frame { max-width: 1040px; margin: 0 auto; }
.eyebrow { font: 500 .75rem/1.3 var(--f-mono); letter-spacing: .09em; text-transform: uppercase; color: var(--muted); margin: 0 0 .5rem; }
header { padding-block: 2.75rem 1.75rem; }
h1 { font-family: var(--f-display); font-weight: 800; font-stretch: 115%; font-size: clamp(2.2rem, 6vw, 3.25rem); line-height: 1; margin: 0; text-wrap: balance; }
.sub { color: var(--muted); margin: .75rem 0 0; max-width: 68ch; }
.sub .ex { font-family: var(--f-mono); font-size: .86em; color: var(--ex); background: var(--ex-bg); padding: 0 .3em; border-radius: 3px; }
section { border-top: 1px solid var(--rule); padding-block: 1.75rem; }
.proj { display: flex; flex-wrap: wrap; align-items: baseline; gap: .25rem 1rem; }
h2 { font-family: var(--f-display); font-weight: 700; font-size: 1.35rem; margin: 0; }
.count { font: 500 .8rem var(--f-mono); color: var(--muted); }
ol.papers { list-style: none; padding: 0; margin: 1rem 0 0; display: grid; gap: .6rem; }
ol.papers a { display: grid; grid-template-columns: 6.5rem minmax(0, 1fr); gap: .1rem 1rem; padding: .85rem 1rem;
  background: var(--surface); border: 1px solid var(--rule); border-radius: 8px; color: inherit; text-decoration: none; }
ol.papers a:hover { border-color: var(--accent); }
.date { font: 500 .82rem/1.9 var(--f-mono); color: var(--muted); grid-row: span 3; }
.name { font-family: var(--f-display); font-weight: 700; font-size: 1.15rem; color: var(--accent); }
.title { font-size: .95rem; }
.tldr { font-size: .9rem; color: var(--muted); }
.empty { color: var(--muted); margin: .75rem 0 0; }
footer { border-top: 1px solid var(--rule); padding-block: 1.25rem 3rem; font-size: .85rem; color: var(--muted); }
code { font-family: var(--f-mono); font-size: .9em; }
@media (max-width: 560px) { ol.papers a { grid-template-columns: minmax(0, 1fr); } .date { grid-row: auto; } }
"""


def library_title(root):
    """The artifact's name, from the profile's "Artifact title:" line."""
    prefs = root / "preferences.md"
    m = re.search(r"Artifact title:\s*(.+)", prefs.read_text()) if prefs.exists() else None
    return m.group(1).strip() if m else "Paper Pile"


def meta(src, name):
    m = re.search(rf'<meta name="{re.escape(name)}" content="([^"]*)"', src)
    return html.unescape(m.group(1)) if m else ""


def paper_item(root, page):
    src = page.read_text(errors="replace")
    m = re.search(r"<title>(.*?)</title>", src, re.S)
    date, short = page.stem[:10], page.stem[11:]  # "2026-10-15-DexAgent"
    e = html.escape
    venue = meta(src, "paper:venue")
    return (f'<li><a href="{e(page.relative_to(root).as_posix())}">'
            f'<span class="date">{e(date)}</span>'
            f'<span class="name">{e(html.unescape(m.group(1).strip()) if m else short)}</span>'
            f'<span class="title">{e(meta(src, "paper:title"))}{" · " + e(venue) if venue else ""}</span>'
            f'<span class="tldr">{e(meta(src, "description"))}</span></a></li>')


def main():
    root = Path(sys.argv[1]).resolve()
    projects = sorted(d for d in root.iterdir() if d.is_dir() and not d.name.startswith("."))
    sections, total = [], 0
    for proj in projects:
        pages = sorted((proj / "artifact").glob("*.html"), reverse=True)
        total += len(pages)
        items = "\n".join(paper_item(root, p) for p in pages)
        body = f'<ol class="papers">\n{items}\n</ol>' if pages else '<p class="empty">还没有 paper。</p>'
        sections.append(f'<section id="{html.escape(proj.name)}"><div class="proj"><h2>{html.escape(proj.name)}</h2>'
                        f'<span class="count">{proj.name}/ · {len(pages)} 篇</span></div>\n{body}\n</section>')

    title = html.escape(library_title(root))
    page = f"""<title>{title}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}</style>
<header class="frame">
  <p class="eyebrow">{root.name}/ · {len(projects)} 个 project · {total} 篇 paper</p>
  <h1>{title}</h1>
  <p class="sub">每篇 paper 先对着一个 <span class="ex">running example</span> 讲清 problem，
  再 big picture → stages → details，并逐块解读作者原图。下面的文件夹和磁盘上的
  <code>{root.name}/</code> 一一对应。</p>
</header>
<main class="frame">
{chr(10).join(sections)}
</main>
<footer><div class="frame">由 <code>build_index.py</code> 按文件夹自动生成。</div></footer>
"""
    (root / "index.html").write_text(page)
    for f in sorted(root.glob("*/artifact/**/*")):
        if f.is_file():
            print(f.relative_to(root).as_posix())


if __name__ == "__main__":
    main()
