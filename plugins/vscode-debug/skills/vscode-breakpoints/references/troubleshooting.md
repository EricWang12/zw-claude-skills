# Troubleshooting

Read this when `apply_breakpoints.py` reports `verified: false`, or when breakpoints
do not appear in the gutter.

## First: what state is the bridge in?

```bash
python3 scripts/install_bridge.py --list     # which editor installs exist
cat /tmp/agent-breakpoints-diag.log         # what the bridge did, if anything
```

The diag log is the ground truth. The bridge writes it on every activate and every
sync. A healthy sync looks like:

```
activate: editor=1.128.0 extension=local.agent-breakpoints
activate: workspaceFolders=["/path/to/repo"]
manifest parsed: 20 usable entries, 0 problem(s)
sync done: desired=20 removed=0 added=20 debug.breakpoints now=20
```

The log is a file rather than only an output channel because the extension host often
runs on a remote machine while the UI runs on a laptop — an output channel is readable
only by someone sitting at the editor, which is no help to an agent.

## Symptom table

| What you see in the diag log | Cause | Fix |
| --- | --- | --- |
| File does not exist at all | The bridge never activated | Profile trap, below |
| `activate:` lines but no `sync` after a write | Manifest is outside the workspace root | Compare `activate: workspaceFolders` with the `manifest` path in the JSON output |
| `sync start` then nothing | Sync stalled mid-run | Stale bridge build; reinstall and reload (see below) |
| `manifest parsed: 0 usable entries` | Manifest unreadable or empty at that path | Check the path in the JSON output actually exists |
| `sync done` with `added=0` | Breakpoints already existed on those lines | Not a failure. Hand-placed breakpoints are never overwritten |
| `problem: ... past EOF` / `blank or a comment` | Line numbers are stale | Re-read the source and fix the lines |
| Confirmed, but nothing is hit at runtime | Breakpoint is on an unreached branch | Check which branch the launch config actually takes; try a `stopOnEntry` config to prove the debugger attached |

## The profile trap

This is the most common cause of a total no-show, and it produces no error anywhere.

An editor keeps two kinds of extension manifest:

```
<extensions>/extensions.json                 application-wide ("default profile")
<userData>/profiles/<id>/extensions.json     per-profile
```

A window running a custom profile loads from **the profile manifest only**. Register
into the application-wide list alone and the extension sits on disk with a
correct-looking entry, logs no error, never activates, and does not appear in the
Extensions list.

`install_bridge.py` writes to every manifest it finds precisely so this cannot happen.
If you installed by hand, re-run it.

Note that the editor's own log line
`Added extensions to default profile from external source [...]` reads as success but
is the symptom — it means the extension was filed where the active profile does not
look.

## When a reload is genuinely needed

Two cases need `Developer: Reload Window`, and **only the user can do it** — say so
rather than retrying:

- **Version change of an already-loaded bridge.** A brand-new registration is picked
  up within about a second, because the editor watches the profile manifest. Swapping
  the version of an extension already loaded in memory is not hot-reloaded; the old
  code keeps running until the extension host restarts.
- **The bridge was never loaded** (profile trap, just fixed).

After a reload, confirm from the log rather than asking the user to look:

```bash
python3 scripts/apply_breakpoints.py --json plan.json --timeout 30
```

## Sync latency

Watcher latency depends on the filesystem. On local disk a manifest write is picked up
essentially immediately. On network or FUSE-backed workspaces, watcher events have been
observed arriving ~19 s late, which is longer than a naive timeout allows.

The bridge therefore polls the manifest mtime every 2 s as well as watching it, so the
delay is bounded even where events are unreliable. If you are on a slow mount and still
see timeouts, raise `--timeout`; the manifest is already written, so waiting longer
costs nothing.

## Reinstalling from scratch

```bash
python3 scripts/install_bridge.py --uninstall
python3 scripts/install_bridge.py
# then: Developer: Reload Window
```

Every manifest is backed up to `extensions.json.bak-agentbp` before first modification.

## Things that are not worth trying

- **Editing `state.vscdb`.** Breakpoint UI state lives there under key
  `debug.breakpoint`, but on any remote setup the file is on the user's laptop and
  absent from the machine you are on. Locally it is reachable but unsupported, needs a
  reload anyway, and can corrupt workspace state.
- **`contributes.languageModelTools` / `vscode.lm.registerTool`.** Looks like the right
  answer for an agent-callable tool. It is a VS Code + Copilot Chat API, missing from
  some forks, and reachable only from an in-editor chat agent — never from a terminal.
  The watched manifest works for every caller.
- **Retrying the same apply repeatedly.** If the bridge is not loaded, the manifest is
  already correct and rewriting it changes nothing. Fix the install or ask for a reload.
