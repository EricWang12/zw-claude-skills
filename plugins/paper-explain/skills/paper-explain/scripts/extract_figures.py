#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pymupdf>=1.24"]
# ///
"""Crop the authors' figures and tables out of a paper PDF.

Every text block that starts with a caption ("Fig. 3:", "Figure 3.", "TABLE II:")
marks one crop. The search area runs from the caption to the nearest body
paragraph, other caption or page margin (upwards for figures, downwards for
tables). Inside it, the crop is the union of the drawn graphics and embedded
images plus the text labels touching them, so titles and author lines next to a
teaser figure stay out. Writes OUT/fig3.jpg, OUT/tab2.jpg, ... plus
OUT/figures.json, and prints one line per crop.

This is a heuristic. Open every crop before you use it. Fix a bad crop with
--box ID=PAGE:x0,y0,x1,y1 (PDF points, origin top-left); a new ID such as
fig2-s1 adds a crop, for example one panel of a figure. --page N prints the
page's text blocks and images with their coordinates, and writes OUT/pageN.png
at 72 dpi, where one pixel is one point.

Usage:
  uv run extract_figures.py paper.pdf OUT_DIR [--box fig3=5:313,45,558,196] [--page 5]
"""
import argparse
import json
import re
import statistics
from collections import Counter
from pathlib import Path

import pymupdf

CAPTION = re.compile(r"^(fig(?:ure)?\.?|table)\s*(S?\d+|[IVXL]+)\s*[:.|]", re.I)
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}
MIN_PX, MAX_PX = 900, 1800  # crop width range in pixels; narrow panels get a higher dpi


def roman_to_int(s):
    vals = [ROMAN[c] for c in s]
    return sum(-v if i + 1 < len(vals) and vals[i + 1] > v else v for i, v in enumerate(vals))


def text_blocks(page):
    blocks = []
    for b in page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
        lines = [l for l in b["lines"] if "".join(s["text"] for s in l["spans"]).strip()]
        if not lines:
            continue
        sizes = Counter()
        for l in lines:
            for s in l["spans"]:
                sizes[round(s["size"], 1)] += len(s["text"].strip())
        blocks.append({
            "rect": pymupdf.Rect(b["bbox"]),
            "n": len(lines),
            "size": sizes.most_common(1)[0][0],
            "first": "".join(s["text"] for s in lines[0]["spans"]).strip(),
            "text": " ".join("".join(s["text"] for s in l["spans"]).strip() for l in lines),
        })
    return blocks


def graphics(page):
    page_area = page.rect.get_area()
    rects = [pymupdf.Rect(i["bbox"]) & page.rect for i in page.get_image_info()]
    rects += [d["rect"] for d in page.get_drawings() if d["rect"].get_area() < 0.8 * page_area]
    return [r for r in rects if r.width > 1 or r.height > 1]


def find_crops(doc):
    pages = [{"blocks": text_blocks(p), "gfx": graphics(p), "rect": p.rect} for p in doc]
    sizes = Counter()
    for p in pages:
        for b in p["blocks"]:
            sizes[b["size"]] += len(b["text"])
    body_size = sizes.most_common(1)[0][0]
    is_body_size = lambda b: abs(b["size"] - body_size) <= 0.6
    paras = [b for p in pages for b in p["blocks"] if b["n"] >= 3 and is_body_size(b)]
    col_w = statistics.median(b["rect"].width for b in paras)
    text_x0 = min(b["rect"].x0 for b in paras)
    text_x1 = max(b["rect"].x1 for b in paras)
    top = min(b["rect"].y0 for b in paras)
    bottom = max(b["rect"].y1 for b in paras)
    starts = Counter(round(b["rect"].x0) for b in paras)
    columns = [(x, x + col_w) for x, c in starts.items() if c >= 3] or [(text_x0, text_x1)]
    is_body = lambda b: is_body_size(b) and b["rect"].width >= 0.8 * col_w
    # a paragraph starts at a column's left edge; a centered table row in body-size type does not
    at_edge = lambda b: any(abs(b["rect"].x0 - x) <= 3 for x, _ in columns)

    crops, taken = {}, {}  # taken: page index -> rects already claimed
    for kind in ("table", "fig"):  # tables first, so figures stop at them
        for pi, page in enumerate(pages):
            for cap in page["blocks"]:
                m = CAPTION.match(cap["first"])
                if not m or (m.group(1)[0].lower() == "t") != (kind == "table"):
                    continue
                num = m.group(2).upper()
                num = str(roman_to_int(num)) if re.fullmatch(r"[IVXL]+", num) else num
                cid = ("tab" if kind == "table" else "fig") + num
                while cid in crops:
                    cid += "b"
                c = cap["rect"]
                x0, x1 = text_x0, text_x1
                if c.width < 0.6 * (text_x1 - text_x0):
                    mid = (c.x0 + c.x1) / 2
                    x0, x1 = next(((a, b) for a, b in columns if a - 5 <= mid <= b + 5), (c.x0, c.x1))
                in_span = lambda r: min(r.x1, x1) - max(r.x0, x0) > 0.3 * max(r.width, 1)
                stops = [b["rect"] for b in page["blocks"] if b is not cap and in_span(b["rect"]) and (
                    (is_body(b) and (kind == "fig" or at_edge(b))) or CAPTION.match(b["first"])
                    or b["rect"].y1 <= top + 2 or b["rect"].y0 >= bottom - 2)]
                stops += [r for r in taken.get(pi, []) if in_span(r)]
                above = pymupdf.Rect(x0 - 6, max([s.y1 for s in stops if s.y1 <= c.y0 + 1] + [0]), x1 + 6, c.y0)
                below = pymupdf.Rect(x0 - 6, c.y1, x1 + 6, min([s.y0 for s in stops if s.y0 >= c.y1 - 1] + [page["rect"].y1]))
                order = (above, below) if kind == "fig" else (below, above)
                box = None
                for area in order:
                    box = content_box(page, area, cap, kind)
                    if box:
                        break
                box = box or order[0]
                taken.setdefault(pi, []).append(box)
                crops[cid] = {"page": pi + 1, "kind": kind, "caption": cap["text"],
                              "box": [round(v, 1) for v in box]}
    return crops


