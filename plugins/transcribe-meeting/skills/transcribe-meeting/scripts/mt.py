"""Shared helpers for the transcribe-meeting scripts (standard library only)."""
import json
import re
import textwrap
from pathlib import Path

SR = 16000
LOOP = re.compile(r"(.{1,35}?)\1{3,}")
SPAM = re.compile(r"请不吝|字幕.*(?:提供|制作)|[点點]赞.*[订訂][阅閱]|感谢.{0,3}观看|謝謝.{0,3}觀看|Amara\.org|"
                  r"thanks? for watching|subscribe to|subtitles? by", re.I)


def load(path):
    return json.loads(Path(path).read_text())


def save_json(path, value):
    """Atomic write, so an interrupted run never leaves half a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def timestamp(seconds, separator="."):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{milliseconds:03d}"


def scripts(text):
    """Writing-system family of a text: cjk, latin, cyrillic, mixed or other.

    Any two families in one segment count as mixed (e.g. Chinese with an English
    term). Mixed segments keep coarse timestamps; a monolingual aligner is not
    evidence of reliable timing across both languages.
    """
    found = [name for name, pattern in [
        ("cjk", r"[぀-ヿ㐀-鿿가-힯]"),
        ("latin", r"[A-Za-zÀ-ɏ]"),
        ("cyrillic", r"[Ѐ-ӿ]")] if re.search(pattern, text)]
    return found[0] if len(found) == 1 else "mixed" if found else "other"


def compact(text):
    return re.sub(r"\s+", "", text)


def has_loop(text):
    """A phrase repeated 4+ times covering >= 18 characters: likely an ASR loop."""
    return any(len(m.group(0)) >= 18 for m in LOOP.finditer(compact(text)))


def export(result, out):
    """Write transcript.json plus TXT, timestamped TXT (with segment IDs) and SRT."""
    out = Path(out)
    save_json(out / "transcript.json", result)
    plain, timed, subtitles = [], [], []
    for i, segment in enumerate(result["segments"], 1):
        text = segment["text"].strip()
        speaker = segment.get("speaker")
        label = f"{speaker}: " if speaker else ""
        plain.append(text)
        timed.append(f'[{timestamp(segment["start"])} --> {timestamp(segment["end"])}] '
                     f'#{segment["id"]} {label}{text}')
        wrapped = textwrap.fill(label + text, width=70, break_long_words=True, break_on_hyphens=False)
        subtitles.append(f'{i}\n{timestamp(segment["start"], ",")} --> '
                         f'{timestamp(segment["end"], ",")}\n{wrapped}\n')
    (out / "transcript.txt").write_text("\n\n".join(plain) + "\n")
    (out / "transcript_timestamped.txt").write_text("\n".join(timed) + "\n")
    (out / "transcript.srt").write_text("\n".join(subtitles))


def read_wav(out, start, end):
    """Float32 samples of meeting.wav between two original-clock times (seconds)."""
    import wave
    import numpy as np
    with wave.open(str(Path(out) / "meeting.wav"), "rb") as audio:
        first = max(0, round(start * SR))
        audio.setpos(min(first, audio.getnframes()))
        frames = audio.readframes(max(0, round(end * SR) - first))
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768


def current_transcript(out):
    """Latest accepted text stage: reviewed, else raw ASR."""
    out = Path(out)
    for name in ["intermediate/asr-reviewed.json", "intermediate/asr-raw.json"]:
        if (out / name).exists():
            return out / name
    raise SystemExit("No ASR result yet: run transcribe.py first")
