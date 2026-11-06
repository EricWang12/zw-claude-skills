# transcribe-meeting

Give it a path to a recording and ask for a transcript, a summary, or both. Transcription
runs on your GPU. Only the summary page is published, into your own private library artifact.

```
recording.m4a ─► prepare ─► GPU gate on a 4-min sample ─► full ASR ─► review ─► align / speakers ─► verify
   (hash kept)    (16 kHz WAV)  (compare language hints)    (checkpoints) (loops, gaps)  (optional)        │
                                                                                                          ▼
        Zhaoning Meeting Notes (one private artifact) ◄─ build ◄─ summary.json (every point cites segment IDs)
          ├─ home: every meeting, newest first
          └─ "Nixon Rd 5 - 2026-11-04 11:08": click a point → its original passage + clip at the recording's HH:MM:SS
```

| You get | |
|---|---|
| `transcript.{txt,srt,json}`, `transcript_timestamped.txt` | Original language, no translation or "fixing"; segment IDs in the timestamped text |
| `review-needed.tsv` | Passages to listen to: loops, redecodes, quiet speech it was unsure about |
| A page in **Zhaoning Meeting Notes** | `<meeting name> - <date time>`: overview → decisions / actions / proposals / open questions → topics. Every row links to its source passage with in-page playback. Local copy: `meeting-summary.html` |
| `run-info.txt` | Model, language policy, versions, runtimes, checks passed, limits |

## Install

```
/plugin marketplace add EricWang12/zw-claude-skills
/plugin install transcribe-meeting@zw-claude-skills
```

## What you say

> transcribe ~/recordings/standup-1104.m4a

> here's yesterday's meeting /data/audio/Nixon Rd 5.m4a — summarize what we decided, with links back to the audio

> transcribe /data/audio/0611.m4a, call it "Lab meeting with Prof. Gao"

> make subtitles for lecture.mp4, it switches between Chinese and English

## Needs

An NVIDIA GPU and Python 3.11+. The first run on a machine sets itself up once
(`scripts/setup.sh`, about 3 min): a WhisperX environment (about 8 GB), the models (about
6 GB), a static ffmpeg if the system has none, then one warm-up run on the GPU. Node and a headless Chromium are
needed only for the summary's playback test. Speaker labels need access to a gated
Hugging Face model; without that access the transcript still comes out, just without
speakers.

Measured: a 2 h 37 min Chinese/English meeting took 218 s of ASR on one RTX PRO 6000.
