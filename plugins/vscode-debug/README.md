# vscode-debug

Agent skills that put **real breakpoints** in the VS Code / Cursor gutter from a terminal,
and turn a command that already works into a steppable walkthrough of the code.

No injected `breakpoint()` calls, no editing the program under debug. The red dots in the
gutter and the rows in the Breakpoints panel, placed from a JSON list of `file:line`
locations — and confirmed by the editor rather than assumed.

Two skills ship in this plugin:

| Skill | What it does |
| --- | --- |
| **`vscode-breakpoints`** | The primitive. `file:line` list in, real editor breakpoints out, verified. Language-agnostic |
| **`codeflow`** | The workflow. Takes a working command → a single-process debug config → breakpoints on the lines that matter → a `CODEFLOW.md` explaining the flow |

Use `vscode-breakpoints` when you know which lines you want. Use `codeflow` when you want
to understand an unfamiliar codebase by stepping through one real run of it.

## Requirements

- **VS Code or Cursor** (or code-server). Local or over Remote-SSH; both work.
- **Python 3.8+** — that is the whole install. The bridge extension is committed
  pre-compiled, so no Node toolchain is needed unless you want to modify it.
- macOS or Linux for the verification step, which reads a log under `/tmp`. Placing
  breakpoints works on Windows; the automatic confirmation does not.
- JetBrains IDEs are not supported — different API, none of this transfers.

Nothing needs to be installed into the editor by hand — the bridge extension registers
itself the first time breakpoints are applied.

## Using it

Ask for what you want; the skills trigger on intent:

- *"set a breakpoint where the dataloader is built"*
- *"walk me through how this training script actually runs"*
- *"onboard me to this repo — I want to step through one inference call"*

Or call the scripts directly. Placing breakpoints:

```bash
cd skills/vscode-breakpoints
python3 scripts/apply_breakpoints.py \
    --set 'src/main.py:42:entry point, args resolved here' \
    --set 'src/loop.py:88:first iteration'
```

With guards, which is how a calling skill uses it:

```bash
echo '[
  {"file": "src/main.py", "line": 42, "note": "1. entry, args resolved"},
  {"file": "src/loop.py", "line": 88, "condition": "i == 0", "note": "2. first item only"},
  {"file": "src/hot.py",  "line": 12, "enabled": false, "note": "3. per-token, opt in"}
]' | python3 scripts/apply_breakpoints.py --json -
```

Stdout is a JSON contract, so a caller can branch on it:

```json
{
  "ok": true,
  "manifest": "/repo/.vscode/breakpoints.json",
  "requested": 3, "written": 3, "skipped": [],
  "verified": true, "applied": 3,
  "diag_line": "sync done: desired=3 removed=0 added=3 debug.breakpoints now=3"
}
```

**Exit status is 0 only when the editor confirmed the breakpoints.** That matters more
than it sounds: every silent failure in this system looks exactly like success from the
outside — the file is written, the JSON is valid, nothing errors, and no breakpoint
appears. See
[`troubleshooting.md`](skills/vscode-breakpoints/references/troubleshooting.md) when
`verified` is false.

## How it works

Breakpoints are not configuration. There is no `launch.json` field for them — they are
workspace UI state, and the only supported way to create one is
`vscode.debug.addBreakpoints()` from inside an extension. So a small bundled extension
watches a manifest file and calls it:

```
agent writes .vscode/breakpoints.json
        │
   FileSystemWatcher
        │
vscode.debug.addBreakpoints()
        │
   red dots in the gutter
```

A watched file rather than a language-model tool, because a watched file works for every
caller — terminal agent, in-editor agent, human, or CI — and makes the breakpoint set
reviewable in a diff. The extension only ever touches breakpoints it created, so your own
survive every sync.

[`docs/AGENT-GUIDE.md`](../../docs/AGENT-GUIDE.md) is the full procedure, machine- and
repo-agnostic, including the routes that look plausible and do not work, the
extension-profile trap that produces a perfectly silent no-op, and why a breakpoint on a
`def` line never fires.

## What it cannot do

You can create, condition, disable, and remove breakpoints and logpoints from a terminal.
You **cannot** step, read variables, or control a running debug session that way — a human
drives the session once the breakpoints are set. If you need runtime values
programmatically, you want a DAP client instead.

## Status

Verified end to end on Cursor over Remote-SSH (VS Code base 1.128.0): 15 breakpoints
applied to a real single-process inference run and confirmed by the editor.

```
sync done: desired=15 removed=14 added=14 debug.breakpoints now=15
```

Editor detection and staging are additionally exercised against a local macOS Cursor
install. Other combinations should work — the detection covers VS Code, Cursor and
code-server across Linux, macOS and Windows — but are not confirmed.

## Development

The bridge is TypeScript, compiled to `bridge/out/extension.js`, which is committed so
installs need only Python. After editing `bridge/src/extension.ts`:

```bash
cd skills/vscode-breakpoints
python3 scripts/install_bridge.py --rebuild   # needs Node 18+
# then in the editor: Developer: Reload Window
```

Reloading is required for a version change of an already-loaded extension; a brand-new
registration is picked up within about a second without one.

Useful while working on it:

```bash
python3 scripts/install_bridge.py --list       # every editor install detected
python3 scripts/install_bridge.py --dry-run    # what would change, writes nothing
python3 scripts/install_bridge.py --uninstall
cat /tmp/agent-breakpoints-diag.log            # what the bridge actually did
```
