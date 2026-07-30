---
name: vscode-breakpoints
description: Place real breakpoints in the VS Code or Cursor debugger UI — the red dots in the gutter and the rows in the Breakpoints panel — from a list of file:line locations, without touching the code under debug. Use this whenever breakpoints need to be set, added, moved, cleared, or verified, and especially when another skill has decided which lines matter and needs them marked (a code-walkthrough, code-flow, or onboarding skill calling in as a step). Also use it when the user says "put a breakpoint on", "mark the important lines", "set breakpoints so I can step through this", "show me the flow of this code", or asks for an interactive debugging walkthrough. Do not hand-write .vscode/breakpoints.json and do not inject breakpoint() or debugpy.breakpoint() calls into source — this skill owns that path and, unlike either alternative, confirms the editor actually applied the breakpoints instead of assuming it did.
---

# Editor breakpoints from file:line

Turn a list of locations into real editor breakpoints. One command, JSON in, JSON out,
and a verified result.

## Scope

This skill places breakpoints. That is all it does, so it can be relied on as a
building block.

It does **not** decide which lines are interesting, and does **not** write
`launch.json`. Those belong to whoever is calling — a code-flow skill analyses the
repo, writes its own debug config, then calls this to mark the lines. Keeping the
split means this stays runtime-agnostic: it works the same for Python, Node, Go, or
Rust, because a breakpoint location is just a file and a line.

There is no `launch.json` field for breakpoints, and editing the program under debug
(`breakpoint()`, `debugpy.breakpoint()`) is never the right way to place one. What works
is a small bundled extension that watches a manifest and calls
`vscode.debug.addBreakpoints()`; the scripts here manage it. Alternatives that look
plausible but do not work are listed in `references/troubleshooting.md`.

## Apply breakpoints

```bash
python3 scripts/apply_breakpoints.py \
    --set 'src/main.py:42:entry point, args resolved here' \
    --set 'src/loop.py:88:first iteration'
```

For anything beyond bare locations — guards, disabled entries — pass JSON. This is
the form a calling skill should use:

```bash
echo '[
  {"file": "src/main.py", "line": 42, "note": "1. entry, args resolved"},
  {"file": "src/loop.py", "line": 88, "condition": "i == 0", "note": "2. first item"},
  {"file": "src/hot.py",  "line": 12, "enabled": false, "note": "3. per-token, opt in"}
]' | python3 scripts/apply_breakpoints.py --json -
```

`--json` also accepts a file path, or an object with a `breakpoints` array.

Other modes: `--append` merges instead of replacing, `--clear` removes everything the
skill manages, `--dry-run` validates and reports without writing, `--repo PATH` sets
the workspace root (defaults to the git top level).

## Entry fields

| Field | Meaning |
| --- | --- |
| `file` | Workspace-relative or absolute path. Required |
| `line` | 1-based, matching what the editor and stack traces show. Required |
| `note` | Why this line matters. Carried in the manifest for the reader |
| `enabled` | Defaults true. `false` shows a hollow marker that never fires |
| `condition` | Expression in the target language, evaluated in that frame |
| `hitCondition` | Hit-count guard, e.g. `==1` for first hit only |
| `logMessage` | Makes it a logpoint: prints and continues instead of pausing |

Unknown fields are dropped with a warning rather than passed through, so a misspelled
`conditon` fails loudly instead of silently becoming an unguarded breakpoint.

## Guard the hot paths

The single thing that makes a breakpoint set unusable is one that fires thousands of
times. Before adding a location inside a loop, decide how it is bounded:

| Situation | Guard |
| --- | --- |
| Loop body, loop variable in scope | `"condition": "i == 0"` |
| No loop variable to key on | `"hitCondition": "==1"` |
| Very hot — per-layer, per-token, per-row | `"enabled": false` and say why in the note |
| Want the trace without stopping | `"logMessage": "step=${i}"` |

**Do not put a condition on the `for` line itself.** It is evaluated before the loop
variable is bound, so `i == 0` raises `NameError` on the first pass and the breakpoint
behaves unpredictably. Anchor on the first statement *inside* the loop instead. This
looks correct and fails confusingly, so it is worth checking every time a condition
mentions a loop variable.

