# Source-linked summary

The reader should understand the meeting in two minutes, and should be able to check
any sentence by clicking it and hearing the passage it came from. Two failures matter
most: a claim that cannot be traced to the audio, and a suggestion presented as a decision.

## summary.json

```json
{
  "lang": "en",
  "title": "Beta launch scope and the sync bug",
  "overview": [
    {"text": "Bottom line in one sentence: ship the beta without offline mode; fix sync first.", "sources": [88, 91]},
    {"text": "What was explicitly NOT decided: the public launch date.", "sources": [140]}
  ],
  "outcomes": [
    {"kind": "decided",  "text": "Offline mode moves out of the beta.", "sources": [88, 89]},
    {"kind": "action",   "text": "Reproduce the sync bug on the two reported devices.", "sources": [102]},
    {"kind": "proposal", "text": "Run a one-week internal dogfood before the beta.", "sources": [115, 116]},
    {"kind": "open",     "text": "Public launch date; whether pricing changes with the beta.", "sources": [140, 142]}
  ],
  "topics": [
    {"title": "Is the sync bug a blocker?",
     "finding": "Yes for the beta: it loses user edits, so it outranks every new feature.",
     "sources": [60, 64],
     "rows": [
       {"label": "Observed", "text": "Edits made on two devices within a minute can overwrite each other.", "sources": [57, 58]},
       {"label": "Concern",  "text": "Testers will lose work and stop trusting the app.", "sources": [61]},
       {"label": "Landed",   "text": "Fix before beta; no new feature work until it is reproduced.", "sources": [64, 66]}
     ]},
    {"title": "What this meeting settled, and what is still open",
     "finding": "Beta scope is fixed; the launch date waits for the sync fix.",
     "sources": [138, 141],
     "rows": [
       {"label": "Settled",  "text": "Beta ships without offline mode.", "sources": [138]},
       {"label": "Next",     "text": "Reproduce the sync bug, then meet again on the date.", "sources": [139]},
       {"label": "Open",     "text": "Public launch date; pricing.", "sources": [140, 142]}
     ]}
  ],
  "notes": ["'Next sprint' is a relative time from the recording."]
}
```

- `sources` are segment IDs from `transcript.json` (the `#N` in `transcript_timestamped.txt`).
  Recovered gaps have string IDs like `gap_291774`. Every overview line, outcome, topic and
  row needs at least one source; `build_summary.py` refuses unknown IDs or empty lists.
- `lang`: `zh` gives Chinese UI labels; anything else gives English. Match the summary language.
- `outcomes.kind`: `decided` (explicitly agreed), `action` (someone will do something —
  name an owner or date only if spoken), `proposal` (an idea, suggestion or experiment
  that was raised, not agreed), `open` (discussed, unresolved). When unsure between
  decided and proposal, it is a proposal.

## Writing it

1. Read the whole transcript first; note IDs as you go. Meetings circle back — the final
   position on a topic is often near the end (in the meeting this skill was built from, the
   conclusions came in the last 20 minutes of 2 h 37 min).
2. Pick 4–8 topics by what was argued about, not by chronology. Title each as the
   question or tension (e.g. "Offline mode: wanted, but not for the beta"), then a one-line
   finding that answers it.
   **The last topic is always the meeting's closing part**, titled "What this meeting
   settled, and what is still open" (Chinese: "这次明确了什么，什么仍然未决定"). It follows
   the end of the recording, where people wrap up, and serves as the summary of the summary.
   Keep it even when `outcomes` repeat some of its points: the user wants it.
3. Rows are 3–6 per topic with short labels that show the argument's shape: what was
   observed → the concern → what was proposed → where it landed / what remains open.
4. Cite the passage where the point is actually made, usually 1–3 IDs. A row citing ten
   segments is not checkable; a general link to the transcript is not a citation.
5. Write in the meeting's language, keeping technical terms as spoken (code-switched
   terms stay in their original script). Compress, but do not upgrade: "we could try X" is a proposal; "X is
   wrong" from one person in a disagreement is that person's view, not a finding.
6. Never invent speaker names, owners, dates or counts. Without diarization, write
   "one participant suggested…" or describe the positions, not the people.
7. Relative times ("tomorrow", "next week") stay relative and get a note.
8. Do not paste the transcript into the summary — the user rejected appending it.
   The source panels show the passage on demand.

Before building, reread each outcome against its cited passage and ask: would the people
in the meeting agree this was decided / proposed / left open?

## What the builder and player do (and why)

- Each cited segment gets a clip `[start − 1 s, end + 1 s]` (`clip_start`/`clip_end`,
  stored separately from the segment's own times) as mono 16 kHz 24 kbps MP3, embedded as
  inert base64 text. A 2.6 h meeting with 66 cited passages produced an 8 MB page.
- The display always shows the **original recording position**:
  `displayed = clip_start + saved offset + (AudioContext.currentTime − playback start)`.
- Why Web Audio and not `<audio>`: a relative `meeting.wav` did not resolve in an inline
  preview, and `data:` URLs in `<audio>` failed with error 4 under a preview's media
  policy. Decoding bytes with `decodeAudioData` and playing an `AudioBufferSourceNode`
  after a click needs no media URL and no network.
- Buffer source nodes are one-shot: pause stops the node and stores the offset; resume
  and seek create a new node. Closing or switching passages stops playback. Errors are
  shown. The local copy has a clip download button. The library page does not, because
  the artifact sandbox blocks downloads that a page starts.
- Internal links update `location.hash` in place, because default fragment navigation
  could navigate a `srcdoc` preview away from the document.

`verify_player.cjs` loads the page in a `srcdoc` iframe with `sandbox="allow-scripts"` and
`media-src 'none'; connect-src 'none'`, checks every row has a resolvable source, then for
the first, middle and last passages checks decoded nonzero audio, a running context and
an advancing original-clock position, plus pause, seek, resume and close. It does not
prove every host preview allows Web Audio or downloads; if the user reports a failure in
their viewer, ask which viewer, and offer the local `$OUT/meeting-summary.html` opened
directly in a browser. Do not change host security settings.

To change content later, edit `summary.json`, rerun step 8 of SKILL.md (same `--name`, same
time: the page is replaced in place) and republish. The transcript files are
hash-checked and never touched.
