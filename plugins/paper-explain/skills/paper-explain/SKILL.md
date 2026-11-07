---
name: paper-explain
description: Explain a research paper or tool the way this user learns best, and file it in their paper library. Given a paper link (arXiv abs/pdf, project page, OpenReview, any PDF URL) or a tool's GitHub repo or release, it downloads the PDF into the right project folder under a dated short name (2026-10-15-DexAgent), reads the whole paper, crops and inspects the authors' figures, and writes a visual page - the problem told on one running example (where each baseline breaks), a concise related-work table (what each neighbor solves, how, and how this paper differs), then big picture → stages → per-stage detail with flowcharts, the original figures explained part by part. The page is saved next to the PDF, added as a new page of the user's single library artifact (Zhaoning Paper Pile, found by its title in the artifact list and created if missing), and the library is pulled from and pushed to its GitHub repo so every machine stays in sync. Use this whenever the user shares a paper, project-page or tool-release link, or asks to read, explain, summarize, break down, TL;DR or "help me understand" a paper or tool, or to add one to the library - even if they never say "explain". A paper called temporary ("temporary", "temp", 临时) gets its own artifact and is never filed or pushed. Also use it to work from the user's starred papers (星标), such as writing related work from them.
---

# Paper explain

The user hands you a paper; you hand back understanding. Four things come out of every
run:

1. The PDF, filed in the right project folder under a short dated name.
2. An explainer page (HTML) beside it, written for this particular reader.
3. That page, published as a new page of the one library artifact, whose home page
   mirrors the folder tree.
4. The library committed and pushed to its GitHub repo, so agents on every machine work
   in the same library.

A paper the user calls temporary gets only the page, in an artifact of its own; see
"Temporary papers" below. "Starred papers" says how to gather the papers the user starred.

`SKILL_DIR` below is the directory containing this file.

## 0. Sync the library, then read the profile

The library is a git clone of **https://github.com/EricWang12/all_papers.git**, and
`<root>` below is that clone. Use the first one that exists:
1. `/nfs/turbo/coe-jungaocv/wzn/workspace/papers` (the lab machine);
2. an `all_papers/` or `papers/` folder in the working directory whose
   `git remote get-url origin` is that repo.
If neither exists, clone it into the working directory:
`git clone https://github.com/EricWang12/all_papers.git all_papers`.

Then pull, before anything else, because another machine may have added papers or
changed the profile:

```bash
git -C <root> pull --rebase --autostash
```

Read `<root>/preferences.md`, the reader's profile. It lives in the library so that
every machine shares it. It holds:
- how this user learns, including the page language;
- their projects, which decide the folder;
- the library repo and the artifact's title.

If the library has no profile yet, ask the user how they like papers explained and what
their projects are, and write the profile with the sections "How I learn", "My
projects", "Library" and "Feedback log".

The template already encodes the page structure; the profile sets the voice and the
emphasis. Where the profile and this file disagree, the profile wins, because it is the
user's newer word.

## 1. Find the paper and its metadata

Resolve the link to a PDF URL. Don't download yet: the download path depends on the
project, which you pick in step 2.

- arXiv `abs/ID`, `pdf/ID`, `html/ID` → `https://arxiv.org/pdf/IDvN`, pinned to a
  version: the one in the link, or else the latest, which the API's `<id>` shows. A
  versioned link always serves the same file, so the page records it for re-downloading.
  `https://export.arxiv.org/api/query?id_list=ID` gives the clean title, authors, date
  and abstract, and its comment field often names the venue and the project page.
- A project page → fetch it and take the paper link (arXiv or PDF).
- OpenReview `forum?id=X` → `https://openreview.net/pdf?id=X`.
- A tool's GitHub repo or release → the page explains the tool at that version. Its
  release notes or README, and the docs pages they link, are the main source; keep a
  copy in the scratchpad. The PDF is the tool's own paper, which the README or docs
  usually cite; it supplies figures and the related work. The end of step 5 says what
  changes on the page.

