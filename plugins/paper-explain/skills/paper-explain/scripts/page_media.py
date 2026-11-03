#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["playwright==1.63.0"]
# ///
"""List the figures, videos and interactive viewers on a paper's project page.

Project pages often load their media from JavaScript, so this opens the page in headless
Chromium, scrolls to the bottom to trigger lazy loading, and prints one line per item:
  kind  size  url  [section heading] alt or nearby text
kind is img, video, gif, canvas (a WebGL or 3D viewer), iframe (an embed such as YouTube)
or net (a media file fetched over the network that no element shows yet, such as a
viewer's frames). It also writes OUT_DIR/project-page.png, a full-page screenshot to look
at, and nothing else: download what you choose with curl.

Usage: uv run page_media.py URL OUT_DIR
"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

MEDIA = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".webm", ".mov", ".m4v")

DOM = """() => {
  const heading = el => {  // the nearest heading before el in document order
    const all = [...document.querySelectorAll('h1,h2,h3,h4')];
    let h = null;
    for (const x of all) if (x.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) h = x;
    return h ? h.textContent.trim().replace(/\\s+/g, ' ').slice(0, 50) : '';
  };
  const near = el => (el.getAttribute('alt') || el.getAttribute('aria-label') || el.title
    || (el.closest('figure')?.querySelector('figcaption')?.textContent) || '').trim().replace(/\\s+/g, ' ').slice(0, 90);
  const out = [];
  for (const el of document.querySelectorAll('img, video, canvas, iframe, model-viewer')) {
    const r = el.getBoundingClientRect();
    if (r.width < 80 || r.height < 60) continue;  // icons, logos
    let kind = el.tagName.toLowerCase(), src = el.currentSrc || el.src || '';
    if (kind === 'video' && !src) src = el.querySelector('source')?.src || '';
    if (kind === 'img' && /\\.gif(\\?|$)/i.test(src)) kind = 'gif';
    if (kind === 'model-viewer') kind = 'canvas';
    const size = kind === 'img' || kind === 'gif' ? `${el.naturalWidth}x${el.naturalHeight}`
               : kind === 'video' ? `${el.videoWidth || Math.round(r.width)}x${el.videoHeight || Math.round(r.height)}`
               : `${Math.round(r.width)}x${Math.round(r.height)}`;
    out.push({kind, size, src, where: heading(el), text: near(el)});
  }
  return out;
}"""


async def main(url, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    fetched = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("response", lambda r: fetched.setdefault(r.url.split("#")[0], r.headers.get("content-length", "?"))
                if r.url.split("?")[0].lower().endswith(MEDIA) else None)
        await page.goto(url, wait_until="networkidle", timeout=60000)
        height = await page.evaluate("document.body.scrollHeight")
        for y in range(0, height, 600):  # lazy-loaded media appear as they scroll into view
            await page.evaluate(f"window.scrollTo(0, {y})")
            await page.wait_for_timeout(250)
        await page.wait_for_timeout(1500)
        items = await page.evaluate(DOM)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.screenshot(path=str(out_dir / "project-page.png"), full_page=True)
        await browser.close()
    shown = set()
    for it in items:
        shown.add(it["src"])
        size = it["size"] + (f" {int(fetched[it['src']]) // 1024}KB" if fetched.get(it["src"], "?").isdigit() else "")
        print(f"{it['kind']:7} {size:20} {it['src'] or '-'}  [{it['where']}] {it['text']}")
    for u, n in fetched.items():
        if u not in shown:
            print(f"{'net':7} {(str(int(n) // 1024) + 'KB') if n.isdigit() else '?':20} {u}")
    print(f"screenshot: {out_dir / 'project-page.png'}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], Path(sys.argv[2])))
