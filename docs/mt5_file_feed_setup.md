# MT5 File Feed Setup (All pairs, multi-TF, no Python MT5 API)

This mode uses MT5 EA export files as forex source for bot/trace/live.

## Exported structure

`<MT5_FEED_DIR>/`
- `HEARTBEAT.txt`
- `<SYMBOL>/M1.csv`
- `<SYMBOL>/M15.csv`
- `<SYMBOL>/H1.csv`
- `<SYMBOL>/H4.csv`
- `<SYMBOL>/D1.csv`
- `<SYMBOL>/W1.csv`

Legacy flat files (`<SYMBOL>_<TF>.csv`) are still read as fallback.

## 1) Install EA

1. Copy `mt5/BarFeedExporter.mq5` to `MQL5/Experts/`.
2. Compile in MetaEditor.
3. In MT5 Market Watch click **Show All**.
4. Attach EA to any chart and enable Algo Trading.

### EA key inputs
- `UseMarketWatchSymbols=true`
- `OutDir=mt5_feed`
- `ExportM1/M15/H1/H4/D1/W1=true`
- bars defaults are preconfigured.

EA exports only **closed bars** (`shift=1`) and refreshes heartbeat each export.

## 2) Find Data Folder

MT5 -> `File -> Open Data Folder`, then locate:
`MQL5/Files/mt5_feed`

## 3) Bot config

`config/default.yaml`:

```yaml
markets:
  forex:
    data_source: "mt5_file"
    feed_dir: "${MT5_FEED_DIR}"
    stale_seconds: 180
```

`.env`:

```env
MT5_FEED_DIR=C:\path\to\terminal\MQL5\Files\mt5_feed
```

## 4) PowerShell checks

```powershell
py scripts\check_mt5_file_feed.py --config config\default.yaml --use-config-forex-symbols --timeframes M1,M15,H1,H4,D1,W1
```

```powershell
$env:PYTHONPATH="."
py -m src.tools.trace_runner --config config\default.yaml --market forex --symbol EURUSD --from "2026-02-25 00:00:00+00:00" --to "2026-02-27 00:00:00+00:00"
```

```powershell
$env:PYTHONPATH="."
py -m src.tools.live_runner --config config\default.yaml --market forex --once
```

```powershell
$env:PYTHONPATH="."
py scripts\forex_trace_audit.py --config config\default.yaml --from "2026-02-25 00:00:00+00:00" --to "2026-02-27 00:00:00+00:00" --use-config-forex-symbols --keep-full-logs
```

## 5) Stale policy

Stale is evaluated by `HEARTBEAT.txt` and/or latest M1 bar only.
D1/W1 are informational and not used for stale panic.
