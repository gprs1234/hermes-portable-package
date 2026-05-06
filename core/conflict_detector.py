#!/usr/bin/env python3
"""
Conflict Detector for PLAN Registry
=====================================
Advisory lock system to prevent multiple PLANs from conflicting on shared resources.

Lock files: ~/.hermes/plan_registry/locks/{resource_name}.lock
Lock TTL:   5 minutes (auto-expire stale locks)

Usage:
    python3 conflict_detector.py locks                          # show all current locks
    python3 conflict_detector.py check <plan_id> <resource> <action>  # check if safe
    python3 conflict_detector.py acquire <plan_id> <resource> <action> # try to acquire lock
    python3 conflict_detector.py release <plan_id> <resource>          # release lock

Integration:
    from conflict_detector import check_conflict, acquire_lock, release_lock
    result = check_conflict("arena", "ea_bridge", "restart")
    if result["safe"]:
        ok = acquire_lock("arena", "ea_bridge", "restart")
        if ok:
            # do the restart
            release_lock("arena", "ea_bridge")
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ─── Paths ──────────────────────────────────────────────────────
REGISTRY_DIR = Path(os.path.expanduser("~/.hermes/plan_registry"))
LOCKS_DIR = REGISTRY_DIR / "locks"
LOCKS_DIR.mkdir(parents=True, exist_ok=True)

LOCK_TTL_SECONDS = 300  # 5 minutes

# ─── Resource Registry ──────────────────────────────────────────
RESOURCES = {
    "ea_bridge": {"type": "service", "owners": ["arena"], "restart_safe": True},
    "simulator": {"type": "service", "owners": ["arena"], "restart_safe": True},
    "server_file": {"type": "service", "owners": ["trading-server"], "restart_safe": True},
    "board_bot": {"type": "service", "owners": ["board-bot"], "restart_safe": True},
    "watchdog": {"type": "service", "owners": ["watchdog"], "restart_safe": True},
    "arena/live_data": {"type": "directory", "owners": ["arena"], "write_safe": True},
    "leaderboard": {"type": "directory", "owners": ["arena"], "write_safe": True},
}

# ─── Dependency Graph (mirrors plan_registry.py) ────────────────
# parent -> [children that depend on parent]
from shared_deps import DEPENDENCY_GRAPH, COMPONENT_GRAPH, COMPONENT_TO_PLAN  # noqa: F401

# Resources whose dependents would be disrupted by a restart.
# Resource names here MUST match keys in RESOURCES below — same vocabulary.
# (Previously these used a third, conflicting set of names; now aligned.)
_RESOURCE_DEPENDENCIES = {
    "ea_bridge":   ["simulator"],   # simulator reads from ea_bridge
    "simulator":   [],              # no known downstream resource
    "watchdog":    ["board_bot"],   # watchdog monitors board_bot
    "server_file": [],              # trading server is leaf in resource space
}


# ══════════════════════════════════════════════════════════════
#  Lock file I/O
# ══════════════════════════════════════════════════════════════

def _lock_path(resource: str) -> Path:
    """Get the lock file path for a resource."""
    safe_name = resource.replace("/", "_")
    return LOCKS_DIR / f"{safe_name}.lock"


def _read_lock(resource: str) -> dict | None:
    """Read a lock file. Returns None if not found or expired."""
    path = _lock_path(resource)
    if not path.exists():
        return None
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    # Check expiry
    expires_at = lock.get("expires_at", 0)
    if time.time() > expires_at:
        # Stale lock — auto-remove
        try:
            path.unlink()
        except OSError:
            pass
        return None
    return lock


def _write_lock(resource: str, lock_data: dict):
    """Write a lock file."""
    path = _lock_path(resource)
    path.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")


def _delete_lock(resource: str):
    """Delete a lock file."""
    path = _lock_path(resource)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


# ══════════════════════════════════════════════════════════════
#  Conflict Detection
# ══════════════════════════════════════════════════════════════

def check_conflict(plan_id: str, resource: str, action: str) -> dict:
    """
    Check if a PLAN can safely perform an action on a resource.

    Returns:
        {"safe": bool, "conflicts": [str, ...]}
    """
    conflicts = []

    # 1) Unknown resource?
    if resource not in RESOURCES:
        conflicts.append(f"Unknown resource '{resource}'. Known: {list(RESOURCES.keys())}")
        return {"safe": False, "conflicts": conflicts}

    res_info = RESOURCES[resource]

    # 2) Ownership check (advisory — non-blocking but warned)
    if plan_id not in res_info["owners"]:
        conflicts.append(
            f"PLAN '{plan_id}' is not an owner of resource '{resource}'. "
            f"Owners: {res_info['owners']}"
        )

    # 3) Is the resource already locked by someone else?
    existing = _read_lock(resource)
    if existing and existing.get("plan_id") != plan_id:
        conflicts.append(
            f"Resource '{resource}' is locked by PLAN '{existing['plan_id']}' "
            f"(action='{existing['action']}', "
            f"expires_at={datetime.fromtimestamp(existing['expires_at'], tz=timezone.utc).isoformat()})"
        )

    # 4) Dependency conflict: restarting a resource that others depend on
    if action in ("restart", "stop"):
        dependents = _RESOURCE_DEPENDENCIES.get(resource, [])
        for dep_resource in dependents:
            dep_lock = _read_lock(dep_resource)
            if dep_lock:
                conflicts.append(
                    f"Dependent resource '{dep_resource}' is currently locked by "
                    f"PLAN '{dep_lock['plan_id']}' (action='{dep_lock['action']}'). "
                    f"Restarting '{resource}' may disrupt it."
                )

    # 5) Reverse check: are we trying to use a resource whose upstream is restarting?
    if action in ("read", "write", "use"):
        for parent, children_deps in _RESOURCE_DEPENDENCIES.items():
            if resource in children_deps:
                parent_lock = _read_lock(parent)
                if parent_lock and parent_lock.get("action") in ("restart", "stop"):
                    conflicts.append(
                        f"Upstream resource '{parent}' is being restarted by "
                        f"PLAN '{parent_lock['plan_id']}'. "
                        f"Using '{resource}' now may fail."
                    )

    safe = len(conflicts) == 0
    return {"safe": safe, "conflicts": conflicts}


# ══════════════════════════════════════════════════════════════
#  Lock Management API
# ══════════════════════════════════════════════════════════════

def acquire_lock(plan_id: str, resource: str, action: str) -> tuple[bool, str]:
    """
    Try to acquire a lock on a resource for a given plan+action.

    Returns:
        (success: bool, reason: str)
    """
    # Validate resource exists
    if resource not in RESOURCES:
        return False, f"Unknown resource '{resource}'"

    # Check for conflicts
    conflict_result = check_conflict(plan_id, resource, action)
    blocking = [c for c in conflict_result["conflicts"]
                if "locked by PLAN" in c or "is being restarted" in c or "Unknown resource" in c]

    if blocking:
        return False, "Blocked: " + "; ".join(blocking)

    # Non-blocking warnings (ownership) are allowed — still acquire
    now = time.time()
    lock_data = {
        "plan_id": plan_id,
        "resource": resource,
        "action": action,
        "acquired_at": now,
        "acquired_at_iso": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "expires_at": now + LOCK_TTL_SECONDS,
    }
    _write_lock(resource, lock_data)

    warnings = [c for c in conflict_result["conflicts"] if c not in blocking]
    if warnings:
        return True, "Lock acquired with warnings: " + "; ".join(warnings)
    return True, "Lock acquired"


def release_lock(plan_id: str, resource: str) -> tuple[bool, str]:
    """
    Release a lock. Only the owning plan can release it (or anyone if stale).

    Returns:
        (success: bool, reason: str)
    """
    existing = _read_lock(resource)
    if existing is None:
        return False, f"No active lock on '{resource}'"

    if existing.get("plan_id") != plan_id:
        return False, (
            f"Lock on '{resource}' is held by PLAN '{existing['plan_id']}', "
            f"not '{plan_id}'"
        )

    _delete_lock(resource)
    return True, f"Lock on '{resource}' released by PLAN '{plan_id}'"


def get_all_locks() -> dict:
    """
    Return all currently active locks.

    Returns:
        {resource: lock_data, ...}
    """
    locks = {}
    for lock_file in sorted(LOCKS_DIR.glob("*.lock")):
        try:
            lock = json.loads(lock_file.read_text(encoding="utf-8"))
            resource = lock.get("resource", lock_file.stem)
            # Filter out expired
            if time.time() <= lock.get("expires_at", 0):
                lock["ttl_remaining_sec"] = round(lock["expires_at"] - time.time())
                locks[resource] = lock
            else:
                # Auto-clean stale
                try:
                    lock_file.unlink()
                except OSError:
                    pass
        except (json.JSONDecodeError, OSError):
            continue
    return locks


# ══════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════

def _print_locks():
    locks = get_all_locks()
    if not locks:
        print("No active locks.")
        return
    print(f"{'Resource':<20} {'Plan':<15} {'Action':<10} {'TTL (s)':<10} {'Acquired At'}")
    print("-" * 80)
    for resource, lock in locks.items():
        print(
            f"{resource:<20} "
            f"{lock['plan_id']:<15} "
            f"{lock['action']:<10} "
            f"{lock['ttl_remaining_sec']:<10} "
            f"{lock.get('acquired_at_iso', 'N/A')}"
        )


def _print_conflict(plan_id, resource, action):
    result = check_conflict(plan_id, resource, action)
    print(f"Conflict check: PLAN '{plan_id}' -> {action} on '{resource}'")
    print(f"  Safe: {result['safe']}")
    if result["conflicts"]:
        print("  Conflicts:")
        for c in result["conflicts"]:
            print(f"    - {c}")
    else:
        print("  No conflicts detected.")


def _print_acquire(plan_id, resource, action):
    ok, reason = acquire_lock(plan_id, resource, action)
    status = "OK" if ok else "DENIED"
    print(f"[{status}] {reason}")


def _print_release(plan_id, resource):
    ok, reason = release_lock(plan_id, resource)
    status = "OK" if ok else "FAILED"
    print(f"[{status}] {reason}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 conflict_detector.py locks")
        print("  python3 conflict_detector.py check <plan_id> <resource> <action>")
        print("  python3 conflict_detector.py acquire <plan_id> <resource> <action>")
        print("  python3 conflict_detector.py release <plan_id> <resource>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "locks":
        _print_locks()

    elif cmd == "check":
        if len(sys.argv) != 5:
            print("Usage: conflict_detector.py check <plan_id> <resource> <action>")
            sys.exit(1)
        _print_conflict(sys.argv[2], sys.argv[3], sys.argv[4])

    elif cmd == "acquire":
        if len(sys.argv) != 5:
            print("Usage: conflict_detector.py acquire <plan_id> <resource> <action>")
            sys.exit(1)
        _print_acquire(sys.argv[2], sys.argv[3], sys.argv[4])

    elif cmd == "release":
        if len(sys.argv) != 4:
            print("Usage: conflict_detector.py release <plan_id> <resource>")
            sys.exit(1)
        _print_release(sys.argv[2], sys.argv[3])

    else:
        print(f"Unknown command: {cmd}")
        print("Valid commands: locks, check, acquire, release")
        sys.exit(1)


if __name__ == "__main__":
    main()
