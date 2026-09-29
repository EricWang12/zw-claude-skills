---
name: reproduce
description: Given a GitHub repo URL or a paper/project page, get the code actually running on this machine - clone it, build a short-named environment, pick the largest model variant that fits the GPU memory that is currently free, run at least three distinct demos, verify their outputs, and publish an artifact that explains what problem the code solves and walks the demo's input-to-output flow with the real examples embedded in the flowchart. Use this whenever the user shares a repo or project link and wants it working - "reproduce this", "clone and set this up", "run the demo", "can you try this model", "get this working here", "show me what this does" - even if they never say the word "reproduce".
---

# Reproduce

A repo link is a claim: "this code does something worth seeing." Your job is to make
that claim true on this machine and then teach it back. The deliverable is twofold: a
working setup the user can rerun with one command, and an artifact that explains the
codebase through the demos you actually ran — not alongside them.

## Definition of done

- The repo is cloned and a fresh environment with a **short name** builds and runs it.
- The **largest model variant that fits the currently-free GPU memory** was chosen,
  downloaded, and used — and the artifact says why that one.
- **At least three demos** ran to completion, each verified by inspecting its output,
  with inputs and outputs saved on disk.
- A published **artifact** shows: the problem the codebase solves, the demo code flow
  (what led to what led to what), the inputs and outputs — with one worked example
  threaded through the flowchart, its per-step input and output shown at every stage,
  so the reader sees how the overall input becomes the overall output. A copy of
  everything in it (the HTML and the examples it shows) lives at `docs/artifact/`
  inside the clone.
- The final message gives the artifact link, the env name, and one command to rerun a
  demo.

Decide everything yourself — model size, env name, GPU, which demos. The user handed
you a link, not a questionnaire.

## 1. Survey before touching anything

If the link is a paper or project page rather than a repo, find the code link on it
first. Clone into the current working directory (a subdirectory named after the repo)
unless the user named a place.

Read the README and docs before installing anything, and pull out four things: what
problem the project claims to solve, the install instructions, the **model zoo** (the
variants and their sizes), and the **demo entrypoints**. Note where the repo keeps
sample inputs — bundled examples are the best demo inputs because they are what the
authors tuned for.

Prefer the most scriptable demo path: a CLI script beats a small Python API call,
which beats code lifted out of a notebook. Never present a launched Gradio/web app as
the demo — a server you can't inspect is not a verifiable output. If the only demo is
a notebook or an app, extract its core calls into a plain script and run that.

## 2. Measure the machine before choosing a model

"Best model that fits" means fits **now**, on a machine you may be sharing:

```bash
nvidia-smi --query-gpu=index,memory.free,memory.total,compute_cap --format=csv
```

- Pick the GPU with the most **free** memory and pin to it with
  `CUDA_VISIBLE_DEVICES`. Total VRAM is irrelevant if someone's training run holds it.
- From the model zoo, choose the largest variant expected to use at most ~70% of that
  free memory. Use the repo's documented requirements; failing that, estimate
  checkpoint size × 1.5–2 for weights plus activations.
- Compare the GPU's compute capability against the repo's pinned torch. Repos pin the
  torch of their era, and a GPU newer than the wheel fails at runtime with "no kernel
  image is available". When that happens, install the newest torch (matching this
  machine's CUDA) that the code tolerates, and adapt small API drift in the code
  rather than downgrading the hardware's capability. Sanity-check before any long
  download: `python -c "import torch; print(torch.tensor([1.]).cuda() * 2)"`.
- No GPU at all: take the smallest variant on CPU and say so in the artifact.

## 3. Environment

Use conda if available, else uv/venv. Name the env something **short** — 2–6
characters abbreviating the repo (`dav2`, `sam`, `wspr`) — because the user will type
it far more often than you will; if the name is taken, append a digit rather than
lengthening it.

Take the Python version from the repo's own metadata (`environment.yml`, `setup.py`,
README badge). Install the way the repo prefers (`environment.yml`,
`requirements.txt`, `pip install -e .`), changing only the pins that fight this
hardware — and record every deviation, because the deviations are the actual cost of
reproduction and belong in the artifact.

## 4. Weights

Download the chosen checkpoint to wherever the repo expects it (its own directory or
the HF cache). Confirm the file size roughly matches what's advertised before running
— a truncated download fails much later with a confusing error.

## 5. Run at least three demos that are actually different

Three near-identical runs teach less than three contrasting ones. Vary the **input**
(different scenes, speakers, domains) and, when the model has modes, the
**capability** (e.g., point prompt vs. box prompt vs. automatic; transcribe vs.
translate). Keep a copy of every exact input used.

Run each demo non-interactively, tee stdout/stderr to a log, and write results under
`demo_outputs/demo<N>/` in the clone. Then **open the output**: read the image — is
it a depth map or noise? read the text — is it a transcript or token soup? An exit
code of 0 over a garbage output is a failed demo. When a demo breaks, debug it and
rerun — version drift is expected in reproduction work; quietly shipping two demos
instead of three is not.

## 6. Trace the flow while the demos run

The flowchart must describe the code as it actually executed, so collect the trace
now, while it is cheap. Read the demo entrypoint and write down the real chain — 4 to
7 load-bearing stages, each anchored to a real location:

> input file → `load_image()` (`run.py:31`) → preprocess/resize (`transform.py:18`)
> → `model.forward()` → colorize/postprocess (`run.py:58`) → `demo_outputs/…`

For **each** demo, record what the data looked like at every stage: the input (copy
or thumbnail), the one or two facts worth knowing mid-pipeline (tensor shape, prompt
used, sampling rate), and the output. This per-demo, per-stage record is the raw
material of the artifact.

## 7. The artifact

Load the artifact-design skill (and artifact-diagramming for the flowchart) before
writing. Author the page as a self-contained HTML file, and keep a copy of
**everything that makes up the artifact** in **`docs/artifact/` inside the clone**
(create the folder): the HTML itself plus the example inputs and outputs it presents
— the images, media, and text snippets that appear in the flow. That folder must
stand on its own, so the report survives with the repo and reopens long after this
session is gone. Then publish the same HTML with the Artifact tool for a shareable
link. If no Artifact tool exists in this session, the `docs/artifact/` copy is the
deliverable — give its path.

Structure, in order:

1. **The problem** — 2–4 sentences in input/output terms: give it X, it returns Y,
   and why that matters. No marketing prose.
2. **The demo code flow** — one diagram of the shared pipeline, every stage labeled
   with its real `file:function`, with **one worked example threaded through it**: at
   every stage, show that example's input and output at that step (thumbnail, snippet,
   or the one fact that matters), so the reader follows a single concrete run from
   the overall input to the overall output. One example carried end to end beats
   three shown in fragments — pick the demo whose data reads most clearly at every
   stage. The other demos are correlated in the per-demo table below the chart. A
   flowchart nobody can match to a concrete run is decoration.
3. **Per-demo table** — exact command, input, output, wall time.
4. **Setup notes** — env name, model variant chosen and the free-VRAM numbers that
   justified it, every deviation from the README and why.

Downscale embedded images (~400px JPEG data URIs) so the page stays far under the
16MB limit; text outputs get short verbatim snippets, not full dumps.

## Ground rules

- Leave the clone, env, weights, and `demo_outputs/` in place — they are the
  deliverable, not litter. Touch nothing you didn't create (other envs, caches,
  running jobs).
- Report honestly. A demo that never worked is stated as such — in the artifact and
  the final message, with the actual error — never padded over with a duplicate run.
- If the repo genuinely ships no demo, build the minimal one from the README's
  quickstart snippet and label it as yours.
