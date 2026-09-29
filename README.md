# zw-claude-skills

A personal plugin marketplace for **Claude Code and Codex**. Add it once, then install
whichever plugins you want. Both hosts use the exact same skills, scripts, references,
and rules from `plugins/`.

| Plugin | What it does |
| --- | --- |
| [**vscode-debug**](plugins/vscode-debug/README.md) | Places **real breakpoints** in the VS Code / Cursor gutter from a terminal — no injected `breakpoint()` calls — and turns a command that already works into a steppable walkthrough of the code |
| [**kiss-rules**](plugins/kiss-rules/README.md) | Injects three standing rules into every session: keep code simple, never commit unless asked, and no authorship trailers in commit messages |
| [**user-sleep**](plugins/user-sleep/README.md) | Tell the agent you're going to sleep: from then on it never asks questions or waits for input — it decides with best judgment, keeps working, and leaves a "while you were asleep" decision log |
| [**reproduce**](plugins/reproduce/README.md) | Paste a GitHub repo or project page: it clones, builds a short-named env, picks the biggest model that fits the *free* GPU memory, runs ≥3 verified demos, and publishes a flow artifact where the real examples ride through the flowchart |

## Install

### Claude Code

```
/plugin marketplace add EricWang12/zw-claude-skills
/plugin install vscode-debug@zw-claude-skills
/plugin install kiss-rules@zw-claude-skills
/plugin install user-sleep@zw-claude-skills
/plugin install reproduce@zw-claude-skills
```

The marketplace only needs adding once; after that, new plugins here are one
`/plugin install` away.

### Codex

From a local checkout, register this repository and install the plugins you want:

```bash
codex plugin marketplace add /absolute/path/to/zw-claude-skills
codex plugin add vscode-debug@zw-claude-skills
codex plugin add kiss-rules@zw-claude-skills
codex plugin add user-sleep@zw-claude-skills
codex plugin add reproduce@zw-claude-skills
```

Once the Codex support files are published to GitHub, the first command can instead be:

```bash
codex plugin marketplace add EricWang12/zw-claude-skills
```

Start a new Codex session after installation. You can also select **ZW Skills** in the
desktop app's Plugins Directory and install from there. Use a current Codex client with
plugin support; `codex plugin --help` lists the commands your version provides.

Ask naturally to use a workflow, or select `codeflow`, `vscode-breakpoints`, `user-sleep`,
or `reproduce` from Codex's skills picker. `kiss-rules` is a session hook, so it does not
add a skill. In the Codex CLI, open `/hooks` to review and trust its hook before relying
on the rules; installation alone does not trust hooks. It requires Bash and Python 3.

The Codex catalog is `.agents/plugins/marketplace.json`, and each plugin has a
`.codex-plugin/plugin.json` manifest pointing to its existing payload. The original
Claude Code catalog and manifests remain available. This uses the supported
[Codex compatibility manifest format](https://developers.openai.com/plugins/build/plugins).
See [Codex hooks](https://learn.chatgpt.com/docs/hooks) for hook trust and lifecycle support.

### Manual skills installation

**Without the plugin system**, `./install.sh` symlinks every plugin's skills into your
chosen skills directory:

```bash
git clone https://github.com/EricWang12/zw-claude-skills.git
cd zw-claude-skills
./install.sh              # symlink into ~/.claude/skills
./install.sh --project    # or into ./.claude/skills, per-project
./install.sh --copy       # copy instead of symlink

# Codex: the same skill directories, with all their supporting files
./install.sh --dest "$HOME/.agents/skills"
./install.sh --dest "$PWD/.agents/skills"  # per-project, relative to your current directory
```

Symlinking is the default so that `git pull` is the update. Start a new session afterwards
so the skills are picked up.

That script handles **skills only**. Install `kiss-rules` as a plugin to load its hook;
[its README](plugins/kiss-rules/README.md) also documents manual Claude Code hook setup.
Choose either plugin installation or manual skills installation to avoid loading the
same skills twice.

## Repo layout

```
.claude-plugin/marketplace.json      Claude Code catalog
.agents/plugins/marketplace.json     Codex catalog, with the same plugins
plugins/
  vscode-debug/
    .claude-plugin/plugin.json
    .codex-plugin/plugin.json
    README.md
    skills/vscode-breakpoints/       the breakpoint primitive
    skills/codeflow/                 command -> debug config -> breakpoints -> CODEFLOW.md
  kiss-rules/
    .claude-plugin/plugin.json
    .codex-plugin/plugin.json
    README.md
    rules/RULES.md                   the rules themselves; edit this one file
    hooks/hooks.json                 SessionStart -> inject the rules
    hooks/session-start
  user-sleep/
    .claude-plugin/plugin.json
    .codex-plugin/plugin.json
    README.md
    skills/user-sleep/               goodnight: no questions, best-judgment mode
  reproduce/
    .claude-plugin/plugin.json
    .codex-plugin/plugin.json
    README.md
    skills/reproduce/                repo link -> clone, env, best-fit model, 3 demos, flow artifact
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

For Codex support, also add `.codex-plugin/plugin.json` at the plugin root and an entry
to `.agents/plugins/marketplace.json`, following the existing plugins. Keep the name,
version, and description aligned with the Claude manifest. Declare `"skills": "./skills/"`
for a skills plugin or `"hooks": "./hooks/hooks.json"` for a hook plugin. Point both hosts
at the same payload directories so skill content cannot drift between them.

## Before you publish this repo

Placeholders that still need your details:

- `YOUR-GITHUB-USERNAME` in both plugin manifests (`plugins/*/.claude-plugin/plugin.json`)
- `YOUR-NAME` in [`LICENSE`](LICENSE)

## License

MIT — see [LICENSE](LICENSE).
