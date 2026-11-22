#!/usr/bin/env python3
"""Rebuild LIBRARY/index.html, the artifact's home page, from the folder tree.

Layout it reads:  LIBRARY/<Project>/artifact/<YYYY-MM-DD>-<Short>.html
The page title is the "Artifact title:" line of LIBRARY/preferences.md.
From each page it takes <title>, <meta name="description"> (the TL;DR line) and
<meta name="paper:title">/<meta name="paper:venue">/<meta name="paper:date">. Every
project folder is a drop list, newest paper first; an empty project shows as empty.

Tabs: a switch under the title shows all papers, the ones filed in the last 7 days
(最近一周), or the starred ones. A tab only hides cards: every paper stays in its own
project folder. library.js, which this script copies from assets/ to LIBRARY/library.js,
runs the switch.

Stars: every card and every folder header has a star button. The stars and their tab
stay hidden until library.js reaches the artifact's database.

index.html is written without <!doctype>/<head>/<body> because the Artifact tool
wraps the main page in its own skeleton. Colors and fonts come from the
tokens block of the paper template, so both pages always match.

Agent context: every page, and the home page, carries a <script type="application/json"
id="agent-context"> block that readers never see: the paper's links, where the page
lives in the library's GitHub repo, and how to answer and change it. An agent opened
beside the artifact (the claude.ai chat) reads it there. This script writes it from the
page's meta tags and header links, so it stays right without anyone writing it by hand,
and rewrites a page only when its block changed. It holds no artifact link: each account
has its own copy of the artifact, and a page must be the same file in all of them.

Prints the paths (relative to LIBRARY) of library.js and every file under */artifact/,
one per line, which is the `files` list for a full publish.

Usage: build_index.py LIBRARY
"""
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
TEMPLATE = ASSETS / "paper-template.html"
FONTS = TEMPLATE.read_text().split('<link rel="stylesheet" href="')[1].split('"')[0]
TOKENS = re.search(r"/\* tokens:start \*/(.*?)/\* tokens:end \*/", TEMPLATE.read_text(), re.S).group(1)
STAR = ('<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.8l2.85 5.9 6.5.85-4.75 4.5 '
        '1.2 6.45L12 17.4l-5.8 3.1 1.2-6.45-4.75-4.5 6.5-.85z"/></svg>')

