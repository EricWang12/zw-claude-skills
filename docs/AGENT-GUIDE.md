# Adding editor breakpoints as an agent

General instructions, not tied to this repo or this machine. Written for an agent
that can run shell commands and write files but cannot click anything.

**Goal:** real breakpoints — the red dot in the gutter and the row in the Breakpoints
panel — placed from a terminal, without editing the program under debug.

## What you get and what you cannot get

You **can** create, condition, disable, and remove source breakpoints and logpoints,
by writing a JSON file. You **cannot** step, read variables, or control an active
debug session from the terminal; the human drives the session once the breakpoints
are set. If you need runtime values programmatically, that is a different tool (a
DAP client), not this.

## Why it needs a small extension

Breakpoints are not configuration. There is no `launch.json` field for them — they
are workspace UI state. Three routes exist and only one works from a terminal:

| Route | Verdict |
| --- | --- |
| `launch.json` entry | **Impossible.** No such field exists |
| Write `state.vscdb` (SQLite, key `debug.breakpoint`) | **Not on remote.** The DB lives on the machine running the UI. On Remote-SSH / code-server it is on the user's laptop and absent from the box you are on. On a purely local setup it is reachable, but it is unsupported, needs a window reload, and can corrupt workspace state |
| Extension calling `vscode.debug.addBreakpoints()` | **Works.** The supported API. Needs a bridge you can reach |

For the bridge, the natural-looking answer is `contributes.languageModelTools` +
`vscode.lm.registerTool`. **Do not build that.** It is a VS Code + Copilot Chat API,
it is missing from some forks' API surface, and even where present it is callable
only from an in-editor chat agent — a terminal agent cannot invoke `vscode.lm` tools
at all. A **watched file** works for every caller: terminal agent, in-editor agent,
human, or CI. It also makes the breakpoint set reviewable in a diff.

```
agent writes <manifest>.json
        │
   FileSystemWatcher
        │
vscode.debug.addBreakpoints()
        │
   red dots in the gutter
```

## Step 0 — install the bridge

The `vscode-breakpoints` skill in this repo, at
`plugins/vscode-debug/skills/vscode-breakpoints/`, is a complete implementation:

```bash
cd plugins/vscode-debug/skills/vscode-breakpoints
python3 scripts/install_bridge.py --list     # what installations exist
python3 scripts/install_bridge.py --dry-run  # what would change
python3 scripts/install_bridge.py            # stage and register
```

It detects local and remote, VS Code and Cursor and code-server, on Linux, macOS,
and Windows, and picks the most recently active. The compiled extension is committed and
has no runtime dependencies, so installing needs only Python; `node`/`npm` are needed
only to rebuild it after editing the source (`--rebuild`).

**The trap that will cost you an hour.** An editor keeps two kinds of extension
manifest, and a window on a custom profile reads **only** the profile one:

```
<extensions>/extensions.json                 application-wide ("default profile")
<userData>/profiles/<id>/extensions.json     per-profile  ← what actually loads
```

Register into the application-wide file alone and you get a perfect silent no-op:
extension on disk, entry correct, nothing logged as an error, never activates, absent
from the Extensions list. `install_bridge.py` writes to all of them for this reason.

If you install by hand instead, note that the log line
`Added extensions to default profile from external source [...]` reads as success but
is actually the symptom — the editor filed it where the active profile does not look.

Alternative on a machine with the editor CLI on `PATH`: package with
`npx @vscode/vsce package` and `code --install-extension <file>.vsix`. Cleaner where
available, unavailable on most headless remotes. Not exercised by this folder.

## Step 1 — pick a single-process entry point

This decides whether the whole exercise is worth doing.

A `torchrun` / MPI / Ray / multi-worker entry point is a poor target: every rank stops
at the same line, and stepping means coordinating N debuggers with per-rank attach
ports. Find a single-process path through the same code and instrument that. Look for
no process-group init, no launcher wrapper, and a knob you can turn down (`--steps`,
`--limit`, a smaller input) so one pass takes seconds rather than minutes.

