from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

try:
    from strategy_sandbox import safe_generate_signal
    _SANDBOX_AVAILABLE = True
except ImportError:
    _SANDBOX_AVAILABLE = False


ARENA_ROOT = Path(__file__).resolve().parents[1]
CONTESTANTS = ARENA_ROOT / "contestants"
LIVE_DATA = ARENA_ROOT / "live_data"
CTRL_DIR = ARENA_ROOT / "arena_control"
TRADE_LOGS = CTRL_DIR / "trade_logs"

TIMEFRAMES = ["M15", "M30", "H1", "H4", "D1"]
CONTRACT_SIZE = 100.0
MAX_LOTS = 0.01
MIN_CONFIDENCE = 0.58


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_bars(tf):
    path = LIVE_DATA / f"data_xauusd_{tf}.csv"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if not row:
                continue
            item = {}
            for key, value in row.items():
                k = key.strip().lower()
                if k == "time":
                    item[k] = value
                else:
                    try:
                        item[k] = float(value)
                    except (TypeError, ValueError):
                        item[k] = 0.0
            rows.append(item)
    return rows


def build_history(bars, current_index, prefer_arrays, tf="", all_bars_by_tf=None):
    current = bars[current_index]
    history_bars = bars[:current_index]
    history = {"bars": history_bars}
    for key in ("open", "high", "low", "close", "volume", "ma20", "ma50", "rsi14", "atr14"):
        values = [bar.get(key, 0.0) for bar in history_bars]
        history[key] = np.array(values, dtype=float) if prefer_arrays else values
    aliases = {
        "opens": "open",
        "highs": "high",
        "lows": "low",
        "closes": "close",
        "volumes": "volume",
    }
    for alias, key in aliases.items():
        history[alias] = history[key]
    if tf:
        history[tf] = history_bars
    if all_bars_by_tf:
        for other_tf, other_bars in all_bars_by_tf.items():
            if other_tf != tf and other_bars:
                current_time = current.get("time", "")
                cutoff = len(other_bars)
                for i, b in enumerate(other_bars):
                    if str(b.get("time", "")) > str(current_time):
                        cutoff = i
                        break
                history[other_tf] = other_bars[:cutoff]
    return current, history


def load_strategy(path):
    module_name = "arena_sim_" + hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def iter_strategies():
    for module_dir in sorted(CONTESTANTS.iterdir()):
        if not module_dir.is_dir():
            continue
        active = module_dir / "active"
        if not active.exists():
            continue
        for path in sorted(active.glob("strategy_*.py")):
            yield module_dir.name, path


def trade_log_path(module, stem):
    return TRADE_LOGS / module / f"{stem}.json"


def append_trade(module, stem, trade):
    path = trade_log_path(module, stem)
    data = read_json(path, [])
    data.append(trade)
    write_json(path, data)


def normalize_action(value):
    action = (value or "HOLD").upper()
    if action in ("BUY", "LONG"):
        return "BUY"
    if action in ("SELL", "SHORT"):
        return "SELL"
    return "HOLD"


def clamp_lots(value):
    try:
        lots = float(value)
    except (TypeError, ValueError):
        lots = MAX_LOTS
    if not math.isfinite(lots) or lots <= 0:
        lots = MAX_LOTS
    return round(min(lots, MAX_LOTS), 2)


def profit_for(action, entry, exit_price, lots):
    direction = 1.0 if action == "BUY" else -1.0
    return round((exit_price - entry) * direction * lots * CONTRACT_SIZE, 2)


def date_from_bar_time(value):
    if not value:
        return datetime.now().strftime("%Y-%m-%d")
    return value[:10].replace(".", "-")


def check_exit(position, bar):
    action = position["type"]
    sl = float(position.get("stop_loss", 0.0) or 0.0)
    tp = float(position.get("take_profit", 0.0) or 0.0)
    high = float(bar.get("high", 0.0) or 0.0)
    low = float(bar.get("low", 0.0) or 0.0)
    close = float(bar.get("close", 0.0) or 0.0)

    if action == "BUY":
        hit_sl = sl > 0 and low <= sl
        hit_tp = tp > 0 and high >= tp
    else:
        hit_sl = sl > 0 and high >= sl
        hit_tp = tp > 0 and low <= tp

    if hit_sl and hit_tp:
        return True, sl, "SL_first_conservative"
    if hit_sl:
        return True, sl, "SL"
    if hit_tp:
        return True, tp, "TP"
    if position.get("max_hold_bars", 0) and position.get("bars_held", 0) >= position["max_hold_bars"]:
        return True, close, "TIME_EXIT"
    return False, 0.0, ""


