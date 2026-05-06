"""Command line interface for portable Hermes templates."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path

from . import __version__
from .paths import hermes_home, portable_home
from .templates import CONFIG_TEMPLATE, KEY_POOL_TEMPLATE, SECRETS_TEMPLATE


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_\-]{20,}"),
    re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"xox[baprs]-[0-9A-Za-z\-]{20,}"),
]


def _write(path: Path, text: str, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _copy_tree(src: Path, dst: Path, force: bool) -> int:
    copied = 0
    if not src.exists():
        return copied
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if target.exists() and not force:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied += 1
    return copied


def cmd_init(args: argparse.Namespace) -> int:
    h_home = hermes_home(args.hermes_home)
    p_home = portable_home(args.portable_home)

    config_text = CONFIG_TEMPLATE.format(
        hermes_home=str(h_home).replace("\\", "/"),
        portable_home=str(p_home).replace("\\", "/"),
    )

    wrote = []
    skipped = []
    for path, text in (
        (p_home / "config.yaml", config_text),
        (p_home / "secrets.env", SECRETS_TEMPLATE),
        (p_home / "key_pool.json", KEY_POOL_TEMPLATE),
    ):
        if _write(path, text, args.force):
            wrote.append(path)
        else:
            skipped.append(path)

    for dirname in ("runtime", "logs", "backups"):
        (p_home / dirname).mkdir(parents=True, exist_ok=True)
    for dirname in ("plan_registry", "scripts", "references"):
        (h_home / dirname).mkdir(parents=True, exist_ok=True)

    root = Path(__file__).resolve().parents[1]
    copied = 0
    if args.install_templates:
        copied += _copy_tree(root / "core", h_home / "plan_registry", args.force)
        copied += _copy_tree(root / "scripts", h_home / "scripts", args.force)
        copied += _copy_tree(root / "knowledge", h_home / "references", args.force)

    print(f"Hermes Portable {__version__}")
    print(f"portable_home: {p_home}")
    print(f"hermes_home:   {h_home}")
    for path in wrote:
        print(f"created: {path}")
    for path in skipped:
        print(f"exists:  {path}")
    if args.install_templates:
        print(f"installed template files: {copied}")
    return 0


def _scan_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    hits = []
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            hits.append(match.group(0)[:10] + "...")
    return hits


def cmd_doctor(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[1]
    h_home = hermes_home(args.hermes_home)
    p_home = portable_home(args.portable_home)
    checks: list[tuple[str, bool, str]] = []

    checks.append(("python", sys.version_info >= (3, 10), platform.python_version()))
    checks.append(("portable_home", p_home.exists(), str(p_home)))
    checks.append(("hermes_home", h_home.exists(), str(h_home)))
    checks.append(("local config", (p_home / "config.yaml").exists(), str(p_home / "config.yaml")))
    checks.append(("local secrets", (p_home / "secrets.env").exists(), str(p_home / "secrets.env")))
    checks.append(("repo key_pool sanitized", not _scan_file(root / "key_pool.json"), "key_pool.json"))

    raw_secret_hits = []
    for candidate in (root / "key_pool.json", root / "config" / "nomi_profile.yaml"):
        hits = _scan_file(candidate)
        if hits:
            raw_secret_hits.append(f"{candidate.name}: {', '.join(hits)}")

    ok = True
    for name, passed, detail in checks:
        ok = ok and passed
        status = "OK" if passed else "FAIL"
        print(f"{status:4} {name:24} {detail}")

    if raw_secret_hits:
        ok = False
        print("FAIL secret scan")
        for hit in raw_secret_hits:
            print(f"     {hit}")

    return 0 if ok else 1


def cmd_show_template(args: argparse.Namespace) -> int:
    templates = {
        "config": CONFIG_TEMPLATE,
        "secrets": SECRETS_TEMPLATE,
        "key-pool": KEY_POOL_TEMPLATE,
    }
    text = templates[args.name]
    if args.name == "config":
        text = text.format(
            hermes_home=str(hermes_home(args.hermes_home)).replace("\\", "/"),
            portable_home=str(portable_home(args.portable_home)).replace("\\", "/"),
        )
    if args.name == "key-pool":
        json.loads(text)
    print(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes-portable")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create per-machine local configuration")
    init_p.add_argument("--hermes-home")
    init_p.add_argument("--portable-home")
    init_p.add_argument("--install-templates", action="store_true")
    init_p.add_argument("--force", action="store_true")
    init_p.set_defaults(func=cmd_init)

    doctor_p = sub.add_parser("doctor", help="Check portability and safety prerequisites")
    doctor_p.add_argument("--hermes-home")
    doctor_p.add_argument("--portable-home")
    doctor_p.set_defaults(func=cmd_doctor)

    tpl_p = sub.add_parser("show-template", help="Print a built-in template")
    tpl_p.add_argument("name", choices=("config", "secrets", "key-pool"))
    tpl_p.add_argument("--hermes-home")
    tpl_p.add_argument("--portable-home")
    tpl_p.set_defaults(func=cmd_show_template)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
