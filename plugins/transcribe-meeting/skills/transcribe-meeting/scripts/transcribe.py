"""Full-recording ASR: VAD windows -> per-window language hint -> batched Whisper.

Usage: python transcribe.py --out DIR --languages zh,en --default zh [--vad-onset 0.3]

* All timestamps stay on the original recording clock (VAD runs on the full WAV).
* Language policy: a window gets a non-default hint only when the whole window and
  both halves all detect that same allowed language at >= --min-prob. Otherwise it
  gets --default (choose it from sample_check.py: the hint that kept mixed speech
  as spoken, without translating or dropping passages). Audio is never cut by language.
* Checkpoints after every batch; rerun the same command to resume.
* Halves the batch size on CUDA OOM before anything else.
Writes intermediate/asr-raw.json (immutable afterwards) and the transcript exports.
"""
import argparse
import gc
import time
from datetime import datetime, timezone
from pathlib import Path

import torch
import whisperx
from faster_whisper.tokenizer import Tokenizer

from mt import SR, export, load, save_json, scripts

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True)
parser.add_argument("--languages", required=True, help="comma list of languages spoken, e.g. zh,en or en")
parser.add_argument("--default", help="hint for mixed/uncertain windows (default: first language)")
parser.add_argument("--min-prob", type=float, default=0.90)
parser.add_argument("--vad-onset", type=float, default=0.3)
parser.add_argument("--batch-size", type=int, default=8)
parser.add_argument("--model", default="large-v3")
args = parser.parse_args()
out = Path(args.out)
languages = args.languages.split(",")
default = args.default or languages[0]
assert default in languages
raw_path, checkpoint_path = out / "intermediate/asr-raw.json", out / "intermediate/asr-checkpoint.json"
if raw_path.exists():
    raise SystemExit(f"{raw_path} exists and is immutable. Use a new --out to start over.")

started = time.perf_counter()
torch.set_num_threads(8)
audio = whisperx.load_audio(str(out / "meeting.wav"))
duration = len(audio) / SR
model = whisperx.load_model(args.model, "cuda", compute_type="float16", vad_method="silero",
                            vad_options={"vad_onset": args.vad_onset}, threads=8)
assert model.model.model.device == "cuda"
settings = {"model": args.model, "languages": languages, "default_language": default,
            "min_prob": args.min_prob, "vad_onset": args.vad_onset}

# 1. Speech windows over the complete recording.
if checkpoint_path.exists() and load(checkpoint_path)["settings"] == settings:
    result = load(checkpoint_path)
    chunks, windows = load(out / "intermediate/vad-chunks.json"), load(out / "intermediate/language-windows.json")
    print("RESUMING at chunk", result["completed_chunks"], flush=True)
else:
    began = time.perf_counter()
    speech = model.vad_model({"waveform": audio, "sample_rate": SR})
    save_json(out / "intermediate/vad-speech.json", [{"start": s.start, "end": s.end} for s in speech])
    chunks = model.vad_model.merge_chunks(speech, 30, onset=args.vad_onset, offset=0.363)
    assert chunks, "VAD found no speech"
    assert all(0 <= c["start"] < c["end"] <= duration + .001 and c["end"] - c["start"] <= 30.001 for c in chunks)
    save_json(out / "intermediate/vad-chunks.json", chunks)
    vad_seconds = time.perf_counter() - began
    print("VAD", len(chunks), "windows over", round(duration, 3), "s", flush=True)

    # 2. Language evidence per window and its halves (no splitting of the decoded audio).
    began = time.perf_counter()
    windows = []
    for i, chunk in enumerate(chunks):
        clip = audio[int(chunk["start"] * SR):int(chunk["end"] * SR)]
        probes = [clip] + ([clip[:len(clip) // 2], clip[len(clip) // 2:]] if len(clip) >= 12 * SR else [])
        detections = []
        for probe in probes:
            language, probability, ranked = model.model.detect_language(audio=probe)
            detections.append({"language": language, "probability": float(probability),
                               "top3": [[l, float(p)] for l, p in ranked[:3]]})
        agreed = {d["language"] for d in detections}
        hint = (detections[0]["language"] if len(agreed) == 1 and detections[0]["language"] in languages
                and all(d["probability"] >= args.min_prob for d in detections) else default)
        windows.append({"start": chunk["start"], "end": chunk["end"], "hint": hint, "probes": detections})
        if (i + 1) % 50 == 0 or i + 1 == len(chunks):
            print("LANGUAGE", i + 1, "/", len(chunks), flush=True)
    save_json(out / "intermediate/language-windows.json", windows)
    integrity = load(out / "logs/source-integrity.json")
    result = {"source_file": integrity["path"], "source_sha256": integrity["sha256"],
              "audio_duration_seconds": duration, "processed_audio_seconds": duration,
              "task": "transcribe", "device": "cuda", "compute_type": "float16", "settings": settings,
              "language_policy": f"{default} for mixed/uncertain windows; another of {languages} only when "
                                 f"whole-window and half-window probes all agree at >= {args.min_prob}",
              "vad": {"method": "silero", "onset": args.vad_onset, "maximum_chunk_seconds": 30},
              "alignment": "not attempted", "diarization": "not attempted", "segments": [],
              "completed_chunks": 0, "started_utc": datetime.now(timezone.utc).isoformat(),
              "runtime_seconds": {"vad": vad_seconds, "language_probes": time.perf_counter() - began}}

# 3. Batched decoding; consecutive windows with the same hint share a batch.
began = time.perf_counter()
batch_size = args.batch_size
index = result["completed_chunks"]
while index < len(chunks):
    hint = windows[index]["hint"]
    stop = index + 1
    while stop < len(chunks) and stop - index < batch_size and windows[stop]["hint"] == hint:
        stop += 1
    batch = chunks[index:stop]
    model.tokenizer = Tokenizer(model.model.hf_tokenizer, True, task="transcribe", language=hint)
    inputs = ({"inputs": audio[int(c["start"] * SR):int(c["end"] * SR)]} for c in batch)
    try:
        outputs = list(model(inputs, batch_size=batch_size, num_workers=0))
    except RuntimeError as error:
        if "out of memory" not in str(error).lower() or batch_size == 1:
            raise
        batch_size = max(1, batch_size // 2)
        gc.collect()
        torch.cuda.empty_cache()
        print("OOM_RETRY_BATCH_SIZE", batch_size, flush=True)
        continue
    assert len(outputs) == len(batch)
    for offset, (chunk, output) in enumerate(zip(batch, outputs)):
        text, score = output["text"], output["avg_logprob"]
        text = text[0] if isinstance(text, list) else text
        score = score[0] if isinstance(score, list) else score
        result["segments"].append({"id": index + offset, "start": chunk["start"], "end": chunk["end"],
                                   "text": text, "avg_logprob": float(score), "language_hint": hint,
                                   "text_scripts": scripts(text),
                                   "language_detection": windows[index + offset]["probes"],
                                   "alignment_status": "segment timestamps only", "words": []})
    index = result["completed_chunks"] = stop
    save_json(checkpoint_path, result)
    print("ASR", index, "/", len(chunks), "through", round(batch[-1]["end"], 1), "s", flush=True)

result["runtime_seconds"]["transcription"] = time.perf_counter() - began
result["runtime_seconds"]["asr_script_wall"] = time.perf_counter() - started
result["final_batch_size"] = batch_size
result["finished_utc"] = datetime.now(timezone.utc).isoformat()
save_json(raw_path, result)
export(result, out)
print("ASR_SAVED", len(result["segments"]), "segments", result["runtime_seconds"], flush=True)