Verify it actually runs before writing anything else: entry script exists, interpreter
exists, model/data assets exist and sit on a **restart-persistent** path — not
scratch, which vanishes and breaks every config.

## Step 2 — write the launch config

Ordinary `launch.json`. What matters for stepping:

```jsonc
{
  "type": "debugpy",              // or node, go, lldb...
  "request": "launch",
  "program": "${workspaceFolder}/path/to/entry.py",
  "console": "integratedTerminal",
  "cwd": "${workspaceFolder}",
  "python": "${workspaceFolder}/.venv/bin/python",
  "justMyCode": false,           // false, or you cannot step into library internals
  "env": { "PYTHONUNBUFFERED": "1" },
  "args": ["--steps", "6"]       // the cheap-but-complete configuration
}
```

`justMyCode: false` is the one people forget. Add a `stopOnEntry: true` variant too —
it is the escape hatch when breakpoints are not binding, since it proves the debugger
attached at all.

Say in a comment that output at the cheap settings is meaningless, or someone will
report it as a bug.

## Step 3 — map the flow

Structure first, then the call sites that connect it:

```bash
grep -nE "^def |^class |^    def " driver.py
grep -nE "^class |^    def forward" model.py
grep -nE "self\.model\(|\.step\(|encode|decode" pipeline.py
```

Aim for 15–20 stops forming a spine: entry → argument resolution → setup → main loop
→ one level into the core → output. Prefer the **call site** over the definition where
you can only have one: that is the frame where arguments are resolved.

## Step 4 — verify every line number

Never trust grep output, a file's own comments, or memory. Print the line:

```python
for f, ln in candidates:
    print(f"{ln:>5} | {f:<32} | {open(f).read().splitlines()[ln-1].strip()[:88]}")
```

Then keep it honest with `apply_breakpoints.py --dry-run`, which fails on a line past
EOF, a line that is blank or a comment, and a missing file. A stale entry is worse than a
missing one: it puts a red dot on an unrelated line and teaches the wrong flow.

## Step 4b — target lines that execute per call

A `def`/`class` line is a statement that runs **once at import**, creating the function
object. A breakpoint on it fires during import and never when the function is called — and it
binds cleanly, so nothing looks wrong:

```
line 1  'def target(x):'   executed at: ['IMPORT']
line 2  'y = x + 1'        executed at: ['CALL', 'CALL']
```

Target the first executable statement of the body instead. Watch out for multi-line
signatures: the body can begin many lines below the `def`, so "+1" is not a reliable fix — it
can land inside the parameter list. Parsing the file (Python's `ast` gives you
`node.body[0].lineno`) is the reliable way, skipping a leading docstring since stopping on a
string constant shows nothing.

`apply_breakpoints.py` in this folder does this automatically and reports each move.

## Step 5 — guard the hot paths

The mistake that makes the result unusable is a breakpoint in a loop that fires
thousands of times. Budget every entry:

| Situation | Guard |
| --- | --- |
| Loop body, loop variable in scope | `"condition": "i == 0"` |
| No loop variable available | `"hitCondition": "==1"` |
| Very hot (per-layer, per-token) | `"enabled": false` plus a note on how to enable |
| Want the trace, not the pause | `"logMessage": "..."` — prints and continues |

**The scope trap.** A condition on a `for` line is evaluated *before* the loop
variable is bound, so `i == 0` raises `NameError` on the first pass. Anchor on the
first statement *inside* the loop. This looks correct and fails confusingly.

**Branch selection.** When a call has several sites selected by config, work out which
one the launch config actually reaches and mark only that. Marking all of them means
most never fire and the reader concludes the instrumentation is broken.

A manifest where every entry is a `logMessage` logpoint gives a printed trace of the
whole run without pausing once — often what you actually want on a first pass through
unfamiliar code.

## Step 6 — write the manifest

