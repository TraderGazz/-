# Layer B Runbook (v9)

## Safe enable sequence
1. **Shadow canary (24-72h)**
   - `rollout.mode=canary`
   - `rollout.canary_symbols=[XAUUSD, EURUSD]`
   - `rollout.shadow_mode=true`
   - `rollout.send_enabled=false`
2. **Canary send**
   - `shadow_mode=false`
   - `send_enabled=true`
3. **Scale-out**
   - Add symbols in batches of 3-5 only after 1-2 stable weeks.

## Kill-switches
- Primary: `strategies.layer_b_9am_cr.enabled=false`
- Runtime: `state.layer_b_runtime_disabled=true`

## Safety defaults
- `safety.max_signals_per_symbol_per_day=1`
- `safety.max_signals_total_per_day=10`
- `safety.max_send_failures_before_auto_pause=5`

## Events to monitor
- Funnel: `LAYER_B_ADM_FIXED`, `LAYER_B_SWEEP_FIXED`, `LAYER_B_CRT15_PURGE_CONFIRMED`, `LAYER_B_M1_ENTRY_FOUND`
- Safety: `LAYER_B_SAFETY_PAUSED`, `LAYER_B_AUTO_PAUSED`
- Re-entry: `LAYER_B_REENTRY_ELIGIBLE`, `LAYER_B_REENTRY_INELIGIBLE`, `LAYER_B_REENTRY_SIGNAL_SENT`, `LAYER_B_REENTRY_RR_REJECTED`
- PREP: `LAYER_B_PREP_SENT`, `LAYER_B_PREP_SKIPPED_DEDUPE`

## Re-entry stop-out trigger (MVP)
Current implementation expects stop-out marker in `state.layer_b_reentry[*].stopout=true` (external/manual source).
Recommended operator flow for canary:
- Set stopout marker via admin tooling / runtime state script.
- Verify `LAYER_B_REENTRY_ELIGIBLE` before any re-entry send.

## Config changes and restart
This project currently applies strategy config at runtime cycle load; restart is recommended after major Layer B config edits (profiles, rollout, safety, reentry thresholds) for deterministic behavior.
