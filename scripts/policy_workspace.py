#!/usr/bin/env python3
"""Keep a small, reversible policy working tree using Git sparse checkout (stdlib only)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        input=input_text, text=True, capture_output=True, check=True,
    ).stdout


def tracked_policies() -> set[str]:
    # The index includes files outside the current sparse view.
    names = git("ls-files", "-z", "--", "policy/")
    # Include HEAD as well so a staged deletion of deploy.yml cannot bypass protection.
    names += git("ls-tree", "-r", "--name-only", "-z", "HEAD", "--", "policy/")
    return {
        parts[1]
        for name in names.split("\0")
        if len(parts := name.split("/")) == 3 and parts[2] == "deploy.yml"
    }


def configured_policies() -> list[str]:
    value = json.loads((ROOT / "configs/policy_workspace.json").read_text())["active_policies"]
    if not isinstance(value, list) or not value or not all(isinstance(x, str) for x in value):
        raise ValueError("active_policies must be a nonempty list of policy directory names")
    return list(dict.fromkeys(value))


def focus(policies: list[str]) -> None:
    known = tracked_policies()
    unknown = set(policies) - known
    if unknown:
        raise ValueError(f"Unknown policies: {', '.join(sorted(unknown))}. Use 'list' for names.")
    local_dirs = {p.name for p in (ROOT / "policy").iterdir() if p.is_dir() and p.name != "__pycache__"}
    excluded = sorted((known | local_dirs) - set(policies))
    paths = [f"policy/{name}/" for name in excluded]
    if paths:
        # Never hide modified code, untracked experiments, or ignored model assets.
        changed = git("diff", "--name-only", "-z", "HEAD", "--", *paths)
        untracked = git("ls-files", "--others", "--exclude-standard", "-z", "--", *paths)
        ignored = git("ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--", *paths)
        leftovers = [p for p in (changed + untracked + ignored).split("\0") if p]
        if leftovers:
            sample = "\n".join(f"  {p}" for p in leftovers[:8])
            raise ValueError(
                "Refusing to hide policies with local changes or artifacts. "
                "Keep them in the view, or preserve the files elsewhere first:\n" + sample
            )

    # Keep all non-policy tracked directories, including docs, skills, and future additions.
    directories = {
        name.split("/", 1)[0]
        for name in git("ls-files", "-z").split("\0")
        if "/" in name and not name.startswith("policy/")
    }
    # Include new local support directories before their first commit as well.
    directories.update(
        name for name in ("configs", "docs", "experiments", "tests", "environment", "web") if (ROOT / name).is_dir()
    )
    directories.update(f"policy/{name}" for name in policies)
    git("sparse-checkout", "set", "--cone", "--stdin", input_text="\n".join(sorted(directories)) + "\n")
    print("Focused policy view: " + ", ".join(policies))
    print(f"{len(excluded)} other policies remain in Git. Restore all with: python3 scripts/policy_workspace.py full")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List all policies retained in the Git index")
    commands.add_parser("status", help="Show the configured and current policy view")
    focused = commands.add_parser("focus", help="Apply defaults, or defaults plus named policies")
    focused.add_argument("extra", nargs="*", help="Additional policies to expose alongside the defaults")
    commands.add_parser("full", help="Restore the complete working tree without reverting local edits")
    args = parser.parse_args()
    defaults = configured_policies()
    if args.command == "focus":
        focus(list(dict.fromkeys([*defaults, *args.extra])))
    elif args.command == "full":
        git("sparse-checkout", "disable")
        print("Full working tree restored; local edits retained.")
    elif args.command == "list":
        for name in sorted(tracked_policies()):
            print(f"{'default' if name in defaults else 'optional':8} {name}")
    else:
        print("Configured defaults: " + ", ".join(defaults))
        result = subprocess.run(
            ["git", "-C", str(ROOT), "sparse-checkout", "list"], capture_output=True, text=True,
        )
        if result.returncode:
            print("View: full (sparse checkout disabled)")
        else:
            print("Sparse paths:\n" + result.stdout.rstrip())
        visible = sorted(p.name for p in (ROOT / "policy").iterdir() if p.is_dir() and p.name != "__pycache__")
        print("Policy directories on disk: " + ", ".join(visible))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f"policy workspace: {exc}", file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        sys.exit(1)
