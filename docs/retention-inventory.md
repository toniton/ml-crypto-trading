# Data Retention Inventory & Dependency Map

This document is the Phase 0 deliverable for Rio's centralized Data Retention Policy.
It maps every persisted data category to its owner table/source, its timestamp column,
its dependencies, whether it can be rebuilt, and the proposed default retention policy.

Retention durations below are illustrative defaults, not legal or regulatory advice.

## Data categories

| Category | Table / source | Definition | Timestamp | Dependencies (must not break) | Rebuildable | Default policy |
|---|---|---|---|---|---|---|
| `FINANCIAL` | `orders`, `trades` | `src/database/dao/order_dao.py`, `trade_dao.py` | `created_timestamp` / `entry_timestamp` | `trades` references `orders.uuid`; `trading_decisions.resulting_order_id` | No | **KEEP** (indefinite until archival policy) |
| `TRADING_DECISION` | `trading_decisions` | `trading_decision_dao.py` | `timestamp` | soft FK to `orders.id`, `vcs_commits.hash` | No | 730d / KEEP (tracked, not deleted) |
| `TRACE` | `timeline_items` | `timeline_item_dao.py` | `timestamp` | soft refs via `entities`/`artifacts` JSON | No | 90d / ARCHIVE |
| `METRICS` | `metric_definitions`, `metric_samples` | `metric_definition_dao.py`, `metric_sample_dao.py` | `timestamp` | FK `metric_id` | No | 30d / DELETE |
| `RUNTIME_ALERT` | `runtime_incidents`, `runtime_error_events` | `runtime_incident_dao.py` | `first_seen` / `timestamp` | FK SET NULL; `commit_hash` | No | 180d / AGGREGATE_THEN_DELETE |
| `EXPERIMENT` | `experiments` | `experiment_dao.py` | `created_at` | soft refs `branch_id`, `base_commit_hash`, `run_bindings` | No | **KEEP** |
| `EXPERIMENT_ARTIFACT` | `experiments.report` (JSON) | `experiment_dao.py` | `updated_at` | referenced by experiment views | No | 90d / DELETE (trim) |
| `REPORT` | `backtest_sessions`, `backtest_results`, `walk_forward_runs` | `backtest_session_dao.py`, `backtest_result_dao.py`, `walk_forward_dao.py` | `created_at` | FK CASCADE; referenced by `experiments.run_bindings` | No | 365d / DELETE (dependency-aware) |
| `CONFIG_HISTORY` | `vcs_blobs`, `vcs_commits`, `vcs_refs` | `blob_dao.py`, `commit_dao.py`, `reference_dao.py` | `created_at` | **RESTRICT FKs**; soft `commit_hash` refs from orders/decisions/experiments/incidents | No | **KEEP** |
| `MARKET_DATA` | `data/datasets/{id}.csv` + `.meta.json` | `src/server/services/dataset_service.py` | file mtime | referenced from `backtest_sessions.config`, `experiments.spec`, `walk_forward_runs.spec` | Sometimes | 365d / DELETE (dependency-aware) |
| `APPLICATION_LOG` | `application-*.log`, `trading-*.log`, `agent-*.log`, `audit-*.log[.N]` | `src/logging/manager.py` | file mtime | none (rotated files only) | No | 30d / DELETE (rotated files only) |
| `MARKET_DATA_BUFFER` | `MarketDataStore` recorded observations | `src/recorder/market_data_store.py` | observation epoch (`MarketData.timestamp`) | read by `RecordedMarketDataSource` for backtests | Yes | **6h / DELETE** (time-based, configurable) |
| `CACHE` | other in-memory buffers | n/a | n/a (in-memory) | none | Yes | 1d / KEEP (no-op) |

> Note: `MARKET_DATA_BUFFER` governs the in-memory `MarketDataStore` only and defaults to a
> short 6h window because it is high-volume and rebuildable. If recorded data needs to survive
> longer for the backtest data source, add a **flush** step that persists the buffer to a
> `MARKET_DATA` dataset before expiry rather than extending the in-memory window.

## Dependency rules

- Financial records (`orders`, `trades`) are never cascade-deleted because a Trace, experiment,
  or report expired. Default mode is `KEEP`.
- Trace detail may expire while `trading_decisions` and order links are retained.
- Experiments retain definition, trigger provenance, config commit reference, dataset identity
  and essential report metadata indefinitely. Bulky intermediate artifacts expire separately.
- A shared market dataset is not deleted while a retained experiment or report depends on it.
- A VCS commit or blob that is still referenced by a ref, experiment, order, decision, or
  incident is never garbage-collected (`RESTRICT` FKs are honored).

## Eligibility vs. deletion

Retention is a two-stage process: (1) identify records eligible for retention actions,
(2) check references/dependencies before archiving or deleting. When a dependency blocks a
deletion the operation is deferred and the reason (`DEPENDENCY`, `LEGAL_HOLD`) is recorded
on the run. Nothing is deleted until an explicit execution run (with `dry_run: false`).

## Gathering storage estimates

Run these against the primary database to baseline defaults before enabling enforcement
(primary key/size queries only; read-only):

```sql
SELECT relname AS table, n_live_tup AS rows, pg_total_relation_size(relid) AS bytes
FROM pg_stat_user_tables
WHERE relname IN (
  'orders','trades','trading_decisions','timeline_items',
  'metric_definitions','metric_samples','experiments',
  'backtest_sessions','backtest_results','walk_forward_runs',
  'vcs_blobs','vcs_commits','vcs_refs',
  'runtime_incidents','runtime_error_events',
  'conversations','conversation_messages'
)
ORDER BY bytes DESC;

-- Eligible-row preview per timestamped table (adjust interval).
SELECT count(*) FROM timeline_items WHERE timestamp < now() - interval '90 days';
SELECT count(*) FROM metric_samples WHERE timestamp < now() - interval '30 days';
```

Dataset and log storage:

```bash
du -sh data/datasets
du -ch *.log *.log.* | tail -1
```

The `GET /api/v1/retention/status` response surfaces `total_storage_bytes`, computed from the
per-policy `estimated_storage_bytes` where measurable (market data, logs) and `null` otherwise.
