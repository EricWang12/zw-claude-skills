"""Find suspicious passages, redecode them from the audio, and suggest decisions.

Usage: python review.py --out DIR [--gap 3] [--context 15]

Looks for three problems the ASR score does not reveal:
  loop    a phrase repeated many times (high confidence can accompany a loop)
  sparse  very little text for the speech the VAD heard
  gap     >= --gap seconds between segments that still holds quiet speech at VAD 0.15
Each candidate gets a fresh decode (no_repeat_ngram_size=5) plus a second decode
with --context seconds of surrounding audio. A candidate is "corroborated" when most
of its text also appears in the context decode. Agreement is corroboration, not truth.

Writes intermediate/review-candidates.json with "suggestion" and an editable
"decision" (accept | reject). Nothing is merged here: read the texts, adjust the
decisions, then run apply_review.py. Silence hallucinations (subtitle spam, canned
phrases) are never suggested.
"""
import argparse
import difflib
import math
import statistics
import time
from pathlib import Path

import numpy as np
import whisperx
from faster_whisper.tokenizer import Tokenizer
from faster_whisper.vad import VadOptions, get_speech_timestamps

from mt import SPAM, SR, compact, has_loop, load, read_wav, save_json

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True)
parser.add_argument("--gap", type=float, default=3)
parser.add_argument("--context", type=float, default=15)
args = parser.parse_args()
out = Path(args.out)
started = time.perf_counter()
raw = load(out / "intermediate/asr-raw.json")
segments, duration = raw["segments"], raw["audio_duration_seconds"]
speech = load(out / "intermediate/vad-speech.json")


def letters(text):
    return len([c for c in compact(text) if c.isalnum()])


def speech_seconds(start, end):
    return sum(max(0, min(end, s["end"]) - max(start, s["start"])) for s in speech)


# 1. Detection.
density = {s["id"]: letters(s["text"]) / max(speech_seconds(s["start"], s["end"]), 1e-6) for s in segments}
median = statistics.median(d for d in density.values() if d > 0)
items = []
for s in segments:
    heard = speech_seconds(s["start"], s["end"])
    if has_loop(s["text"]):
        items.append({"kind": "loop", "segment": s, "reason": "repeated phrase loop"})
    elif heard >= 3 and density[s["id"]] < 0.35 * median:
        items.append({"kind": "sparse", "segment": s,
                      "reason": f"{letters(s['text'])} letters for {heard:.1f} s of detected speech "
                                f"(median density {median:.2f}/s)"})
bounds = [(0, 0)] + [(s["start"], s["end"]) for s in segments] + [(duration, duration)]
for (_, previous_end), (next_start, _) in zip(bounds, bounds[1:]):
    if next_start - previous_end < args.gap:
        continue
    clip = read_wav(out, previous_end, next_start)
    found = get_speech_timestamps(clip, VadOptions(threshold=.15, min_speech_duration_ms=250,
                                                   min_silence_duration_ms=100))
    heard = sum(f["end"] - f["start"] for f in found) / SR
    rms = float(np.sqrt(np.mean(clip ** 2))) if len(clip) else 0
    if heard >= 1:
        hint = min(segments, key=lambda s: abs(s["start"] - previous_end))["language_hint"]
        items.append({"kind": "gap", "start": previous_end, "end": next_start, "language_hint": hint,
                      "reason": f"{heard:.1f} s of possible speech at VAD 0.15 in a "
                                f"{next_start - previous_end:.1f} s gap, {20 * math.log10(max(rms, 1e-12)):.1f} dBFS"})
print("CANDIDATES", {k: sum(i["kind"] == k for i in items) for k in ["loop", "sparse", "gap"]}, flush=True)

# 2. Redecoding.
model = whisperx.load_model(raw["settings"]["model"], "cuda", compute_type="float16", vad_method="silero",
                            vad_options={"vad_onset": raw["vad"]["onset"]}, threads=8,
                            asr_options={"no_repeat_ngram_size": 5})


def native(start, end, language, threshold):
    """faster-whisper with its own VAD, which drops long pauses inside the clip."""
    start, end = max(0, start), min(duration, end)
    decoded, _ = model.model.transcribe(read_wav(out, start, end), language=language, task="transcribe",
        vad_filter=True, vad_parameters={"threshold": threshold, "min_silence_duration_ms": 300},
        beam_size=5, condition_on_previous_text=False, no_repeat_ngram_size=5, temperature=0)
    return [{"start": p.start + start, "end": p.end + start, "text": p.text.strip(),
             "avg_logprob": p.avg_logprob, "no_speech_prob": p.no_speech_prob} for p in decoded]


def matched_fraction(candidate, context):
    a, b = compact(candidate).lower(), compact(context).lower()
    if not a:
        return 0.0
    blocks = difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
    return sum(m.size for m in blocks if m.size >= 2) / len(a)


candidates = []
for item in items:
    segment = item.get("segment")
    start, end = (segment["start"], segment["end"]) if segment else (item["start"], item["end"])
    language = segment["language_hint"] if segment else item["language_hint"]
    threshold = .15 if item["kind"] == "gap" else raw["vad"]["onset"]
    if item["kind"] == "loop":  # same window as the original decode, loop-suppressed
        model.tokenizer = Tokenizer(model.model.hf_tokenizer, True, task="transcribe", language=language)
        clip = read_wav(out, start, end)
        output = next(iter(model(({"inputs": c} for c in [clip]), batch_size=1, num_workers=0)))
        text = output["text"][0] if isinstance(output["text"], list) else output["text"]
        score = output["avg_logprob"][0] if isinstance(output["avg_logprob"], list) else output["avg_logprob"]
        pieces = [{"start": start, "end": end, "text": text.strip(), "avg_logprob": float(score)}]
        method = "whisperx pipeline, same window, no_repeat_ngram_size 5"
    else:
        pieces = native(start, end, language, threshold)
        method = f"faster-whisper native VAD {threshold}, beam 5, no_repeat_ngram_size 5"
    text = " ".join(p["text"] for p in pieces).strip()
    context = native(start - args.context, end + args.context, language, threshold)
    context_text = " ".join(p["text"] for p in context)
    agreement = matched_fraction(text, context_text)
    original = segment["text"] if segment else ""
    usable = bool(letters(text) >= 2) and not has_loop(text) and not SPAM.search(text)
    if item["kind"] == "loop":
        good = usable
    elif item["kind"] == "sparse":
        good = usable and letters(text) >= 1.5 * max(letters(original), 1) and agreement >= .6
    else:
        good = usable and agreement >= .6 and len(compact(text)) >= 4
    candidates.append({
        "id": segment["id"] if segment else f"gap_{round(start * 1000)}",
        "kind": item["kind"], "start": start, "end": end, "language_hint": language,
        "reason": item["reason"], "original_text": original, "candidate_text": text,
        "candidate_pieces": pieces, "method": method, "context_text": context_text,
        "context_agreement": round(agreement, 3),
        "suggestion": "accept" if good else "reject", "decision": "accept" if good else "reject"})
    save_json(out / "intermediate/review-candidates.json", candidates)
    print(f'{candidates[-1]["id"]}\t{item["kind"]}\t{candidates[-1]["suggestion"]}\t'
          f'agree={agreement:.2f}\t{original[:40]!r} -> {text[:60]!r}', flush=True)
save_json(out / "intermediate/review-candidates.json", candidates)
save_json(out / "logs/review-runtime.json", {"seconds": time.perf_counter() - started,
                                              "median_letters_per_speech_second": median})
print("REVIEW_SAVED", len(candidates), "candidates in", round(time.perf_counter() - started, 1), "s")