def open_position(signal, bar, meta):
    action = normalize_action(signal.get("action", "HOLD"))
    confidence = float(signal.get("confidence", 0.0) or 0.0)
    if action == "HOLD" or confidence < MIN_CONFIDENCE:
        return None
    price = float(bar.get("close", 0.0) or 0.0)
    if price <= 0:
        return None
    return {
        "type": action,
        "entry_price": price,
        "lots": clamp_lots(signal.get("lots", MAX_LOTS)),
        "stop_loss": float(signal.get("stop_loss", 0.0) or 0.0),
        "take_profit": float(signal.get("take_profit", 0.0) or 0.0),
        "open_time": bar.get("time", ""),
        "bars_held": 0,
        "max_hold_bars": 24 if meta.get("timeframe") in ("M15", "M30") else 12,
        "confidence": round(confidence, 4),
        "reasoning": signal.get("reasoning", ""),
    }


def process_strategy(module, path, bars_by_tf, state, backfill):
    key = f"{module}/{path.stem}"
    item_state = state.setdefault("strategies", {}).setdefault(key, {})
    strategy = load_strategy(path)
    meta = getattr(strategy, "STRATEGY_META", {})
    tf = str(meta.get("timeframe") or "H1").upper()
    if tf not in bars_by_tf:
        tf = "H1"
    bars = bars_by_tf.get(tf, [])
    if len(bars) < 30:
        return {"processed": 0, "closed": 0, "opened": 0}

    if item_state.get("last_bar_time"):
        start = next((i for i, bar in enumerate(bars) if str(bar.get("time", "")) > item_state["last_bar_time"]), len(bars))
    elif item_state.get("open_position", {}).get("open_time"):
        open_time = str(item_state["open_position"].get("open_time", ""))
        start = next((i for i, bar in enumerate(bars) if str(bar.get("time", "")) > open_time), len(bars))
    elif backfill:
        start = 26
    else:
        start = max(len(bars) - 1, 26)
    end = len(bars) - 1
    processed = closed = opened = 0

    for index in range(start, end + 1):
        bar = bars[index]
        position = item_state.get("open_position")
        if position:
            position["bars_held"] = int(position.get("bars_held", 0)) + 1
            exited, exit_price, reason = check_exit(position, bar)
            if exited:
                profit = profit_for(position["type"], float(position["entry_price"]), exit_price, float(position["lots"]))
                append_trade(module, path.stem, {
                    "date": date_from_bar_time(bar.get("time", "")),
                    "profit": profit,
                    "lots": float(position["lots"]),
                    "type": position["type"],
                    "entry_price": round(float(position["entry_price"]), 3),
                    "exit_price": round(exit_price, 3),
                    "open_time": position.get("open_time", ""),
                    "close_time": bar.get("time", ""),
                    "exit_reason": reason,
                    "strategy_id": meta.get("id", path.stem),
                    "strategy_name": meta.get("name", path.stem),
                    "timeframe": tf,
                })
                item_state["open_position"] = None
                closed += 1
            else:
                item_state["open_position"] = position
        else:
            current, history = build_history(bars, index, prefer_arrays=(module == "deepseek_v4_pro"), tf=tf, all_bars_by_tf=bars_by_tf)
            signal = strategy.generate_signal(current, history)
            position = open_position(signal, current, meta)
            if position:
                item_state["open_position"] = position
                opened += 1
        item_state["last_index"] = index
        item_state["last_bar_time"] = str(bar.get("time", ""))
        processed += 1

    return {"processed": processed, "closed": closed, "opened": opened}


