"""Render summary.json into a source-linked HTML page with playback, and file it in the library.

Usage:
  python build_summary.py --out DIR --name "Nixon Rd 5" --tz America/Detroit [--library STAGING]

Every overview line, topic finding, topic row and outcome must cite segment IDs
from transcript.json. Clicking a citation opens that exact original passage and
plays its clip; the time shown is the ORIGINAL recording position (HH:MM:SS).
Clips (mono 16 kHz 24 kbps MP3 with --context s of padding) are embedded as inert
base64 text and played through Web Audio after a click, so the page works in
sandboxed viewers that block media URLs.

The page is named "<name> - <YYYY-MM-DD HH:MM>": the meeting's name and when it was
recorded (prepare.json's recorded_utc in --tz, unless --time is given).

Always writes DIR/meeting-summary.html (local copy, with a clip download button) and
DIR/meeting-summary.txt. With --library STAGING it also writes the artifact variant to
STAGING/meetings/<slug>.html (no download button: the artifact sandbox blocks
downloads; a link back to the library home), updates STAGING/meetings.json and
regenerates STAGING/index.html. Pages contain private meeting audio.
"""
import argparse
import base64
import hashlib
import html
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from mt import load, save_json

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True)
parser.add_argument("--name", required=True, help="meeting name: the user's own name for it, else the recording's file name")
parser.add_argument("--tz", help="IANA zone for the meeting time, e.g. America/Detroit (default: system zone)")
parser.add_argument("--time", help="override, 'YYYY-MM-DD HH:MM' local time")
parser.add_argument("--summary")
parser.add_argument("--context", type=float, default=1.0)
parser.add_argument("--library", help="staging folder of the library artifact")
parser.add_argument("--library-title", default="Zhaoning Meeting Notes")
args = parser.parse_args()
out = Path(args.out)
summary = load(args.summary or out / "summary.json")
transcript = load(out / "transcript.json")
segments = {str(s["id"]): s for s in transcript["segments"]}
duration = transcript["audio_duration_seconds"]
protected = ["transcript.json", "transcript.txt", "transcript_timestamped.txt", "transcript.srt"]
hashes = {n: hashlib.sha256((out / n).read_bytes()).hexdigest() for n in protected}
assets = Path(__file__).resolve().parent.parent / "assets"
escape = html.escape

if args.time:
    when = args.time
else:
    recorded = datetime.fromisoformat(load(out / "logs/prepare.json")["recorded_utc"].replace("Z", "+00:00"))
    when = recorded.astimezone(ZoneInfo(args.tz) if args.tz else None).strftime("%Y-%m-%d %H:%M")
page_name = f"{args.name} - {when}"
ascii_name = re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")
slug = re.sub(r"\D", "", when)[:12] + "-" + (ascii_name or hashlib.sha1(args.name.encode()).hexdigest()[:8])