**Project and code links.** Papers sometimes point to stale pages, and the arXiv comment
and the PDF can disagree. Open the candidates and keep the page that links back to this
paper and, if there is one, a live code repository.

**Already in the library?** Run `grep -sl "<arXiv ID or URL>" <root>/*/artifact/*.html || true`.
If it is there, say so and point to its page instead of redoing it, unless the user asks
for a redo. A redo reuses the crops. If this machine has no copy of the PDF, download
it from the page's `paper:pdf` link.

## 2. Name it, pick the project, download

- **Short name**: the name the user calls the paper by, if they use one, such as its code
  or framework name (`RPent` for the Harness VLA paper). Otherwise the method's own
  name, usually the word before the colon in the title (`DexAgent`); a tool release adds
  its major version (`IsaacLab3`). If there is none, use 1–3 CamelCase words for the
  key idea. Letters, digits and hyphens only.
- **Name**: `<YYYY-MM-DD>-<Short>`, with today's date (the day it was retrieved, not the
  publication date). The PDF, the page and the figure folder all use this exact name.
- **Project**: compare the abstract with each project's scope line in the profile and
  pick the one the paper serves best. Write a one-line reason; it goes on the page. If
  it serves two, pick the main one and name the other in that same line. If it fits
  none, ask the user whether to use the closest project or create a new folder, and add
  a new folder to the profile's project table.
- **Download** with `curl -sSL -A "Mozilla/5.0" -o <root>/<Project>/<name>.pdf <url>` and
  confirm with `pdfinfo` that it is a real PDF. Error pages saved as `.pdf` are common.

```
<root>/
├── index.html                    library home page, generated
└── <Project>/
    ├── <name>.pdf
    └── artifact/
        ├── <name>.html           the explainer, same name as the PDF
        └── <name>/               figure crops the page shows
```

The PDF is neither published nor committed: `*.pdf` is in the library's `.gitignore`.
- arXiv PDFs often exceed the artifact's per-file limit.
- Git keeps every committed file in its history for good, so PDFs would push the repo
  past GitHub's 1 GB guideline within a few dozen papers.

Each machine keeps its own copy, and the page's `paper:pdf` link fetches the same file
again. Scratch files (notes, test renders, the paper's text) go in the session
scratchpad, never in the library, which holds only the files above.

## 3. Read the whole paper, figures included

Read the PDF with the Read tool, at most 20 pages per call. Read the main paper in full.
In the appendix, read whatever the stages need: implementation details, prompts,
extra figures, failure cases and per-baseline discussion.

Crop the authors' figures and tables:

```bash
uv run SKILL_DIR/scripts/extract_figures.py <root>/<Project>/<name>.pdf <root>/<Project>/artifact/<name>/
```

It prints one line per caption it found (`fig2 p3 [box] size caption…`). Narrow crops
are rendered at a higher dpi, so they come out at least about 900 px wide. Open every
crop you may use with the Read tool. There are two reasons:

- **Check the crop.** The cropper is a heuristic. A crop can be cut off, include stray
  body text, or miss a figure whose caption sits beside it. Fix it with
  `--box fig2=3:51,47,561,216` (page:x0,y0,x1,y1 in PDF points). Use a new ID such as
  `--box fig2-s1=3:120,47,230,216` to add a crop of a single panel for a stage.
  `--page 3` prints page 3's text blocks and images with their coordinates, and writes
  a 72-dpi render, `page3.png`, to look at. A common miss: a table captioned above with
  a figure below it on the same page, where the table crop swallows the figure. Each
  call re-detects every caption and overwrites crops with the same ID, so pass all your
  `--box` flags in one call. It never deletes anything.
- **Understand the figure.** The authors' figure is the most precise statement of
  their method, more precise than their prose and more precise than anything you
  redraw. Note what each region shows and which labels are printed in it. The page's
  "怎么读这张图" lists come from these notes.

### The project page's figures, videos and viewers

A project page often shows the method better than the PDF can: a sharper or cleaner
version of a figure, an animation of a stage, result videos side by side, an interactive
viewer. Whenever the paper has a project page, list what it shows:

```bash
uv run SKILL_DIR/scripts/page_media.py <project page URL> <scratchpad>/project-page/
```

It opens the page in headless Chromium and scrolls it, so media loaded by JavaScript
count too. It prints one line per image, video, GIF, canvas or iframe, with its size, URL
and the section heading above it, and writes a full-page screenshot, `project-page.png`.
Look at the screenshot in pieces with the Read tool to see what each item is and what the
page's own captions say. Items a viewer loads only on click (a carousel's later steps)
are missing from the list; their URLs usually follow the listed ones' pattern, so try
them with `curl -sI`.

