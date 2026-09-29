# reproduce

Paste a GitHub repo (or a paper/project page) and say "get this running". The skill:

1. **Clones** the repo and reads its README/docs before installing anything.
2. **Builds an environment with a short name** (`dav2`, not `depth-anything-v2-env`) —
   conda first, uv/venv fallback — using the repo's own pinned Python and deps,
   adapting only what fights the hardware (e.g., a pinned torch too old for the GPU).
3. **Picks the largest model variant that fits the *currently free* GPU memory** — on a
   shared machine, total VRAM is a lie — and pins to the least-busy GPU.
4. **Runs at least three genuinely different demos** (different inputs, different
   capabilities), saves every input and output, and verifies each output by actually
   looking at it, not by trusting the exit code.
5. **Publishes an artifact** that explains the codebase through the runs: the problem
   it solves in input/output terms, and a flowchart of the demo code path anchored to
   real `file:function` locations with one worked example threaded through it — every
   stage shows that example's input and output, so you follow one concrete run from
   the overall input to the overall output (the other demos are correlated in a table
   below). A copy of everything in the artifact (HTML + the examples it shows) is
   saved to `<clone>/docs/artifact/` so the report stays with the repo.

The final message hands back the artifact link, the env name, and a one-line command to
rerun a demo.

## Install

For Codex, follow the [Codex installation instructions](../../README.md#codex).
Both hosts load the same `skills/reproduce/SKILL.md`.

```
/plugin marketplace add EricWang12/zw-claude-skills
/plugin install reproduce@zw-claude-skills
```

## What you say

> reproduce https://github.com/DepthAnything/Depth-Anything-V2

> can you get this working on our machine? https://github.com/Wan-Video/Wan2.2

> here's the project page for that paper — set it up and show me what it does

## What you get back

- A clone in your working directory with `demo_outputs/demo1..3/` inside it
- A short-named env you can `conda activate` immediately
- An artifact: problem statement → demo flowchart with the actual examples riding
  through it → per-demo command/input/output table → setup notes (model chosen, the
  free-VRAM numbers that justified it, every deviation from the README and why)
