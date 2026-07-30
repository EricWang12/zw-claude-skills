"""Turn a working run command into a steppable VS Code / Cursor debug configuration.

The interesting part is not writing JSON -- it is that most real training commands are
launched under `torchrun` (or accelerate / deepspeed / mpirun), and a multi-process job is
close to undebuggable interactively: every rank stops at the same breakpoint and you need
one debugger per rank. So the launcher is stripped and the program is run directly as a
single process, with the rank environment `torch.distributed` expects supplied by hand.
That turns N processes into one, which is what makes stepping possible at all.

    python3 scripts/make_debug_config.py \
        --name "train tiny (debug, 1 proc)" \
        --command '.venv/bin/torchrun --standalone --nproc-per-node=2 train.py --steps 100' \
        --override steps=1

Reads the command, writes/merges one entry into .vscode/launch.json, and prints a JSON
summary on stdout. Nothing about the program under debug is modified.
"""

import argparse
import json
import re
import shlex
import sys
from pathlib import Path

# Launchers whose own flags must be dropped, and which take the real program after them.
LAUNCHERS = ("torchrun", "torch.distributed.run", "torch.distributed.launch", "accelerate", "deepspeed", "mpirun", "srun")

# Launcher flags that take a value, so both tokens get skipped.
LAUNCHER_VALUE_FLAGS = (
    "--nproc-per-node", "--nproc_per_node", "--nnodes", "--node-rank", "--node_rank",
    "--master-addr", "--master_addr", "--master-port", "--master_port", "--rdzv-backend",
    "--rdzv_backend", "--rdzv-endpoint", "--rdzv_endpoint", "--rdzv-id", "--rdzv_id",
    "--max-restarts", "--max_restarts", "--num_processes", "--num-processes",
    "--num_machines", "--config_file", "--main_process_port", "-n", "-np",
)

# What torch.distributed reads to form a one-rank world. Without these, a script that
# calls init_process_group either hangs waiting for peers or fails outright.
SINGLE_PROC_ENV = {
    "RANK": "0",
    "WORLD_SIZE": "1",
    "LOCAL_RANK": "0",
    "LOCAL_WORLD_SIZE": "1",
    "MASTER_ADDR": "127.0.0.1",
    "MASTER_PORT": "29500",
}

DEFAULT_ENV = {
    "PYTHONPATH": ".",
    "PYTHONUNBUFFERED": "1",
    "CUDA_VISIBLE_DEVICES": "0",
    "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
}


def parse_command(tokens):
    """Split a shell command into (interpreter, module, program, args, launcher)."""
    interpreter = None
    launcher = None
    i = 0

    # Leading VAR=value assignments belong in env, not argv.
    inline_env = {}
    while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
        key, _, value = tokens[i].partition("=")
        inline_env[key] = value
        i += 1

    if i < len(tokens) and ("python" in Path(tokens[i]).name or tokens[i].endswith("torchrun")):
        candidate = tokens[i]
        if candidate.endswith("torchrun"):
            launcher = "torchrun"
            # `.venv/bin/torchrun` implies `.venv/bin/python`. Without carrying that over,
            # the debug run silently uses whichever interpreter the editor has selected,
            # which is rarely the project venv and fails on the first import.
            sibling = Path(candidate).parent / "python"
            if str(sibling) != "python":
                interpreter = str(sibling)
            i += 1
        else:
            interpreter = candidate
            i += 1
            # `python -m torch.distributed.run ...` is the launcher in module form.
            if i + 1 < len(tokens) and tokens[i] == "-m" and tokens[i + 1] in LAUNCHERS:
                launcher = tokens[i + 1]
                i += 2
    elif i < len(tokens) and Path(tokens[i]).name in LAUNCHERS:
        launcher = Path(tokens[i]).name
        i += 1

    # Drop the launcher's own flags; the program is the first bare token after them.
    if launcher:
        while i < len(tokens):
            token = tokens[i]
            if token in LAUNCHER_VALUE_FLAGS:
                i += 2
                continue
            if token.startswith("-"):
                i += 1
                continue
            break

    module = None
    program = None
    if i < len(tokens) and tokens[i] == "-m":
        module = tokens[i + 1] if i + 1 < len(tokens) else None
        i += 2
    elif i < len(tokens):
        program = tokens[i]
        i += 1

    return interpreter, module, program, tokens[i:], launcher


