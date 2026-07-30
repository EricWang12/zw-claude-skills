---
name: user-sleep
description: The user is going to sleep or stepping away and cannot answer anything until they return. Use this skill the moment the user says they are going to bed, signing off, going AFK, leaving for the night, "keep going while I'm gone", "don't wait for me", "have it done by morning", or otherwise hands over work to finish unattended. From that point on, never ask the user a question and never wait for input — make every decision with your best judgment and log it for their review.
---

# User Sleep

The user has gone to sleep. Until they return, they cannot see questions, pick from
options, or approve plans. A question is no longer a conversation — it is a full stop
that freezes the work for hours, waiting on someone who is not there. So keep every
question to yourself and keep moving.

## The rule

Do not ask the user anything until the work is done or genuinely impossible. All of
these count as asking:

- Ending a message with "Should I…?", "Do you want…?", "Which do you prefer?"
- Interactive option menus (AskUserQuestion and the like) — a menu blocks exactly like
  a question
- Presenting a plan and waiting for sign-off
- Pausing partway to "check in"

When you have doubts, use your best judgment and decide *for* the user. A reasonable
decision made now beats a perfect answer tomorrow morning, because the reasonable
decision ships tonight and can still be revised tomorrow.

## Deciding when you would normally ask

Most questions have discoverable answers. Work down this list and take the first hit:

1. **The stated goal.** Choose whatever best serves what the user actually asked for.
2. **The project.** Existing conventions, configs, dependencies, and history settle
   most format, style, and tooling choices.
3. **The boring default.** If the project is silent, pick the standard, unsurprising
   option most people would expect.
4. **Reversibility.** Still torn? Take the choice that is easiest to undo later.

Then commit to it and move on — record the call in the morning report instead of
relitigating it.

## Autonomy is not recklessness

"Never ask" does not license risky action; it changes what you do *instead* of asking.
If an action is destructive, irreversible, or outward-facing — deleting things you are
not sure about, force-pushing, sending messages on the user's behalf, deploying,
spending money — and the user did not clearly authorize that specific action, then
neither ask nor do it. Set that piece aside, finish everything else, and flag it in the
morning report as awaiting their call. Losing one deferred subtask overnight is fine;
waking up to a surprise deletion is not.

## When you hit a wall

Missing credential, failing service, denied permission: do not stop the whole job.
Prefer routes that need no new approvals, try an alternative, and if a piece truly
cannot proceed, shelve it, finish the rest, and report what is left and why.

## The morning report

The user was not there to steer, so your final message must let them audit the
steering. End it with a **While you were asleep** section:

- Every question you would have asked, the answer you chose, and the reason in a phrase
- Anything deferred as too risky or blocked, and what you need from them
- Anything worth double-checking

This log is what makes the autonomy safe: every judgment call stays visible, and still
reversible in the morning.
