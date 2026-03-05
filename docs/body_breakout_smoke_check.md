# CRT+TBS BODY-breakout smoke check

Quick production check (forex + crypto) after deploy.

1. Enable debug logs for `src.strategy.m1_execution.tbs_detector`.
2. Run bot for at least 1 day on one forex symbol and one crypto symbol.
3. Verify in logs:
   - `breakout_check=BODY` appears with OHLC/body fields.
   - Case A (wick-only): high/low crosses CRT, but body stays inside => no confirmed TBS.
   - Case B (body-breakout): body crosses CRT => confirmed TBS.
   - Case C (SL): resulting SL is strictly beyond wick extreme + buffer.

Recommended grep examples:

```bash
rg "breakout_check=BODY|sweep_found|\[ENTRY\]\[SL\]" logs/live.log
```

For each confirmed TBS, verify `tbs_wick_extreme_high/low` covers breakout bar and all bars until return.
