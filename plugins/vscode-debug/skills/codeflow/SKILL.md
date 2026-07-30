---
name: codeflow
description: Turn a real run — a training job, an inference job, any command that works — into an interactive walkthrough of the code: a steppable VS Code/Cursor debug configuration, breakpoints on the lines that actually matter, and a CODEFLOW.md explaining the flow with a diagram. Use this whenever someone wants to understand how a codebase actually executes rather than read it statically: "help me understand this training loop", "walk me through the code flow", "I want to step through this", "where does the data loading happen", "onboard me to this repo", "how does this pipeline work end to end", or when they point at a session or log of a job they have been running and want to know what it does. Also use it after a long debugging or training session when someone asks to capture what was learned into something reviewable. Prefer this over reading files and writing a prose summary — a summary cannot be stepped through, and the breakpoints are what make the explanation verifiable.
---

# CodeFlow

Take a command that works and turn it into three artifacts that teach the code:

1. **A debug configuration** in `.vscode/launch.json` that runs in seconds, single-process
2. **Breakpoints** on the lines worth stopping at, applied to the editor gutter
3. **`CODEFLOW.md`** — diagram, flow narrative, and one entry per breakpoint

The work is mostly judgment: which command represents the system, which lines matter, and
what to say about each. The mechanical parts are scripted.

## 1. Find the representative command

Look for what someone actually ran, not what the README says. In order of usefulness:

- **The conversation or session** you were given — a command someone ran and iterated on
- **Launch scripts** — `train_*.sh`, `run_*.sh`, tracked launch configs
- **Ops docs** — RUNBOOK, INFERENCE.md, README run sections
- **Test smokes** — `tests/run_*_smoke.sh` are often the only commands guaranteed to work
  on the local machine, and they exercise the same code path at tiny scale
- **Shell history / job logs** — `history`, prior job submissions, log headers

When several exist, prefer the one that exercises the most of the system while still being
runnable *here*. A 24-GPU production command is more representative but useless if the
hardware is not present; a tiny smoke through the same entry point teaches the same flow.
Say which you chose and why.

## 2. Prove it works before building anything on it

A debug config derived from a command that no longer runs is worse than nothing — the
person hits F5, gets a stack trace, and now distrusts the whole document. Establish proof,
stopping at the first level you reach:

| Level | Evidence |
| --- | --- |
| 1 | A prior successful run — logs, job history, checkpoints it produced |
| 2 | A tracked launch config or launch script currently in use |
| 3 | An ops doc that documents it as the current procedure |
| 4 | **You ran it yourself** — shrunk to 1-2 steps, single process, tiny input |
| 5 | Nothing. Say so prominently in the doc and mark the config unverified |

Do not submit a full multi-GPU job to verify. If levels 1-3 fail, shrink and run locally.
Check the cheap preconditions either way: entry script exists, interpreter exists, weights
and data are present and on a **restart-persistent** path rather than scratch.

Read `references/verifying-commands.md` for how to mine each evidence source.

## 3. Convert it into something steppable

```bash
python3 scripts/make_debug_config.py \
    --name "<system> (debug, 1 proc)" \
    --command '<the verified command>' \
    --override steps=1
```

The script strips `torchrun`/`accelerate`/`deepspeed`, supplies the rank environment
`torch.distributed` needs for a one-rank world, sets `justMyCode: false`, infers the
project interpreter, applies your shrink overrides, and merges one entry into
`.vscode/launch.json`. It prints JSON; check `ok` and `problems`.

Two things decide whether the result is actually usable:

**Collapse to one process.** A multi-rank job stops every rank at the same breakpoint and
needs a debugger each. Single-process is the difference between steppable and not. The
script handles the mechanics; you confirm the code tolerates `WORLD_SIZE=1` — most FSDP and
DDP code does, but a script that hardcodes a device count or asserts `world_size > 1` needs
that noted in the doc.

**Shrink until one pass takes seconds.** Turn down steps, batch, resolution, dataset size —
whatever makes a full pass through the interesting code fast. Then say in a comment that
output at these settings is meaningless, or someone will report it as a bug.

Add a `stopOnEntry` variant when the entry point is doing something subtle before the
main work; it is also the way to prove the debugger attached when breakpoints seem not to
bind.

## 4. Choose the breakpoints

Aim for a spine of 8-15 stops that follow one pass through the system in execution order.
For a training job the shape is usually:

entry and argument resolution → dataset and dataloader construction → model build and
wrapping → the step loop → batch to device → forward → loss → backward → optimizer step →
logging and checkpointing.

Prefer the **call site** over the function definition when you can only have one — that is
the frame where arguments are resolved, which is what a reader needs. Put a stop wherever
configuration collapses into behaviour: the line where every effective argument is finally
assembled is usually the single most useful stop in the whole run.

**Never point a breakpoint at a `def` line.** A `def` statement runs once, at import — it is
what creates the function object — so a breakpoint there fires during import and never on a
call. It still binds, so it looks correct while showing you nothing. To stop inside a
function, target the first executable statement of its body, and note that for a multi-line
signature the body can start many lines below the `def` — a wide `__call__` with one keyword
argument per line routinely puts the first real statement twenty-plus lines down, so `+1` is
not a fix. `apply_breakpoints.py` corrects this automatically and reports each move under
`adjusted` — check that list and make sure your notes describe the line you actually got.

**Verify every line number by reading it.** Never emit one from grep output or memory:

```bash
python3 -c "
for f, ln in [('train.py', 42)]:
    print(ln, repr(open(f).read().splitlines()[ln-1].strip()))
"
```

**Guard anything hot.** A breakpoint that fires 500 times is worse than no breakpoint.

| Situation | Guard |
| --- | --- |
| Inside a loop, loop variable in scope | `"condition": "step == 0"` |
| No loop variable to key on | `"hitCondition": "==1"` |
| Very hot — per-layer, per-batch-element | `"enabled": false`, and say how to enable |
| Want the trace, not the pause | `"logMessage": "step=${step} loss=${loss}"` |

A condition on a `for` line is evaluated before the loop variable is bound and raises
`NameError`. Anchor on the first statement *inside* the loop instead.

## 5. Apply them with the vscode-breakpoints skill

Do not hand-write the manifest and never inject `breakpoint()` into the source. Use the
`vscode-breakpoints` skill, which validates the lines, applies them, and confirms the editor
took them:

It ships beside this one, so resolve its path rather than guessing: when installed as a
plugin use `${CLAUDE_PLUGIN_ROOT}/skills/vscode-breakpoints`, and otherwise the
`vscode-breakpoints` directory sitting next to this skill's own directory.

```bash
BP="${CLAUDE_PLUGIN_ROOT}/skills/vscode-breakpoints/scripts/apply_breakpoints.py"
echo '[{"file": "train.py", "line": 42, "note": "1. entry, args resolved"}]' \
  | python3 "$BP" --json -
```

Exit 0 only when the editor confirmed. If it reports staged-but-unconfirmed, say so rather
than claiming the breakpoints are set — and check that the target files are inside the open
workspace, since that is the usual cause.

## 6. Write CODEFLOW.md

Use `references/doc-template.md`. Required sections:

- **The command** — verified form, how it was proven, and the debug form beside it
- **Diagram** — Mermaid *and* an ASCII version. Mermaid renders in Cursor and on GitHub;
  ASCII survives terminals, diffs, and pasting into chat. Mark breakpoint positions in both
- **Flow narrative** — prose over the diagram, naming real files and functions, explaining
  what each stage is for rather than restating call order
- **Breakpoint table** — every breakpoint: number, `file:line`, guard, and what to inspect
  when stopped
- **Suggested first pass** — a 4-6 stop subset, because 15 stops is a lot for a first run
- **Gotchas** — anything that silently produces wrong behaviour
- **Not covered** — paths deliberately excluded, so absence reads as a decision

What makes the doc worth reading is the *why*, not the *what*. `"calls the model"` beside a
line that says `self.model(...)` is noise. Useful entries carry what the reader cannot see:
which branch this is, what to inspect here, what silently overrides what, what breaks if
it is wrong.

## Report back

State plainly: the command and its proof level, where the config and doc are, how many
breakpoints were applied and whether the editor confirmed, and how to start — pick the
config in the Run and Debug panel and press F5.

## Files

| Path | Role |
| --- | --- |
| `scripts/make_debug_config.py` | Command → single-process debug config, merged into `launch.json` |
| `references/verifying-commands.md` | How to mine each evidence source; the proof ladder |
| `references/doc-template.md` | CODEFLOW.md skeleton with both diagram forms |