```json
{
  "version": 1,
  "breakpoints": [
    { "file": "src/entry.py", "line": 15,
      "note": "01 entry. argv rewriting happens here, before main sees it" },
    { "file": "src/loop.py", "line": 483, "condition": "i == 0",
      "note": "11 first iteration only; i is bound here, unlike the for line above" },
    { "file": "src/model.py", "line": 763, "enabled": false,
      "note": "14 per-layer forward, 30x per step. Add hitCondition ==1 before enabling" }
  ]
}
```

Paths are workspace-relative or absolute; `line` is 1-based, matching what the editor
and stack traces show. `note` is ignored by the debug API and exists to document the
set — number them so reading order survives the panel's own sorting.

Notes are the actual deliverable. `"calls the model"` is worthless beside a line that
says `self.model(...)`. Useful notes carry what the reader cannot see: which branch
this is, what to inspect here, what silently overrides what.

## Step 7 — verify from inside, not by looking

```bash
cat /tmp/agent-breakpoints-diag.log
```

```
activate: editor=1.128.0 extension=local.agent-breakpoints
activate: workspaceFolders=["/path/to/repo"]
manifest parsed: 20 usable entries, 0 problem(s)
sync done: desired=20 removed=0 added=20 debug.breakpoints now=20
```

Log to a **file**, not only an output channel. With a remote extension host, a channel
is readable only by someone sitting at the editor — useless to you.

| Symptom | Meaning | Fix |
| --- | --- | --- |
| Diag file never appears | `activate()` never ran | The profile trap. Re-run `install.py`; confirm it lists a profile manifest |
| Extension absent from Extensions list | Same | Same |
| `0 usable entries` | Manifest not at the resolved path | Compare `activate: workspaceFolders` against where you wrote the file |
| `added=0`, `desired=N` | Breakpoints already at those lines | Expected; hand-placed ones are never overwritten |
| `past EOF` problems | Manifest is stale | Re-verify line numbers |
| Listed but never hit | Wrong branch, or guard never true | Check which branch the config reaches; try `stopOnEntry` |
| Stops thousands of times | Hot path enabled unguarded | Add `hitCondition` |

## If it does not work, measure before fixing

The order that matters, each step eliminating one cause:

1. Is the registration still present after a reload? (else something is stripping it)
2. Did the reload actually happen? (look for a new extension-host process in the logs)
3. Is the workspace root what you assumed? (compare against where the manifest is)
4. Are you in the right editor directory at all? (several can exist; check recency)
5. **Which profile is active?** (this is usually the answer)

The temptation at every step is to change something instead of measuring the next
thing. Resist it. When this failed during development, the decisive evidence had been
sitting in the log from before the first reload and was read as success.

## Portability notes

- **Language-agnostic.** `SourceBreakpoint` is not Python-specific; `condition` and
  `hitCondition` are evaluated by whichever debug adapter is attached, so the
  expression syntax follows the target language.
- **Cursor and other forks.** Verified working on Cursor (VS Code base 1.128.0).
  `vscode.debug.addBreakpoints` and `SourceBreakpoint` are stable API present in
  forks; `vscode.lm` is not.
- **JetBrains has no equivalent** — different API, none of this transfers.
- **Multi-root workspaces.** Resolve relative paths against the folder that contains
  the file, not blindly against `workspaceFolders[0]`.
- **Never modify the program under debug.** `breakpoint()` and
  `debugpy.breakpoint()` work but edit the code under test, cannot be reviewed as
  configuration, and get committed by accident.

## Checklist

```
[ ] entry point is single-process
[ ] cheap-but-complete config exists, and says so
[ ] assets verified: script, interpreter, inputs, persistent paths
[ ] launch.json has justMyCode: false and a stopOnEntry variant
[ ] flow mapped: definitions and call sites
[ ] every line number printed and eyeballed
[ ] no breakpoint on a def/class header or a signature continuation line
[ ] validator passes N/N
[ ] hot paths guarded; scope trap checked on every loop condition
[ ] correct branch identified where a call has several sites
[ ] notes say what the frame shows, not what the line says
[ ] extension registered in ALL manifests, profile included
[ ] diag log shows added=N
[ ] documented only after it works
```