Then, for each item, decide where it helps the reader, and take it only if it does:
- **A better version of a paper figure** (same content, higher resolution or clearer):
  use it in place of the PDF crop.
- **Related media the PDF cannot show** (an animation of a stage, a simulation rollout,
  real-vs-sim videos, a before-and-after pair): put it in the level, stage or experiment
  it illustrates, next to the authors' figure, not instead of it.
- **An interactive viewer** (3D, slider, tool-call trace): it cannot be embedded. Take
  its still frames or videos if the page serves them, and link to the section.
- **Skip** decoration, logos, near-duplicates and long galleries: one or two cases per
  point, preferably the running example.

Example (SceneRig, 2026-11-03): the PDF's Fig. 5 is an animation that plays only in
Acrobat, so the project page's real/ours/baseline videos replace it in Results; the
page's correlation plot is Fig. 4 at higher resolution and replaces the crop; its gallery
shows every baseline on the running example's scene, which made the problem section
concrete; and its recorded tool-call trace (five steps, with IoU values) became the
running example of the refinement stage.

Download what you keep into the figure folder with a `web-` prefix
(`web-gravity-ours.mp4`, `web-settlement.webp`) and open each image with the Read tool.
Keep the page light, since everything is published and committed:
- every video under about 3 MB: re-encode a larger one with
  `ffmpeg -i in.mp4 -an -vf "scale='min(960,iw)':-2" -c:v libx264 -crf 28 -movflags +faststart out.mp4`;
- the whole folder under about 15 MB;
- no audio, and only MP4, WebM, WebP, PNG, JPG, GIF or SVG.

Before publishing, delete the crops the page does not use, `figures.json` and any
`pageN.png`.

## 4. Plan before writing any HTML

Settle these first, because the page is only as clear as this plan:

- **The running example**: one concrete case taken from the paper itself, usually its
  teaser task or main demo, with real names and real values. It carries the whole
  page, the problem included.
- **The problem, on that example.** Take the baselines the paper compares against or
  builds on, at most 4 families. For each, work out what it does with this example's
  input, the exact step where it breaks and the visible symptom, and its number on this
  example (or the closest one the paper reports). The reader should see where things
  break, not a survey. Papers often report only outcomes (✗ or 0% per task); then infer
  the breaking step from the paper's own analysis, cite the section, and mark it as an
  inference. Then write the root cause in one line, and the paper's way in.
- **Related work**: existing efforts that solve a similar problem, or solve it with a
  similar approach. Take them from the paper's related-work section and wherever else
  it compares itself (intro, method, experiments, appendix); a technical report often
  has no such section, and then those passages are the source. Search beyond the paper
  only when the user asks for an in-depth search. Make 3–5 families with their method
  names, closest first:
  - the flowchart's baselines come first;
  - merge strands that share a method;
  - drop a family whose difference the paper neither states nor makes plain.
  A family goes under 同一问题 if it tackles this problem, whatever its method, and under
  相似做法 if it is this kind of method used on another problem, or on one part of this
  one. For each family, write a phrase (about 25 characters) on each of:
  - what it solves;
  - how it solves it;
  - how this paper differs: what the family lacks → what this paper does instead.
  The reader should be able to place the paper among its neighbors at a glance, so
  leave out history and citation lists.
- **Stages**: 3–6 in order, each written as input → output, plus any mechanism that
  spans several stages (a shared library, a verify-and-retry loop).
