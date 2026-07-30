"""Put breakpoints in the editor gutter, given file:line locations.

This is the whole primitive. It validates the locations, writes the manifest the
bridge extension watches, installs the bridge if it is missing, and then confirms the
editor actually applied them -- rather than assuming it did. The confirmation matters:
every silent failure mode in this system looks identical to success from the outside.

Machine-readable summary goes to stdout as JSON so a calling skill can branch on it.
Human-readable progress goes to stderr, so piping stdout stays clean.

    # simple: locations plus a note each
    python3 scripts/apply_breakpoints.py \
        --set 'src/main.py:42:entry point' \
        --set 'src/loop.py:88:first iteration only'

    # full control (guards, enabled state) -- what a calling skill normally uses
    echo '[{"file":"src/loop.py","line":88,"condition":"i == 0","note":"3. per-item"}]' \
        | python3 scripts/apply_breakpoints.py --json -

    python3 scripts/apply_breakpoints.py --json plan.json --repo /path/to/repo
    python3 scripts/apply_breakpoints.py --clear
    python3 scripts/apply_breakpoints.py --json plan.json --append --dry-run

Exit status is 0 only when the breakpoints were written AND the editor confirmed them,
so a caller can treat non-zero as "do not tell the user this worked".
"""

import argparse
import ast
import json
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
DIAG_LOG = Path("/tmp/agent-breakpoints-diag.log")
SPEC_RE = re.compile(r"^(?P<file>.*?):(?P<line>\d+)(?::(?P<note>.*))?$")

# Fields the bridge understands. Anything else in an entry is dropped with a warning
# rather than written through, so a typo does not silently become a no-op guard.
PASSTHROUGH = ("file", "line", "enabled", "condition", "hitCondition", "logMessage", "note")


def _log(message):
    print(message, file=sys.stderr)


def _default_repo():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10, check=True
        )
        return Path(out.stdout.strip())
    except (subprocess.SubprocessError, OSError):
        return Path.cwd()


def _parse_spec(spec):
    match = SPEC_RE.match(spec)
    if not match:
        raise ValueError(f"cannot parse --set {spec!r}; expected file:line or file:line:note")
    entry = {"file": match.group("file"), "line": int(match.group("line"))}
    if match.group("note"):
        entry["note"] = match.group("note")
    return entry


def _load_json(source):
    raw = sys.stdin.read() if source == "-" else Path(source).read_text()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc
    entries = data if isinstance(data, list) else data.get("breakpoints", [])
    if not isinstance(entries, list):
        raise ValueError("expected a JSON array, or an object with a 'breakpoints' array")
    return entries


def _validate(entries, repo, advance_defs=True):
    """Drop entries that cannot produce a working breakpoint, with a reason for each.

    Line numbers drift as code moves. A breakpoint on a line that has become blank, a
    comment, or past end-of-file will not bind -- or worse, binds somewhere unrelated
    and teaches the reader the wrong flow. Catching it here is much cheaper than
    letting someone discover it mid-session.
    """
    good, skipped, adjusted = [], [], []
    cache = {}
    def_map = {}

    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            skipped.append({"index": index, "reason": "entry is not an object"})
            continue

        entry = {k: v for k, v in raw.items() if k in PASSTHROUGH}
        for key in set(raw) - set(PASSTHROUGH):
            if not key.startswith("//"):
                _log(f"WARN  entry {index}: dropping unknown field {key!r}")

        file_field, line = entry.get("file"), entry.get("line")
        label = f"{file_field}:{line}"

        if not isinstance(file_field, str) or not file_field:
            skipped.append({"index": index, "reason": "missing 'file'"})
            continue
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            skipped.append({"index": index, "target": label, "reason": f"'line' must be a positive integer, got {line!r}"})
            continue

        target = Path(file_field)
        if not target.is_absolute():
            target = repo / target
        if not target.is_file():
            skipped.append({"index": index, "target": label, "reason": "file does not exist"})
            continue

        # Refuse files outside the workspace. The editor syncs one manifest per open
        # workspace, so a breakpoint on an outside file cannot bind -- and the tempting
        # workaround, writing it into the open workspace's manifest by absolute path,
        # silently replaces breakpoints belonging to whatever else is using that file.
        # Better to refuse here than to let a caller destroy unrelated state.
        try:
            outside = repo.resolve() not in target.resolve().parents
        except OSError:
            outside = False
        if outside:
            skipped.append({"index": index, "target": label,
                            "reason": f"outside the workspace root {repo} -- open that folder as the workspace, or pass --repo"})
            continue

        if target not in cache:
            try:
                cache[target] = target.read_text(errors="replace").splitlines()
            except OSError as exc:
                cache[target] = None
                _log(f"WARN  {label}: unreadable ({exc}); trusting the entry")
        lines = cache[target]

        if lines is not None:
            if line > len(lines):
                skipped.append({"index": index, "target": label, "reason": f"past EOF ({len(lines)} lines) -- stale"})
                continue

            # Move a `def`/`class` header onto the first line of the body. Stopping on the
            # header would fire once at import and never on a call, so the intent behind
            # "break in this function" is only served by the body line.
            if advance_defs and target.suffix == ".py":
                if target not in def_map:
                    def_map[target] = _first_body_line(target)
                moved_to = def_map[target].get(line)
                if moved_to and moved_to != line and moved_to <= len(lines):
                    adjusted.append({
                        "target": label,
                        "from": line,
                        "to": moved_to,
                        "reason": "def/class header runs at import, not per call -- moved to first body line",
                        "source": lines[moved_to - 1].strip()[:100],
                    })
                    line = moved_to
                    entry["line"] = moved_to
                    label = f"{file_field}:{line}"

            source = lines[line - 1].strip()
            if not source or source.startswith("#") or source.startswith("//"):
                skipped.append({"index": index, "target": label, "reason": f"line is blank or a comment: {source[:60]!r}"})
                continue
            entry["//source"] = source[:120]

        good.append(entry)

    return good, skipped, adjusted


