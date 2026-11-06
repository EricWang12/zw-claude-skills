"""Structural verification of the deliverables, plus review list and run-info.txt.

Usage: python verify.py --out DIR      (standard library only; exits non-zero on errors)

Checks: recording hash unchanged; the whole WAV processed; every ASR window decoded;
every final text traces to a saved ASR/redecode output; finite, ordered, in-range
segment and word times; every VAD speech interval covered; SRT matches JSON.
Covering detected speech does not prove VAD detected all speech, and none of this
certifies words: review-needed.tsv lists what a person should listen to.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import re
import wave
from pathlib import Path

from mt import SPAM, current_transcript, has_loop, load, save_json, timestamp

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True)
args = parser.parse_args()
out = Path(args.out)
result = load(out / "transcript.json")
reference = load(current_transcript(out))
raw = load(out / "intermediate/asr-raw.json")
source = load(out / "logs/source-integrity.json")
errors, flags = [], []

with open(source["path"], "rb") as file:
    unchanged = hashlib.file_digest(file, "sha256").hexdigest() == source["sha256"]
if not unchanged:
    errors.append("Original recording hash changed")
with wave.open(str(out / "meeting.wav")) as wav:
    duration = wav.getnframes() / wav.getframerate()
if abs(result["processed_audio_seconds"] - duration) > .001:
    errors.append("Processed duration differs from the WAV duration")
if raw["completed_chunks"] != len(load(out / "intermediate/vad-chunks.json")):
    errors.append("Not every VAD window was decoded")

# Text provenance: final == accepted stage; accepted == raw ASR or an accepted redecode.
if [s["text"] for s in result["segments"]] != [s["text"] for s in reference["segments"]]:
    errors.append("Postprocessing changed, lost or reordered accepted text")
allowed = {s["id"]: s["text"] for s in raw["segments"]}
review_path = out / "intermediate/review-candidates.json"
if review_path.exists() and "review" in reference:
    for c in load(review_path):
        if c["decision"] == "accept":
            allowed[c["id"]] = c["candidate_text"]
untraced = [s["id"] for s in result["segments"] if allowed.get(s["id"]) != s["text"]]
if untraced:
    errors.append(f"Text not traceable to saved ASR output: {untraced[:10]}")

previous_end, timed_words, gaps = 0.0, 0, []
for s in result["segments"]:
    start, end, text = s["start"], s["end"], s["text"]
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration + .002):
        errors.append(f"Invalid segment time: {s['id']}")
    if start < previous_end - .002:
        errors.append(f"Overlapping or out-of-order segment: {s['id']}")
    if start - previous_end > 10:
        gaps.append([round(previous_end, 3), round(start, 3)])
    previous_end = max(previous_end, end)
    last = start - .02
    for w in s.get("words", []):
        if "start" in w:
            timed_words += 1
            if not (math.isfinite(w["start"]) and math.isfinite(w["end"]) and
                    start - .02 <= w["start"] < w["end"] <= end + .02 and w["start"] >= last):
                errors.append(f"Invalid word time in segment {s['id']}")
            last = w["start"]
    reasons = []
    if not re.search(r"\w", text):
        reasons.append("empty or punctuation-only text")
    if s.get("avg_logprob", 0) < -.65:
        reasons.append("low ASR log probability")
    if has_loop(text):
        reasons.append("repeated phrase: disfluency or ASR loop")
    if SPAM.search(text):
        reasons.append("possible silence hallucination (subtitle/outro phrase)")
    if any(d["probability"] < .70 for d in s.get("language_detection", [])):
        reasons.append("uncertain language detection")
    if "redecode" in s:
        reasons.append(f"{s['redecode']['kind']} redecode accepted; compare redecode-comparison.tsv")
    if reasons:
        flags.append([s["id"], start, end, "; ".join(reasons), text])
for g in reference.get("review", {}).get("rejected_candidates", []):
    what = ("possible quiet speech NOT in transcript" if g["kind"] == "gap"
            else "rejected redecode differs from transcript")
    flags.append([g["id"], g["start"], g["end"], f"{what} (uncertain); listen: {g['reason']}",
                  g["candidate_text"] or "[no reliable text]"])
flags.sort(key=lambda f: f[1])

uncovered = []
for interval in load(out / "intermediate/vad-speech.json"):
    covered = sum(max(0, min(s["end"], interval["end"]) - max(s["start"], interval["start"]))
                  for s in result["segments"])
    if interval["end"] - interval["start"] - covered > .01:
        uncovered.append(interval)
if uncovered:
    errors.append(f"Uncovered VAD speech intervals: {len(uncovered)}")

blocks = (out / "transcript.srt").read_text().strip().split("\n\n")
if len(blocks) != len(result["segments"]):
    errors.append("SRT cue count differs from JSON")
for i, (block, s) in enumerate(zip(blocks, result["segments"]), 1):
    lines = block.splitlines()
    label = f"{s['speaker']}: " if s.get("speaker") else ""
    if (lines[0] != str(i) or lines[1] != f'{timestamp(s["start"], ",")} --> {timestamp(s["end"], ",")}'
            or re.sub(r"\s+", "", "".join(lines[2:])) != re.sub(r"\s+", "", label + s["text"].strip())):
        errors.append(f"SRT cue {i} differs from JSON")
        break
for name in ["transcript.txt", "transcript_timestamped.txt", "transcript.srt", "transcript.json"]:
    if (out / name).stat().st_size == 0:
        errors.append(f"Empty output: {name}")

with (out / "review-needed.tsv").open("w", newline="") as file:
    writer = csv.writer(file, delimiter="\t")
    writer.writerow(["id", "start", "end", "reason", "text_or_excluded_candidate"])
    writer.writerows([f[0], timestamp(f[1]), timestamp(f[2]), f[3], f[4]] for f in flags)
with (out / "logs/beginning-middle-end.txt").open("w") as file:
    for label, target in [("beginning", 0), ("middle", duration / 2), ("end", duration)]:
        file.write(label + "\n")
        for s in sorted(sorted(result["segments"], key=lambda s: abs((s["start"] + s["end"]) / 2 - target))[:3],
                        key=lambda s: s["start"]):
            file.write(f'#{s["id"]} [{timestamp(s["start"])} --> {timestamp(s["end"])}] {s["text"]}\n')

prepare = load(out / "logs/prepare.json")
report = {"status": "passed" if not errors else "failed", "errors": errors,
          "original_sha256_unchanged": unchanged, "decoded_wav_seconds": duration,
          "container_minus_decoded_seconds": prepare["container_minus_decoded_seconds"],
          "segments": len(result["segments"]), "first_speech": result["segments"][0]["start"],
          "last_speech": result["segments"][-1]["end"], "timed_words": timed_words,
          "text_scripts": dict(collections.Counter(s["text_scripts"] for s in result["segments"])),
          "language_hints": dict(collections.Counter(s["language_hint"] for s in result["segments"])),
          "gaps_over_10_seconds": gaps, "review_rows": len(flags),
          "limitation": "Structural checks and alternate decodes do not certify every spoken word; "
                        "names, terms and flagged passages need listening review."}
save_json(out / "logs/verification.json", report)

sample = load(out / "logs/sample-comparison.json") if (out / "logs/sample-comparison.json").exists() else {}
machine = sample.get("machine", {})
diarization = result.get("diarization")
review = reference.get("review", {})
alignment = result.get("alignment")
lines = [
    f"Recording: {source['path']}",
    f"SHA256 {source['sha256']} ({'unchanged' if unchanged else 'CHANGED'}); {source['bytes']} bytes",
    f"Decoded WAV: {timestamp(duration)} mono 16 kHz; container minus decoded "
    f"{prepare['container_minus_decoded_seconds'] * 1000:.1f} ms",
    f"GPU: {machine.get('gpu', '?')}; torch CUDA {machine.get('torch_cuda', '?')}; versions {machine.get('versions', {})}",
    f"Model: {raw['settings']['model']}, transcribe, CUDA float16, final batch {raw.get('final_batch_size')}",
    f"VAD: Silero onset {raw['vad']['onset']}, windows <= 30 s on the original clock",
    f"Language policy: {raw['language_policy']}",
    f"Sample check: {sample.get('sample_start', '?')} s + {sample.get('sample_duration', '?')} s, hints "
    f"{list(sample.get('hints', {}))}; see sample-comparison.tsv",
    f"Review: accepted redecodes {review.get('accepted_ids', 'not run')}; "
    f"rejected candidates listed for listening {len(review.get('rejected_candidates', []))}",
    f"Alignment: {json.dumps(alignment['languages']) if isinstance(alignment, dict) else alignment}",
    f"Diarization: {diarization.get('status') + ' ' + diarization.get('error_type', '') if isinstance(diarization, dict) else diarization}",
    f"Segments {len(result['segments'])}; review rows {len(flags)} (review-needed.tsv)",
    f"Runtimes (s): {json.dumps({k: round(v, 1) for k, v in raw['runtime_seconds'].items()})}",
    f"Verification: {report['status']} {errors if errors else ''}",
    "Limits: " + report["limitation"]]
(out / "run-info.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
raise SystemExit(1 if errors else 0)
