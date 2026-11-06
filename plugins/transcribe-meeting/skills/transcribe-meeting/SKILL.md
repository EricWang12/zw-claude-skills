---
name: transcribe-meeting
description: Transcribe a local meeting recording (m4a, mp3, wav, mp4, any audio/video file) on this machine's GPU with WhisperX large-v3, keeping the original language (including Chinese/English code-switching), then write a source-linked summary where every point opens its exact original passage and plays that clip at its original HH:MM:SS position, filed as a page ("meeting name - date time") in the user's single private meeting-library artifact. Use whenever the user gives a path to a recording, lecture, interview, call or voice memo and wants it transcribed, turned into subtitles/SRT, summarized, turned into minutes/notes/action items, or wants to "know what was said" — even if they never say "transcribe". Transcription stays local; no cloud ASR.
---

# Transcribe meeting

Input: a path to a recording. Output, in `<recording dir>/<recording stem>-transcript/`
unless the user names another folder:

| File | What it is |
|---|---|
| `transcript.txt` / `transcript_timestamped.txt` / `transcript.srt` / `transcript.json` | Original-language transcript. The timestamped text carries segment IDs (`#42`) |
| `review-needed.tsv` | Passages a person should listen to, and why |
| `run-info.txt`, `logs/verification.json` | Settings, versions, runtimes, checks passed, limits |
| `meeting-summary.html` / `.txt` | Summary: each claim links to its source passage + clip (skip if the user wants only a transcript) |
| Library artifact **Zhaoning Meeting Notes** | The same summary as a page `<meeting name> - <YYYY-MM-DD HH:MM>`, listed on the library's home page |

The scripts are in `scripts/` next to this file (call that folder `$S`). Each stage
saves its results before the next starts, so a failure never loses earlier work.

## Rules that protect the user

- **The recording is never modified.** Outputs go in their own folder; `verify.py` re-hashes it.
- **The transcript is what was said, in the language it was said.** Do not translate, fix
  terms, or polish. A cleaned-up version, if the user asks for one, is a separate derived
  file that keeps the raw text.
- **Never invent.** No speaker names, speaker counts, owners or dates that the audio
  does not state. If diarization runs, labels stay `SPEAKER_00`, `SPEAKER_01`.
- **Data stays private.** Transcription runs locally: no cloud ASR or LLM transcription
  service. The summary pages embed meeting audio, and they go only into the user's own
  private library artifact. Never share that artifact, make it public, or push its pages to git.
- **Times are `HH:MM:SS` on the original recording's clock.** `01:21` is ambiguous.
- **Report honestly.** Automated checks do not prove every word is right. Say what was
  checked, what was not, and point to `review-needed.tsv`.

## Workflow

### 1. Environment and GPU (first use on a machine sets everything up)

```bash
bash $S/setup.sh                 # prints SETUP_READY venv=<path>
source $S/env.sh <that path>     # picks the GPU with the most free memory; ffmpeg on PATH
```

`setup.sh` is safe to run every time. On a machine that has used this skill before it
returns in seconds. On the first use it installs the WhisperX env in
`~/.local/share/transcribe-meeting/venv`, downloads large-v3, the VAD and the zh/en
aligners (about 14 GB; about 3 min on a fast network; run it in the background and tell the user it is a
one-time setup), and runs the model once on the GPU. If ffmpeg is missing, it fetches a
static build into its own folder rather than using apt. If the home disk has less than
20 GB free, pass a path on a bigger disk (`bash $S/setup.sh /big/disk/venv`) and set
`TRANSCRIBE_MEETING_VENV` to it for later runs. If it fails, use **references/setup.md**.

Do not touch drivers, system CUDA, or other people's jobs or environments.

### 2. Resolve and prepare the input

Find the real, completed file: an upload or sync in progress is not the recording. Then:

```bash
python3 $S/prepare.py "/path/to/recording.m4a" --out "$OUT"
```

It refuses partial files, records the SHA256 and ffprobe data, and decodes a mono 16 kHz
`meeting.wav`. If it warns that the container and decoded durations differ, inspect the
last frames before you claim full coverage. Do not pad or truncate.

### 3. Gate: real inference on a representative sample

Choose 3–5 minutes of real conversation (skip the silent start). If languages switch,
include a switch. Decode the same sample with each plausible language hint:

```bash
python $S/sample_check.py --out "$OUT" --start 60 --duration 240 --hints auto,zh,en
```

The run must end with `GATE_PASSED`. If torch works but Whisper inference fails, the
gate has failed: fix the environment before you do the full run. Read
`sample-comparison.tsv` side by side and choose `--languages` and `--default` for
the full run from what the outputs actually contain, not from the detected-language
probability. Read **references/languages-and-review.md** before deciding on mixed-language
speech: a wrong hint can translate speech silently or drop whole passages.

### 4. Full transcription

```bash
python $S/transcribe.py --out "$OUT" --languages zh,en --default zh > "$OUT/logs/transcribe.log" 2>&1
```

Run it in the background. Measured on a 2 h 37 min recording on one RTX PRO 6000:
ASR 210 s (VAD 74 s, language probes 43 s, decoding 59 s); later steps took review 68 s,
alignment 55 s and the summary build with player test under 1 min. It saves a checkpoint after every
batch. To resume after a crash, run the same command again. If CUDA runs out of memory, it
halves the batch size. Do not switch to a smaller model as a first response.

### 5. Review suspicious passages

```bash
python $S/review.py --out "$OUT"
```