zh = summary.get("lang", "en").startswith("zh")
KINDS = ["decided", "action", "proposal", "open"]
L = {"source": "原文与回听", "back": "返回总结 ×", "play": "播放", "pause": "暂停", "position": "原录音位置",
     "download": "下载此音频片段", "excerpt": "原文", "segment": "原始转写片段", "home": "← 全部会议",
     "review": "这段含待复核内容，名称、重复或轻声处请结合回听判断；原文未作猜测性改写。",
     "ready": "点击播放可回听；进度显示的是原录音位置。", "paused": "已暂停", "loading": "正在准备音频…",
     "playing": "正在回听原录音片段", "ended": "本段播放结束", "located": "已定位到原录音 ",
     "noaudio": "当前预览未提供 Web Audio 播放能力", "blocked": "音频输出尚未获准，请再次点击播放",
     "failed": "播放未开始：", "fallback": "。", "fallback_local": "。可下载此片段，用本地播放器打开。",
     "recording": "录音", "outcomes": "结论、行动与未决事项", "point": "要点", "summary": "总结",
     "cites": "对应原文（时:分:秒）", "kind": {"decided": "已决定", "action": "行动", "proposal": "提议 / 待验证",
                                             "open": "未决定"},
     "timenote": "所有时间均为原录音的<strong>时:分:秒</strong>。例如 <strong>01:21:50 = 1小时21分50秒</strong>。"
                 "点击“原文与回听”查看对应原文并播放该段。",
     "footer": "原文按需打开，整篇转写不附在总结下面。回听片段直接嵌在本页，显示原录音时间。"
               "专有名词与有疑问的识别文字仍需结合录音核对。"} if zh else {
     "source": "Source & audio", "back": "Back to summary ×", "play": "Play", "pause": "Pause",
     "position": "Recording position", "download": "Download this clip", "excerpt": "Source",
     "segment": "transcript segment", "home": "← All meetings",
     "review": "This passage is flagged for review (names, repetition or quiet speech). Listen before relying on it; "
               "the text was not guessed or rewritten.",
     "ready": "Press Play to listen; the position shown is the original recording time.", "paused": "Paused",
     "loading": "Preparing audio…", "playing": "Playing the original passage", "ended": "End of clip",
     "located": "Positioned at ", "noaudio": "This viewer does not provide Web Audio playback",
     "blocked": "Audio output is not yet allowed; press Play again", "failed": "Playback did not start: ",
     "fallback": ".", "fallback_local": ". Download the clip and open it in a local player.",
     "recording": "recording", "outcomes": "Decisions, actions and open questions", "point": "Point",
     "summary": "Summary", "cites": "Source (HH:MM:SS)",
     "kind": {"decided": "Decided", "action": "Action", "proposal": "Proposal / to test", "open": "Open"},
     "timenote": "All times are positions in the original recording as <strong>HH:MM:SS</strong>; "
                 "e.g. <strong>01:21:50 = 1 h 21 min 50 s</strong>. Click a source link to read and hear that passage.",
     "footer": "Sources open on demand; the full transcript is not appended. Clips are embedded in this page and show "
               "original recording time. Names and flagged passages still need listening review."}


