#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["playwright==1.63.0"]
# ///
"""Check a paper page before publishing it.

Static checks: no double-brace placeholders left, meta tags filled, every <img> file
exists, no unused files in the figure folder, Level 2 click targets match the Level 3
stage ids.
Rendered checks (headless Chromium, every <details> opened): each flowchart draws, no
chart is wider than its box at desktop width, no script errors, no sideways page scroll
at 390 px phone width.

Prints PASS/WARN/FAIL lines and exits 1 on any FAIL.
Usage: uv run check_page.py PAGE.html
First run on a new machine: uv run --with playwright==1.63.0 playwright install chromium-headless-shell
"""
import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright


def static_checks(page):
    src = page.read_text()
    out = [("FAIL" if "{{" in src else "PASS", f"placeholders left: {src.count('{{')}")]
    for name in ("description", "paper:title", "paper:source", "paper:venue", "paper:pdf"):
        m = re.search(rf'<meta name="{name}" content="([^"]*)"', src)
        out.append(("PASS" if m and m.group(1).strip() else "FAIL", f"meta {name} filled"))
    imgs = re.findall(r'<img src="([^"]+)"', src)
    missing = [i for i in imgs if not (page.parent / i).is_file()]
    out.append(("FAIL" if missing or not imgs else "PASS", f"{len(imgs)} authors' figures embedded"
                + (f"; missing files: {missing}" if missing else "")))
    figdir = page.parent / page.stem
    unused = [f.name for f in figdir.glob("*") if f"{page.stem}/{f.name}" not in imgs] if figdir.is_dir() else []
    out.append(("WARN" if unused else "PASS", f"unused files in {figdir.name}/: {unused or 'none'}"))
    stages = re.findall(r'<details class="stage" id="([\w-]+)"', src)
    links = set(re.findall(r'href\s*=?\s*"#([\w-]+)"', src))  # Mermaid `href "#x"` and HTML `href="#x"`
    broken = sorted(l for l in links if l.startswith("stage") and l not in stages)
    unlinked = sorted(set(stages) - links)
    out.append(("FAIL" if broken or unlinked or not stages else "PASS", f"{len(stages)} stage blocks"
                + (f"; links to missing blocks: {broken}" if broken else "")
                + (f"; blocks nothing links to: {unlinked}" if unlinked else "")))
    return out


async def rendered_checks(page):
    out = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for width, scheme in ((1200, "light"), (390, "dark")):
            tab = await browser.new_page(viewport={"width": width, "height": 900}, color_scheme=scheme)
            errors = []
            tab.on("pageerror", lambda e: errors.append(str(e)))
            tab.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            await tab.goto(page.resolve().as_uri(), wait_until="networkidle")
            await tab.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            await tab.wait_for_timeout(3000)
            flows = await tab.eval_on_selector_all(".flow", """els => els.map(e => {
                const svg = e.querySelector('svg');
                return {drawn: !!svg, w: svg ? Math.round(svg.getBoundingClientRect().width) : 0,
                        box: e.clientWidth - 30, src: (e.dataset.src || '').trim().split('\\n').slice(0, 2).join(' | ')};
            })""")
            label = f"{width}px {scheme}"
            failed = [f"#{i + 1} ({f['src'][:60]})" for i, f in enumerate(flows) if not f["drawn"]]
            out.append(("FAIL" if failed else "PASS", f"{label}: {len(flows) - len(failed)}/{len(flows)} flowcharts drawn"
                        + (f"; not drawn: {failed}" if failed else "")))
            if width > 1000:
                wide = [f"#{i + 1} is {f['w']}px in a {f['box']}px box ({f['src'][:50]})"
                        for i, f in enumerate(flows) if f["drawn"] and f["w"] > f["box"]]
                out.append(("WARN" if wide else "PASS", f"{label}: charts fit their box"
                            + (f"; too wide, shorten labels or use TD: {wide}" if wide else "")))
                tables = await tab.eval_on_selector_all(".table-wrap", "els => els.filter(e => e.scrollWidth > e.clientWidth + 2).length")
                out.append(("WARN" if tables else "PASS", f"{label}: tables fit their box" + (f"; {tables} scroll sideways" if tables else "")))
            scroll = await tab.evaluate("document.documentElement.scrollWidth")
            out.append(("FAIL" if scroll > width else "PASS", f"{label}: page width {scroll}px"))
            out.append(("FAIL" if errors else "PASS", f"{label}: script errors: {errors[:3] or 'none'}"))
            await tab.close()
        await browser.close()
    return out


def main():
    page = Path(sys.argv[1])
    results = static_checks(page) + asyncio.run(rendered_checks(page))
    for status, text in results:
        print(f"{status}  {text}")
    sys.exit(1 if any(s == "FAIL" for s, _ in results) else 0)


if __name__ == "__main__":
    main()
