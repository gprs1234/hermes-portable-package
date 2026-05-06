#!/usr/bin/env python3
"""
backup_system.py - Backs up critical Hermes data.

Backup targets:
  1. registry.json -> ~/.hermes/backups/registry/registry_YYYYMMDD_HH.json
  2. Worker skills -> ~/.hermes/backups/skills/
  3. ~/.hermes/references/*.md -> ~/.hermes/backups/references/
  4. ~/.hermes/skills/ tree -> ~/.hermes/backups/hermes_skills/
  5. Strategy snapshot (count) -> ~/.hermes/backups/strategy_snapshot.json
  6. Strategy .py files -> ~/.hermes/backups/strategies/{module}/

Features:
  - Keeps last 7 daily backups (auto-cleanup)
  - Writes backup_manifest.json with timestamp, files_backed_up, total_size
  - Skips files larger than 10MB

Usage:
  python3 backup_system.py          # Full backup
  python3 backup_system.py --status # Show last backup info
"""

import argparse
import datetime
import glob
import json
import os
import shutil
import sys

HERMES_HOME = os.path.expanduser("~/.hermes")
BACKUP_DIR = os.path.join(HERMES_HOME, "backups")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_DAILY_BACKUPS = 7

REGISTRY_SRC = os.path.join(HERMES_HOME, "plan_registry", "registry.json")
WORKER_SKILLS_GLOB = os.path.join(HERMES_HOME, "**", "worker_skills", "**", "*.json")
REFERENCES_SRC = os.path.join(HERMES_HOME, "references")
HERMES_SKILLS_SRC = os.path.join(HERMES_HOME, "skills")

ARENA_ROOTS = [
    "/mnt/c/Users/User/Desktop/百大交易競技場/arena",
    os.path.expanduser("~/arena"),
    os.path.expanduser("~/projects/arena"),
]

BACKUP_REGISTRY_DIR = os.path.join(BACKUP_DIR, "registry")
BACKUP_SKILLS_DIR = os.path.join(BACKUP_DIR, "skills")
BACKUP_REFERENCES_DIR = os.path.join(BACKUP_DIR, "references")
BACKUP_HERMES_SKILLS_DIR = os.path.join(BACKUP_DIR, "hermes_skills")
BACKUP_STRATEGIES_DIR = os.path.join(BACKUP_DIR, "strategies")
BACKUP_MANIFEST = os.path.join(BACKUP_DIR, "backup_manifest.json")
STRATEGY_SNAPSHOT = os.path.join(BACKUP_DIR, "strategy_snapshot.json")


def get_timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H")


def get_iso_timestamp():
    return datetime.datetime.now().isoformat()


def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def ensure_dirs():
    for d in [
        BACKUP_DIR,
        BACKUP_REGISTRY_DIR,
        BACKUP_SKILLS_DIR,
        BACKUP_REFERENCES_DIR,
        BACKUP_HERMES_SKILLS_DIR,
        BACKUP_STRATEGIES_DIR,
    ]:
        os.makedirs(d, exist_ok=True)


def find_arena_root():
    for root in ARENA_ROOTS:
        if os.path.isdir(root):
            return root
    return None


def safe_copy(src, dst_dir):
    if not os.path.isfile(src):
        return None, 0
    size = os.path.getsize(src)
    if size > MAX_FILE_SIZE:
        print(f"  SKIP (>{MAX_FILE_SIZE // (1024*1024)}MB): {src}")
        return None, 0
    try:
        dst = shutil.copy2(src, dst_dir)
        return dst, size
    except Exception as e:
        print(f"  ERROR copying {src}: {e}")
        return None, 0


def safe_copy_tree(src, dst_dir):
    copied = []
    if not os.path.isdir(src):
        return copied
    for root, dirs, files in os.walk(src):
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".")
            and d not in ("__pycache__", "node_modules", "venv", ".git")
        ]
        for f in files:
            if f.startswith("."):
                continue
            src_file = os.path.join(root, f)
            rel = os.path.relpath(src_file, src)
            dst_file = os.path.join(dst_dir, rel)
            size = os.path.getsize(src_file)
            if size > MAX_FILE_SIZE:
                print(f"  SKIP (>{MAX_FILE_SIZE // (1024*1024)}MB): {src_file}")
                continue
            try:
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied.append((dst_file, size))
            except Exception as e:
                print(f"  ERROR copying {src_file}: {e}")
    return copied


