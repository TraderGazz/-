from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MARKERS = [
    "[DATA] Loaded",
    "[MT5]",
    "[PIPELINE]",
    "[M1][ENTRY] created",
    "[M1][ENTRY]",
    "[ENTRY][SL]",
    "CRT=",
    "KeyLevel=",
    "Sweep=",
    "TBS=",
    "Model1=",
    "Trades=",
    "trades=",
]

ENTRY_RE = re.compile(
    r"\[M1\]\[ENTRY\]\s+created.*?ctx=(?P<ctx>\S+).*?(?:dir|direction)=(?P<dir>BUY|SELL).*?"
    r"model1_confirmation_time=(?P<model1>\d+).*?chosen_entry_time=(?P<entry_time>\d+).*?"
    r"chosen_entry_price=(?P<entry_price>[0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
SL_RE = re.compile(r"\[ENTRY\]\[SL\]\s+source=(?P<source>\w+)\s+price=(?P<price>[0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)

GATE_WORDS = ["stale", "duplicate", "dedup", "missed", "skip", "no_sweep", "no_model1", "no_entry", "blocked", "disabled"]

REPO_ROOT = Path(__file__).resolve().parents[1]


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
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    if not p.exists():
        raise SystemExit(f"Config not found: {p}")
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


def _extract_markers(text: str) -> list[str]:
    lines = text.splitlines()
    return [line for line in lines if any(m in line for m in MARKERS)]


def _tail_lines(text: str, n: int) -> list[str]:
    lines = text.splitlines()
    if n <= 0:
        return []
    return lines[-n:]


def _classify_error(text: str) -> tuple[str, str]:
    lower = text.lower()

    def first_match(keys: list[str]) -> str:
        for line in text.splitlines():
            for k in keys:
                if k.lower() in line.lower():
                    return line.strip()
        return ""

    if "modulenotfounderror" in lower:
        return "IMPORT_ERROR", first_match(["ModuleNotFoundError", "ImportError"])
    if "no such file or directory" in lower or "filenotfounderror" in lower:
        return "CONFIG_ERROR", first_match(["No such file or directory", "FileNotFoundError"])
    if "mt5" in lower and ("initialize failed" in lower or "copy_rates" in lower):
        return "MT5_ERROR", first_match(["MT5", "initialize failed", "copy_rates"])
    if "traceback" in lower:
        return "TRACEBACK", first_match(["Traceback", "Exception", "Error"])
    return "UNKNOWN", first_match(["Error", "Exception", "failed"]) or "unknown failure"


def _fmt_utc(epoch_text: str | None) -> str:
    if not epoch_text:
        return ""
    try:
        ts = int(epoch_text)
    except Exception:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")


def _parse_entries(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in text.splitlines():
        if "[M1][ENTRY] created" not in line:
            continue
        m = ENTRY_RE.search(line)
        d = m.groupdict() if m else {}
        def _g(pat: str) -> str:
            mm = re.search(pat, line)
            return mm.group(1) if mm else ""

        ctx = d.get("ctx") or _g(r"ctx=([^\s]+)")
        direction = (d.get("dir") or _g(r"(?:dir|direction)=(BUY|SELL)")).upper()
        model1 = d.get("model1") or _g(r"model1_confirmation_time=(\d+)")
        entry_time = d.get("entry_time") or _g(r"chosen_entry_time=(\d+)")
        entry_price = d.get("entry_price") or _g(r"chosen_entry_price=([0-9.]+)")
        entries.append(
            {
                "ctx": ctx,
                "dir": direction,
                "model1_confirmation_time": model1,
                "model1_confirmation_time_utc": _fmt_utc(model1),
                "chosen_entry_time": entry_time,
                "chosen_entry_time_utc": _fmt_utc(entry_time),
                "chosen_entry_price": entry_price,
                "raw": line,
            }
        )
    return entries


def _parse_sl_sources(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in text.splitlines():
        m = SL_RE.search(line)
        if not m:
            continue
        k = str(m.group("source") or "").lower()
        if not k:
            continue
        out[k] = out.get(k, 0) + 1
    return out


def _gate_hints(text: str) -> dict[str, int]:
    out: dict[str, int] = {k: 0 for k in GATE_WORDS}
    for line in text.splitlines():
        ll = line.lower()
        for k in GATE_WORDS:
            if k in ll:
                out[k] += 1
    return {k: v for k, v in out.items() if v > 0}


def _fmt_counts(d: dict[str, int]) -> str:
    if not d:
        return ""
    return ",".join(f"{k}:{v}" for k, v in sorted(d.items(), key=lambda x: x[0]))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch audit trace_runner for forex symbols")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--from", dest="from_ts", default="2026-02-25 00:00:00+00:00")
    p.add_argument("--to", dest="to_ts", default="2026-02-27 00:00:00+00:00")
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--use-config-forex-symbols", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--market", default="forex")
    p.add_argument("--outdir", default="out/forex_audit_2026-02-25_2026-02-26")
    p.add_argument("--keep-full-logs", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--max-symbols", type=int, default=0)
    p.add_argument("--error-tail-lines", type=int, default=80)
    p.add_argument("--debug-failures", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--max-print-entries", type=int, default=5)
    p.add_argument("--write-entries-csv", action=argparse.BooleanOptionalAction, default=True)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    symbols = [str(s) for s in (args.symbols or [])]
    if not symbols and args.use_config_forex_symbols:
        cfg = _load_cfg(args.config)
        symbols = _cfg_symbols(cfg)
    if not symbols:
        raise SystemExit("No symbols provided. Use --symbols or --use-config-forex-symbols.")
    if int(args.max_symbols) > 0:
        symbols = symbols[: int(args.max_symbols)]

    outdir = Path(args.outdir)
    if not outdir.is_absolute():
        outdir = (REPO_ROOT / outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    raw_dir = outdir / "raw"
    if args.keep_full_logs:
        raw_dir.mkdir(parents=True, exist_ok=True)

    summary_lines: list[str] = []
    csv_rows: list[dict[str, str]] = []
    entries_rows: list[dict[str, str]] = []

    for symbol in symbols:
        cmd = [
            sys.executable,
            "-m",
            "src.tools.trace_runner",
            "--config",
            args.config,
            "--market",
            args.market,
            "--symbol",
            symbol,
            "--from",
            args.from_ts,
            "--to",
            args.to_ts,
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = "."
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), env=env)
        combined = (proc.stdout or "") + ("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or "")

        raw_log_path = ""
        if args.keep_full_logs:
            p = raw_dir / f"{symbol}.log"
            p.write_text(combined, encoding="utf-8")
            raw_log_path = str(p)

        marker_lines = _extract_markers(combined)
        entries = _parse_entries(combined)
        sl_sources = _parse_sl_sources(combined)
        gate_counts = _gate_hints(combined)

        has_data_loaded = any("[DATA] Loaded" in x for x in marker_lines)
        pipeline_present = any("[PIPELINE]" in x for x in marker_lines)
        last_loaded = ""
        for line in marker_lines:
            if "[DATA] Loaded" in line:
                last_loaded = line

        entries_total = len(entries)
        entries_buy = sum(1 for e in entries if e.get("dir") == "BUY")
        entries_sell = sum(1 for e in entries if e.get("dir") == "SELL")
        ctx_unique = len({e.get("ctx", "") for e in entries if e.get("ctx", "")})
        first_entry_utc = entries[0].get("chosen_entry_time_utc", "") if entries else ""
        last_entry_utc = entries[-1].get("chosen_entry_time_utc", "") if entries else ""

        has_entry_created = entries_total > 0
        has_markers = has_entry_created or bool(marker_lines)

        notes: list[str] = []
        error_kind = ""
        error_hint = ""
        if proc.returncode != 0:
            notes.append("TRACE_ERROR")
            error_kind, error_hint = _classify_error(combined)
        elif entries_total > 0:
            notes.append("HAS_ENTRIES")
        else:
            notes.append("NO_ENTRIES")
        if not has_markers and proc.returncode != 0:
            notes.append("NO_MARKERS")
        if has_data_loaded and ("bars=0" in last_loaded or "h1=0" in last_loaded or "m1=0" in last_loaded):
            notes.append("DATA_ZERO")

        block = [f"=== {symbol} === returncode={proc.returncode}"]
        if entries_total > 0:
            block.append(
                f"entries={entries_total} (BUY={entries_buy} SELL={entries_sell}) "
                f"first_entry_utc={first_entry_utc or 'N/A'} last_entry_utc={last_entry_utc or 'N/A'} ctx_unique={ctx_unique}"
            )
        else:
            block.append(
                f"entries=0 no entries found gate_hints={_fmt_counts(gate_counts) or 'none'}"
            )

        if args.verbose and entries_total > 0:
            block.append("entry_samples:")
            for e in entries[: max(1, int(args.max_print_entries))]:
                block.append(
                    f"  ctx={e.get('ctx','')} dir={e.get('dir','')} model1_confirmation_time_utc={e.get('model1_confirmation_time_utc','')} "
                    f"chosen_entry_time_utc={e.get('chosen_entry_time_utc','')} chosen_entry_price={e.get('chosen_entry_price','')}"
                )

        if marker_lines:
            block.extend(marker_lines)
        else:
            if has_entry_created:
                block.append("marker_status=entry_detected_without_legacy_markers")
            else:
                block.append("NO MARKERS FOUND")

        if sl_sources:
            block.append(f"sl_sources={_fmt_counts(sl_sources)}")
        if gate_counts:
            block.append(f"gate_hints={_fmt_counts(gate_counts)}")

        if notes:
            block.append(f"notes={';'.join(notes)}")
        if error_kind:
            block.append(f"error_kind={error_kind}")
        if error_hint:
            block.append(f"error_hint={error_hint}")

        if proc.returncode != 0:
            tail = _tail_lines(combined, int(args.error_tail_lines))
            if tail:
                block.append("--- error tail ---")
                block.extend(tail)
                block.append("--- end error tail ---")
        elif args.debug_failures and entries_total == 0:
            tail = _tail_lines(combined, int(args.error_tail_lines))
            if tail:
                block.append("--- log tail ---")
                block.extend(tail)
                block.append("--- end log tail ---")

        block.append("")

        if not args.quiet:
            print("\n".join(block))

        summary_lines.extend(block)
        csv_rows.append(
            {
                "symbol": symbol,
                "returncode": str(proc.returncode),
                "entries_total": str(entries_total),
                "entries_buy": str(entries_buy),
                "entries_sell": str(entries_sell),
                "first_entry_utc": first_entry_utc,
                "last_entry_utc": last_entry_utc,
                "ctx_unique": str(ctx_unique),
                "sl_sources": _fmt_counts(sl_sources),
                "gate_hints": _fmt_counts(gate_counts),
                "has_data_loaded": str(bool(has_data_loaded)),
                "last_loaded_hint": last_loaded,
                "pipeline_present": str(bool(pipeline_present)),
                "notes": ";".join(notes),
                "error_kind": error_kind,
                "error_hint": error_hint,
                "raw_log_path": raw_log_path,
            }
        )

        for e in entries:
            entries_rows.append(
                {
                    "symbol": symbol,
                    "ctx": e.get("ctx", ""),
                    "dir": e.get("dir", ""),
                    "model1_confirmation_time_utc": e.get("model1_confirmation_time_utc", ""),
                    "chosen_entry_time_utc": e.get("chosen_entry_time_utc", ""),
                    "chosen_entry_price": e.get("chosen_entry_price", ""),
                }
            )

    (outdir / "summary.txt").write_text("\n".join(summary_lines).rstrip() + "\n", encoding="utf-8")
    with (outdir / "summary.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "returncode",
                "entries_total",
                "entries_buy",
                "entries_sell",
                "first_entry_utc",
                "last_entry_utc",
                "ctx_unique",
                "sl_sources",
                "gate_hints",
                "has_data_loaded",
                "last_loaded_hint",
                "pipeline_present",
                "notes",
                "error_kind",
                "error_hint",
                "raw_log_path",
            ],
        )
        w.writeheader()
        w.writerows(csv_rows)

    if args.write_entries_csv:
        with (outdir / "entries.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "symbol",
                    "ctx",
                    "dir",
                    "model1_confirmation_time_utc",
                    "chosen_entry_time_utc",
                    "chosen_entry_price",
                ],
            )
            w.writeheader()
            w.writerows(entries_rows)

    if args.quiet:
        print(f"Wrote: {outdir / 'summary.txt'}")
        print(f"Wrote: {outdir / 'summary.csv'}")
        if args.write_entries_csv:
            print(f"Wrote: {outdir / 'entries.csv'}")


if __name__ == "__main__":
    main()