- **Coverage.** List every idea in the paper: each stage and module, each special
  mechanism (verification, retry on failure, learning over time, a key trick), and the
  main result. Make sure the example shows each one. If one case cannot show an idea,
  extend the same case ("…then a second video arrives") rather than starting a second
  example. This list becomes the Recap table. Any idea the example skips stays abstract
  for the reader.
- **Figure map**: which author figure explains which level or stage, and which table or
  plot is the evidence. Add the project-page media you kept: which point each one
  shows, and whether it replaces a PDF crop or sits beside it.
- **Experiments**: list them in the order of the paper's argument (usually its §4
  questions; an appendix experiment gets its own entry only when the main text leans on
  it, otherwise it goes into the entry it supports). For each: the question it answers,
  its table or plot, what it shows and against what (higher success, less time, more
  robust), the metric with the paper's own definition of success, and how it was run:
  where, which objects or tasks, trials or seeds, how each baseline was run, and anything
  that favours one side. Note what the paper leaves unsaid.

## 5. Write the page

Copy `SKILL_DIR/assets/paper-template.html` to `<root>/<Project>/artifact/<name>.html`
and fill it. The template fixes the section order and the look, and it already meets
the Artifact page contract, both themes and phone width. Fill it in; do not redesign
it. If the Artifact tool asks you to load the artifact-design skill or run a quickstart
first, do that, then still use the template: where their advice differs from it, the
template wins. Two things in the template look wrong but are deliberate:
- It has a doctype and loads Mermaid itself, because pages other than the library home
  are served without the artifact skeleton.
- It reads `class='ex'` inside quoted chart labels correctly.

- **Language**: follow the profile.
- **Concise.** Bullets of one line, no paragraphs. Get coverage from the levels, not from
  longer text.
- **The problem section** opens with the example in the amber box. Then a flowchart
  with one lane per baseline family, starting from the example's input and ending at the
  `:::gap` node where it breaks, with the symptom and its number. Under it go a note on
  any breaking step you inferred, then the one-line root cause and the paper's way in.
  The related-work table closes the section: rows grouped under 同一问题 and 相似做法,
  columns 解决什么 / 怎么解决 / 和本文的区别. The note under the table names the sections
  the rows come from and says whether you searched beyond them. Big picture follows
  directly.
- **A flowchart at every level.** Write Mermaid inside `<div class="flow"><pre>…</pre></div>`.
  Put a short name on the first line of each node and the example's value on the
  second: `S2["<b>2 · Reconstruct</b><br/><span class='ex'>screw-cap bottle</span>"]`.
  Mark nodes with `:::gap` (what fails), `:::win` (what the paper adds) or `:::example`.
  Link each Level 2 stage node with `click S2 href "#stage-2"`. A mechanism spanning
  several stages gets an `id="stage-all"` block, linked from the hint under the chart.
- **Charts that fit.** Charts are read in the artifact's side panel, about 760 px wide.
  The page shrinks a chart to fit, down to 70 % of its natural width, and scrolls it
  beyond that, which hides the right-hand nodes. `check_page.py` fails a chart that still
  scrolls at 760 px and warns above 760 px natural width, so aim for 760 px or less:
  - put at most 3 nodes in an LR row; use TD for longer chains, or when the edges
    carry labels, because labels widen the gaps; a two-lane chart has at most 2 columns;
  - keep a node to a short name plus one example line of about 18 Latin or 10 Chinese
    characters, splitting longer values with `<br/>`;
  - use plain boxes: diamond `{}` nodes balloon in size;
  - keep a `subgraph` title under 200 px (about 24 Latin or 12 Chinese characters):
    Mermaid wraps a longer title onto a second line that the first node then covers.
    Prefer a header node per lane. The check fails any wrapped or covered subgraph
    title, any label larger than its box, and any label outside the drawing;
  - inside a label write `#quot;` for a raw `"`, and `&lt;`/`&amp;` for `<`/`&` meant as
    text.