def stamp(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def human(seconds):
    seconds = int(seconds)
    h, m, s = seconds // 3600, seconds // 60 % 60, seconds % 60
    return f"{h}小时{m}分{s}秒" if zh else f"{h} h {m} min {s} s"


def anchor(i):  # artifact hashes pass only letters, digits and hyphens
    return "source-" + re.sub(r"[^A-Za-z0-9-]", "-", i)


cited = []


def refs(ids, where):
    assert ids, f"{where} cites no source segment"
    links = []
    for i in map(str, ids):
        assert i in segments, f"{where} cites unknown segment {i}"
        if i not in cited:
            cited.append(i)
        s = segments[i]
        links.append(f'<a class="source-link" href="#{anchor(i)}" data-source="{anchor(i)}" '
                     f'title="{L["source"]}: {human(s["start"])}">{L["source"]} {stamp(s["start"])}–{stamp(s["end"])}</a>')
    return '<span class="references">' + "".join(links) + "</span>"


def text_refs(ids):
    return "    " + "  ".join(f'{stamp(segments[str(i)]["start"])}–{stamp(segments[str(i)]["end"])} (#{i})' for i in ids)


# Body shared by both variants.
body, text = [], [page_name, summary["title"], re.sub(r"</?strong>", "", L["timenote"]), ""]
body += [f'<h1>{escape(summary["title"])}</h1>', f'<p class="note">{L["timenote"]}</p>',
         '<section class="card lead" id="overview">']
for n, item in enumerate(summary["overview"]):
    body.append(f'<p>{"<strong>" if n == 0 else ""}{escape(item["text"])}{"</strong>" if n == 0 else ""}</p>'
                + refs(item["sources"], "overview"))
    text += [item["text"], text_refs(item["sources"])]
body.append("</section>")
outcomes = summary.get("outcomes", [])
for o in outcomes:
    assert o["kind"] in KINDS, f'outcome kind {o["kind"]} not in {KINDS}'
if outcomes:
    body.append(f'<section class="card" id="outcomes"><h2>{L["outcomes"]}</h2><div class="table-wrap"><table><tbody>')
    text += ["", L["outcomes"]]
    for o in sorted(outcomes, key=lambda o: KINDS.index(o["kind"])):
        body.append(f'<tr data-summary-row="outcome"><th scope="row"><span class="kind {o["kind"]}">'
                    f'{L["kind"][o["kind"]]}</span></th><td>{escape(o["text"])}</td>'
                    f'<td class="source-column">{refs(o["sources"], "outcome")}</td></tr>')
        text += [f'  [{L["kind"][o["kind"]]}] {o["text"]}', text_refs(o["sources"])]
    body.append("</tbody></table></div></section>")
body.append('<nav class="toc">' + "".join(f'<a href="#topic-{i}">{i}. {escape(t["title"])}</a>'
                                          for i, t in enumerate(summary["topics"], 1)) + "</nav>")
for i, topic in enumerate(summary["topics"], 1):
    body += [f'<section class="card" id="topic-{i}"><h2>{i}. {escape(topic["title"])}</h2>',
             f'<p class="finding">{escape(topic["finding"])}</p>', refs(topic["sources"], f"topic {i}"),
             f'<div class="table-wrap"><table><thead><tr><th>{L["point"]}</th><th>{L["summary"]}</th>'
             f'<th class="source-column">{L["cites"]}</th></tr></thead><tbody>']
    text += ["", f'{i}. {topic["title"]}', topic["finding"], text_refs(topic["sources"])]
    for row in topic["rows"]:
        body.append(f'<tr data-summary-row="{i}"><th scope="row">{escape(row["label"])}</th>'
                    f'<td>{escape(row["text"])}</td><td>{refs(row["sources"], f"topic {i} row")}</td></tr>')
        text += [f'  {row["label"]}: {row["text"]}', text_refs(row["sources"])]
    body.append("</tbody></table></div></section>")
for note in summary.get("notes", []):
    body.append(f'<p class="note">{escape(note)}</p>')
body.append(f'<p class="note">{L["footer"]}</p></main>')

# Clips: original-clock bounds stored separately from the segment's own start/end.
clip_dir = out / "playback-clips"
clip_dir.mkdir(exist_ok=True)
flagged = set()
if (out / "review-needed.tsv").exists():
    flagged = {line.split("\t")[0] for line in (out / "review-needed.tsv").read_text().splitlines()[1:]}
clip_log, panels = [], []
for i in cited:
    s = segments[i]
    clip_start, clip_end = max(0.0, s["start"] - args.context), min(duration, s["end"] + args.context)
    path = clip_dir / f"segment-{i}.mp3"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{clip_start:.3f}", "-i",
                    str(out / "meeting.wav"), "-t", f"{clip_end - clip_start:.3f}", "-vn", "-ac", "1", "-ar",
                    "16000", "-c:a", "libmp3lame", "-b:a", "24k", str(path)], check=True)
    clip_log.append({"id": i, "clip_start": clip_start, "clip_end": clip_end, "bytes": path.stat().st_size})
    panels.append((i, s, clip_start, clip_end, base64.b64encode(path.read_bytes()).decode("ascii")))


