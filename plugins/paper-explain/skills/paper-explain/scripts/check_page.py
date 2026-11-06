#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["playwright==1.63.0"]
# ///
"""Check a paper page before publishing it.

Static checks: no double-brace placeholders left, meta tags filled, every <img> and
<video> file exists, no unused files in the figure folder, Level 2 click targets match the Level 3
stage ids.
Rendered checks (headless Chromium, every <details> opened) at 1200 px (desktop), 760 px
(the artifact's side panel, where charts are read) and 390 px (phone): each flowchart
draws, no script errors, the page never scrolls sideways. At 1200 px no chart text is
clipped (a subgraph title wider than its cluster, a node label larger than its box, a
label outside the drawing) and tables fit. At 760 px no chart still scrolls after the
page's 70 % shrink (FAIL) and no chart is wider than 760 px natural (WARN: it is shown
below 90 % in the panel).

Prints PASS/WARN/FAIL lines and exits 1 on any FAIL.
Usage: uv run check_page.py PAGE.html
First run on a new machine: uv run --with playwright==1.63.0 playwright install chromium-headless-shell
"""
import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

PANEL = 760  # the artifact's side panel, where the charts are read

# One record per .flow box: natural width, whether it still scrolls, and clipped text.
MEASURE = r"""els => els.map((e, i) => {
  const svg = e.querySelector('svg');
  const sc = e.querySelector('.flow-scroller') || e;
  const r = {n: i + 1, drawn: !!svg, natural: 0, overflow: false, clipped: [],
             src: (e.dataset.src || '').trim().split('\n').slice(0, 2).join(' | ')};
  if (!svg) return r;
  const vb = (svg.getAttribute('viewBox') || '').split(/[ ,]+/).map(Number);
  r.natural = Math.round(parseFloat(svg.getAttribute('width')) || vb[2] || svg.getBoundingClientRect().width);
  r.overflow = sc.scrollWidth > sc.clientWidth + 1;
  const sb = svg.getBoundingClientRect();
  const txt = el => (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 50);
  const outside = b => b.right > sb.right + 1 || b.left < sb.left - 1 || b.bottom > sb.bottom + 1 || b.top < sb.top - 1;
  // Every HTML label sits in a <foreignObject>, which clips whatever is larger than it:
  // Mermaid gives a subgraph title a 200px box, so a longer title loses its tail.
  svg.querySelectorAll('foreignObject').forEach(fo => {
    const kid = fo.firstElementChild; if (!kid) return;
    const f = fo.getBoundingClientRect(), k = kid.getBoundingClientRect();
    const need = Math.max(k.width, kid.scrollWidth || 0);
    if (need > f.width + 1 || k.height > f.height + 1)
      r.clipped.push(`label "${txt(kid)}" needs ${Math.round(need)}x${Math.round(k.height)}px, its box is ${Math.round(f.width)}x${Math.round(f.height)}px`);
  });
  // A subgraph title longer than its 200px box wraps onto a second line that Mermaid never
  // reserves room for, so the first node covers it; the same holds for any label under a node.
  const shapes = [...svg.querySelectorAll('g.node')].map(n => n.querySelector('rect, polygon, circle, path')).filter(Boolean).map(x => x.getBoundingClientRect());
  const covered = b => shapes.some(a => a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1);
  svg.querySelectorAll('g.cluster').forEach(c => {
    const rect = c.querySelector('rect'), lab = c.querySelector('.cluster-label');
    if (!rect || !lab) return;
    const a = rect.getBoundingClientRect(), div = lab.querySelector('div') || lab, b = div.getBoundingClientRect();
    const lines = Math.round(b.height / (parseFloat(getComputedStyle(div).lineHeight) || 22));
    if (b.right > a.right + 1 || b.left < a.left - 1)
      r.clipped.push(`subgraph title "${txt(lab)}" (${Math.round(b.width)}px) sticks out of its cluster (${Math.round(a.width)}px)`);
    if (lines > 1 || covered(b))
      r.clipped.push(`subgraph title "${txt(lab)}" ${lines > 1 ? 'wraps to ' + lines + ' lines and ' : ''}is covered by a node; keep it under 200px or use a header node`);
  });
  svg.querySelectorAll('.edgeLabel').forEach(el => {
    const b = el.getBoundingClientRect();
    if (b.width && covered(b)) r.clipped.push(`edge label "${txt(el)}" is covered by a node`);
  });
  svg.querySelectorAll('g.node').forEach(n => {
    const shape = n.querySelector('rect, polygon, circle, path'), lab = n.querySelector('.label');
    if (!shape || !lab) return;
    const a = shape.getBoundingClientRect(), b = lab.getBoundingClientRect();
    if (b.right > a.right + 1 || b.left < a.left - 1 || b.bottom > a.bottom + 1 || b.top < a.top - 1)
      r.clipped.push(`node label "${txt(lab)}" sticks out of its box`);
    if (outside(b)) r.clipped.push(`node label "${txt(lab)}" is outside the drawing`);
  });
  svg.querySelectorAll('.edgeLabel').forEach(el => {
    const b = el.getBoundingClientRect();
    if (b.width && outside(b)) r.clipped.push(`edge label "${txt(el)}" is outside the drawing`);
  });
  return r;
})"""


