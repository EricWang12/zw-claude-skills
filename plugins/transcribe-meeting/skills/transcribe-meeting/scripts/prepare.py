"""Probe and hash the finished recording, then decode a mono 16 kHz WAV.

Usage: python prepare.py RECORDING --out OUTPUT_DIR
Needs only Python 3.11+ and ffmpeg/ffprobe. Never modifies or overwrites the recording.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import wave
from pathlib import Path

from mt import save_json, load

parser = argparse.ArgumentParser()
parser.add_argument("recording")
parser.add_argument("--out", required=True)
args = parser.parse_args()

source = Path(args.recording).expanduser().resolve()
out = Path(args.out).expanduser().resolve()
(out / "logs").mkdir(parents=True, exist_ok=True)
(out / "intermediate").mkdir(exist_ok=True)

if not source.is_file():
    sys.exit(f"Recording not found: {source}")
if source.suffix.lower() in {".part", ".crdownload", ".tmp", ".download", ".partial"}:
    sys.exit(f"Looks like an unfinished upload/download: {source.name}. Use the completed file.")
size = source.stat().st_size
time.sleep(3)
if source.stat().st_size != size or size == 0:
    sys.exit(f"File size is changing or zero; it may still be uploading: {source}")

probe = json.loads(subprocess.run(
    ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)],
    check=True, capture_output=True, text=True).stdout)
if not any(s.get("codec_type") == "audio" for s in probe["streams"]):
    sys.exit("No audio stream found")
save_json(out / "logs/input-ffprobe.json", probe)

with source.open("rb") as file:
    digest = hashlib.file_digest(file, "sha256").hexdigest()
integrity = out / "logs/source-integrity.json"
if integrity.exists() and load(integrity)["sha256"] != digest:
    sys.exit(f"{out} already holds results for a different recording; choose another --out")
save_json(integrity, {"path": str(source), "bytes": size, "sha256": digest})

wav = out / "meeting.wav"
if not wav.exists():
    log = subprocess.run(["ffmpeg", "-nostdin", "-v", "warning", "-n", "-i", str(source), "-vn",
                          "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
                         capture_output=True, text=True)
    (out / "logs/decode.log").write_text(log.stderr)
    if log.returncode:
        wav.unlink(missing_ok=True)
        sys.exit("ffmpeg decode failed:\n" + log.stderr[-2000:])
with wave.open(str(wav)) as audio:
    assert (audio.getnchannels(), audio.getframerate(), audio.getsampwidth()) == (1, 16000, 2)
    decoded = audio.getnframes() / 16000
container = float(probe["format"].get("duration", "nan"))
# When the meeting happened: the container's creation_time (UTC; Voice Memos and most
# recorders set it), else the file's modification time, which is only an upper bound.
tags = probe["format"].get("tags", {})
recorded = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate")
recorded_source = "container creation_time" if recorded else "file modification time (approximate)"
if not recorded:
    from datetime import datetime, timezone
    recorded = datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat()
report = {"recording": str(source), "sha256": digest, "bytes": size,
          "recorded_utc": recorded, "recorded_source": recorded_source,
          "codec": next(s["codec_name"] for s in probe["streams"] if s["codec_type"] == "audio"),
          "container_seconds": container, "decoded_wav_seconds": decoded,
          "container_minus_decoded_seconds": container - decoded,
          "decode_warnings": (out / "logs/decode.log").read_text().strip() if (out / "logs/decode.log").exists() else ""}
save_json(out / "logs/prepare.json", report)
print(json.dumps(report, indent=2, ensure_ascii=False))
if abs(container - decoded) > 0.25:
    print("WARNING: container and decoded durations differ by more than 0.25 s. Inspect the last "
          "frames (ffprobe -show_frames) before trusting coverage; do not pad or truncate silently.")
