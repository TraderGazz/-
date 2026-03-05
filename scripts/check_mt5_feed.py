from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import MetaTrader5 as mt5
except Exception:  # pragma: no cover
    mt5 = None


def _yaml_module_or_none():
    try:
        import yaml  # type: ignore

        return yaml
    except Exception:
        return None


def _load_cfg(path: str) -> dict[str, Any]:
    yaml = _yaml_module_or_none()
    if yaml is None:
        raise SystemExit(
            "PyYAML is required to read config. Install with `pip install PyYAML` "
            "or run with --symbols ..."
        )
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"Config not found: {path}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _cfg_symbols(cfg: dict[str, Any]) -> list[str]:
    markets = cfg.get("markets", {}) if isinstance(cfg.get("markets", {}), dict) else {}
    forex = markets.get("forex", {}) if isinstance(markets.get("forex", {}), dict) else {}
    s1 = forex.get("symbols", []) if isinstance(forex.get("symbols", []), list) else []
    if s1:
        return [str(x) for x in s1]

    strategies = cfg.get("strategies", {}) if isinstance(cfg.get("strategies", {}), dict) else {}
    h1m1 = strategies.get("h1_m1", {}) if isinstance(strategies.get("h1_m1", {}), dict) else {}
    s2 = h1m1.get("symbols", []) if isinstance(h1m1.get("symbols", []), list) else []
    return [str(x) for x in s2]


def _fmt_utc(ts: int | float | None) -> str:
    if ts is None:
        return "N/A"
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")


def _age_hours_str(ts: int | float | None) -> str:
    if ts is None:
        return "N/A"
    now = datetime.now(timezone.utc).timestamp()
    hours = max(0.0, (float(now) - float(ts)) / 3600.0)
    return f"{hours:.2f}h"


def _freshness(ts: int | float | None, stale_hours: float) -> str:
    if ts is None:
        return "STALE(age=N/A)"
    now = datetime.now(timezone.utc).timestamp()
    age_h = max(0.0, (float(now) - float(ts)) / 3600.0)
    if age_h <= float(stale_hours):
        return f"FRESH(age={age_h:.2f}h)"
    return f"STALE(age={age_h:.2f}h)"


def _tick_info(symbol: str) -> tuple[int | None, float | None, float | None]:
    t = mt5.symbol_info_tick(symbol)
    if t is None:
        return None, None, None
    return int(getattr(t, "time", 0) or 0) or None, getattr(t, "bid", None), getattr(t, "ask", None)


def _rates_last_time(symbol: str, tf: int, n: int) -> tuple[int | None, int]:
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, int(n))
    if rates is None or len(rates) == 0:
        return None, 0
    last_ts = rates[-1]["time"] if "time" in rates.dtype.names else None
    return (int(last_ts) if last_ts is not None else None), len(rates)


def _report_for_symbol(symbol: str, n: int, stale_hours: float, include_tick: bool) -> list[str]:
    out: list[str] = []
    selected = mt5.symbol_select(symbol, True)
    out.append(f"[{symbol}] symbol_select={selected}")

    tick_ts: int | None = None
    if include_tick:
        tick_ts, bid, ask = _tick_info(symbol)
        out.append(
            f"[{symbol}][TICK] tick_utc={_fmt_utc(tick_ts)} bid={bid if bid is not None else 'N/A'} "
            f"ask={ask if ask is not None else 'N/A'} status={_freshness(tick_ts, stale_hours)}"
        )

    for tf_name, tf in (("M1", mt5.TIMEFRAME_M1), ("H1", mt5.TIMEFRAME_H1)):
        last_ts, bars = _rates_last_time(symbol, tf, int(n))
        if bars == 0 or last_ts is None:
            out.append(f"[{symbol}][{tf_name}] NO DATA last_error={mt5.last_error()} status=STALE(age=N/A)")
            continue
        out.append(
            f"[{symbol}][{tf_name}] bars={bars} last_utc={_fmt_utc(last_ts)} "
            f"status={_freshness(last_ts, stale_hours)}"
        )
    return out


def _variant_names(base_symbol: str, limit: int) -> list[str]:
    names: list[str] = []
    for group in (base_symbol, f"*{base_symbol}*", f"*{base_symbol}*.*", f"*{base_symbol}*m*"):
        items = mt5.symbols_get(group)
        if not items:
            continue
        for item in items:
            nm = str(getattr(item, "name", "") or "")
            if nm and nm not in names:
                names.append(nm)
            if len(names) >= int(limit):
                return names
    return names[: int(limit)]