def static_checks(page):
    src = page.read_text()
    out = [("FAIL" if "{{" in src else "PASS", f"placeholders left: {src.count('{{')}")]
    for name in ("description", "paper:title", "paper:source", "paper:venue", "paper:pdf"):
        m = re.search(rf'<meta name="{name}" content="([^"]*)"', src)
        out.append(("PASS" if m and m.group(1).strip() else "FAIL", f"meta {name} filled"))
    m = re.search(r'<meta name="paper:date" content="(\d{4}-\d{2}-\d{2})"', src)
    out.append(("PASS" if m else "WARN", "meta paper:date filled (YYYY-MM-DD, first public date)"))
    imgs = re.findall(r'<(?:img|video) src="([^"]+)"', src)
    missing = [i for i in imgs if not (page.parent / i).is_file()]
    out.append(("FAIL" if missing or not imgs else "PASS", f"{len(imgs)} figures and videos embedded"
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
        for width, scheme in ((1200, "light"), (PANEL, "light"), (390, "dark")):
            tab = await browser.new_page(viewport={"width": width, "height": 900}, color_scheme=scheme)
            errors = []
            tab.on("pageerror", lambda e: errors.append(str(e)))
            tab.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            await tab.goto(page.resolve().as_uri(), wait_until="networkidle")
            await tab.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            await tab.wait_for_timeout(3000)
            flows = await tab.eval_on_selector_all(".flow", MEASURE)
            label = f"{width}px {scheme}"
            failed = [f"#{f['n']} ({f['src'][:60]})" for f in flows if not f["drawn"]]
            out.append(("FAIL" if failed else "PASS", f"{label}: {len(flows) - len(failed)}/{len(flows)} flowcharts drawn"
                        + (f"; not drawn: {failed}" if failed else "")))
            if width == 1200:
                clipped = [f"#{f['n']}: {c}" for f in flows for c in f["clipped"]]
                out.append(("FAIL" if clipped else "PASS", f"{label}: chart text clipped: {clipped or 'none'}"))
                tables = await tab.eval_on_selector_all(".table-wrap", "els => els.filter(e => e.scrollWidth > e.clientWidth + 2).length")
                out.append(("WARN" if tables else "PASS", f"{label}: tables fit their box" + (f"; {tables} scroll sideways" if tables else "")))
            if width == PANEL:
                scrolling = [f"#{f['n']} is {f['natural']}px natural ({f['src'][:50]})" for f in flows if f["drawn"] and f["overflow"]]
                out.append(("FAIL" if scrolling else "PASS", f"{label}: charts fit the panel after shrinking"
                            + (f"; still scroll, use 3 nodes per LR row or TD: {scrolling}" if scrolling else "")))
                wide = [f"#{f['n']} is {f['natural']}px" for f in flows if f["drawn"] and not f["overflow"] and f["natural"] > PANEL]
                out.append(("WARN" if wide else "PASS", f"{label}: charts at most {PANEL}px natural"
                            + (f"; shown below 90% in the panel, shorten labels: {wide}" if wide else "")))
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
