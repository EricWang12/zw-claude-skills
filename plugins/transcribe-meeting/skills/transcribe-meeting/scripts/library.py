"""The meeting library artifact: meetings.json (manifest) + index.html (home page).

build_summary.py --library calls add(). The manifest is read back from the published
artifact before each run, so any machine can add a meeting without a local library.
"""
import html
import json
from pathlib import Path

TITLE = "Zhaoning Meeting Notes"
KIND = {"zh": {"decided": "已决定", "action": "行动", "proposal": "提议", "open": "未决定"},
        "en": {"decided": "Decided", "action": "Actions", "proposal": "Proposals", "open": "Open"}}

STYLE = """
/* Layout: one column of meeting cards grouped by month; date block left, content right. */
:root{--bg:#eef3f5;--surface:#ffffff;--ink:#14232e;--muted:#56697a;--line:#d5e0e6;--accent:#145d74;
 --decided-bg:#dff3e6;--decided-ink:#1d6b3a;--action-bg:#dcecff;--action-ink:#1d4f8f;
 --proposal-bg:#fff1d6;--proposal-ink:#7a5410;--open-bg:#f1e4f7;--open-ink:#6b2d84;
 --display:"IBM Plex Sans","Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
 --mono:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0e161c;--surface:#152129;--ink:#e1eaef;
 --muted:#98adbb;--line:#293a45;--accent:#6cc0d8;--decided-bg:#173524;--decided-ink:#8fdcaa;--action-bg:#172c47;
 --action-ink:#9cc7ff;--proposal-bg:#3a2e12;--proposal-ink:#f2cd7c;--open-bg:#30203a;--open-ink:#dcaef0;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0e161c;--surface:#152129;--ink:#e1eaef;--muted:#98adbb;--line:#293a45;--accent:#6cc0d8;
 --decided-bg:#173524;--decided-ink:#8fdcaa;--action-bg:#172c47;--action-ink:#9cc7ff;--proposal-bg:#3a2e12;
 --proposal-ink:#f2cd7c;--open-bg:#30203a;--open-ink:#dcaef0;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font:15px/1.6 var(--display)}
.wrap{max-width:920px;margin:auto;padding-block:32px 56px;padding-left:max(16px,env(safe-area-inset-left,0px));
 padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:22px}
header{display:flex;flex-wrap:wrap;align-items:end;justify-content:space-between;gap:12px 24px}
h1{margin:0;font-size:30px;line-height:1.2;letter-spacing:-.01em;text-wrap:balance}
.stats{color:var(--muted);font:13px/1.4 var(--mono);font-variant-numeric:tabular-nums}
input{width:100%;font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--line);
 border-radius:8px;padding:9px 12px}
input:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.month{display:grid;gap:12px}
.month h2{margin:6px 0 0;font:600 12px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.meeting{display:grid;grid-template-columns:96px minmax(0,1fr);gap:18px;background:var(--surface);
 border:1px solid var(--line);border-radius:10px;padding:16px 18px;text-decoration:none;color:inherit}
.meeting:hover{border-color:var(--accent)}
.date{font-family:var(--mono);font-variant-numeric:tabular-nums;color:var(--accent);line-height:1.15}
.date b{display:block;font-size:24px;white-space:nowrap}
.date span{display:block;font-size:13px;color:var(--muted);margin-top:4px}
.body{display:grid;gap:6px;min-width:0}
.name{font-weight:650;font-size:17px;overflow-wrap:anywhere}
.title{color:var(--muted);font-size:14px}
.lead{margin:0;overflow-wrap:anywhere}
.chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.chip{border-radius:999px;padding:1px 9px;font-size:12px;font-weight:650;white-space:nowrap;font-variant-numeric:tabular-nums}
.chip.decided{background:var(--decided-bg);color:var(--decided-ink)}.chip.action{background:var(--action-bg);color:var(--action-ink)}
.chip.proposal{background:var(--proposal-bg);color:var(--proposal-ink)}.chip.open{background:var(--open-bg);color:var(--open-ink)}
.len{font:12px var(--mono);color:var(--muted);font-variant-numeric:tabular-nums}
.topics{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--muted)}
.empty{color:var(--muted)}
@media(max-width:520px){.meeting{grid-template-columns:1fr;gap:8px}.date b{display:inline;font-size:18px}.date span{display:inline;margin-left:8px}}
"""

