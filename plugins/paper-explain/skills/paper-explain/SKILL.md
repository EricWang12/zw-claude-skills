---
name: paper-explain
description: Explain a research paper the way this user learns best, and file it in their paper library. Given a paper link (arXiv abs/pdf, project page, OpenReview, any PDF URL) it downloads the PDF into the right project folder under a dated short name (2026-10-15-DexAgent), reads the whole paper, crops and inspects the authors' figures, and writes a visual page - the problem told on one running example (what each baseline does and where it breaks), then big picture → stages → per-stage detail with flowcharts, the original figures explained part by part. The page is saved next to the PDF, published into the user's single library artifact (Zhaoning Paper Pile), and the library is pulled from and pushed to its GitHub repo so every machine stays in sync. Use this whenever the user shares a paper or project-page link, or asks to read, explain, summarize, break down, TL;DR or "help me understand" a paper, or to add a paper to the library - even if they never say "explain".
---

# Paper explain

The user hands you a paper; you hand back understanding. Three things come out of every
run:

1. The PDF, filed in the right project folder under a short dated name.
2. An explainer page (HTML) beside it, written for this particular reader.
3. That page, published as a new page of the one library artifact, whose home page
   mirrors the folder tree.
4. The library committed and pushed to its GitHub repo, so agents on every machine work
   in the same library.

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
- the library repo, the artifact's title and its URL.

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
  name, usually the word before the colon in the title (`DexAgent`). If there is none,
  use 1–3 CamelCase words for the key idea. Letters, digits and hyphens only.
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
again. Scratch files (notes, test
renders) go in the session scratchpad and are deleted at the end. The library holds
only the files above.

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
  `--page 3` writes a 72-dpi render of page 3 to read coordinates from. Each call
  re-detects every caption and overwrites crops with the same ID, so pass all your
  `--box` flags in one call. It never deletes anything.
- **Understand the figure.** The authors' figure is the most precise statement of
  their method, more precise than their prose and more precise than anything you
  redraw. Note what each region shows and which labels are printed in it. The page's
  "怎么读这张图" lists come from these notes.

Before publishing, delete the crops the page does not use, and delete `figures.json`.

## 4. Plan before writing any HTML

Settle these first, because the page is only as clear as this plan:

- **The running example**: one concrete case taken from the paper itself, usually its
  teaser task or main demo, with real names and real values. It carries the whole
  page, the problem included.
- **The problem, on that example.** Which baselines does the paper build on or compare
  against? Group them into at most 4 families and name the methods. For each family,
  work out:
  - what it does with this example's input;
  - the exact step where it breaks on this example and the visible symptom;
  - its number on this example, or the closest one the paper reports.
  The reader should see where things break, not a survey of related work.
  Papers often report only outcomes (✗ or 0% per task). Then infer the breaking step
  from the paper's own descriptions and analysis, cite the sections, and say so in the
  note under the table. Work the paper builds on but never evaluates can take a row,
  with "未对比" as its number. Then write the root cause in one line, and the paper's
  way in.
- **Stages**: 3–6 in order, each written as input → output, plus any mechanism that
  spans every stage (a shared library, a verify-and-retry loop).
- **Coverage.** List every idea in the paper: each stage and module, each special
  mechanism (verification, retry on failure, learning over time, a key trick), and the
  main result. Make sure the example shows each one. If one case cannot show an idea,
  extend the same case ("…then a second video arrives") rather than starting a second
  example. This list becomes the Recap table. Any idea the example skips stays abstract
  for the reader.
- **Figure map**: which author figure explains which level or stage, and which table or
  plot is the evidence.

## 5. Write the page

If the Artifact tool requires the artifact-design skill before writing a file, load
it now. Copy `SKILL_DIR/assets/paper-template.html` to
`<root>/<Project>/artifact/<name>.html` and fill it. The template fixes the section order and the look, and it already meets the
Artifact page contract, both themes and phone width. Fill it in; do not redesign it. If
the Artifact tool asks for a quickstart or the artifact-design skill first, do that,
then still use the template. Two things in the template look wrong but are deliberate:
- It loads Mermaid itself, because pages other than the library home are served
  without the artifact skeleton.
- It reads `class='ex'` inside quoted chart labels correctly.

- **Language**: follow the profile.
- **Concise.** Bullets of one line, no paragraphs. Get coverage from the levels, not from
  longer text.
