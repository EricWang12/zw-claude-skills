"""Apply the decisions in intermediate/review-candidates.json.

Usage: python apply_review.py --out DIR

accept on a loop/sparse candidate  -> replace that segment's text, keep the old text in "redecode"
accept on a gap candidate          -> insert a new segment with ID gap_<ms>
reject                              -> keep the original; gap candidates stay listed for listening
Always starts from the immutable asr-raw.json, so it can be rerun after editing decisions.
Writes intermediate/asr-reviewed.json, redecode-comparison.tsv and fresh exports
(rerun align_diarize.py afterwards: changed text invalidates old word timings).
"""
import argparse
import csv
from pathlib import Path

import re

from mt import SPAM, export, load, save_json, scripts

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True)
args = parser.parse_args()
out = Path(args.out)
result = load(out / "intermediate/asr-raw.json")
candidates = load(out / "intermediate/review-candidates.json")
by_id = {s["id"]: s for s in result["segments"]}
accepted, excluded = [], []
for c in candidates:
    assert c["decision"] in ("accept", "reject"), c["id"]
    if c["decision"] == "reject":
        text = c["candidate_text"]  # worth a listen unless empty, unchanged or a known hallucination
        if len(re.findall(r"\w", text)) >= 2 and not SPAM.search(text) and text != c["original_text"]:
            excluded.append({k: c[k] for k in ["id", "kind", "start", "end", "reason", "candidate_text"]})
        continue
    provenance = {"kind": c["kind"], "reason": c["reason"], "method": c["method"],
                  "initial_text": c["original_text"], "context_agreement": c["context_agreement"],
                  "suggestion": c["suggestion"], "candidates_file": "intermediate/review-candidates.json"}
    pieces = c["candidate_pieces"]
    if c["kind"] == "gap":
        segment = {"id": c["id"], "start": c["start"], "end": c["end"],
                   "language_hint": c["language_hint"], "language_detection": [],
                   "alignment_status": "recovered quiet speech: segment timestamps only"}
        result["segments"].append(segment)
    else:
        segment = by_id[c["id"]]
    segment.update(text=c["candidate_text"], text_scripts=scripts(c["candidate_text"]), words=[],
                   avg_logprob=sum(p["avg_logprob"] for p in pieces) / max(len(pieces), 1),
                   redecode=provenance)
    accepted.append(c["id"])
result["segments"].sort(key=lambda s: s["start"])
result["review"] = {"accepted_ids": accepted, "rejected_candidates": excluded,
                    "manual_lexical_substitutions": 0,
                    "note": "Accepted texts are fresh local decodes; original texts kept in each segment's redecode field."}
save_json(out / "intermediate/asr-reviewed.json", result)
export(result, out)
with (out / "redecode-comparison.tsv").open("w", newline="") as file:
    writer = csv.writer(file, delimiter="\t")
    writer.writerow(["id", "kind", "decision", "start", "end", "initial_text", "candidate_text"])
    for c in candidates:
        writer.writerow([c["id"], c["kind"], c["decision"], round(c["start"], 3), round(c["end"], 3),
                         c["original_text"], c["candidate_text"]])
print("REVIEWED", len(result["segments"]), "segments; accepted", accepted, "; rejected but listed", len(excluded))