SCRIPT = """
const box=document.getElementById('filter');
box.addEventListener('input',()=>{const q=box.value.trim().toLowerCase();
 for(const m of document.querySelectorAll('.meeting'))m.hidden=!!q&&!m.dataset.text.includes(q);
 for(const g of document.querySelectorAll('.month'))g.hidden=![...g.querySelectorAll('.meeting')].some(m=>!m.hidden);});
"""


def add(root, entry, title=TITLE):
    """Add or replace a meeting. The same slug or the same recording (a rename) is replaced.
    Returns the pages that are no longer listed, so the caller can unpublish them."""
    root = Path(root)
    manifest = root / "meetings.json"
    meetings = json.loads(manifest.read_text()) if manifest.exists() else []
    same = [m for m in meetings if m["slug"] == entry["slug"] or m.get("recording") == entry["recording"]]
    meetings = [m for m in meetings if m not in same] + [entry]
    meetings.sort(key=lambda m: m["time"], reverse=True)
    manifest.write_text(json.dumps(meetings, ensure_ascii=False, indent=1) + "\n")
    (root / "index.html").write_text(render(meetings, title), encoding="utf-8")
    return [m["page"] for m in same if m["page"] != entry["page"]]


def seconds(hms):
    h, m, s = map(int, hms.split(":"))
    return h * 3600 + m * 60 + s


def render(meetings, title):
    e = html.escape
    total = sum(seconds(m["duration"]) for m in meetings)
    parts = [f"<title>{e(title)}</title>", '<meta name="claude:viewport-fit-sides" content="cover">',
             '<link rel="preconnect" href="https://fonts.googleapis.com">',
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600'
             '&family=IBM+Plex+Sans:wght@400;600;700&display=swap">', f"<style>{STYLE}</style>",
             '<div class="wrap"><header><h1>' + e(title) + '</h1><div class="stats">'
             f'{len(meetings)} meeting{"" if len(meetings) == 1 else "s"} · {total // 3600} h {total // 60 % 60} min recorded</div></header>',
             '<input id="filter" type="search" placeholder="Filter by name, date, topic…" aria-label="Filter meetings">']
    if not meetings:
        parts.append('<p class="empty">No meetings yet.</p>')
    month = None
    for m in meetings:
        if m["time"][:7] != month:
            parts.append(("</section>" if month else "") + f'<section class="month"><h2>{m["time"][:7]}</h2>')
            month = m["time"][:7]
        labels = KIND["zh" if m.get("lang", "en").startswith("zh") else "en"]
        chips = "".join(f'<span class="chip {k}">{labels[k]} {n}</span>' for k, n in m["outcomes"].items() if n)
        searchable = " ".join([m["name"], m["time"], m["title"], m["lead"]] + m["topics"]).lower()
        parts.append(
            f'<a class="meeting" href="{e(m["page"])}" data-text="{e(searchable)}">'
            f'<div class="date"><b>{m["time"][5:10]}</b><span>{m["time"][11:16]}</span></div>'
            f'<div class="body"><div class="name">{e(m["name"])} - {e(m["time"])}</div>'
            f'<div class="title">{e(m["title"])}</div><p class="lead">{e(m["lead"])}</p>'
            f'<div class="chips">{chips}<span class="len">{m["duration"]}</span></div>'
            f'<div class="topics">{"".join(f"<span>{e(t)}</span>" for t in m["topics"])}</div></div></a>')
    if month:
        parts.append("</section>")
    parts.append(f"</div><script>{SCRIPT}</script>")
    return "\n".join(parts)
