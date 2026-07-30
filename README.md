# zw-claude-skills

A personal Claude Code plugin marketplace. Add it once, then install whichever plugins you
want.

| Plugin | What it does |
| --- | --- |
| [**vscode-debug**](plugins/vscode-debug/README.md) | Places **real breakpoints** in the VS Code / Cursor gutter from a terminal — no injected `breakpoint()` calls — and turns a command that already works into a steppable walkthrough of the code |
| [**kiss-rules**](plugins/kiss-rules/README.md) | Injects three standing rules into every session: keep code simple, never commit unless asked, and no authorship trailers in commit messages |

## Install

```
/plugin marketplace add EricWang12/zw-claude-skills
/plugin install vscode-debug@zw-claude-skills
/plugin install kiss-rules@zw-claude-skills
```

The marketplace only needs adding once; after that, new plugins here are one
`/plugin install` away.

**Without the plugin system**, `./install.sh` symlinks every plugin's skills into
`~/.claude/skills`:

```bash
git clone https://github.com/EricWang12/zw-claude-skills.git
cd zw-claude-skills
./install.sh              # symlink into ~/.claude/skills
./install.sh --project    # or into ./.claude/skills, per-project
./install.sh --copy       # copy instead of symlink
```

Symlinking is the default so that `git pull` is the update. Start a new session afterwards
so the skills are picked up.

That script handles **skills only**. `kiss-rules` works through a hook, which has to be
registered in settings — see [its README](plugins/kiss-rules/README.md) for the four lines
of JSON, or just install it as a plugin.

## Repo layout

```
.claude-plugin/marketplace.json      the index; every plugin is listed here
plugins/
  vscode-debug/
    .claude-plugin/plugin.json
    README.md
    skills/vscode-breakpoints/       the breakpoint primitive
    skills/codeflow/                 command -> debug config -> breakpoints -> CODEFLOW.md
  kiss-rules/
    .claude-plugin/plugin.json
    README.md
    rules/RULES.md                   the rules themselves; edit this one file
    hooks/hooks.json                 SessionStart -> inject the rules
    hooks/session-start
docs/AGENT-GUIDE.md                  how terminal-driven breakpoints work, portably
install.sh                           manual install of every plugin's skills
```

## Adding another plugin

Three steps, no ceremony:

```bash
mkdir -p plugins/my-plugin/.claude-plugin
```

1. Write `plugins/my-plugin/.claude-plugin/plugin.json` with at minimum a `name`. It must
   be lowercase kebab-case — uppercase is not valid.
2. Add an entry to the `plugins` array in `.claude-plugin/marketplace.json`:
   `{ "name": "my-plugin", "source": "./plugins/my-plugin", "description": "..." }`
3. Put the payload at the plugin root — `skills/<name>/SKILL.md`, `agents/`, `commands/`,
   `hooks/hooks.json`. Everything is optional, and nothing except `plugin.json` goes
   inside `.claude-plugin/`.

Which component to reach for is the part worth getting right. Skills are invoked when the
model judges them relevant, so they suit on-demand procedures. A rule that must always
apply belongs in a `SessionStart` hook instead, and a rule that must be *enforced* belongs
in a `PreToolUse` hook — that one also fires for subagent tool calls, which
`SessionStart` does not.

Renaming the marketplace later forces everyone who added it to remove and re-add it, so
`zw-claude-skills` in `.claude-plugin/marketplace.json` is worth settling before you publish.
Individual plugin names are free to change any time.

## Before you publish this repo

Placeholders that still need your details:

- `YOUR-GITHUB-USERNAME` in both plugin manifests (`plugins/*/.claude-plugin/plugin.json`)
- `YOUR-NAME` in [`LICENSE`](LICENSE)

## License

MIT — see [LICENSE](LICENSE).