- **The authors' figures carry the explanation.** Show each one with
  `<img src="<name>/figN.jpg">` in a `.paper-fig` block, captioned "Fig. N（作者原图）".
  Follow it with a "怎么读这张图" list that walks the figure region by region, using the
  labels printed in it, and ties each region to the running example. When the authors
  drew something, show their figure first. Your flowchart then adds the example's values
  and the level structure.
- **Project-page media** go in the same `.paper-fig` blocks, captioned "项目页" with a
  link to the page's section, and get a one- or two-line reading guide too (what moves,
  what to compare). Show a video with `<video src="<name>/web-x.mp4" autoplay muted loop
  playsinline controls>`. Put two or three videos to compare in one `.media-row`, each
  in a `<figure>` with a short label (真机 / SceneRig / baseline). Numbers still come from
  the paper. If the project page reports different numbers (another model, more scenes),
  give the paper's and note the difference.
- **Results, one experiment at a time.** Each planned experiment becomes an `.exp`
  block: the question as its heading, then the authors' table or plot (an experiment
  reported only in the text gets a small table built from those numbers, labelled as
  such), then four lines: 说明什么 (the claim in bold, such as higher success, less time
  or more robust, then the key numbers and what they beat), 在故事里 (which step of the
  paper's argument it carries), 指标 (what counts as success, as the paper defines it)
  and 怎么评测 (setup and baselines, as bullets). A one-line intro links the blocks in
  order and says whether the paper compares success, time or both. Never open with a
  list of headline numbers: a number means nothing without its table, its metric and
  what it is compared against.
- **Exact numbers.** Copy numbers as printed and name their table or figure. If the
  paper does not report something, say so rather than estimating. Mark your own
  inferences as inferences.
- **For you**: at most 3 bullets, drawn from the profile's "Our work" column.
- **Meta tags.** Fill these:
  - `description`: the one-line TL;DR;
  - `paper:title`, `paper:source` and `paper:venue`;
  - `paper:pdf`: the versioned PDF link, which other machines use to download the PDF;
  - `paper:date`: the day the paper first went public, as YYYY-MM-DD: the arXiv v1 date
    (the API's `<published>`), else the release or venue date. The home page shows it on
    each card, above the filing date.
  The home page lists papers from them.
- **A tool instead of a paper** keeps the same template:
  - the problem's lanes are what users did before this version, or with the
    alternatives the paper names, and the symptoms come from the release notes and docs;
  - tag what this version adds with `<span class="win">3.0 新</span>` in the text and
    `:::win` in the charts, so the reader can tell it from what the paper describes;
  - figures the docs show (PNG or SVG) go into the figure folder as they are, with their
    source in the caption;
  - Results are what the release notes and docs report; if there are no new numbers,
    say so and give the paper's;
  - `paper:title` and `paper:venue` describe the release (`Isaac Lab 3.0 (v3.0.0)`,
    `GitHub release 2026-10-20`), and `paper:date` is the release date; the paper goes in
    the header's links.

## 6. Check, rebuild the home page, publish

```bash
uv run SKILL_DIR/scripts/check_page.py <root>/<Project>/artifact/<name>.html
python3 SKILL_DIR/scripts/build_index.py <root>
```

`check_page.py` checks two things:
- **Statically**: placeholders, meta tags, figure and video files, and stage links.
- **In headless Chromium**: every flowchart draws, no chart text is clipped, every chart
  fits a 760 px panel after shrinking, no errors, and the page does not scroll sideways
  at phone width.

Fix every FAIL and every too-wide chart, then rerun it. `build_index.py` rewrites
`<root>/index.html`, copies `library.js` (stars, folder drop lists, new-tab links) beside
it, and prints every publishable file path.

The whole library is **one** artifact, titled by the profile's "Artifact title" (Zhaoning
Paper Pile; `build_index.py` puts it in the home page's `<title>`). Agents on every
machine publish into the same one, so find it by its title on every run:

1. `list` your artifacts (`limit: 200`) and take the one whose title is exactly the
   artifact title. Only your own count: one shared from another account cannot take a
   publish, so it counts as not found.
2. **Found:** `read` it, then `list` its files (`scope: "files"`); the tool refuses to
   update an artifact this session has not read. Publish into it, which adds the paper
   as a new page: `url`, `file_path: <root>/index.html`, `root: <root>`,
   `capabilities: {"db": {}}` (the database that keeps the stars) and `files:` set to
   `library.js` and the new or changed page and its figure files. If the listing has no
   `library.js` yet, also add every page (`.html`) that is both in the listing and in
   the printed paths, so the older pages get their star. Files you leave out stay as they
   are. When a redo removes a figure, use the map form of `files`
   (`{"<path>": "<path>", "<old path>": null}`), because only the map form can pass
   `null`.
3. **Not found:** create it with the whole library: `file_path: <root>/index.html`,
   `root: <root>`, `files:` every path the script printed (as `{"path": …}` items),
   `capabilities: {"db": {}}`, `icon: "book"` and a one-sentence description. Then give
   it its own link, below.

**The artifact's own link.** A link opened in a new tab must reach the artifact's
claude.ai link, so `library.js` reads it from the artifact's database: the doc
`config/home`, `{"url": "<artifact url>"}`. Write it with the ArtifactData tool (`set`)
when you create the artifact, and whenever the user says a page opened in a new tab
shows the home page instead. Each account's copy has its own.

Artifact sources must sit under the session's working directory or scratchpad. If the
library does not, copy `index.html`, `library.js` and the new files into the scratchpad
with the same relative paths, and use that copy as `root`.

After publishing, `list` the files once to confirm that the page and its figures are
there.

## 7. Commit and push

Commits in the library are always authorized. Commit and push every run, so the next
agent on any machine starts from this state:

```bash
git -C <root> add -A
git -C <root> commit -m "Add <name>"      # a redo: "Redo <name>"; a profile change: "Update profile: <what>"
git -C <root> push
```

- Write a one-line message: what changed, nothing else, and no Co-Authored-By or other
  attribution trailers.
- PDFs stay out of git through `.gitignore`. Never force-add one.
- If the push is rejected because another machine pushed first, run
  `git -C <root> pull --rebase`. If `index.html` conflicts, rerun `build_index.py`,
  `git add index.html`, `git rebase --continue`, then push again.
- If the push fails for any other reason (no network, no credentials), keep the local
  commit and tell the user.

## 8. Be ready for questions about the paper

The user's next message is often a question about the paper ("why does stage 2 need
verifiers?", "how did the ablation go?"). Answer it from the paper itself, so make sure
this session holds the paper before you report:

- If you read the paper in this session and it is still in your context, you are ready.
- Otherwise load it now. That applies when the work ran in a subagent, when the context
  was compacted, or when this is a later session. If the PDF is not on this machine,
  download it from the page's `paper:pdf` link first. Then load the finished page's
  text and the paper's own text (for a tool, also its release notes):

  ```bash
  sed -e '/<style>/,/<\/style>/d' -e '/<script/,/<\/script>/d' <page> | sed 's/<[^>]*>//g' | grep -v '^\s*$' > <scratchpad>/<name>.page.txt
  pdftotext <root>/<Project>/<name>.pdf <scratchpad>/<name>.txt   # reading order, even for two columns
  ```

  Then Read both files: the page in full, and the paper's main body in full up to the
  references. Read appendix parts when a question needs them. Both go through files
  because shell output is cut off at about 30 KB.

When a question goes past what is loaded, read the relevant PDF pages or open the
figure crop again before answering. Name the section, table or figure the answer comes
from. A guess about a paper the user is trying to understand does more harm than saying
"let me check".

## 9. Report, then ask what to change

Keep the terminal message short, in the profile's language:
- the artifact link, and how to reach the page (home → project → paper);
- where the PDF and the page live;
- the project chosen and why;
- the three TL;DR lines.

Then ask what the user would change.

End your first reply with `/remote-control` on a line of its own, whatever that reply
is: this report, a question from step 0 or 2, or the step 1 pointer to a page already in
the library. The user types it to continue the session from their phone or
claude.ai/code, for example to ask about the paper (step 8). It is a built-in Claude Code
command that only the user can run, so do not try it through Bash or the Skill tool.
Later replies leave it out.

When the user answers, sort the feedback:
- **About this paper** (a wrong number, an unclear stage, a missing figure): fix the
  page, republish, commit and push.
- **About how they like papers explained** ("fewer bullets", "always show the key
  equation"): fix the page, and also edit the matching line in the profile's "How I
  learn" section (rewrite the line rather than appending a contradiction), and add a
  dated line to its feedback log. Commit and push, so every machine picks it up. Every
  later paper then follows it. Tell the user what changed in the profile.
- **About structure or design for every page**: change the template or this file, and
  say which one you changed.

Every change to this skill (this file, the template, the scripts) goes into the
zw-claude-skills plugin repo, where it lives under `plugins/paper-explain/`. Commit and
push that repo right after the change, with a one-line message and no attribution
trailers, so every machine gets the new version. The user has authorized these commits.
If `SKILL_DIR` is not inside a git clone of that repo, for example in a plugin cache,
tell the user that the change still needs to go into the plugin repo.

## Temporary papers

When the user calls a paper temporary ("temporary", "temp" or 临时), explain it in full but
keep it out of the library: it gets its own artifact, and nothing is filed or pushed.

- Steps 0 and 1 run as usual. The profile still sets the voice, and a paper already in
  the library gets a pointer to its page instead.
- Wherever the steps say `<root>/<Project>`, use `<scratchpad>/temp`: the PDF, the page
  in `artifact/` and its crops beside the page. Still pick the closest project, because
  "For you" and the filed line need it.
- The page has no library to point to. In the copy of the template, change:
  - the crumb to `<span class="crumb">Temporary</span>`;
  - the eyebrow to `临时 · <today>`;
  - the filed line to `临时，不进 library。最接近 <b>{{Project}}</b>：{{一句话理由}}`;
  - the footer to `临时页面，不在 library 里。`;
  - and delete the `library.js` script line, because stars live in the library.
- Step 6: run `check_page.py`, skip `build_index.py`, and publish a new artifact:
  `file_path: <scratchpad>/temp/artifact/<name>.html`, `root: <scratchpad>/temp/artifact`,
  `files:` its crops (`<name>/…`), `icon: "book"` and a description that starts with
  "Temporary:". The tool nests the page, doctype and all, inside its own skeleton, which
  renders fine. A fix republishes to the same artifact.
- Skip step 7. Steps 8 and 9 run as usual; the report says the paper is temporary and
  that its files go when the scratchpad is cleared. Feedback on how the user likes papers
  explained still goes into the profile, committed and pushed as usual.
- If the user then wants to keep it, file it: move the PDF, the page and its crops into
  the project folder, restore those five places from the template, and run steps 6
  and 7.

## Starred papers

On the library pages the user stars papers, or whole project folders, to mark the ones
they will work from, such as the papers for a related-work section or a paper to review
carefully. When they ask for their starred papers (星标), gather them yourself:

1. `list` artifacts with `scope: "all"` and `limit: 200`, and keep every one titled
   exactly the artifact title. Each account has its own copy with its own stars, so use
   them all.
2. For each copy, `list` the collection `stars` with the ArtifactData tool, and take the
   union of the doc ids. `<Project>:<name>` is one paper, the page
   `<root>/<Project>/artifact/<name>.html`. A bare `<Project>` is the whole folder: every
   page in `<root>/<Project>/artifact/` now, including papers filed after the star. Skip
   an id whose page is no longer in the library, and say so.
3. Load each paper's page and PDF text as in step 8, downloading a missing PDF from the
   page's `paper:pdf` link. With many papers, read the pages first and open each PDF
   where the task needs its details.
4. Say which papers you are using and which copies their stars came from, then do the
   task.

## Ground rules

- Every claim, number and example value comes from the paper. The page is a reading
  aid, so an invented detail does more harm than a missing one.
- Write only inside the library clone and the scratchpad. Never delete or overwrite
  another paper's files.
