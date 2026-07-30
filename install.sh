#!/usr/bin/env bash
# Install the skills from every plugin in this repo for any agent that reads
# ~/.claude/skills.
#
# If you use Claude Code plugins, prefer the plugin install in the README -- it
# handles updates, and it is the only way to install hooks. This script is for
# everything else, and for a checkout you intend to keep editing: the default is a
# symlink, so `git pull` is the update.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.claude/skills"
MODE=symlink
FORCE=0

usage() {
    cat <<'EOF'
Usage: ./install.sh [options]

  --project      install into ./.claude/skills instead of ~/.claude/skills
  --dest DIR     install into DIR
  --copy         copy the skills instead of symlinking them
  --force        replace anything already installed under those names
  -h, --help     show this

Default: symlink into ~/.claude/skills, so updating is `git pull`.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --project) DEST="$PWD/.claude/skills" ;;
        --dest)    shift; DEST="${1:?--dest needs a directory}" ;;
        --copy)    MODE=copy ;;
        --force)   FORCE=1 ;;
        -h|--help) usage; exit 0 ;;
        *)         echo "unknown option: $1" >&2; echo >&2; usage >&2; exit 2 ;;
    esac
    shift
done

mkdir -p "$DEST"

installed=0
for path in "$REPO"/plugins/*/skills/*/; do
    [ -d "$path" ] || continue
    name="$(basename "$path")"
    target="$DEST/$name"

    # An existing symlink to this same checkout is already what we would create.
    if [ -L "$target" ] && [ "$(readlink "$target")" = "${path%/}" ]; then
        echo "OK    $name already linked to this checkout"
        installed=$((installed + 1))
        continue
    fi

    if [ -e "$target" ] || [ -L "$target" ]; then
        if [ "$FORCE" -ne 1 ]; then
            echo "FAIL  $target already exists. Inspect it, then re-run with --force to replace it." >&2
            exit 1
        fi
        rm -rf "$target"
    fi

    if [ "$MODE" = copy ]; then
        cp -R "${path%/}" "$target"
    else
        ln -s "${path%/}" "$target"
    fi

    [ -f "$target/SKILL.md" ] || { echo "FAIL  $target/SKILL.md is not readable after install" >&2; exit 1; }
    echo "OK    $name -> $target"
    installed=$((installed + 1))
done

# Hooks are registered in settings, not installed by copying files, so this script
# cannot set them up. Say so rather than leaving the plugin half-installed silently.
hooked=0
for hooks in "$REPO"/plugins/*/hooks/hooks.json; do
    [ -f "$hooks" ] || continue
    plugin="$(basename "$(dirname "$(dirname "$hooks")")")"
    [ "$hooked" -eq 0 ] && echo
    hooked=$((hooked + 1))
    echo "NOTE  the '$plugin' plugin works through hooks, which this script cannot install."
    echo "      Install it as a plugin, or see its README to wire the hook in by hand."
done

if [ "$installed" -eq 0 ] && [ "$hooked" -eq 0 ]; then
    echo "FAIL  found no skills under $REPO/plugins/*/skills/" >&2
    exit 1
fi

echo
echo "Installed $installed skill(s) into $DEST."
echo "Start a new session so they are picked up."
