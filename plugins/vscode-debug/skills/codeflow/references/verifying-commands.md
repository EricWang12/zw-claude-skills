# Finding and proving the command

The command is the foundation. Everything else — the debug config, the breakpoints, the
doc — is derived from it, so a wrong command invalidates all of it at once.

## Mining each source

**The conversation you were given.** Usually the best source, because it shows a command
someone actually iterated on until it worked, including the corrections. Look for the last
version, not the first — earlier attempts in a session are often the broken ones.

**Launch scripts.** `train_*.sh`, `run_*.sh`, `submit_*.py`. These carry the flags that
matter in practice and often a comment explaining a hard-won value ("batch 24 is the
sustainable max; 32 OOMs after a few thousand steps"). That comment is worth more than the
flag — it belongs in the doc.

**Ops docs.** RUNBOOK, INFERENCE.md, README run sections. Treat as level-3 evidence: they
describe intent and can lag the code. Cross-check paths and flags against the source.

**Test smokes.** `tests/run_*_smoke.sh` are the quiet winners. They are usually the only
commands *guaranteed* to run on the local machine, they exercise the real entry point, and
they are kept working by CI. A smoke through the same code path teaches the same flow as
the production command at a fraction of the cost.

To read one, resolve its shell variables — the actual invocation is often assembled from a
`COMMON="..."` string plus per-arm additions, so grep for both the launcher line and the
variable definitions.

**Shell history and job logs.** `history`, prior submissions, log headers. Job logs are
strong evidence: a log means it ran. Check the header for the full argv, which many
trainers print at startup.

**Tracked launch configs.** Where a repo keeps per-run configs under version control, those
are both current and reviewed.

## The proof ladder

Stop at the first level you reach and record which one it was.

| Level | Evidence | Strength |
| --- | --- | --- |
| 1 | Prior successful run — logs, checkpoints, job history | It ran |
| 2 | Tracked launch config or launch script in current use | It is what people run |
| 3 | Ops doc documenting it as the procedure | It is intended to work |
| 4 | You ran it, shrunk to 1-2 steps and one process | You saw it start |
| 5 | Nothing | Mark unverified, prominently |

Level 4 means shrunk: one process, one or two steps, smallest input. The goal is proving
the thing starts and reaches the interesting code, not producing a result.

**Never submit a full multi-GPU or cluster job to verify.** It is slow, it costs shared
capacity, and it proves nothing that a tiny local run does not.

## Cheap preconditions worth checking regardless

These take seconds and catch most F5 failures:

- entry script exists at the path in the command
- interpreter exists — for `X/bin/torchrun`, check `X/bin/python`
- weights, checkpoints, and data exist
- those paths are **restart-persistent**, not scratch. A config pointing at local scratch
  works until the next restart wipes it, then every config breaks at once and the cause is
  not obvious
- the output directory is writable

## Level 5 is a legitimate outcome

If the command cannot be verified — hardware absent, data not staged, credentials missing —
say so at the top of the doc and in the config's comment. An honestly-labelled unverified
config is useful. One that is silently unverified destroys trust in the whole document the
first time it fails.
