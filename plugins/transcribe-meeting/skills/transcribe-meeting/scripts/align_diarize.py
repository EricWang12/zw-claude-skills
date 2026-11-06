"""Optional word timing and speaker labels. Never changes the accepted text.

Usage: python align_diarize.py --out DIR [--no-diarize] [--speakers N]

Alignment: only single-script segments whose first language probe agrees with the
hint at >= 0.90 are aligned, against the original clock. No interpolation; words
below score 0.5 (a model score, not a probability) or outside the segment lose
their times. Mixed-language segments keep segment timestamps only. For CJK
languages the "words" entries are characters.
Diarization: pyannote/speaker-diarization-community-1 (gated). Reads the token from
HF_TOKEN or the existing `hf auth login`; never prints it. Failure is recorded and
the transcript is still delivered. Labels stay neutral (SPEAKER_00); never names.
"""
import argparse
import copy
import gc
import math
import os
import statistics
import time
from pathlib import Path

import torch
import whisperx

from mt import current_transcript, export, load, save_json

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True)
parser.add_argument("--no-diarize", action="store_true")
parser.add_argument("--speakers", type=int, help="only if the user states the number")
parser.add_argument("--min-score", type=float, default=0.5)
args = parser.parse_args()
out = Path(args.out)
started = time.perf_counter()
result = load(current_transcript(out))
texts = [s["text"] for s in result["segments"]]
audio = whisperx.load_audio(str(out / "meeting.wav"))

report = {"languages": {}, "policy": "single-script segments with confident language only; no interpolation; "
          f"words with score < {args.min_score} untimed; scores are not calibrated probabilities"}
for s in result["segments"]:
    s["words"] = []
    s["alignment_status"] = ("mixed language: segment timestamps only" if s["text_scripts"] == "mixed"
                             else "segment timestamps only")
for language in sorted({s["language_hint"] for s in result["segments"]}):
    expected = ("cjk" if language in {"zh", "yue", "ja", "ko"} else
                "cyrillic" if language in {"ru", "uk", "bg", "sr", "be", "mk", "kk"} else "latin")
    eligible = [s for s in result["segments"] if s["language_hint"] == language
                and s["text_scripts"] == expected and s["language_detection"]
                and s["language_detection"][0]["language"] == language
                and s["language_detection"][0]["probability"] >= .90]
    stats = report["languages"][language] = {"eligible_segments": len(eligible), "accepted_segments": 0,
                                             "timed_words": 0, "failed_ids": []}
    if not eligible:
        continue
    try:
        align_model, metadata = whisperx.load_align_model(language_code=language, device="cuda")
    except Exception as error:  # no aligner for this language: keep segment times
        stats["error"] = f"{type(error).__name__}: {error}"[:300]
        continue
    stats["model"] = metadata.get("type")
    for s in eligible:
        try:
            words = whisperx.align([s], align_model, metadata, audio, "cuda",
                                   interpolate_method="ignore")["word_segments"]
        except Exception as error:
            stats["failed_ids"].append(s["id"])
            s["alignment_status"] = "alignment failed: segment timestamps preserved"
            continue
        scores = [w["score"] for w in words if isinstance(w.get("score"), (int, float))]
        if not scores or statistics.median(scores) < args.min_score:
            s["alignment_status"] = "low alignment confidence: segment timestamps only"
            continue
        kept = []
        for w in map(dict, words):
            a, b = w.get("start"), w.get("end")
            if not (isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isfinite(a)
                    and math.isfinite(b) and s["start"] - .02 <= a < b <= s["end"] + .02
                    and w.get("score", 0) >= args.min_score):
                w.pop("start", None)
                w.pop("end", None)
            kept.append(w)
        timed = sum("start" in w for w in kept)
        if timed:
            s["words"] = kept
            s["alignment_status"] = ("word timestamps available" if timed == len(kept)
                                     else "partial word timestamps; uncertain words untimed")
            stats["accepted_segments"] += 1
            stats["timed_words"] += timed
    del align_model
    gc.collect()
    torch.cuda.empty_cache()
report["runtime_seconds"] = time.perf_counter() - started
result["alignment"] = report
assert [s["text"] for s in result["segments"]] == texts
export(result, out)  # transcript is complete before the optional gated step
print("ALIGNED", report["languages"], flush=True)

if not args.no_diarize:
    began = time.perf_counter()
    from huggingface_hub import get_token
    from whisperx.diarize import DiarizationPipeline, assign_word_speakers
    name = "pyannote/speaker-diarization-community-1"
    token = os.environ.get("HF_TOKEN") or get_token()
    diarization = {"model": name, "token_available": bool(token), "speaker_count_forced": args.speakers}
    try:
        pipeline = DiarizationPipeline(model_name=name, token=token, device="cuda")
        turns = pipeline(audio, **({"num_speakers": args.speakers} if args.speakers else {}))
        turns[["start", "end", "speaker"]].to_csv(out / "intermediate/speaker-turns.csv", index=False)
        labeled = assign_word_speakers(turns, copy.deepcopy(result))
        assert [s["text"] for s in labeled["segments"]] == texts
        result = labeled
        diarization.update(status="succeeded", speakers=sorted(set(turns["speaker"])))
    except Exception as error:
        diarization.update(status="unavailable", error_type=type(error).__name__,
                           http_status=getattr(getattr(error, "response", None), "status_code", None),
                           setup_required=[f"Accept the conditions at https://huggingface.co/{name}",
                                           "Use a read token with access to that gated repo (HF_TOKEN or `hf auth login`)",
                                           "Rerun align_diarize.py; the transcript is already saved"])
    diarization["runtime_seconds"] = time.perf_counter() - began
    result["diarization"] = diarization
    save_json(out / "logs/diarization-result.json", diarization)
    print("DIARIZATION", diarization["status"], diarization.get("error_type", ""), flush=True)
export(result, out)
print("FINAL_EXPORTS_SAVED")