def _read_strategy_meta_subprocess(path):
    """Read STRATEGY_META from a strategy file via a one-shot subprocess."""
    try:
        meta_script = (
            "import json, sys, importlib.util\n"
            "spec = importlib.util.spec_from_file_location('_m', sys.argv[1])\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "print(json.dumps(getattr(mod, 'STRATEGY_META', {}), default=str))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", meta_script, str(path)],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout.strip())
    except Exception:
        pass
    return {}


def process_strategy_sandbox(module, path, bars_by_tf, state, backfill):
    """Like process_strategy but runs generate_signal() in an isolated subprocess.

    Performance note: STRATEGY_META is read once and cached in
    state['strategies'][key]['meta'] together with the file mtime, so we
    don't pay the subprocess cost every loop iteration. The cache is
    invalidated automatically when the strategy file is edited.
    """
    key = f"{module}/{path.stem}"
    item_state = state.setdefault("strategies", {}).setdefault(key, {})

    try:
        cur_mtime = path.stat().st_mtime
    except OSError:
        cur_mtime = 0.0
    cached = item_state.get("meta")
    cached_mtime = item_state.get("meta_mtime")
    if isinstance(cached, dict) and cached_mtime == cur_mtime:
        meta = cached
    else:
        meta = _read_strategy_meta_subprocess(path)
        item_state["meta"] = meta
        item_state["meta_mtime"] = cur_mtime

    tf = str(meta.get("timeframe") or "H1").upper()
    if tf not in bars_by_tf:
        tf = "H1"
    bars = bars_by_tf.get(tf, [])
    if len(bars) < 30:
        return {"processed": 0, "closed": 0, "opened": 0}

    if item_state.get("last_bar_time"):
        start = next((i for i, bar in enumerate(bars) if str(bar.get("time", "")) > item_state["last_bar_time"]), len(bars))
    elif item_state.get("open_position", {}).get("open_time"):
        open_time = str(item_state["open_position"].get("open_time", ""))
        start = next((i for i, bar in enumerate(bars) if str(bar.get("time", "")) > open_time), len(bars))
    elif backfill:
        start = 26
    else:
        start = max(len(bars) - 1, 26)
    end = len(bars) - 1
    processed = closed = opened = 0

    for index in range(start, end + 1):
        bar = bars[index]
        position = item_state.get("open_position")
        if position:
            position["bars_held"] = int(position.get("bars_held", 0)) + 1
            exited, exit_price, reason = check_exit(position, bar)
            if exited:
                profit = profit_for(position["type"], float(position["entry_price"]), exit_price, float(position["lots"]))
                append_trade(module, path.stem, {
                    "date": date_from_bar_time(bar.get("time", "")),
                    "profit": profit,
                    "lots": float(position["lots"]),
                    "type": position["type"],
                    "entry_price": round(float(position["entry_price"]), 3),
                    "exit_price": round(exit_price, 3),
                    "open_time": position.get("open_time", ""),
                    "close_time": bar.get("time", ""),
                    "exit_reason": reason,
                    "strategy_id": meta.get("id", path.stem),
                    "strategy_name": meta.get("name", path.stem),
                    "timeframe": tf,
                })
                item_state["open_position"] = None
                closed += 1
            else:
                item_state["open_position"] = position
        else:
            current, history = build_history(bars, index, prefer_arrays=False, tf=tf, all_bars_by_tf=bars_by_tf)
            signal = safe_generate_signal(path, current, history)
            if signal.get("error"):
                pass
            position = open_position(signal, current, meta)
            if position:
                item_state["open_position"] = position
                opened += 1
        item_state["last_index"] = index
        item_state["last_bar_time"] = str(bar.get("time", ""))
        processed += 1

    return {"processed": processed, "closed": closed, "opened": opened}


def run_once(backfill, sandbox=False):
    bars_by_tf = {tf: read_bars(tf) for tf in TIMEFRAMES}
    state_path = CTRL_DIR / "arena_simulator_state.json"
    state = read_json(state_path, {"strategies": {}})
    summary = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "backfill": backfill,
        "sandbox": sandbox,
        "timeframes": {tf: len(rows) for tf, rows in bars_by_tf.items()},
        "strategies": 0,
        "processed": 0,
        "opened": 0,
        "closed": 0,
        "errors": [],
    }

    if sandbox and not _SANDBOX_AVAILABLE:
        summary["errors"].append({"module": "_system", "file": "", "error": "strategy_sandbox module not available"})
        summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
        return summary

    handler = process_strategy_sandbox if sandbox else process_strategy

    for module, path in iter_strategies():
        try:
            result = handler(module, path, bars_by_tf, state, backfill)
            summary["strategies"] += 1
            summary["processed"] += result["processed"]
            summary["opened"] += result["opened"]
            summary["closed"] += result["closed"]
        except Exception as exc:
            summary["errors"].append({"module": module, "file": path.name, "error": repr(exc)})

    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
    state["last_summary"] = summary
    write_json(state_path, state)
    write_json(CTRL_DIR / "arena_simulator_status.json", summary)
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description="Virtual competition simulator for arena strategies.")
    parser.add_argument("--once", action="store_true", help="run once and exit")
    parser.add_argument("--interval", type=int, default=30, help="loop interval seconds")
    parser.add_argument("--backfill", action="store_true", help="simulate over existing CSV history on first run")
    parser.add_argument("--sandbox", action="store_true", help="run strategies in isolated subprocess (safer but slower)")
    parser.add_argument("--no-sandbox", action="store_true", help="explicitly disable sandbox (default already disables it)")
    return parser.parse_args()


def main():
    args = parse_args()
    use_sandbox = args.sandbox and not args.no_sandbox
    while True:
        summary = run_once(args.backfill, use_sandbox)
        print(
            f"{summary['finished_at']} strategies={summary['strategies']} "
            f"processed={summary['processed']} opened={summary['opened']} "
            f"closed={summary['closed']} errors={len(summary['errors'])}",
            flush=True,
        )
        if args.once:
            return
        time.sleep(max(args.interval, 5))


if __name__ == "__main__":
    main()
