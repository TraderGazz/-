# Audit: live outcome tracking + re-entry attempt=2

Дата аудита: 2026-02-21  
Scope: `src/tools/live_runner.py`, `src/tools/trace_runner.py`, `src/runtime/state_store.py`, `config/default.yaml`, профильные тесты.

---

## Использованные команды (C1)

```bash
rg -n "min_rr_tp1|rr_|reward|risk|tp1|sl" src/tools src/strategy src/runtime tests
rg -n "new_sweep|sweep_delta|anchor_time|sweep_time|sweep_price|_has_new_sweep" src/tools src/strategy tests
rg -n "mark_sent|was_sent|_entry_id|_signal_key|dedup|prevent_duplicates|sent_signals" src/tools src/runtime src/strategy tests
rg -n "load_state|save_state|state_path|live_state|sent_signals_path" src/tools src/runtime config tests
rg -n "_record_sl_exit_if_needed|set_last_exit\(|EXIT=SL|TP1|TP2|clear_active_trade|clear_active_entry" src/tools src/runtime tests
```

---

## Часть A — DRY audit (карта дублирования)

### A1) RR / risk / TP1 / SL

| Локация | Что делает | Статус |
|---|---|---|
| `src/tools/live_runner.py::_rr_to_tp1` | единая формула `abs(tp1-entry)/abs(entry-sl)` | **OK (single source)** |
| `src/tools/trace_runner.py` | использует импорт `_rr_to_tp1` из live_runner | **OK (reuse)** |
| `tests/test_reentry_logic.py` | тесты порогов 1.14/1.15 | **OK** |
| `src/paper/virtual_account.py` | отдельная PnL/r-multiple логика для paper-account | **Ожидаемо отдельный домен** |

Вывод:
- Для re-entry RR формула не дублируется между live и trace (reuse есть).
- Потенциальная зона улучшения: вынести `_rr_to_tp1` из `live_runner` в отдельный `src/strategy/reentry_utils.py`, чтобы утилита не жила в runtime-инструменте.

### A2) Sweep / new-sweep detection

| Локация | Логика | Статус |
|---|---|---|
| `src/tools/live_runner.py::_has_new_sweep` | единая проверка time + delta + direction | **OK (single source)** |
| `src/tools/live_runner.py::_sweep_delta_price` | delta из points/spread/min_tick | **OK (single source)** |
| `src/tools/live_runner.py` re-entry | `new_extreme_time/new_extreme` берутся из `tbs.meta`, anchor=`new_extreme_time` | **INCONSISTENT vs trace** |
| `src/tools/trace_runner.py` re-entry | ищет `sweep_bar` через `_find_sweep_bar`, anchor=`sweep_bar.time` | **INCONSISTENT vs live** |

Вывод:
- Базовые primitive shared (`_has_new_sweep`, `_sweep_delta_price`) — хорошо.
- Но pipeline anchor-time отличается: live ориентируется на текущий `tbs.meta`, trace — на отдельный sweep-bar search после SL. Это даёт расхождения по re-entry разрешению.

### A3) Dedup keys для ENTRY/alert

| Локация | Ключ | Attempt учтён? | Статус |
|---|---|---:|---|
| `src/tools/live_runner.py::_entry_id` | `market:symbol:ctx_id:ENTRY:entry_time:direction:attempt=n` | Да | **OK** |
| `src/tools/live_runner.py::_signal_key` | `symbol-ctx_id-entry_time-direction-attempt=n` | Да | **OK** |
| `src/tools/live_runner.py` | `was_sent/mark_sent + sent_signals` | Да | **OK** |
| `src/tools/trace_runner.py` | для attempt=2 dedup использует `_entry_id(..., context.id, ..., 2, ...)` | Да, но **ctx_id не re2** | **INCONSISTENT** |

Вывод:
- В live dedup полностью attempt-aware.
- В trace есть несогласованность: re-entry считается на cloned context `:re2`, но dedup key строится по `context.id` (origin), а не `re_context.id`.

### A4) State-store “параллельные реализации”

| Наблюдение | Статус |
|---|---|
| `live_runner` использует единый `load_state/save_state` и `runtime.state_path` | **OK** |
| `save_state` делает `mkdir(parents=True, exist_ok=True)` | **OK** |
| Есть отдельный файл `sent_signals.json` вне `state_store` (локальный JSON helper в live_runner) | **INCONSISTENT (второй dedup-store)** |
| `trace_runner` импортирует приватный `_default_state` напрямую | **INCONSISTENT (обход публичного API)** |

### A5) SL/exit recording

