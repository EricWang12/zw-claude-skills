# Language hints and review judgment

These lessons come from a real 2 h 37 min Chinese/English research meeting with
mid-sentence code-switching. They generalize, but the exact thresholds were tuned on that
meeting. Check them against your own sample.

## Choosing the hint from the sample

`sample_check.py` decodes the same audio once for each hint. Compare the columns in
`sample-comparison.tsv`:

| Look for | Meaning |
|---|---|
| A hint's column has no characters of a language you can hear | That hint **translated** the speech, even with `task=transcribe` |
| A hint's column is shorter, or has punctuation-only rows where others have text | That hint **dropped** speech (one 27 s passage became "。") |
| Technical terms in the second language survive under the main-language hint | Good: Whisper keeps embedded terms in Latin script |
| Two hints give the same text | Either hint works. Choose the main language as `--default` |

What happened in the reference meeting: auto-detect said `zh` at 0.94 and matched the
`zh` hint. The `en` hint translated the Chinese and dropped a passage. The resulting policy:
`--languages zh,en --default zh`. A window becomes `en` only when the whole window and both
halves are detected as English at ≥ 0.90. In that meeting all 315 windows chose `zh`, and
the English terms were kept as spoken.

This rule fits that meeting's language pair. Do not make every non-English recording
default to Chinese. Choose the default from your own sample:

- Monolingual meeting: `--languages xx` (one language; probes are still recorded).
- Two languages with code-switching: the default is the language whose hint kept **both**
  languages as spoken in the sample. That is usually the language of the sentence
  structure, not the language of the borrowed terms.
- Separate long passages in different languages (e.g. a talk followed by a Q&A in
  another language): list both languages. The probe rule switches whole windows only on
  confident evidence. The audio is never cut inside a sentence.

Do not trust metadata alone. The WhisperX 3.8.6 CLI logged `zh` but saved `language=en`
(its default alignment language) in `--no_align` output. The scripts use the API and
record each window's own detection.

## VAD

- The default onset of 0.5 missed quiet speech. 0.3 recovered it with no obvious false
  speech. The scripts use 0.3.
- 0.15 is a diagnostic level: `review.py` uses it only in gaps, to find candidates. It also
  finds noise.
- **Never decode with VAD off.** Over a pause, the model invented fluent text unrelated to
  the meeting.
- Coverage has two parts. One: every sample was processed (`verify.py` checks this). Two:
  no speech was missed. The gap audit helps with the second part but does not prove it.

## Judging review candidates

`review.py` proposes a decision. Your job is to read each candidate and decide.

| Kind | Accept when | Reject when |
|---|---|---|
| loop | The new text reads naturally and keeps the content before and after the loop | The new text is empty, or it repeats the loop with different wording |
| sparse | The new text is clearly longer, fits the neighbouring segments, and the context decode contains the same words | The new text is canned or off-topic, or the context decode disagrees |
| gap | The context decode contains the same words (`context_agreement` ≥ 0.6) and the text fits the conversation | Outro or subtitle phrases, single interjections, or no agreement. These stay listed for listening, not inserted |

Real repetition ("这个这个这个", "no no no") is a disfluency, not a loop. Keep it. A loop
repeats a long phrase many times, often with a high score, and the score does not reveal
it. Two decodes that agree corroborate each other, but neither is ground truth. Uncertain
names and terms still need someone to listen.

`apply_review.py` always starts from the immutable `asr-raw.json`. Rerunning it after
you edit decisions is therefore safe. Then rerun `align_diarize.py` and `verify.py`,
because a changed text invalidates its old word timings.

## External chunking (only if ever needed)

The scripts run VAD on the full WAV, so every timestamp is already on the original
clock. If you must split the file (e.g. memory limits on a very long recording), record
each chunk's original offset. Add that offset to every segment and word time, and
reconcile overlapping boundaries so that no text is duplicated or dropped.
