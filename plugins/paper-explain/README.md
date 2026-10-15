# paper-explain

Paste a paper link (arXiv, project page, OpenReview, any PDF) and say "help me understand
this". The skill:

1. **Syncs the library first.** The library is a git clone of your papers repo. It
   pulls before doing anything, so agents on every machine work in the same library.
2. **Files the PDF** under the project it serves, as `<Project>/<YYYY-MM-DD>-<Short>.pdf`
   (`2026-10-15-DexAgent.pdf`). The project comes from the scope lines in the library's
   `preferences.md`.
3. **Reads the whole paper and crops the authors' figures** straight from the PDF
   (`extract_figures.py`). Then it looks at every crop, both to check the crop and to
   understand the figure, because the authors' figure is the most precise description
   of the method.
4. **Writes the explainer page** next to the PDF, as `<Project>/artifact/<name>.html`,
   in the reader's style from `preferences.md`:
   - the problem told on one running example: what each baseline does and exactly
     where it breaks;
   - then big picture → stages → per-stage details;
   - flowcharts that carry the example's values;
   - the original figures, explained region by region.
5. **Checks the page** in headless Chromium (`check_page.py`): every flowchart draws and
   fits, and nothing scrolls sideways on a phone.
6. **Publishes it as a page of one artifact**, whose home page mirrors the folder tree.
   It finds the artifact by its title, so every machine publishes into the same one.
7. **Commits and pushes** the library, then loads the paper into the session so it can
   answer your follow-up questions.

Some feedback is about how you like papers explained in general, such as "fewer bullets"
or "explain the problem on the example". That kind goes into `preferences.md` and is
pushed, so every later paper follows it on every machine.

## Install

For Codex, follow the [Codex installation instructions](../../README.md#codex).
Both hosts load the same `skills/paper-explain/SKILL.md`.

```
/plugin marketplace add EricWang12/zw-claude-skills
/plugin install paper-explain@zw-claude-skills
```

## Setup

- **The library repo.** Step 0 of `skills/paper-explain/SKILL.md` names it
  (`EricWang12/all_papers`), together with the lab-machine clone path. Point both at
  your own repo. The reader profile, the projects and the artifact title live in that
  repo's `preferences.md`. If the repo has none, the first run asks and writes one.
- **Push access** to that repo from every machine that runs the skill.
- **PDFs stay local.** The library's `.gitignore` keeps them out of git, which keeps
  the repo small. Each page records a versioned PDF link, so any machine can fetch the
  same file again.
- **Tools:** `uv` (the scripts bring PyMuPDF and Playwright through inline script
  metadata) and poppler's `pdfinfo`.
- **Page check browser.** On a new machine, install it once:
  `uv run --with playwright==1.63.0 playwright install chromium-headless-shell`

## What you say

> help me understand this paper https://arxiv.org/abs/2609.35318

> add this to my library: https://dexagent1.github.io

> TL;DR this one for the real-to-sim project https://openreview.net/forum?id=...

## What you get back

- The PDF and its explainer page in the library, committed and pushed
- A link to the page in the library artifact (home → project → paper)
- The project it was filed under and why, plus three TL;DR lines
- A session that already holds the paper, ready for your questions