A manifest where every entry is a `logMessage` gives a printed trace of a whole run
without pausing once — often what someone actually wants the first time through
unfamiliar code, and worth offering.

## Aim at code that runs, not at definitions

A `def` (or `class`) line is a statement that runs **once, when the module is imported** — it
is what creates the function object. A breakpoint there fires during import and never when
the function is called. It looks like it bound correctly, which is what makes this so easy to
get wrong:

```
line 1  'def target(x):'   executed at: ['IMPORT']
line 2  'y = x + 1'        executed at: ['CALL', 'CALL']
```

So to stop when a function *runs*, point at the first executable statement in its body. The
same applies to the continuation lines of a multi-line signature — none of them execute per
call either.

`apply_breakpoints.py` fixes this for you: any entry landing on a `def`/`class` header or its
signature is moved to the first body statement, skipping a docstring, and the move is
reported in the `adjusted` array and as a `MOVED` line on stderr. Read those — the line you
get back is the one your note should describe.

This is worth understanding rather than relying on: naming a function and letting the tool
find its body is fine, but if you compute a line number some other way, remember that "the
line the function starts on" and "the line that runs when it is called" are different lines,
sometimes dozens apart. `--allow-def-lines` opts out, and is only useful for watching import
itself.

## Verify the line before you send it

Never emit a line number you have not read. Grep output, stale notes, and memory all
drift as code moves, and a breakpoint on the wrong line is worse than a missing one:
it puts a red dot somewhere unrelated and teaches the wrong flow.

```bash
python3 -c "
for f, ln in [('src/main.py', 42)]:
    print(ln, repr(open(f).read().splitlines()[ln-1].strip()))
"
```

`apply_breakpoints.py` re-checks this anyway and refuses entries that are past
end-of-file, blank, or comment-only — but if it starts rejecting entries, the fix is
to look at the source, not to loosen the check.

## Reading the result

The JSON on stdout is the contract. Branch on it rather than on log text:

```json
{
  "ok": true,
  "manifest": "/repo/.vscode/breakpoints.json",
  "requested": 3, "written": 3, "skipped": [],
  "bridge": {"installed": true, "action": "already-present"},
  "verified": true, "applied": 3,
  "diag_line": "sync done: desired=3 removed=0 added=3 debug.breakpoints now=3"
}
```

**Exit status is 0 only when the editor confirmed the breakpoints.** `ok: false` with
a written manifest means they were staged but the editor did not apply them — do not
report success to the user in that case. The confirmation exists because every silent
failure in this system looks exactly like success from the outside: the file is
written, the JSON is valid, nothing errors, and no breakpoint appears.

If `verified` is false, read `references/troubleshooting.md`. The most common cause by
far is the bridge not being loaded in the editor's **active profile**, which needs one
`Developer: Reload Window` from the user — something you cannot do for them, so say so
plainly rather than retrying.

`skipped` entries are not fatal on their own; the rest still apply. Report which ones
were dropped and why, because a skip usually means the line numbers are stale.

## Calling this from another skill

- **One call, whole set.** Default behaviour replaces the managed set, so re-running
  with the full list is idempotent — no need to diff or clear first.
- **`--append` only for adding to someone else's set.** Prefer replace; it keeps the
  manifest matching your plan exactly.
- **Hand-placed breakpoints are never touched.** The bridge tracks only what it
  created, so a user's own breakpoints survive every sync.
- **Order the notes.** Number them (`1.`, `2.`, …) so the intended reading order
  survives the Breakpoints panel's own sorting.
- **Breakpoints need a session to hit them.** This skill does not check for one. If
  you are the caller, make sure a usable debug configuration exists, and prefer a
  single-process entry point — a `torchrun`/MPI/multi-worker target stops every rank
  at the same line and is miserable to step through.

## Files

| Path | Role |
| --- | --- |
| `scripts/apply_breakpoints.py` | The entry point. Validate, write, install if needed, verify |
| `scripts/install_bridge.py` | Builds and registers the bridge. Called automatically; run by hand to inspect with `--list` |
| `bridge/` | Extension source, bundled so this works in any repo. Needs `node`/`npm` once to compile |
| `references/troubleshooting.md` | Read when `verified` is false |