- **The problem section** opens with the example in the amber box. Then a flowchart
  with one lane per baseline family, starting from the example's input and ending at the
  `:::gap` node where it breaks, with the symptom. Then the table of at most 4 rows:
  family, what it does, where it breaks on the example, number with its source. End
  with the one-line root cause and the paper's way in. Big picture follows directly.
- **A flowchart at every level.** Write Mermaid inside `<div class="flow"><pre>…</pre></div>`.
  Put a short name on the first line of each node and the example's value on the
  second: `S2["<b>2 · Reconstruct</b><br/><span class='ex'>screw-cap bottle</span>"]`.
  Mark nodes with `:::gap` (what fails), `:::win` (what the paper adds) or `:::example`.
  Link each Level 2 stage node with `click S2 href "#stage-2"`. A mechanism spanning
  every stage gets an `id="stage-all"` block, linked from the hint under the chart.
- **Charts that fit.** A chart wider than its 1040 px box scrolls sideways, which breaks
  the picture:
  - put at most 4 nodes in an LR row; use TD for longer chains, or when the edges
    carry labels, because labels widen the gaps;
  - keep a node to a short name plus one example line of about 18 Latin or 10 Chinese
    characters, splitting longer values with `<br/>`;
  - use plain boxes: diamond `{}` nodes balloon in size;
  - inside a label write `#quot;` for a raw `"`, and `&lt;`/`&amp;` for `<`/`&` meant as
    text.
- **The authors' figures carry the explanation.** Show each one with
  `<img src="<name>/figN.jpg">` in a `.paper-fig` block, captioned "Fig. N（作者原图）".
  Follow it with a "怎么读这张图" list that walks the figure region by region, using the
  labels printed in it, and ties each region to the running example. When the authors
  drew something, show their figure first. Your flowchart then adds the example's values
  and the level structure.
- **Exact numbers.** Copy numbers as printed and name their table or figure. If the
  paper does not report something, say so rather than estimating. Mark your own
  inferences as inferences.
- **For you**: at most 3 bullets, drawn from the profile's "Our work" column.
- **Meta tags.** Fill these:
  - `description`: the one-line TL;DR;
  - `paper:title`, `paper:source` and `paper:venue`;
  - `paper:pdf`: the versioned PDF link, which other machines use to download the PDF.
  The home page lists papers from them.

## 6. Check, rebuild the home page, publish

```bash
uv run SKILL_DIR/scripts/check_page.py <root>/<Project>/artifact/<name>.html
python3 SKILL_DIR/scripts/build_index.py <root>
```

`check_page.py` checks two things:
- **Statically**: placeholders, meta tags, figure files and stage links.
- **In headless Chromium**: every flowchart draws, fits its box, raises no errors, and
  the page does not scroll sideways at phone width.

Fix every FAIL and every too-wide chart, then rerun it. `build_index.py` rewrites
`<root>/index.html` and prints every publishable file path.

The whole library is **one** artifact, named by the profile's "Artifact title" (its home
page `<title>`, which `build_index.py` sets). Agents on other machines publish into the
same one, so always look for it before creating anything:

1. Take the profile's Artifact URL, and `read` it.
2. If there is no URL, or it does not read, `list` your artifacts (`limit: 200`) and
   take the one whose title is exactly the artifact title. Write its URL into the
   profile.
3. Only if neither finds it, create it: publish with `file_path: <root>/index.html`,
   `root: <root>`, `files:` every path the script printed (as `{"path": …}` items),
   `icon: "book"` and a one-sentence description. Write the returned URL into the
   profile.

To publish into the artifact you found:
- **Found:** after the `read`, `list` it with `scope: "files"`. The tool refuses to update
  an artifact this session has not read. Then publish with `url`,
  `file_path: <root>/index.html`, `root: <root>` and `files:` set to the new or changed
  page and its figure files. Files you leave out stay as they are. When a redo removes
  a figure, use the map form of `files` (`{"<path>": "<path>", "<old path>": null}`),
  because only the map form can pass `null`.
- Artifact sources must sit under the session's working directory or scratchpad. If the
  library does not, copy `index.html` and the new files into the scratchpad with the
  same relative paths, and use that copy as `root`.

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
  text and the paper's own text:

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

## Ground rules

- Every claim, number and example value comes from the paper. The page is a reading
  aid, so an invented detail does more harm than a missing one.
- Write only inside the library clone and the scratchpad. Never delete or overwrite
  another paper's files.