def _first_body_line(path):
    """Map every `def`/`class` header line to the first executable line of its body.

    A `def` statement runs once, when the module is imported -- it is the statement that
    creates the function object. A breakpoint on that line therefore fires at import time
    and never when the function is called, which is almost never what someone wants and is
    confusing because the breakpoint does appear to bind. The same applies to continuation
    lines of a multi-line signature.

    Returns {header_or_signature_line: first_body_line} so any of those lines can be moved
    onto the first statement that actually runs per call.
    """
    try:
        tree = ast.parse(Path(path).read_text(errors="replace"))
    except (OSError, SyntaxError, ValueError):
        return {}

    mapping = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        # A docstring is a constant expression: stopping on it shows nothing useful, so
        # prefer the next statement when there is one.
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
            and len(body) > 1
        ):
            first = body[1]
        target = first.lineno
        # node.lineno is the `def`/`class` line itself (decorators carry their own linenos),
        # so this span covers the header plus any signature continuation lines.
        for line in range(node.lineno, target):
            mapping.setdefault(line, target)
    return mapping


def _bridge_installed():
    """The bridge announces itself by writing the diag log on activate."""
    return DIAG_LOG.is_file()


def _install_bridge(dry_run):
    installer = SCRIPTS / "install_bridge.py"
    if dry_run:
        _log("DRY   would run install_bridge.py")
        return {"installed": False, "action": "dry-run"}
    _log("      bridge not detected; installing ...")
    result = subprocess.run([sys.executable, str(installer)], capture_output=True, text=True)
    for line in (result.stdout + result.stderr).splitlines():
        _log(f"      | {line}")
    if result.returncode != 0:
        return {"installed": False, "action": "install-failed", "returncode": result.returncode}
    return {"installed": True, "action": "installed"}