CSS = TOKENS + """
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.6 var(--f-body);
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
a:focus-visible, summary:focus-visible, button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.frame { max-width: 1040px; margin: 0 auto; }
.eyebrow { font: 500 .75rem/1.3 var(--f-mono); letter-spacing: .09em; text-transform: uppercase; color: var(--muted); margin: 0 0 .5rem; }
header { padding-block: 2.75rem 1.75rem; }
h1 { font-family: var(--f-display); font-weight: 800; font-stretch: 115%; font-size: clamp(2.2rem, 6vw, 3.25rem); line-height: 1; margin: 0; text-wrap: balance; }
.sub { color: var(--muted); margin: .75rem 0 0; max-width: 68ch; }
.sub .ex { font-family: var(--f-mono); font-size: .86em; color: var(--ex); background: var(--ex-bg); padding: 0 .3em; border-radius: 3px; }
/* each project folder is a drop list: its header line, with a chevron, until opened */
details { border-top: 1px solid var(--rule); padding-block: 1.1rem; }
details[open] { padding-bottom: 1.75rem; }
summary { list-style: none; cursor: pointer; }
summary::-webkit-details-marker { display: none; }
.proj { display: flex; flex-wrap: wrap; align-items: center; gap: .25rem .75rem; }
.proj::before { content: ""; width: .5rem; height: .5rem; border: solid var(--muted); border-width: 0 2px 2px 0;
  transform: rotate(-45deg); margin-right: .1rem; transition: transform .15s; }
details[open] > .proj::before { transform: rotate(45deg); }
@media (prefers-reduced-motion: reduce) { .proj::before { transition: none; } }
h2 { font-family: var(--f-display); font-weight: 700; font-size: 1.35rem; margin: 0; }
.count { font: 500 .8rem var(--f-mono); color: var(--muted); }
ol.papers { list-style: none; padding: 0; margin: 1rem 0 0; display: grid; gap: .6rem; }
ol.papers li { position: relative; }
ol.papers a { display: grid; grid-template-columns: 6.5rem minmax(0, 1fr); gap: .1rem 1rem; padding: .85rem 1rem;
  background: var(--surface); border: 1px solid var(--rule); border-radius: 8px; color: inherit; text-decoration: none; }
ol.papers a:hover { border-color: var(--accent); }
.date { font: 500 .82rem/1.9 var(--f-mono); color: var(--muted); grid-row: span 3; }
.date b { font-weight: 500; color: var(--ink); }
.date small { display: block; font-size: .72rem; line-height: 1.3; }
.name { font-family: var(--f-display); font-weight: 700; font-size: 1.15rem; color: var(--accent); }
.title { font-size: .95rem; }
.tldr { font-size: .9rem; color: var(--muted); }
.empty { color: var(--muted); margin: .75rem 0 0; }
/* stars: hidden until library.js reaches the artifact's database and sets .stars-on */
.star, .fstar, .seg [data-filter="starred"] { display: none; }
.stars-on .seg [data-filter="starred"] { display: inline-flex; }
.stars-on .star { display: grid; }
.stars-on .fstar { display: inline-flex; }
.stars-on ol.papers a { padding-right: 3rem; }
.seg { display: inline-flex; margin-top: 1.25rem; border: 1px solid var(--rule); border-radius: 6px; overflow: hidden; }
.seg button { border: 0; background: var(--surface); color: var(--muted); font: 500 .8rem var(--f-mono);
  padding: .4rem .9rem; cursor: pointer; display: inline-flex; gap: .35rem; align-items: center; }
.seg button + button { border-left: 1px solid var(--rule); }
.seg button[aria-pressed="true"] { background: var(--accent); color: var(--surface); }
.star { position: absolute; top: .45rem; right: .45rem; width: 2.2rem; height: 2.2rem; place-items: center;
  border: 0; border-radius: 6px; background: none; color: var(--muted); cursor: pointer; }
.star:hover { color: var(--accent); background: color-mix(in srgb, var(--accent) 9%, transparent); }
.fstar { gap: .35rem; align-items: center; font: 500 .75rem var(--f-mono); color: var(--muted); background: none;
  border: 1px solid var(--rule); border-radius: 4px; padding: .2rem .55rem; cursor: pointer; }
.star[aria-pressed="true"], .fstar[aria-pressed="true"] { color: var(--accent); }
.fstar[aria-pressed="true"] { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, transparent); }
svg.ico { width: 18px; height: 18px; display: block; }
.seg svg.ico, .fstar svg.ico { width: 14px; height: 14px; }
svg.ico path { fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linejoin: round; }
[aria-pressed="true"] svg.ico path { fill: currentColor; }
.hint { color: var(--muted); font-size: .9rem; margin: .75rem 0 0; }
.hint b { color: var(--ink); font-weight: 700; }
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


SKILL_REPO = "https://github.com/EricWang12/zw-claude-skills/tree/main/plugins/paper-explain"
CONTEXT = re.compile(r'\n?<script type="application/json" id="agent-context">.*?</script>', re.S)


def repo_url(root):
    """The library's GitHub repo as a browsable https link, from its origin remote."""
    try:
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""
    url = re.sub(r"^git@([^:]+):", r"https://\1/", url)
    return re.sub(r"\.git$", "", url)


def header_links(src):
    """The page header's links (arXiv, PDF, Project page, Code), by their text."""
    m = re.search(r'<p class="links">(.*?)</p>', src, re.S)
    if not m:
        return {}
    return {html.unescape(re.sub(r"<[^>]+>", "", text)).strip(): html.unescape(href)
            for href, text in re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', m.group(1), re.S)
            if href.startswith("http")}