def backup_registry():
    print("[1/6] Backing up registry.json ...")
    if not os.path.isfile(REGISTRY_SRC):
        print(f"  NOT FOUND: {REGISTRY_SRC}")
        return [], 0
    ts = get_timestamp()
    dst = os.path.join(BACKUP_REGISTRY_DIR, f"registry_{ts}.json")
    try:
        shutil.copy2(REGISTRY_SRC, dst)
        size = os.path.getsize(dst)
        print(f"  OK: {dst}")
        return [dst], size
    except Exception as e:
        print(f"  ERROR: {e}")
        return [], 0


def backup_worker_skills():
    print("[2/6] Backing up worker skills ...")
    files = glob.glob(WORKER_SKILLS_GLOB, recursive=True)
    if not files:
        print("  No worker_skills JSON files found (searched recursively)")
        return [], 0
    total_size = 0
    all_files = []
    for f in files:
        dst, size = safe_copy(f, BACKUP_SKILLS_DIR)
        if dst:
            all_files.append(dst)
            total_size += size
            print(f"  OK: {os.path.basename(f)}")
    return all_files, total_size


def backup_references():
    print("[3/6] Backing up references ...")
    if not os.path.isdir(REFERENCES_SRC):
        print(f"  NOT FOUND: {REFERENCES_SRC}")
        return [], 0
    pattern = os.path.join(REFERENCES_SRC, "*.md")
    files = glob.glob(pattern)
    if not files:
        print("  No .md files found in references/")
        return [], 0
    total_size = 0
    all_files = []
    for f in files:
        dst, size = safe_copy(f, BACKUP_REFERENCES_DIR)
        if dst:
            all_files.append(dst)
            total_size += size
            print(f"  OK: {os.path.basename(f)}")
    return all_files, total_size


def backup_hermes_skills():
    print("[4/6] Backing up Hermes skills ...")
    if not os.path.isdir(HERMES_SKILLS_SRC):
        print(f"  NOT FOUND: {HERMES_SKILLS_SRC}")
        return [], 0
    if os.path.exists(BACKUP_HERMES_SKILLS_DIR):
        shutil.rmtree(BACKUP_HERMES_SKILLS_DIR)
    copied = safe_copy_tree(HERMES_SKILLS_SRC, BACKUP_HERMES_SKILLS_DIR)
    if copied:
        print(f"  OK: {len(copied)} files backed up")
    else:
        print("  No files copied")
    return [c[0] for c in copied], sum(c[1] for c in copied)


