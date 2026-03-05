from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data.mt5_file_feed import get_latest_bar_time, read_heartbeat


def _yaml_module_or_none():
    try:
        import yaml  # type: ignore

        return yaml
    except Exception:
        return None


def _load_cfg(path: str) -> dict[str, Any]:
    yaml = _yaml_module_or_none()
    if yaml is None:
        raise SystemExit("PyYAML is required to read config. Install with `pip install PyYAML`.")
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"Config not found: {path}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _forex_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    markets = cfg.get("markets", {}) if isinstance(cfg.get("markets", {}), dict) else {}
    return markets.get("forex", {}) if isinstance(markets.get("forex", {}), dict) else {}


def _symbols_from_cfg(cfg: dict[str, Any]) -> list[str]:
    fcfg = _forex_cfg(cfg)
    s = fcfg.get("symbols", []) if isinstance(fcfg.get("symbols", []), list) else []
    return [str(x) for x in s]


def _resolve_env_value(raw: str) -> str:
    txt = str(raw).strip()
    if txt.startswith("${") and txt.endswith("}") and len(txt) > 3:
        import os

        return os.getenv(txt[2:-1], txt)
    return txt


def _fmt_utc(ts: int | None) -> str:
    if ts is None:
        return "N/A"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")


def _status(ts: int | None, stale_seconds: int) -> str:
    if ts is None:
        return "STALE(age=N/A)"
    now = int(datetime.now(timezone.utc).timestamp())
    age = max(0, now - int(ts))
    if age <= int(stale_seconds):
        return f"FRESH(age={age}s)"
    return f"STALE(age={age}s)"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Check MT5 file feed freshness")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--use-config-forex-symbols", action="store_true")
    p.add_argument("--feed-dir", default="")
    p.add_argument("--stale-seconds", type=int, default=0)
    p.add_argument("--timeframes", default="M1,M5,M15,H1,H4,D1,W1")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = _load_cfg(args.config)
    fcfg = _forex_cfg(cfg)

    symbols = [str(s) for s in (args.symbols or [])]
    if not symbols and args.use_config_forex_symbols:
        symbols = _symbols_from_cfg(cfg)
    if not symbols:
        raise SystemExit("No symbols provided. Use --symbols or --use-config-forex-symbols.")

    feed_dir = args.feed_dir or _resolve_env_value(str(fcfg.get("feed_dir", "mt5_feed")))
    stale_seconds = int(args.stale_seconds or int(fcfg.get("stale_seconds", 180) or 180))
    timeframes = [x.strip().upper() for x in str(args.timeframes).split(",") if x.strip()]
    tf_map = {"M1": "1m", "M5": "5m", "M15": "15m", "H1": "1h", "H4": "4h", "D1": "1d", "W1": "1w"}

    print("=== MT5 FILE FEED CHECK ===")
    print(f"feed_dir={feed_dir}")
    print(f"stale_seconds={stale_seconds}")
    if not Path(feed_dir).exists():
        print("ERROR: feed_dir does not exist")
        return

    hb = read_heartbeat(feed_dir)
    print(f"heartbeat_utc={_fmt_utc(hb)} status={_status(hb, stale_seconds)}")

    for symbol in symbols:
        parts: list[str] = []
        m1_ts = get_latest_bar_time(symbol, "1m", feed_dir)
        for tf in timeframes:
            tf_key = tf_map.get(tf)
            if tf_key is None:
                continue
            latest = get_latest_bar_time(symbol, tf_key, feed_dir)
            if tf == "M1":
                file_st = _status(latest, stale_seconds)
            else:
                file_st = "OK" if latest is not None else "MISSING"
            parts.append(f"{tf}={_fmt_utc(latest)} {file_st}")
        parts.append(f"freshness=heartbeat:{_status(hb, stale_seconds)} m1:{_status(m1_ts, stale_seconds)}")
        print(f"[{symbol}] " + " | ".join(parts))


if __name__ == "__main__":
    main()
