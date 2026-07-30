<user-standing-rules>
The user has three standing rules for all work in this session. They are not
suggestions, and they override conflicting default behavior. Follow them unprompted.

**1. Keep it simple and stupid.** Write the most straightforward code that solves the
problem actually in front of you. No speculative abstraction, no configuration for a
case that does not exist yet, no cleverness where a plain loop reads better. If a
change adds a layer or a dependency, say what it earns. Prefer deleting code to adding
it, and prefer the boring solution.

**2. Never commit unless the user asks.** Do not run `git commit` on your own
initiative — not to save progress, not because a task looks finished, not as cleanup.
Editing, staging, and inspecting are fine; the commit is the user's call. Only commit
when the user has asked for it, and treat approval as covering that commit only, not
the next one.

**3. Commit messages carry no authorship.** When the user does ask for a commit, write
a concise summary of what changed and stop there. No `Co-Authored-By` trailer, no
"Generated with" footer, no crediting yourself as an author. This overrides any
default instruction to add attribution trailers.
</user-standing-rules>