This command finds repetition loops, segments with very little text for the speech they
contain, and quiet speech in gaps. It decodes each candidate again from the audio and
proposes `accept` or `reject`. Open `intermediate/review-candidates.json` and read every
candidate: original text, new text and context text. Change `decision` when you disagree
with the proposal. Reject text that looks like a silence hallucination (outro phrases,
subtitle credits, words unrelated to the conversation). Then run:

```bash
python $S/apply_review.py --out "$OUT"
```

### 6. Optional word timing and speakers

```bash
python $S/align_diarize.py --out "$OUT"            # add --no-diarize to skip speakers
```

Alignment is applied only to confident single-language segments. Mixed-language segments
keep their segment times. Diarization needs a gated Hugging Face model. If access fails
(HTTP 403), the transcript is still delivered. Tell the user the exact setup step from
`logs/diarization-result.json`. Never print a token.

### 7. Verify

```bash
python3 $S/verify.py --out "$OUT"
```

The command must exit 0. Also read `logs/beginning-middle-end.txt` and skim
`review-needed.tsv`: the structural checks cannot detect text that is fluent but wrong.

### 8. Summary page, filed in the meeting library artifact (skip if not wanted)

Read the **whole** `transcript_timestamped.txt`. For a very long meeting, read it in parts
and do not skim. Then write `$OUT/summary.json` as described in **references/summary.md**.
That reference gives the schema, how to separate decisions from proposals and open
questions, and the writing style. Write the summary in the meeting's main language unless
the user asks for a different one.

All meetings live in **one** private artifact, **Zhaoning Meeting Notes**: a home page
that lists every meeting, and one page per meeting named **`<meeting name> - <YYYY-MM-DD HH:MM>`**.
- **The meeting name is the user's name when they give one.** Look for it anywhere in the
  request ("call it Weekly sync", "this is the lab meeting with Prof. Gao", "name it 周会"),
  and pass it to `--name` exactly as written, in any language. Only when the user gives no
  name, use the recording's file name without its extension (`Nixon Rd 5`), and say in
  the reply that they can rename it.
- To rename a filed meeting, run step 8 again with the new `--name`. The page of the same
  recording (matched by its SHA256) is replaced. The build lists the old page under
  `unpublish_files`.
- The time is when recording started, in the user's time zone (`--tz`; America/Detroit
  unless the user says otherwise). It comes from `prepare.json`'s `recorded_utc`. If that
  value fell back to the file's modification time, say so, or ask the user.

Steps:

1. `list` your artifacts (`limit: 200`) and take the one titled exactly `Zhaoning Meeting
   Notes`. It must be your own.
2. Staging folder: `STAGING=<scratchpad>/meeting-library` (empty). Artifact sources must be
   in the scratchpad or the working directory.
   - **Found:** `read` the artifact (the tool refuses updates to an unread artifact). Then
     `read` it with `path: "meetings.json"` and `out_dir: STAGING`, so the manifest of
     earlier meetings lands at `STAGING/meetings.json`.
   - **Not found:** leave STAGING empty. This run creates the library.
3. Build. This writes the local copy `$OUT/meeting-summary.html`, the library page
   `STAGING/meetings/<slug>.html`, the updated `meetings.json` and `index.html`:
   ```bash
   python3 $S/build_summary.py --out "$OUT" --name "Nixon Rd 5" --tz America/Detroit --library "$STAGING"
   node $S/verify_player.cjs "$STAGING"/meetings/<slug>.html   # sandboxed-viewer playback test
   ```
   If the player test cannot run (no Node or Chromium), say so. Do not claim that playback
   was verified. The test's report files stay out of the publish.
4. Publish with `file_path: STAGING/index.html`, `root: STAGING`, and
   `files: {"meetings.json": "meetings.json", "meetings/<slug>.html": "meetings/<slug>.html"}`,
   the two `publish_files` paths that the build printed. Map each path in
   `unpublish_files` to `null` in the same `files` map. When the library was found, add its `url`. The other meetings'
   pages stay published as they are. When the library is new, add `icon: "notes"` and a
   one-sentence description. Rebuilding the same meeting (same name and time) replaces
   its page.
5. `list` the artifact's files (`scope: "files"`) once to confirm the new page is there.

Pages embed the meeting's audio clips (about 8 MB for a 2.5-hour meeting with 66 cited
passages). One artifact version holds at most 256 MB, so tell the user when the
library's pages in `meetings.json` (`bytes`) approach that limit. If this session has
no Artifact tool, deliver `$OUT/meeting-summary.html` as a local file.

### 9. Deliver

Reply briefly. Include:
- the library link, and the meeting page's name;
- the output folder and its files;
- the measured runtimes;
- the language policy you chose and why;
- the alignment and speaker status;
- the number of review rows, and what still needs listening;
- the 2–3 most important outcomes of the meeting.

## If something goes wrong

| Symptom | Likely cause → action |
|---|---|
| `GATE_PASSED` missing, cuDNN/cuBLAS errors | CUDA wheels not on the library path → `source env.sh` again; see references/setup.md |
| A hint's output has none of the expected script, or is shorter | That hint translated or dropped speech → do not use it as the default |
| The same phrase repeats many times | ASR loop → `review.py` decodes it again with `no_repeat_ngram_size=5` |
| Long stretch with almost no text | VAD missed quiet speech or the decoder skipped it → review candidate. Never decode with VAD off: it invents text over silence |
| `transcribe.py` says asr-raw.json exists | The raw result must not change → use a new `--out` to start over |
| Diarization 403 | The user must accept the model's conditions and give a read token; it does not block the transcript |