def _wait_for_sync(baseline_offset, expected, timeout):
    """Poll the bridge's log for a sync newer than our write.

    Reading from a byte offset captured before the write means we only ever look at
    lines this run caused, so a stale success from a previous run cannot be mistaken
    for confirmation.
    """
    deadline = time.monotonic() + timeout
    last_seen = ""
    while time.monotonic() < deadline:
        if DIAG_LOG.is_file():
            with DIAG_LOG.open("r", errors="replace") as handle:
                handle.seek(baseline_offset)
                fresh = handle.read()
            for line in fresh.splitlines():
                if "sync done:" in line:
                    last_seen = line
                    match = re.search(r"now=(\d+)", line)
                    applied = int(match.group(1)) if match else None
                    if applied is None or applied >= expected:
                        return {"verified": True, "applied": applied, "diag_line": line.strip()}
        time.sleep(0.3)
    return {"verified": False, "applied": None, "diag_line": last_seen.strip() or None}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", dest="specs", action="append", default=[], metavar="FILE:LINE[:NOTE]",
                        help="A breakpoint location. Repeatable. Use --json for guards.")
    parser.add_argument("--json", dest="json_source", metavar="PATH",
                        help="JSON array of entries, or an object with a 'breakpoints' array. '-' reads stdin.")
    parser.add_argument("--clear", action="store_true", help="Remove all agent-managed breakpoints.")
    parser.add_argument("--append", action="store_true", help="Merge into the existing manifest instead of replacing it.")
    parser.add_argument("--repo", help="Workspace root (default: git toplevel, else cwd).")
    parser.add_argument("--manifest", default=".vscode/breakpoints.json", help="Manifest path, relative to the repo.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report; write nothing.")
    parser.add_argument("--no-install", action="store_true", help="Do not install the bridge if it is missing.")
    parser.add_argument("--allow-def-lines", action="store_true",
                        help="Keep breakpoints on `def`/`class` header lines instead of moving them to the first body "
                             "line. Those fire once at import, not per call -- only useful to observe import itself.")
    parser.add_argument("--no-verify", action="store_true", help="Skip waiting for the editor to confirm.")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for confirmation (default 15).")
    args = parser.parse_args()

    if not (args.specs or args.json_source or args.clear):
        parser.error("give at least one of --set, --json, or --clear")

    repo = Path(args.repo).expanduser().resolve() if args.repo else _default_repo()
    if not repo.is_dir():
        _log(f"FAIL  repo not found: {repo}")
        return 2
    manifest_path = repo / args.manifest

    try:
        requested = [] if args.clear else [_parse_spec(s) for s in args.specs] + (
            _load_json(args.json_source) if args.json_source else []
        )
    except (ValueError, OSError) as exc:
        _log(f"FAIL  {exc}")
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2

    _log(f"OK    repo {repo}")
    entries, skipped, adjusted = _validate(requested, repo, advance_defs=not args.allow_def_lines)

    if args.append and manifest_path.is_file() and not args.clear:
        try:
            existing = _load_json(str(manifest_path))
        except (ValueError, OSError):
            existing = []
        seen = {(e.get("file"), e.get("line")) for e in entries}
        entries = [e for e in existing if (e.get("file"), e.get("line")) not in seen] + entries

    for item in adjusted:
        _log(f"MOVED {item['target']} -> line {item['to']}  ({item['reason']})\n      now on: {item['source']}")
    for item in skipped:
        target = item.get("target") or f"entry {item['index']}"
        _log(f"SKIP  {target}: {item['reason']}")

    summary = {
        "ok": False,
        "repo": str(repo),
        "manifest": str(manifest_path),
        "requested": len(requested),
        "written": len(entries),
        "skipped": skipped,
        "adjusted": adjusted,
        "dry_run": args.dry_run,
    }

    if args.dry_run:
        _log(f"DRY   would write {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} to {manifest_path}")
        summary["ok"] = not skipped
        print(json.dumps(summary, indent=2))
        return 0 if not skipped else 1

    bridge = {"installed": True, "action": "already-present"}
    if not _bridge_installed():
        bridge = {"installed": False, "action": "absent"} if args.no_install else _install_bridge(args.dry_run)
    summary["bridge"] = bridge

    baseline_offset = DIAG_LOG.stat().st_size if DIAG_LOG.is_file() else 0

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "//": "Managed by the vscode-breakpoints skill. Edits are overwritten on the next apply.",
        "version": 1,
        "breakpoints": entries,
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n")
    _log(f"OK    wrote {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} to {manifest_path}")

    if args.no_verify:
        summary["ok"] = True
        summary["verified"] = None
        print(json.dumps(summary, indent=2))
        return 0

    result = _wait_for_sync(baseline_offset, len(entries), args.timeout)
    summary.update(result)
    summary["ok"] = bool(result["verified"])

    if result["verified"]:
        _log(f"OK    editor confirmed: {result['diag_line']}")
    else:
        _log(
            f"FAIL  no confirmation within {args.timeout:g}s. The manifest is written, but the editor did not apply it.\n"
            "      Most likely the bridge is not loaded in the ACTIVE editor profile -- see references/troubleshooting.md.\n"
            "      Check:  python3 scripts/install_bridge.py --list"
        )

    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