def apply_overrides(args, overrides):
    """Replace `--flag value` / `--flag=value` in place, appending when absent.

    Shrinking the workload is what makes a debug run finish in seconds instead of hours,
    so this has to handle both flag spellings the same way.
    """
    out = list(args)
    for raw in overrides:
        key, _, value = raw.partition("=")
        if not key:
            continue
        flag = key if key.startswith("-") else f"--{key}"
        alt = flag.replace("_", "-") if "_" in flag else flag.replace("-", "_")
        replaced = False
        i = 0
        while i < len(out):
            token = out[i]
            if token in (flag, alt):
                if i + 1 < len(out) and not out[i + 1].startswith("-"):
                    out[i + 1] = value
                    replaced = True
                    i += 2
                    continue
                # Valueless flag: leave it alone rather than corrupt the argv shape.
                replaced = True
            elif token.startswith(f"{flag}=") or token.startswith(f"{alt}="):
                out[i] = f"{flag}={value}"
                replaced = True
            i += 1
        if not replaced:
            out.extend([flag, value])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--command", required=True, help="The working run command, quoted.")
    parser.add_argument("--name", required=True, help="Configuration name shown in the Run and Debug panel.")
    parser.add_argument("--repo", help="Workspace root (default: cwd).")
    parser.add_argument("--override", action="append", default=[], metavar="FLAG=VALUE",
                        help="Shrink the workload, e.g. --override steps=1. Repeatable.")
    parser.add_argument("--env", action="append", default=[], metavar="KEY=VALUE", help="Extra env var. Repeatable.")
    parser.add_argument("--cwd", default="${workspaceFolder}",
                        help="Working directory for the debug run. Set this when the command runs from a subdirectory "
                             "and its arguments use paths relative to it, e.g. ${workspaceFolder}/subproject.")
    parser.add_argument("--keep-multiproc", action="store_true",
                        help="Keep the launcher instead of collapsing to one process. Rarely what you want.")
    parser.add_argument("--launch-json", default=".vscode/launch.json", help="Path relative to the repo.")
    parser.add_argument("--dry-run", action="store_true", help="Print the config; write nothing.")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve() if args.repo else Path.cwd()
    interpreter, module, program, program_args, launcher = parse_command(shlex.split(args.command))

    if not module and not program:
        print(json.dumps({"ok": False, "error": "could not find a program or -m module in the command"}, indent=2))
        return 2

    program_args = apply_overrides(program_args, args.override)

    env = dict(DEFAULT_ENV)
    if launcher and not args.keep_multiproc:
        env.update(SINGLE_PROC_ENV)
    for raw in args.env:
        key, _, value = raw.partition("=")
        if key:
            env[key] = value

    config = {
        "name": args.name,
        "type": "debugpy",
        "request": "launch",
        "console": "integratedTerminal",
        "cwd": args.cwd,
        # false, or you cannot step into library internals -- which is most of what a
        # reader of an unfamiliar training loop actually needs to see.
        "justMyCode": False,
        "env": env,
        "args": program_args,
    }
    if module:
        config["module"] = module
    else:
        rel = program
        try:
            resolved = (repo / program).resolve()
            if resolved.is_file():
                rel = str(resolved.relative_to(repo))
        except (OSError, ValueError):
            pass
        config["program"] = "${workspaceFolder}/" + rel.removeprefix("./")
    if interpreter:
        candidate = Path(interpreter)
        # Deliberately NOT resolve(): a venv's bin/python is a symlink to the system
        # interpreter, and following it points the debug run at an environment without the
        # project's packages -- which fails on the first import, far from the real cause.
        if candidate.is_absolute():
            if candidate.is_file():
                config["python"] = str(candidate)
        elif (repo / candidate).is_file():
            config["python"] = "${workspaceFolder}/" + candidate.as_posix().removeprefix("./")

    problems = []
    if "program" in config:
        target = repo / config["program"].replace("${workspaceFolder}/", "")
        if not target.is_file():
            problems.append(f"program not found: {target}")
    if "python" in config:
        interp = config["python"].replace("${workspaceFolder}/", "")
        if not (repo / interp).is_file() and not Path(interp).is_file():
            problems.append(f"interpreter not found: {interp}")

    summary = {
        "ok": not problems,
        "launcher_stripped": launcher,
        "single_process": bool(launcher) and not args.keep_multiproc,
        "config_name": args.name,
        "launch_json": str(repo / args.launch_json),
        "problems": problems,
        "config": config,
    }

    if args.dry_run or problems:
        print(json.dumps(summary, indent=2))
        return 0 if not problems else 1

    path = repo / args.launch_json
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {"version": "0.2.0", "configurations": []}
    if path.is_file():
        try:
            # Tolerate JSONC: launch.json legitimately allows // comments.
            text = re.sub(r"^\s*//.*$", "", path.read_text(), flags=re.MULTILINE)
            existing = json.loads(text)
        except json.JSONDecodeError as exc:
            summary.update(ok=False, problems=[f"existing launch.json is unparseable: {exc}"])
            print(json.dumps(summary, indent=2))
            return 1

    configs = [c for c in existing.get("configurations", []) if c.get("name") != args.name]
    configs.append(config)
    existing["configurations"] = configs
    existing.setdefault("version", "0.2.0")
    path.write_text(json.dumps(existing, indent=2) + "\n")

    summary["total_configurations"] = len(configs)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
