#!/usr/bin/env python3
"""
Portable Package sync helper.

This helper is intentionally conservative:
  - status/diff never copy local runtime files into the repo
  - push requires --yes
  - local refresh requires --refresh-local
  - subprocess calls use argv lists, not shell=True
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPO_DIR = Path(os.environ.get("HERMES_PORTABLE_REPO", Path(__file__).resolve().parent)).resolve()
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser().resolve()

SOURCE_MAP = {
    "core/plan_registry.py": HERMES_HOME / "plan_registry" / "plan_registry.py",
    "core/plan_factory.py": HERMES_HOME / "plan_factory" / "plan_factory.py",
    "core/watchdog.py": HERMES_HOME / "plan_registry" / "watchdog.py",
    "core/conflict_detector.py": HERMES_HOME / "plan_registry" / "conflict_detector.py",
    "config/profile.template.yaml": HERMES_HOME / "references" / "profile.template.yaml",
    "knowledge/architecture.template.md": HERMES_HOME / "references" / "architecture.template.md",
    "knowledge/plan_factory.template.md": HERMES_HOME / "references" / "plan_factory.template.md",
    "knowledge/active_context.template.md": HERMES_HOME / "references" / "active_context.template.md",
}


def run_git(*args: str) -> tuple[str, str, int]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def refresh_from_local(dry_run: bool = False) -> list[str]:
    """Copy selected local template files into the repo."""
    updated: list[str] = []
    for repo_file, source_file in SOURCE_MAP.items():
        src = Path(source_file).expanduser()
        dst = REPO_DIR / repo_file
        if not src.exists():
            continue
        if dst.exists() and os.path.getmtime(src) <= os.path.getmtime(dst):
            continue
        updated.append(repo_file)
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    src_skills = HERMES_HOME / "plan_registry" / "worker_skills"
    dst_skills = REPO_DIR / "skills" / "worker_skills"
    if src_skills.exists():
        updated.append("skills/worker_skills/")
        if not dry_run:
            if dst_skills.exists():
                shutil.rmtree(dst_skills)
            shutil.copytree(src_skills, dst_skills)
    return updated


def install_to_local(dry_run: bool = False) -> list[str]:
    """Copy template repo files into the local Hermes runtime."""
    updated: list[str] = []
    for repo_file, source_file in SOURCE_MAP.items():
        src = REPO_DIR / repo_file
        dst = Path(source_file).expanduser()
        if not src.exists():
            continue
        updated.append(str(dst))
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return updated


def cmd_status(args: argparse.Namespace) -> int:
    if args.refresh_local:
        updated = refresh_from_local(dry_run=args.dry_run)
        prefix = "would refresh" if args.dry_run else "refreshed"
        for item in updated:
            print(f"{prefix}: {item}")

    out, err, code = run_git("status", "--short")
    if code != 0:
        print(err or out)
        return code
    print(out or "clean")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    if args.refresh_local:
        refresh_from_local(dry_run=args.dry_run)
    out, err, code = run_git("diff")
    if code != 0:
        print(err or out)
        return code
    print(out[: args.limit] if out else "no diff")
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to push without --yes. Run status/diff first.")
        return 2
    if args.refresh_local:
        refresh_from_local(dry_run=False)

    out, _, _ = run_git("status", "--porcelain")
    if not out:
        print("no changes to push")
        return 0

    run_git("add", "-A")
    files, _, _ = run_git("diff", "--cached", "--name-only")
    names = [x for x in files.splitlines() if x]
    msg = f"Portable sync: {', '.join(names[:5])}"
    if len(names) > 5:
        msg += f" (+{len(names) - 5} more)"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    _, err, code = run_git("commit", "-m", msg, "-m", f"Synced at {timestamp}")
    if code != 0:
        print(err)
        return code
    out, err, code = run_git("push", "origin", args.branch)
    print(out or err)
    return code


def cmd_pull(args: argparse.Namespace) -> int:
    out, err, code = run_git("pull", "origin", args.branch)
    print(out or err)
    if code == 0 and args.install_local:
        for item in install_to_local(dry_run=args.dry_run):
            print(("would install: " if args.dry_run else "installed: ") + item)
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes Portable sync helper")
    parser.add_argument("--dry-run", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.add_argument("--refresh-local", action="store_true")
    status.set_defaults(func=cmd_status)

    diff = sub.add_parser("diff")
    diff.add_argument("--refresh-local", action="store_true")
    diff.add_argument("--limit", type=int, default=3000)
    diff.set_defaults(func=cmd_diff)

    push = sub.add_parser("push")
    push.add_argument("--branch", default="main")
    push.add_argument("--refresh-local", action="store_true")
    push.add_argument("--yes", action="store_true")
    push.set_defaults(func=cmd_push)

    pull = sub.add_parser("pull")
    pull.add_argument("--branch", default="main")
    pull.add_argument("--install-local", action="store_true")
    pull.set_defaults(func=cmd_pull)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
