# kiss-rules

Three standing rules, injected into the top of every session:

1. **Keep it simple and stupid** — the straightforward solution, no speculative abstraction.
2. **Never commit unless asked** — no `git commit` on the agent's own initiative.
3. **No authorship in commit messages** — concise summary only, no `Co-Authored-By`, no
   "Generated with" footer.

The rules live in [`rules/RULES.md`](rules/RULES.md). Edit that one file to change them;
nothing else needs touching.

## How it works

A `SessionStart` hook runs [`hooks/session-start`](hooks/session-start), which prints
`rules/RULES.md` as `hookSpecificOutput.additionalContext`. The harness prepends that to
the session, so the rules are in context before the first message rather than waiting to
be discovered.

The matcher is `startup|clear|compact`, so the rules are re-injected after a `/clear` and
after a compaction. Without the last one, rules quietly evaporate partway through a long
session — which is exactly when they matter most.

A skill would be the wrong tool here. Skills are invoked when the model judges them
relevant, and a rule that only applies when someone remembers it is not a rule.

## What this does and does not guarantee

Two honest limits.

**Injected rules are instructions, not enforcement.** They raise compliance a great deal
and they survive compaction, but nothing mechanically prevents a violation.

**Subagents do not see them.** `SessionStart` fires once per session; a subagent dispatched
mid-session is not a new session, so the injected block is not in its context. If you hand
work to a subagent and the rules matter for it, put them in the dispatch prompt.

To make rule 2 mechanical rather than advisory, add this to your **own** settings
(`~/.claude/settings.json`) — a plugin cannot ship it, because plugin `settings.json`
honors only the `agent` and `subagentStatusLine` keys:

```json
{
  "permissions": {
    "ask": ["Bash(git commit)", "Bash(git commit *)"]
  }
}
```

Both entries are listed because the wildcard form does not match a bare `git commit` with
no arguments. Now an unasked commit stops and waits for you, and an asked-for commit costs
one keystroke — which is exactly what rule 2 describes. Check it landed with
`/permissions`.

That covers the main thread but not subagents. If you want the rule enforced everywhere,
the mechanism is a `PreToolUse` hook, which — unlike `SessionStart` — does fire for
subagent tool calls. It would return:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "kiss-rules: commits need explicit approval"
  }
}
```

That is deliberately not shipped here. One mechanism that works is worth more than two
that overlap, and this plugin's own first rule says not to build the second one until it
is needed.

## Install

As a plugin, from the repo root that contains this directory:

```
/plugin marketplace add YOUR-GITHUB-USERNAME/skill-vscode-debug
/plugin install kiss-rules@claude-plugins
```

Without the plugin system, register the hook yourself in `~/.claude/settings.json`, using
an absolute path — the script falls back to locating its own rules file when
`CLAUDE_PLUGIN_ROOT` is unset:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "/absolute/path/to/plugins/kiss-rules/hooks/session-start",
            "async": false
          }
        ]
      }
    ]
  }
}
```

`./install.sh` at the repo root does **not** install this plugin — it only handles skills,
and hooks have to be registered in settings.

## Checking it works

```bash
CLAUDE_PLUGIN_ROOT="$PWD" ./hooks/session-start | python3 -m json.tool
```

You should see the rules under `hookSpecificOutput.additionalContext`. In a live session,
`/context` shows the injected block.

If you edit `rules/RULES.md`, keep the `<user-standing-rules>` wrapper — it is what marks
the block as instructions rather than background reading.