def page_context(root, page, src, repo):
    """What an agent beside the artifact needs to answer questions about this page and
    to change it; written into the page, hidden from readers."""
    path = page.relative_to(root).as_posix()
    blob = f"{repo}/blob/main" if repo else ""
    return {
        "about": "Hidden from readers: the facts an agent needs to answer questions about this "
                 "page and to change it. Written by the paper-explain skill's build_index.py.",
        "page": page.stem,
        "open": f"#{page.stem} after the library artifact's link opens this page directly",
        "project": page.parent.parent.name,
        "tldr": meta(src, "description"),
        "paper": {
            "title": meta(src, "paper:title"),
            "venue": meta(src, "paper:venue"),
            "date": meta(src, "paper:date"),
            "source": meta(src, "paper:source"),
            "pdf": meta(src, "paper:pdf"),
            "links": header_links(src),
        },
        "sections": re.findall(r'<section id="([^"]+)"', src),
        "library": {
            "repo": repo,
            "page_file": f"{blob}/{path}" if blob else path,
            "figures": f"{repo}/tree/main/{path[:-5]}" if repo else path[:-5],
            "profile": f"{blob}/preferences.md" if blob else "preferences.md",
            "pdf_note": "The PDF is not in the repo (too large): fetch paper.pdf.",
        },
        "answering": "Answer from the paper itself (paper.pdf), not only from this page; name the "
                     "figure, table or section a number comes from, and say so when the paper does "
                     "not report something. The reader's profile (library.profile) says how they "
                     "like answers.",
        "changing": "To change the page, edit library.page_file in the repo and republish it to "
                    "this artifact, with the paper-explain skill (" + SKILL_REPO + ") when you can. "
                    "A page changed only in this artifact is copied into the repo by the skill's "
                    "next run, so it is not lost.",
    }


def put_context(page, src, data):
    """Writes the agent-context block before </head>, replacing an older one; the file is
    rewritten only when the block changed. Returns the page's text."""
    body = json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")
    block = f'<script type="application/json" id="agent-context">{body}</script>'
    bare = CONTEXT.sub("", src)
    new = bare.replace("</head>", block + "\n</head>", 1) if "</head>" in bare else block + "\n" + bare
    if new != src:
        page.write_text(new)
    return new


def paper_item(root, page):
    src = page.read_text(errors="replace")
    m = re.search(r"<title>(.*?)</title>", src, re.S)
    date, short = page.stem[:10], page.stem[11:]  # "2026-10-15-DexAgent"
    name = html.unescape(m.group(1).strip()) if m else short
    e = html.escape
    venue = meta(src, "paper:venue")
    published = meta(src, "paper:date")  # first public date (arXiv v1); the filing date goes below it
    when = f'<b>{e(published)}</b><small>归档 {e(date)}</small>' if published else e(date)
    key = f"{page.parent.parent.name}:{page.stem}"  # the star's id in the artifact's database
    return (f'<li data-added="{e(date)}"><a href="{e(page.relative_to(root).as_posix())}">'
            f'<span class="date">{when}</span>'
            f'<span class="name">{e(name)}</span>'
            f'<span class="title">{e(meta(src, "paper:title"))}{" · " + e(venue) if venue else ""}</span>'
            f'<span class="tldr">{e(meta(src, "description"))}</span></a>'
            f'<button type="button" class="star" data-star="{e(key)}" aria-pressed="false" aria-label="星标 {e(name)}">{STAR}</button></li>')