def render(library):
    labels = {k: v for k, v in L.items() if isinstance(v, str)}
    if not library:
        labels["fallback"] = L["fallback_local"]
    eyebrow = (f'<a class="home" href="../index.html">{L["home"]}</a>' if library else "") + \
              f'<div class="tag">{escape(page_name)} · {L["recording"]} {stamp(duration)}</div>'
    page = ['<!doctype html><html lang="' + ("zh-CN" if zh else "en") + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<title>{escape(page_name)}</title><meta name="claude:viewport-fit-sides" content="cover">'
            f'<style>{(assets / "summary.css").read_text()}</style></head><body><main>', eyebrow] + body
    for i, s, clip_start, clip_end, data in panels:
        page += [f'<section class="source-panel" id="{anchor(i)}" role="dialog" aria-modal="true" '
                 f'aria-labelledby="title-{anchor(i)}" data-start="{s["start"]}" data-end="{s["end"]}" '
                 f'data-clip-start="{clip_start}" data-clip-end="{clip_end}"><div class="source-card">',
                 f'<div class="source-header"><div><h2 id="title-{anchor(i)}">{L["excerpt"]} · {stamp(s["start"])}–'
                 f'{stamp(s["end"])}</h2><div class="note">{human(s["start"])} – {human(s["end"])} · '
                 f'{L["segment"]} #{escape(i)}</div></div><a class="close-source" href="#overview">{L["back"]}</a></div>',
                 f'<p class="source-text">{escape(s["text"].strip())}</p>',
                 f'<p class="review">{L["review"]}</p>' if i in flagged else "",
                 '<div class="playback"><div class="custom-controls" hidden><div class="player-row">'
                 f'<button class="toggle-play" type="button">{L["play"]}</button><div>{L["position"]} '
                 f'<output class="global-time">{stamp(s["start"])}</output> / {stamp(duration)}</div></div>'
                 f'<input class="timeline" aria-label="{L["position"]}" type="range" min="{clip_start}" '
                 f'max="{clip_end}" value="{s["start"]}" step="0.01"><div class="bounds"><span>{stamp(clip_start)}'
                 f'</span><span>{stamp(clip_end)}</span></div></div><div class="clip-bytes" hidden>{data}</div>',
                 "" if library else f'<p><button class="download-clip" type="button">{L["download"]}</button></p>',
                 f'<p class="playback-status" role="status">{L["ready"]}</p></div></div></section>']
    page.append(f"<script>const L={json.dumps(labels, ensure_ascii=False)};\n"
                f"{(assets / 'summary-player.js').read_text()}</script></body></html>")
    return "\n".join(page)


(out / "meeting-summary.html").write_text(render(False), encoding="utf-8")
(out / "meeting-summary.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
save_json(out / "logs/playback-clips.json", {"context_seconds": args.context, "codec": "mp3 mono 16 kHz 24 kbps",
                                             "clips": clip_log})
report = {"page_name": page_name, "topics": len(summary["topics"]), "outcomes": len(outcomes),
          "rows": sum(len(t["rows"]) for t in summary["topics"]), "cited_segments": len(cited),
          "html_bytes": (out / "meeting-summary.html").stat().st_size}

if args.library:
    import library
    root = Path(args.library)
    page_path = root / "meetings" / f"{slug}.html"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(render(True), encoding="utf-8")
    counts = {k: sum(o["kind"] == k for o in outcomes) for k in KINDS}
    recording = load(out / "logs/source-integrity.json")["sha256"]
    removed = library.add(root, {"slug": slug, "page": f"meetings/{slug}.html", "name": args.name, "time": when,
                       "recording": recording,
                       "title": summary["title"], "lead": summary["overview"][0]["text"], "lang": summary.get("lang", "en"),
                       "duration": stamp(duration), "outcomes": counts,
                       "topics": [t["title"] for t in summary["topics"]], "bytes": page_path.stat().st_size},
                args.library_title)
    report.update(library_page=str(page_path), publish_files=["meetings.json", f"meetings/{slug}.html"],
                  unpublish_files=removed)
    if page_path.stat().st_size > 15_000_000:
        raise SystemExit("Library page exceeds the artifact's 16 MB page limit: cite fewer/shorter passages")

assert hashes == {n: hashlib.sha256((out / n).read_bytes()).hexdigest() for n in protected}
print(json.dumps(report, indent=2, ensure_ascii=False))
