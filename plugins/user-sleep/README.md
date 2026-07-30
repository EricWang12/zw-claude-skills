# user-sleep

One skill: tell Claude you are going to sleep, and it stops asking.

Say "I'm going to bed, finish the refactor" (or `/user-sleep`, or "going AFK", "have it
ready by morning") and from that point on the agent treats every question as what it
really is while you are unavailable — a full stop that blocks the work until you wake.
Instead of asking, it:

1. **Decides for you**, in order of preference: what serves your stated goal, what the
   project's own conventions imply, the boring standard default, and failing all that,
   whichever option is easiest to reverse.
2. **Refuses to confuse autonomy with recklessness** — destructive, irreversible, or
   outward-facing actions you didn't clearly authorize are neither asked about nor
   done; they are deferred with a note.
3. **Keeps going around obstacles** — a blocked subtask gets shelved and reported, not
   turned into a stalled session.
4. **Leaves a morning report** — a "While you were asleep" section listing every
   question it would have asked, the answer it chose, and anything deferred for you.

The skill lives in [`skills/user-sleep/SKILL.md`](skills/user-sleep/SKILL.md). Edit
that one file to change the behavior.

## What this does and does not guarantee

Two honest limits.

**It is instructions, not enforcement.** The skill strongly steers the model away from
asking, but nothing mechanically prevents a question.

**It cannot suppress the harness's own permission prompts.** If a tool call needs
approval under your current permission settings, Claude Code will still stop and wait —
the skill only tells the model to prefer routes that avoid new approvals. For a truly
unattended run, set the permission mode you are comfortable with (`/permissions`, or
auto-accept edits) before you log off.

## Install

As a plugin, from the marketplace this repo publishes:

```
/plugin marketplace add EricWang12/zw-claude-skills
/plugin install user-sleep@zw-claude-skills
```

Without the plugin system, `./install.sh` at the repo root symlinks the skill into
`~/.claude/skills`.