def main():
    root = Path(sys.argv[1]).resolve()
    repo = repo_url(root)
    projects = sorted(d for d in root.iterdir() if d.is_dir() and not d.name.startswith("."))
    sections, total, listed = [], 0, []
    for proj in projects:
        pages = sorted((proj / "artifact").glob("*.html"), reverse=True)
        for p in pages:  # each page carries its hidden agent context
            src = p.read_text(errors="replace")
            src = put_context(p, src, page_context(root, p, src, repo))
            listed.append({"page": p.stem, "project": proj.name, "title": meta(src, "paper:title"),
                           "date": meta(src, "paper:date"), "source": meta(src, "paper:source"),
                           "file": p.relative_to(root).as_posix()})
        total += len(pages)
        items = "\n".join(paper_item(root, p) for p in pages)
        body = f'<ol class="papers">\n{items}\n</ol>' if pages else '<p class="empty">还没有 paper。</p>'
        p = html.escape(proj.name)
        sections.append(f'<details id="{p}" data-proj="{p}"><summary class="proj"><h2>{p}</h2>'
                        f'<span class="count">{p}/ · {len(pages)} 篇</span>'
                        f'<button type="button" class="fstar" data-star="{p}" aria-pressed="false" '
                        f'aria-label="给整个 {p} 文件夹加星标">{STAR}整个文件夹</button></summary>\n{body}\n</details>')

    title = html.escape(library_title(root))
    blob = f"{repo}/blob/main" if repo else ""
    context = json.dumps({
        "about": "Hidden from readers: the facts an agent needs to answer questions about this "
                 "paper library. Written by the paper-explain skill's build_index.py.",
        "library": {"title": library_title(root), "repo": repo,
                    "profile": f"{blob}/preferences.md" if blob else "preferences.md"},
        "open": "Add #<page> to this artifact's link to open one paper's page directly.",
        "each_page": "Every page carries its own agent-context block: the paper's links, its file "
                     "in the repo, and how to answer and change it.",
        "pages": listed,
        "changing": "Pages are made by the paper-explain skill (" + SKILL_REPO + "), which keeps "
                    "this artifact and the repo in step on every run.",
    }, ensure_ascii=False, indent=1).replace("</", "<\\/")
    page = f"""<title>{title}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}</style>
<script type="application/json" id="agent-context">{context}</script>
<header class="frame">
  <p class="eyebrow">{root.name}/ · {len(projects)} 个 project · {total} 篇 paper</p>
  <h1>{title}</h1>
  <p class="sub">每篇 paper 先对着一个 <span class="ex">running example</span> 讲清 problem，
  再 big picture → stages → details，并逐块解读作者原图。下面的文件夹和磁盘上的
  <code>{root.name}/</code> 一一对应，点名字展开。每张卡左边是论文首次公开的日期（arXiv v1 或 release），小字是归档日期。</p>
  <div class="seg" id="star-filter" role="group" aria-label="显示哪些 paper">
    <button type="button" data-filter="all" aria-pressed="true">全部 {total}</button>
    <button type="button" data-filter="recent" aria-pressed="false">最近一周 <span id="recent-count">0</span></button>
    <button type="button" data-filter="starred" aria-pressed="false">{STAR}星标 <span id="star-count">0</span></button>
  </div>
  <p class="hint" id="star-hint" hidden>交给 Claude：说 <b>“用我的星标 paper 写 related work”</b>，它会自己读这份清单。</p>
  <p class="hint" id="recent-empty" hidden>最近一周没有新归档的 paper。</p>
  <p class="hint" id="star-empty" hidden>还没有星标。点 paper 右上角的星，或文件夹旁的“整个文件夹”。</p>
</header>
<main class="frame" id="library">
{chr(10).join(sections)}
</main>
<footer><div class="frame">由 <code>build_index.py</code> 按文件夹自动生成。</div></footer>
<script src="library.js"></script>
"""
    (root / "index.html").write_text(page)
    shutil.copyfile(ASSETS / "library.js", root / "library.js")
    print("library.js")
    for f in sorted(root.glob("*/artifact/**/*")):
        if f.is_file():
            print(f.relative_to(root).as_posix())


if __name__ == "__main__":
    main()
