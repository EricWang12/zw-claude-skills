"""Build and register the Agent Breakpoints extension into VS Code / Cursor.

Works on any machine -- local or remote, VS Code or Cursor or code-server, Linux or
macOS or Windows. Detection is code rather than a documented path table because the
layouts differ per OS and per variant, and a table rots.

The reason this is a script and not a click-path: an editor keeps TWO kinds of
extension manifest, and writing only the obvious one silently does nothing.

    <extensions>/extensions.json                 application-wide ("default profile")
    <userData>/profiles/<id>/extensions.json     per-profile, and this is what a
                                                 running window actually loads

A window on a custom profile ignores the application-wide list entirely. The failure
is silent -- the extension is on disk, the entry looks right, and it never activates.
This registers into the application list AND every profile it finds, which is correct
regardless of which profile is active. A spare entry in an unused profile is harmless.

Most callers do not run this directly -- apply_breakpoints.py invokes it when the
bridge is missing. Run it by hand to inspect or repair an installation.

    python3 scripts/install_bridge.py --list      # detected installations, change nothing
    python3 scripts/install_bridge.py --dry-run   # report what would change
    python3 scripts/install_bridge.py             # stage and register everywhere
    python3 scripts/install_bridge.py --rebuild   # recompile from src/ first (needs Node)
    python3 scripts/install_bridge.py --uninstall
    python3 scripts/install_bridge.py --server ~/.cursor-server   # override detection

The compiled bridge is committed, so installing needs only Python 3.8+.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

EXT_ID = "local.agent-breakpoints"
VERSION = "0.2.0"
REL_DIR = f"{EXT_ID}-{VERSION}"

# Identifiers this extension used to ship under. Deregistered alongside the current
# one, because two copies watching the same manifest both call addBreakpoints() and
# the user gets every breakpoint twice.
LEGACY_EXT_IDS = ("nflx-local.agent-breakpoints",)

# The extension source is bundled at <skill>/bridge/ so this works in any repo,
# with no dependency on where the skill happens to be checked out.
HERE = Path(__file__).resolve().parent.parent / "bridge"


class Layout:
    """One editor installation: where extensions live, and where per-profile state lives.

    Remote installs keep both under one server directory. Local installs split them --
    extensions in the home directory, user data under an OS-specific application path.
    """

    def __init__(self, label: str, extensions_dir: Path, user_data_dir: Path):
        self.label = label
        self.extensions_dir = extensions_dir
        self.user_data_dir = user_data_dir

    def exists(self) -> bool:
        return self.extensions_dir.is_dir()

    def last_active(self) -> float:
        """Freshest mtime across logs and manifests. Several installs can coexist; only one is in use."""
        stamps = [0.0]
        for logs in (self.user_data_dir.parent / "logs", self.extensions_dir.parent / "data" / "logs"):
            if logs.is_dir():
                stamps.extend(p.stat().st_mtime for p in logs.glob("*"))
        for manifest in self.manifests():
            stamps.append(manifest.stat().st_mtime)
        return max(stamps)

    def manifests(self) -> list[Path]:
        """Every manifest that could govern loading.

        Both must be written. A window on a custom profile reads ONLY the profile
        manifest and ignores the application-wide one, so writing just the obvious
        file is a silent no-op.
        """
        found = [self.extensions_dir / "extensions.json"]
        profiles = self.user_data_dir / "profiles"
        if profiles.is_dir():
            found.extend(sorted(profiles.glob("*/extensions.json")))
        return [p for p in found if p.is_file()]


def _candidate_layouts() -> list[Layout]:
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    mac_app = home / "Library" / "Application Support"
    out = [
        # Remote / server installs keep extensions and user data together.
        Layout("cursor-remote", home / ".cursor-server" / "extensions", home / ".cursor-server" / "data" / "User"),
        Layout("vscode-remote", home / ".vscode-server" / "extensions", home / ".vscode-server" / "data" / "User"),
        Layout("vscode-remote-alt", home / ".vscode-remote" / "extensions", home / ".vscode-remote" / "data" / "User"),
        Layout("code-server", home / ".local" / "share" / "code-server" / "extensions", home / ".local" / "share" / "code-server" / "User"),
    ]
    for name, ext_dir in (("vscode", home / ".vscode"), ("cursor", home / ".cursor")):
        product = "Code" if name == "vscode" else "Cursor"
        for plat, user_dir in (
            ("linux", home / ".config" / product / "User"),
            ("macos", mac_app / product / "User"),
            ("windows", appdata / product / "User"),
        ):
            out.append(Layout(f"{name}-local-{plat}", ext_dir / "extensions", user_dir))
    return out


def _pick_layout(explicit: str | None, show_all: bool) -> Layout:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        # Accept either the server root or the extensions dir itself.
        ext_dir = root / "extensions" if (root / "extensions").is_dir() else root
        if not ext_dir.is_dir():
            sys.exit(f"FAIL  {root} has no extensions directory")
        for cand in _candidate_layouts():
            if cand.extensions_dir == ext_dir and cand.user_data_dir.is_dir():
                return cand
        return Layout("explicit", ext_dir, root / "data" / "User")

    found = [c for c in _candidate_layouts() if c.exists()]
    if not found:
        sys.exit("FAIL  found no VS Code / Cursor installation; pass --server")

    found.sort(key=lambda c: c.last_active(), reverse=True)
    if show_all or len(found) > 1:
        for cand in found:
            stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(cand.last_active())) if cand.last_active() else "never"
            profiles = len(cand.manifests()) - 1
            print(f"      candidate {cand.label:<22} {cand.extensions_dir}  (active {stamp}, {profiles} profile(s))")
    return found[0]


def _build(force: bool = False) -> None:
    """Ensure out/extension.js exists, compiling only when it has to.

    The compiled bridge is committed, so a fresh clone installs with nothing but
    Python -- which matters because the machines that need this most, headless
    remotes, are the least likely to have a Node toolchain. Recompiling is for
    people editing src/extension.ts.
    """
    out = HERE / "out" / "extension.js"
    if out.is_file() and not force:
        print(f"OK    using bundled {out.relative_to(HERE)}  (--rebuild to recompile from src/)")
        return
    if shutil.which("npm") is None:
        sys.exit(
            "FAIL  npm not found, so the bridge cannot be compiled.\n"
            "      Install Node 18+ and re-run, or restore the committed build at\n"
            f"      {out}"
        )
    if not (HERE / "node_modules").is_dir():
        print("      npm install ...")
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=HERE, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(HERE / "node_modules" / ".bin" / "tsc"), "-p", "."], cwd=HERE, check=True)
    if not out.is_file():
        sys.exit("FAIL  compile produced no out/extension.js")
    print(f"OK    compiled {out.relative_to(HERE)}")


def _stage(layout: Layout, dry_run: bool) -> Path:
    dest = layout.extensions_dir / REL_DIR
    if dry_run:
        print(f"DRY   would stage -> {dest}")
        return dest
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "out").mkdir(parents=True)
    shutil.copy2(HERE / "package.json", dest / "package.json")
    for name in ("extension.js", "extension.js.map"):
        src = HERE / "out" / name
        if src.is_file():
            shutil.copy2(src, dest / "out" / name)
    print(f"OK    staged -> {dest}")
    return dest


def _purge_legacy(layout: Layout, dry_run: bool) -> None:
    """Delete staged copies of earlier extension IDs. Registration is dropped in _register."""
    for legacy in LEGACY_EXT_IDS:
        for old in sorted(layout.extensions_dir.glob(f"{legacy}-*")):
            if dry_run:
                print(f"DRY   would delete superseded {old}")
            else:
                shutil.rmtree(old, ignore_errors=True)
                print(f"OK    deleted superseded {old}")


def _register(manifest: Path, dest: Path, remove: bool, dry_run: bool) -> str:
    try:
        entries = json.loads(manifest.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return f"SKIP  {manifest} unreadable ({exc})"

    superseded = {EXT_ID, *LEGACY_EXT_IDS}
    before = len(entries)
    entries = [e for e in entries if e.get("identifier", {}).get("id") not in superseded]
    existed = len(entries) != before

    if not remove:
        entries.append(
            {
                "identifier": {"id": EXT_ID},
                "version": VERSION,
                "location": {"$mid": 1, "path": str(dest), "scheme": "file"},
                "relativeLocation": REL_DIR,
                "metadata": {"installedTimestamp": int(time.time() * 1000), "source": "vsix"},
            }
        )

    verb = "would remove" if remove else ("would update" if existed else "would add")
    if dry_run:
        return f"DRY   {verb} in {manifest} ({len(entries)} entries after)"

    backup = manifest.with_suffix(".json.bak-agentbp")
    if not backup.exists():
        shutil.copy2(manifest, backup)
    tmp = manifest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    # Atomic swap, and the mtime bump is what invalidates the editor's scan cache.
    os.replace(tmp, manifest)
    return f"OK    {'removed from' if remove else 'registered in'} {manifest} ({len(entries)} entries)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", help="Editor root or extensions dir (default: auto-detect the most recently active).")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change and exit.")
    parser.add_argument("--uninstall", action="store_true", help="Deregister and delete the staged extension.")
    parser.add_argument("--rebuild", action="store_true", help="Recompile from src/ rather than using the committed build. Needs Node.")
    parser.add_argument("--skip-build", action="store_true", help="Register out/ exactly as it stands, never compiling.")
    parser.add_argument("--list", action="store_true", help="List every detected installation and exit.")
    args = parser.parse_args()

    layout = _pick_layout(args.server, show_all=args.list)
    if args.list:
        return 0
    print(f"OK    {layout.label}  extensions={layout.extensions_dir}  userData={layout.user_data_dir}")

    manifests = layout.manifests()
    if not manifests:
        sys.exit(
            f"FAIL  no extensions.json under {layout.extensions_dir} or {layout.user_data_dir}/profiles.\n"
            "      Open the editor once so it creates them, then re-run."
        )
    print(f"OK    {len(manifests)} manifest(s) to update:")
    for m in manifests:
        scope = "application" if m.parent == layout.extensions_dir else f"profile {m.parent.name}"
        print(f"        {scope:<20} {m}")

    dest = layout.extensions_dir / REL_DIR
    _purge_legacy(layout, args.dry_run)
    if not args.uninstall:
        if not args.skip_build:
            _build(force=args.rebuild)
        dest = _stage(layout, args.dry_run)

    for m in manifests:
        print(_register(m, dest, remove=args.uninstall, dry_run=args.dry_run))

    if args.uninstall and not args.dry_run and dest.exists():
        shutil.rmtree(dest)
        print(f"OK    deleted {dest}")

    if args.dry_run:
        print("\nDRY   nothing written")
        return 0

    if args.uninstall:
        print("\nDone. Reload the window to drop the extension.")
        return 0

    print(
        "\nDone. The editor watches the profile manifest, so it normally activates within a second.\n"
        "If nothing appears, run 'Developer: Reload Window', then check /tmp/agent-breakpoints-diag.log."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
