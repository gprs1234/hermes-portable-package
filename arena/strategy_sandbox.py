"""
Strategy Sandbox - Run strategies in isolated subprocesses.

This module provides process isolation for strategy execution. Instead of
importing and running strategy code directly in the simulator process,
each call to generate_signal() is executed in a separate subprocess.

Benefits:
  - A buggy or malicious strategy cannot crash the simulator
  - Infinite loops are killed after a timeout (default 10s)
  - Excessive memory usage is bounded by the subprocess

Tradeoffs:
  - Each strategy call spawns a new Python process (~100-300ms overhead)
  - History data must be JSON-serialized (numpy arrays become plain lists)
  - Strategies cannot maintain in-process caches across bars
  - Debugging is harder (errors appear as subprocess stderr)

Usage:
  from strategy_sandbox import safe_generate_signal

  signal = safe_generate_signal(
      strategy_path="/path/to/strategy.py",
      current_bar=current,
      history=history,
      timeout=10
  )

Integration with arena_simulator.py:
  Use the --sandbox flag to run all strategies through this module.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Memory ceiling per strategy subprocess (bytes). Default 1 GiB.
# Override via env var STRATEGY_SANDBOX_MEM_MB.
_DEFAULT_MEM_MB = int(os.environ.get("STRATEGY_SANDBOX_MEM_MB", "1024"))
_MEM_LIMIT_BYTES = _DEFAULT_MEM_MB * 1024 * 1024
_CPU_LIMIT_SECONDS = int(os.environ.get("STRATEGY_SANDBOX_CPU_SEC", "60"))


def _set_subprocess_limits():
    """preexec_fn for subprocess.run — caps virtual memory and CPU time.

    POSIX-only (Linux/WSL). On Windows ``resource`` is missing and Popen
    won't accept preexec_fn anyway, so callers should skip preexec on Win.
    """
    try:
        import resource  # type: ignore
        try:
            resource.setrlimit(resource.RLIMIT_AS, (_MEM_LIMIT_BYTES, _MEM_LIMIT_BYTES))
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (_CPU_LIMIT_SECONDS, _CPU_LIMIT_SECONDS))
        except (ValueError, OSError):
            pass
    except ImportError:
        pass


_PREEXEC = _set_subprocess_limits if os.name == "posix" else None


# The worker script template. It:
#   1. Loads the strategy module from the given path
#   2. Deserializes current_bar and history from JSON (argv)
#   3. Calls generate_signal(current_bar, history)
#   4. Prints the result as JSON to stdout
_WORKER_SCRIPT = '''
import json, sys, importlib.util

strategy_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("strategy", strategy_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

current = json.loads(sys.argv[2])
history = json.loads(sys.argv[3])

result = mod.generate_signal(current, history)
print(json.dumps(result, default=str))
'''

# Default HOLD response when something goes wrong
_DEFAULT_HOLD = {"action": "HOLD", "confidence": 0.0}


def _make_json_safe(obj):
    """Recursively convert numpy arrays and other non-JSON types to plain Python."""
    try:
        import numpy as np
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    return obj


def safe_generate_signal(strategy_path, current_bar, history, timeout=10):
    """Run strategy.generate_signal() in an isolated subprocess.

    Parameters
    ----------
    strategy_path : str or Path
        Absolute path to the strategy .py file.
    current_bar : dict
        The current bar data (must be JSON-serializable).
    history : dict
        The history dict. All values must be JSON-serializable.
        Numpy arrays are converted to plain lists automatically.
    timeout : int
        Maximum seconds to wait before killing the subprocess.

    Returns
    -------
    dict
        The strategy's signal dict on success, or a HOLD dict with an
        "error" key describing what went wrong.
    """
    strategy_path = str(strategy_path)

    # Sanitize history: convert numpy arrays to lists for JSON serialization
    safe_history = _make_json_safe(history)
    safe_bar = _make_json_safe(current_bar)

    try:
        current_json = json.dumps(safe_bar)
        history_json = json.dumps(safe_history)
    except (TypeError, ValueError) as exc:
        result = dict(_DEFAULT_HOLD)
        result["error"] = f"json_serialize_error: {exc}"
        return result

    try:
        run_kwargs = dict(
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if _PREEXEC is not None:
            run_kwargs["preexec_fn"] = _PREEXEC
        proc = subprocess.run(
            [sys.executable, "-c", _WORKER_SCRIPT, strategy_path, current_json, history_json],
            **run_kwargs,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout.strip())
        else:
            stderr_snippet = proc.stderr[:300] if proc.stderr else "unknown error"
            result = dict(_DEFAULT_HOLD)
            result["error"] = stderr_snippet
            return result

    except subprocess.TimeoutExpired:
        result = dict(_DEFAULT_HOLD)
        result["error"] = f"timeout after {timeout}s"
        return result
    except json.JSONDecodeError as exc:
        result = dict(_DEFAULT_HOLD)
        result["error"] = f"json_decode_error: {exc}"
        return result
    except Exception as exc:
        result = dict(_DEFAULT_HOLD)
        result["error"] = repr(exc)
        return result
