#!/usr/bin/env python3
"""Check research docs, workspace config and active adapter syntax without model dependencies."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_KEYS = set(re.findall(r"^([a-zA-Z_][\w]*):", (ROOT / "policy/demo_policy/deploy.yml").read_text(), re.MULTILINE))
REQUIRED_FILES = {
    "README.md", "__init__.py", "deploy.yml", "deploy.py", "model.py",
    "eval.sh", "setup_eval_policy_server.sh", "setup_eval_env_client.sh",
}


def markdown_anchors(source: str) -> set[str]:
    source = re.sub(r"```.*?```", "", source, flags=re.DOTALL)
    anchors = set(re.findall(r'<a\s+(?:id|name)=[\"\']([^\"\']+)[\"\']', source))
    counts: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6} (.+)$", source, flags=re.MULTILINE):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def main() -> int:
    errors: list[str] = []
    files = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "-z"], text=True).split("\0")
    tracked = set(files)
    config = json.loads((ROOT / "configs/policy_workspace.json").read_text())
    policies = config["active_policies"]
    if not isinstance(policies, list) or not policies or not all(isinstance(p, str) for p in policies):
        raise ValueError("active_policies must be a nonempty list of names")
    if len(set(policies)) != len(policies):
        errors.append("active_policies contains duplicate names")

    docs = sorted((ROOT / "docs").rglob("*.md")) + sorted((ROOT / "experiments").rglob("*.md"))
    docs += [ROOT / name for name in ("README.md", "README_zh.md", "AGENTS.md", "CONTRIBUTING.md", "policy/README.md")]
    docs += [ROOT / "environment/README.md"]
    docs += [ROOT / "web/README.md", ROOT / "evaluation/README.md"]
    docs += [ROOT / "UPSTREAM.md"]
    docs += [ROOT / "policy" / name / "README.md" for name in policies if isinstance(name, str)]
    for doc in docs:
        for raw in re.findall(r"\[[^\]]*\]\(([^)]+)\)", doc.read_text(encoding="utf-8")):
            target = raw.strip().split(' "', 1)[0].strip("<>")
            if not target or urlsplit(target).scheme:
                continue
            path, _, fragment = target.partition("#")
            local = (doc.parent / unquote(path)).resolve() if path else doc
            try:
                rel = local.relative_to(ROOT).as_posix()
            except ValueError:
                errors.append(f"{doc.relative_to(ROOT)}: local link leaves the repository: {target}")
                continue
            # Optional policies can be absent from disk but still retained in Git.
            if not local.exists() and rel not in tracked and not any(p.startswith(rel + "/") for p in tracked):
                errors.append(f"{doc.relative_to(ROOT)}: missing link target: {target}")
            elif fragment and local.is_file() and local.suffix == ".md":
                if unquote(fragment) not in markdown_anchors(local.read_text(encoding="utf-8")):
                    errors.append(f"{doc.relative_to(ROOT)}: missing Markdown anchor: {target}")

    python_files = list((ROOT / "scripts").glob("*.py")) + list((ROOT / "tests").glob("*.py"))
    python_files += list((ROOT / "environment").rglob("*.py")) + [ROOT / "model_template.py"]
    python_files += list((ROOT / "web").glob("*.py"))
    python_files += list((ROOT / "evaluation").rglob("*.py"))
    python_files += list((ROOT / "utils").glob("*.py")) + [ROOT / "client_server/service.py", ROOT / "XPolicyLab.py", ROOT / "_robolab_compat.py"]
    shell_files: list[Path] = list((ROOT / "utils").glob("*.sh")) + [ROOT / "start.sh"]
    for policy in policies:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", policy):
            errors.append(f"Invalid policy directory name: {policy!r}")
            continue
        base = ROOT / "policy" / policy
        if not base.is_dir():
            errors.append(f"policy/{policy} absent; run python3 scripts/policy_workspace.py focus")
            continue
        for name in sorted(REQUIRED_FILES):
            if not (base / name).is_file():
                errors.append(f"policy/{policy}: missing {name}")
        if (base / "deploy.yml").is_file():
            # Read top-level scalar keys only; no PyYAML dependency in this checker.
            pairs = dict(re.findall(r"^([a-zA-Z_][\w]*):[ \t]*(.*)$", (base / "deploy.yml").read_text(), re.MULTILINE))
            for key in sorted(REQUIRED_KEYS - pairs.keys()):
                errors.append(f"policy/{policy}/deploy.yml: missing {key}")
            if pairs.get("policy_name", "").split("#", 1)[0].strip().strip("\"'") != policy:
                errors.append(f"policy/{policy}/deploy.yml: policy_name differs from directory")
            if pairs.get("protocol", "").split("#", 1)[0].strip().strip("\"'") != "ws":
                errors.append(f"policy/{policy}/deploy.yml: protocol must be ws")
        python_files.extend(base.glob("*.py"))
        shell_files.extend(base.glob("*.sh"))

    for path in sorted(set(python_files)):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    for path in sorted(shell_files):
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
        if result.returncode:
            errors.append(f"{path.relative_to(ROOT)}: {result.stderr.strip()}")

    if errors:
        print("Workspace checks failed:\n" + "\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"PASS: {len(docs)} Markdown files, {len(policies)} active adapters, "
          f"{len(set(python_files))} Python files, {len(shell_files)} shell scripts")
    print("Scope: local link paths/visible Markdown anchors, config, required adapter files/keys, Python/shell syntax. Model/simulator execution not checked.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Workspace checks failed: {exc}", file=sys.stderr)
        sys.exit(1)