def _variant_report(base_symbol: str, n: int, stale_hours: float, limit: int) -> tuple[list[str], str | None]:
    lines: list[str] = [f"--- variants for {base_symbol} ---"]
    variants = _variant_names(base_symbol, int(limit))
    if not variants:
        lines.append("NO VARIANTS FOUND")
        return lines, None

    best_name: str | None = None
    best_key: tuple[int, int] = (0, 0)  # tick_ts, m1_ts

    for name in variants:
        mt5.symbol_select(name, True)
        info = mt5.symbol_info(name)
        visible = getattr(info, "visible", None) if info is not None else None
        trade_mode = getattr(info, "trade_mode", None) if info is not None else None

        tick_ts, bid, ask = _tick_info(name)
        m1_ts, m1_bars = _rates_last_time(name, mt5.TIMEFRAME_M1, int(n))
        h1_ts, h1_bars = _rates_last_time(name, mt5.TIMEFRAME_H1, int(n))

        m1_status = _freshness(m1_ts, stale_hours)
        h1_status = _freshness(h1_ts, stale_hours)
        lines.append(
            f"{name} | visible={visible} trade_mode={trade_mode} "
            f"| tick_utc={_fmt_utc(tick_ts)} bid={bid if bid is not None else 'N/A'} ask={ask if ask is not None else 'N/A'} "
            f"| M1 bars={m1_bars} last_utc={_fmt_utc(m1_ts)} {m1_status} "
            f"| H1 bars={h1_bars} last_utc={_fmt_utc(h1_ts)} {h1_status}"
        )

        tick_rank = int(tick_ts or 0)
        m1_rank = int(m1_ts or 0)
        if (tick_rank, m1_rank) > best_key:
            best_key = (tick_rank, m1_rank)
            best_name = name

    lines.append(f"BEST: {base_symbol} -> {best_name or 'N/A'}")
    return lines, best_name


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Check MT5 feed freshness for forex symbols")
    p.add_argument("--symbols", nargs="*", default=None, help="Symbols list, e.g. EURUSD GBPUSD")
    p.add_argument("--config", default="config/default.yaml", help="Path to config yaml")
    p.add_argument("--use-config-forex-symbols", action="store_true", help="Use symbols from config when --symbols is not set")
    p.add_argument("--n", type=int, default=5, help="Number of latest bars to fetch for M1/H1")
    p.add_argument("--stale-hours", type=float, default=6.0, help="Hours threshold to classify feed as stale")
    p.add_argument("--include-tick", action=argparse.BooleanOptionalAction, default=True, help="Include tick_utc and bid/ask")
    p.add_argument("--find-variants", action="store_true", help="Find broker symbol variants for base symbols")
    p.add_argument("--variants-limit", type=int, default=20, help="Max variant names per base symbol")
    p.add_argument("--suggest-map", action="store_true", help="Suggest BASE -> RESOLVED mapping and YAML snippet")
    p.add_argument("--out", default="", help="Optional output report file path")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if mt5 is None:
        raise SystemExit("MetaTrader5 module is not installed. Install with `pip install MetaTrader5`.")

    symbols = [str(s) for s in (args.symbols or [])]
    if not symbols and args.use_config_forex_symbols:
        cfg = _load_cfg(args.config)
        symbols = _cfg_symbols(cfg)
    if not symbols:
        raise SystemExit("No symbols provided. Use --symbols or --use-config-forex-symbols.")

    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize() failed: {mt5.last_error()}")

    try:
        lines: list[str] = []
        lines.append("=== MT5 FEED CHECK ===")
        lines.append(f"config={args.config}")
        lines.append(f"symbols={symbols}")
        lines.append(f"n={int(args.n)} stale_hours={float(args.stale_hours)}")
        lines.append("")

        suggested: dict[str, str] = {}

        for s in symbols:
            lines.extend(_report_for_symbol(s, int(args.n), float(args.stale_hours), bool(args.include_tick)))
            if args.find_variants:
                v_lines, best = _variant_report(s, int(args.n), float(args.stale_hours), int(args.variants_limit))
                lines.extend(v_lines)
                if best:
                    suggested[s] = best
            lines.append("")

        if args.suggest_map:
            lines.append("=== SUGGESTED MAPPING ===")
            if not suggested:
                lines.append("No mapping suggestions (run with --find-variants and ensure variants are available).")
            else:
                for base in symbols:
                    resolved = suggested.get(base)
                    if resolved:
                        lines.append(f"{base} -> {resolved}")
                resolved_list = [suggested.get(base, base) for base in symbols]
                lines.append("")
                lines.append("YAML snippet (not applied):")
                lines.append("markets:")
                lines.append("  forex:")
                lines.append(f"    symbols: [{', '.join(resolved_list)}]")
            lines.append("")

        text = "\n".join(lines).rstrip() + "\n"
        print(text, end="")

        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text, encoding="utf-8")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