| Локация | Поведение | Статус |
|---|---|---|
| `_record_sl_exit_if_needed` (live) | идемпотентность по `(reason,time)`, increment attempts только на SL | **OK** |
| `_monitor_active_trades` (live) | SL/TP1/TP2 first-hit на закрытых M1, `SL_FIRST` приоритет | **OK** |
| `trace_runner` | вызывает `_record_sl_exit_if_needed` на SL, чистит active entry | **OK** |

Риск:
- В `_monitor_active_trades` фильтр активных сделок идёт по глобальному `ctx_active_sl` без привязки `ctx -> symbol`, т.е. при мульти-символьном цикле возможен кросс-символьный false-exit.

---

## Часть B — components checklist

| Компонент | Статус | Файл/заметка |
|---|---|---|
| `last_processed_bars` | OK | `state_store` есть |
| sent-store (`mark_sent/was_sent`) | OK | `state_store` есть |
| `ctx_reentry_attempts` | OK | есть |
| `ctx_last_exit_reason/time/sweep_extreme/entry_direction` | OK | есть |
| `ctx_active_*` для live outcome tracking | OK | есть полный набор |
| `save_state` mkdir parent | OK | есть |
| ENTRY → Telegram → mark_sent → lock → active-trade write | OK | live pipeline собран |
| Outcome monitor по закрытым M1 | OK | `_monitor_active_trades` присутствует |
| Re-entry variant B gates (new sweep, anchor, RR, max attempts) | PARTIAL | логика есть, но live/trace anchor не полностью parity |
| Attempt-aware dedup | PARTIAL | live OK, trace re-entry key не на `:re2` |
| lock_scope=context conflict for attempt=2 | OK | live ставит lock по re-entry ctx id |
| Trace parity with live | INCONSISTENT | отличается anchor/dedup-key поведение |

### B2) Краткая схема live-потока

`fetch candles -> latest_closed anti-replay gate -> build contexts -> monitor_active_trades -> detect TBS/Model1 -> try_entry -> telegram send -> mark_sent/sent_signals -> set_lock -> set_last_exit(OPEN) + set_active_trade -> save_state`

### B3/B4/B5 итог

- Полный базовый live-цикл **ENTRY → monitor SL/TP → record exit → re-entry attempt=2** присутствует.
- Критичные несоответствия не блокируют цикл целиком, но есть 3 важных consistency-gap:
  1. нет symbol-фильтра у active trade monitor;
  2. trace attempt=2 dedup key использует origin ctx_id;
  3. live/trace различаются по source anchor-time после SL.

### B6) Source of truth

**Source of truth = `live_runner`** (по требованию для прод-поведения). `trace_runner` рекомендуется привести к тем же правилам dedup/anchor.

---

## Часть C2 — recommended single source of truth

Рекомендуемые единые функции (вынести в `src/strategy/reentry_utils.py`):

1. `calc_rr_tp1(entry, sl, tp1, direction)`
2. `is_new_sweep_after_sl(last_extreme, new_extreme, delta, direction, last_exit_time, new_sweep_time)`
3. `make_entry_dedup_key(ctx_id, direction, chosen_entry_time, attempt, symbol, market)`
4. `record_sl_exit(state, ctx_id, now_ts, sweep_extreme, direction, tbs_level)` (идемпотентный)

---

## Часть D — минимальный список правок (max 10)

1. Добавить `ctx_active_symbol` в state и фильтровать `_monitor_active_trades` по текущему `symbol`.
2. Заполнять `ctx_active_symbol` в `set_active_trade(...)` и удалять в `clear_active_trade(...)`.
3. В `trace_runner` для attempt=2 dedup key использовать `re_context.id` вместо `context.id`.
4. В `trace_runner` для event `context_id` у attempt=2 писать `re_context.id`.
5. Убрать импорт приватного `_default_state` из trace; добавить публичный `new_state()` в `state_store` (или использовать `load_state` fallback).
6. Вынести `_entry_id/_signal_key` в общую утилиту (единый генератор dedup keys).
7. Вынести `_rr_to_tp1` в общую strategy-утилиту (не в tool-layer).
8. Явно унифицировать anchor-time policy между live и trace (документ + код).
9. Добавить unit-test: multi-symbol active trades не должны закрываться чужими свечами.
10. Добавить parity-test: одинаковый synthetic-case должен дать одинаковое решение по re-entry в live-like и trace simulate_outcomes.

---

## Короткий TODO

- [ ] symbol-aware active trade monitor
- [ ] trace dedup/context id parity for `:re2`
- [ ] extract shared reentry primitives to `strategy/reentry_utils`
- [ ] add multi-symbol and live/trace parity tests