def content_box(page, area, cap, kind):
    """Union of graphics inside `area`, grown to the text labels that touch it.

    A table instead grows from its caption through the rows and rules that touch, so a
    figure further along the same column stays out of the table's crop."""
    inside = lambda r: (r & area).get_area() >= 0.5 * max(r.get_area(), 1) or (r.height < 1 and r in area)
    gfx = [r for r in page["gfx"] if inside(r)]
    labels = [b["rect"] for b in page["blocks"] if b is not cap and inside(b["rect"])]
    box = pymupdf.Rect()
    if kind == "table":
        reach = cap["rect"] + (0, -15, 0, 15)
        while True:
            grown = pymupdf.Rect()
            for r in gfx + labels:
                if (r + (-12, -12, 12, 12)).intersects(reach):
                    grown |= r
            if grown.is_empty or grown == box:
                break
            box = reach = grown
    else:
        for r in gfx:
            box |= r
        if box.is_empty:
            return None
        for _ in range(3):  # labels can chain: axis title next to tick labels next to the plot
            for r in labels:
                if (r + (-12, -12, 12, 12)).intersects(box):
                    box |= r
    return None if box.is_empty else (box + (-3, -3, 3, 3)) & area


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--box", action="append", default=[], metavar="ID=PAGE:x0,y0,x1,y1")
    ap.add_argument("--page", action="append", type=int, default=[], metavar="N")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(a.pdf)

    for n in a.page:
        page = doc[n - 1]
        page.get_pixmap(dpi=72).save(a.out / f"page{n}.png")
        print(f"page {n} -> {a.out / f'page{n}.png'} (1 px = 1 pt); boxes are x0,y0,x1,y1")
        items = [(b["rect"], "text ", b["text"][:70]) for b in text_blocks(page)]
        items += [(pymupdf.Rect(i["bbox"]), "image", "") for i in page.get_image_info()]
        for r, kind, text in sorted(items, key=lambda it: (it[0].y0, it[0].x0)):
            print(f"  {kind} [{r.x0:.0f},{r.y0:.0f},{r.x1:.0f},{r.y1:.0f}] {text}")

    crops = find_crops(doc)
    for spec in a.box:
        cid, rest = spec.split("=", 1)
        page, coords = rest.split(":", 1)
        old = crops.get(cid, {})
        crops[cid] = {"page": int(page), "kind": old.get("kind", "fig"), "caption": old.get("caption", ""),
                      "box": [float(v) for v in coords.split(",")], "manual": True}

    for cid, c in sorted(crops.items(), key=lambda kv: (kv[1]["page"], kv[0])):
        rect = pymupdf.Rect(c["box"])
        w = max(rect.width, 1)
        dpi = int(min(max(200, MIN_PX * 72 / w), 600, MAX_PX * 72 / w))
        pix = doc[c["page"] - 1].get_pixmap(clip=rect, dpi=dpi)
        pix.save(a.out / f"{cid}.jpg", jpg_quality=88)
        c.update(file=f"{cid}.jpg", size=[pix.width, pix.height])
        box = ",".join(f"{v:.0f}" for v in c["box"])
        print(f"{cid:6} p{c['page']:<3} [{box:>17}] {pix.width}x{pix.height:<5} {c['caption'][:70]}")
    (a.out / "figures.json").write_text(json.dumps(crops, indent=1))


if __name__ == "__main__":
    main()