def backup_strategy_snapshot():
    print("[5/6] Creating strategy count snapshot ...")
    snapshot = {
        "timestamp": get_iso_timestamp(),
        "strategy_sources": [],
    }

    registry_file = os.path.join(HERMES_HOME, "plan_registry", "registry.json")
    if os.path.isfile(registry_file):
        try:
            with open(registry_file, "r") as f:
                reg = json.load(f)
            if isinstance(reg, dict):
                entries = []
                for key, val in reg.items():
                    if isinstance(val, list):
                        entries.extend(val)
                    elif isinstance(val, dict):
                        entries.append(val)
                snapshot["strategy_sources"].append({
                    "source": "plan_registry/registry.json",
                    "count": len(entries),
                    "keys": list(reg.keys())[:20],
                })
            elif isinstance(reg, list):
                snapshot["strategy_sources"].append({
                    "source": "plan_registry/registry.json",
                    "count": len(reg),
                })
        except Exception as e:
            snapshot["strategy_sources"].append({
                "source": "plan_registry/registry.json",
                "error": str(e),
            })

    plans_dir = os.path.join(HERMES_HOME, "plans")
    if os.path.isdir(plans_dir):
        plan_files = [
            f for f in os.listdir(plans_dir)
            if os.path.isfile(os.path.join(plans_dir, f))
        ]
        snapshot["strategy_sources"].append({
            "source": "plans/",
            "count": len(plan_files),
            "files": plan_files[:50],
        })

    skills_dir = os.path.join(HERMES_HOME, "skills")
    if os.path.isdir(skills_dir):
        skill_count = 0
        skill_names = []
        for root, dirs, files in os.walk(skills_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", "venv")]
            for f in files:
                if f.endswith((".json", ".py", ".md")):
                    skill_count += 1
                    rel = os.path.relpath(os.path.join(root, f), skills_dir)
                    skill_names.append(rel)
        snapshot["strategy_sources"].append({
            "source": "skills/",
            "count": skill_count,
            "sample_names": skill_names[:30],
        })

    try:
        with open(STRATEGY_SNAPSHOT, "w") as f:
            json.dump(snapshot, f, indent=2)
        size = os.path.getsize(STRATEGY_SNAPSHOT)
        print(f"  OK: {STRATEGY_SNAPSHOT}")
        return [STRATEGY_SNAPSHOT], size
    except Exception as e:
        print(f"  ERROR: {e}")
        return [], 0


def backup_strategy_files():
    """Backup actual strategy .py files (not just count snapshot).

    Walks arena/contestants/{module}/active/strategy_*.py and copies each
    file into BACKUP_STRATEGIES_DIR/{module}/{filename}, preserving mtime.
    """
    print("[6/6] Backing up strategy .py files ...")
    arena_root = find_arena_root()
    if not arena_root:
        print(f"  Arena root not found in any of: {ARENA_ROOTS}")
        return [], 0

    contestants_dir = os.path.join(arena_root, "contestants")
    if not os.path.isdir(contestants_dir):
        print(f"  contestants/ not found at {contestants_dir}")
        return [], 0

    if os.path.isdir(BACKUP_STRATEGIES_DIR):
        shutil.rmtree(BACKUP_STRATEGIES_DIR)
    os.makedirs(BACKUP_STRATEGIES_DIR, exist_ok=True)

    copied = []
    total_size = 0
    for module_name in sorted(os.listdir(contestants_dir)):
        module_dir = os.path.join(contestants_dir, module_name)
        if not os.path.isdir(module_dir):
            continue
        active_dir = os.path.join(module_dir, "active")
        if not os.path.isdir(active_dir):
            continue
        dst_module_dir = os.path.join(BACKUP_STRATEGIES_DIR, module_name)
        os.makedirs(dst_module_dir, exist_ok=True)
        for fname in sorted(os.listdir(active_dir)):
            if not fname.endswith(".py"):
                continue
            src_path = os.path.join(active_dir, fname)
            try:
                size = os.path.getsize(src_path)
            except OSError:
                continue
            if size > MAX_FILE_SIZE:
                print(f"  SKIP (>{MAX_FILE_SIZE // (1024*1024)}MB): {src_path}")
                continue
            try:
                dst = shutil.copy2(src_path, os.path.join(dst_module_dir, fname))
                copied.append(dst)
                total_size += size
            except Exception as e:
                print(f"  ERROR copying {src_path}: {e}")
        manifest_src = os.path.join(active_dir, "manifest.json")
        if os.path.isfile(manifest_src):
            try:
                shutil.copy2(manifest_src, os.path.join(dst_module_dir, "manifest.json"))
                copied.append(os.path.join(dst_module_dir, "manifest.json"))
                total_size += os.path.getsize(manifest_src)
            except Exception:
                pass

    print(f"  OK: {len(copied)} strategy files backed up ({format_size(total_size)})")
    return copied, total_size


def cleanup_old_backups():
    print(f"\nCleanup: keeping last {MAX_DAILY_BACKUPS} daily backups ...")
    registry_files = sorted(glob.glob(os.path.join(BACKUP_REGISTRY_DIR, "registry_*.json")))
    if len(registry_files) <= MAX_DAILY_BACKUPS:
        print(f"  {len(registry_files)} registry backups (<= {MAX_DAILY_BACKUPS}), no cleanup needed")
        return

    dated = []
    for f in registry_files:
        base = os.path.basename(f)
        try:
            parts = base.replace("registry_", "").replace(".json", "")
            date_str = parts[:8]
            dated.append((date_str, f))
        except (ValueError, IndexError):
            continue

    by_date = {}
    for date_str, path in dated:
        by_date.setdefault(date_str, []).append(path)

    sorted_dates = sorted(by_date.keys(), reverse=True)
    to_remove = []
    for old_date in sorted_dates[MAX_DAILY_BACKUPS:]:
        for path in by_date[old_date]:
            to_remove.append(path)

    for path in to_remove:
        try:
            os.remove(path)
            print(f"  Removed old backup: {os.path.basename(path)}")
        except Exception as e:
            print(f"  Error removing {path}: {e}")


def write_manifest(files_list, total_size):
    manifest = {
        "timestamp": get_iso_timestamp(),
        "files_backed_up": len(files_list),
        "total_size_bytes": total_size,
        "total_size_human": format_size(total_size),
        "files": files_list,
        "backup_dir": BACKUP_DIR,
    }
    try:
        with open(BACKUP_MANIFEST, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"\nManifest written: {BACKUP_MANIFEST}")
    except Exception as e:
        print(f"\nERROR writing manifest: {e}")
    return manifest


def show_status():
    if not os.path.isfile(BACKUP_MANIFEST):
        print("No backup manifest found. Run a backup first.")
        print(f"  Expected: {BACKUP_MANIFEST}")
        return 1

    with open(BACKUP_MANIFEST, "r") as f:
        manifest = json.load(f)

    print("=" * 55)
    print("  HERMES BACKUP STATUS")
    print("=" * 55)
    print(f"  Last backup:      {manifest.get('timestamp', 'unknown')}")
    print(f"  Files backed up:  {manifest.get('files_backed_up', 0)}")
    print(f"  Total size:       {manifest.get('total_size_human', 'unknown')}")
    print(f"  Backup directory: {manifest.get('backup_dir', BACKUP_DIR)}")
    print()

    categories = {
        "registry": BACKUP_REGISTRY_DIR,
        "skills": BACKUP_SKILLS_DIR,
        "references": BACKUP_REFERENCES_DIR,
        "hermes_skills": BACKUP_HERMES_SKILLS_DIR,
        "strategies": BACKUP_STRATEGIES_DIR,
    }
    print("  Backup contents:")
    for name, path in categories.items():
        if os.path.isdir(path):
            count = sum(1 for _, _, files in os.walk(path) for _ in files)
        else:
            count = 0
        print(f"    {name:20s} {count:4d} files")

    if os.path.isfile(STRATEGY_SNAPSHOT):
        try:
            with open(STRATEGY_SNAPSHOT, "r") as f:
                snap = json.load(f)
            print(f"    {'strategy_snapshot':20s} captured {snap.get('timestamp', '?')[:19]}")
            for src in snap.get("strategy_sources", []):
                print(f"      - {src.get('source', '?')}: {src.get('count', '?')} items")
        except Exception:
            pass

    files = manifest.get("files", [])
    if files:
        print()
        print("  Files in last backup (showing up to 20):")
        for f in files[:20]:
            rel = os.path.relpath(f, BACKUP_DIR) if f.startswith(BACKUP_DIR) else os.path.basename(f)
            print(f"    {rel}")
        if len(files) > 20:
            print(f"    ... and {len(files) - 20} more")

    print()
    return 0


def run_backup():
    print("=" * 55)
    print("  HERMES BACKUP SYSTEM")
    print(f"  {get_iso_timestamp()}")
    print("=" * 55)
    print()

    ensure_dirs()

    all_files = []
    total_size = 0

    files, size = backup_registry()
    all_files.extend(files); total_size += size

    files, size = backup_worker_skills()
    all_files.extend(files); total_size += size

    files, size = backup_references()
    all_files.extend(files); total_size += size

    files, size = backup_hermes_skills()
    all_files.extend(files); total_size += size

    files, size = backup_strategy_snapshot()
    all_files.extend(files); total_size += size

    files, size = backup_strategy_files()
    all_files.extend(files); total_size += size

    cleanup_old_backups()
    manifest = write_manifest(all_files, total_size)

    print()
    print("  BACKUP COMPLETE")
    print(f"  Files: {len(all_files)}  |  Size: {format_size(total_size)}")
    print("=" * 55)
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Hermes Backup System - backs up critical data")
    parser.add_argument("--status", action="store_true", help="Show last backup status info")
    args = parser.parse_args()

    if args.status:
        return show_status()
    else:
        run_backup()
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
