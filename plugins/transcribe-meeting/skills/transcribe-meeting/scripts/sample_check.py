"""GPU gate + language-hint comparison on a representative speech sample.

Usage: python sample_check.py --out DIR --start SECONDS [--duration 240] [--hints auto,zh,en]

Passing requires CUDA math AND real Whisper inference on this GPU: torch working
alone does not prove the CTranslate2 backend works. Every hint decodes the same
audio so their outputs can be compared side by side (sample-comparison.tsv).
"""
import argparse
import csv
import importlib.metadata
import json
import re
import time

import ctranslate2
import torch
import whisperx

from mt import SR, has_loop, read_wav, save_json, scripts

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True)
parser.add_argument("--start", type=float, required=True, help="sample offset in the original recording")
parser.add_argument("--duration", type=float, default=240)
parser.add_argument("--hints", default="auto", help="comma list: auto and/or language codes")
parser.add_argument("--model", default="large-v3")
parser.add_argument("--vad-onset", type=float, default=0.3)
args = parser.parse_args()

# 1. CUDA math on the selected GPU.
assert torch.cuda.is_available(), "CUDA unavailable to torch"
a = torch.randn(512, 512, device="cuda", dtype=torch.float16)
b = torch.randn(512, 512, device="cuda", dtype=torch.float16)
error = ((a @ b).float().cpu() - a.float().cpu() @ b.float().cpu()).abs().max().item()
assert error < 0.1, f"fp16 matmul error {error}"
assert "float16" in ctranslate2.get_supported_compute_types("cuda", 0), "CTranslate2 lacks CUDA float16"
machine = {"gpu": torch.cuda.get_device_name(0), "capability": torch.cuda.get_device_capability(0),
           "torch_cuda": torch.version.cuda, "cudnn": torch.backends.cudnn.version(),
           "matmul_max_abs_error": error,
           "versions": {n: importlib.metadata.version(n) for n in [
               "whisperx", "faster-whisper", "ctranslate2", "torch", "torchaudio", "transformers"]}}

# 2. Actual ASR inference, once per hint, on the same audio.
audio = read_wav(args.out, args.start, args.start + args.duration)
model = whisperx.load_model(args.model, "cuda", compute_type="float16", vad_method="silero",
                            vad_options={"vad_onset": args.vad_onset}, threads=8)
assert model.model.model.device == "cuda"
results = {}
for hint in args.hints.split(","):
    began = time.perf_counter()
    output = model.transcribe(audio, batch_size=8, language=None if hint == "auto" else hint,
                              task="transcribe")
    text = " ".join(s["text"].strip() for s in output["segments"])
    results[hint] = {
        "language_reported": output.get("language"), "seconds": time.perf_counter() - began,
        "segments": [{"start": s["start"] + args.start, "end": s["end"] + args.start,
                      "text": s["text"]} for s in output["segments"]],
        "cjk_chars": len(re.findall(r"[぀-ヿ㐀-鿿가-힯]", text)),
        "latin_words": len(re.findall(r"[A-Za-zÀ-ɏ]+", text)),
        "segments_with_loops": sum(has_loop(s["text"]) for s in output["segments"]),
        "near_empty_segments": sum(len(re.sub(r"\W", "", s["text"])) < 3 for s in output["segments"]),
        "scripts": scripts(text)}
    print(hint, {k: v for k, v in results[hint].items() if k != "segments"}, flush=True)
detected = model.detect_language(audio[:30 * SR])  # logs probability; returns the code

save_json(f"{args.out}/logs/sample-comparison.json",
          {"sample_start": args.start, "sample_duration": args.duration, "model": args.model,
           "vad_onset": args.vad_onset, "machine": machine, "auto_first_30s": detected, "hints": results})
with open(f"{args.out}/sample-comparison.tsv", "w", newline="") as file:
    writer = csv.writer(file, delimiter="\t")
    hints = list(results)
    writer.writerow(["start", "end"] + hints)
    for row in zip(*(results[h]["segments"] for h in hints)):
        writer.writerow([round(row[0]["start"], 1), round(row[0]["end"], 1)] + [s["text"].strip() for s in row])
print(json.dumps(machine, indent=2))
print("GATE_PASSED: CUDA math and real Whisper inference both ran on", machine["gpu"])
