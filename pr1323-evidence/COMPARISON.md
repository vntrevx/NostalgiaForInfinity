# Official matched X8 comparison — 20260101-20260806 (exclusive end)

**PASS** — unmodified Native vs PR modified, one portfolio per arm under the frozen matched-study plan. A tagged cohort is **not** an independent signal-only backtest.

| Whole portfolio | Native before | Modified after | Difference (after − before) |
|---|---:|---:|---:|
| trades | 441 | 441 | 0 |
| wins | 401 | 401 | 0 |
| losses | 40 | 40 | 0 |
| zero | 0 | 0 | 0 |
| net_pnl | -59146.010779790004008 | -59146.010779790004008 | 0E-15 |
| losing_pnl_subtotal | -227703.9134178200035 | -227703.9134178200035 | 0E-13 |
| Official total_trades | 441 | 441 | 0 |
| Official profit_total_abs | -59146.010779790005 | -59146.010779790005 | 0E-12 |
| Official profit_total | -0.5914601077979 | -0.5914601077979 | 0E-13 |
| Official final_balance | 40853.989220210016 | 40853.989220210016 | 0E-12 |
| Official max_drawdown_account | 0.6648884926669492 | 0.6648884926669492 | 0E-16 |
| Official max_drawdown_abs | 81057.63818209 | 81057.63818209 | 0E-8 |
| Official wins | 401 | 401 | 0 |
| Official losses | 40 | 40 | 0 |
| Official draws | 0 | 0 | 0 |

Official strategy-stat max_drawdown_abs is the largest drop of cumulative closed-trade profit_abs from its running high (floored at zero), in wallet currency, with trades sorted by close_date. max_drawdown_account is the fraction lost at **that maximum-absolute-DD trough**: max_drawdown_abs / (starting_balance + cumulative PnL at its peak). The separately maximized relative metric is max_relative_drawdown. Neither statistic marks open trades to market; wallet_stats uses a separate wallet-snapshot series. Definition: pinned-image [report mapping](runtime_sources/optimize_reports.py) and [drawdown calculation](runtime_sources/metrics.py), [image/SHA receipt](runtime_sources/RECEIPT.json).
The losing-PnL subtotal is already included in net PnL; zero denotes exactly zero trade profit_abs.

Exact full enter_tag strings (JSON-quoted to preserve spaces) form **mutually exclusive** cohorts. Their counts, wins/losses/zero, net PnL, and losing subtotals reconcile exactly to the whole portfolio.
| Full enter_tag string | Native trades / W-L-Z / net PnL / losing subtotal | Modified trades / W-L-Z / net PnL / losing subtotal | Δ trades / net PnL / losses / losing subtotal |
|---|---:|---:|---:|
| `"166 "` | 106 / 95-11-0 / -38490.247038140001538 / -72479.2461502200015 | 106 / 95-11-0 / -38490.247038140001538 / -72479.2461502200015 | 0 / 0E-15 / 0 / 0E-13 |
| `"166 169 "` | 1 / 1-0-0 / 2207.25090927 / 0 | 1 / 1-0-0 / 2207.25090927 / 0 | 0 / 0E-8 / 0 / 0 |
| `"169 "` | 44 / 42-2-0 / 7559.36124637999996 / -10638.21428631 | 44 / 42-2-0 / 7559.36124637999996 / -10638.21428631 | 0 / 0E-14 / 0 / 0E-8 |
| `"171 "` | 20 / 16-4-0 / -14720.37628697000302 / -20094.554474380003 | 20 / 16-4-0 / -14720.37628697000302 / -20094.554474380003 | 0 / 0E-14 / 0 / 0E-12 |
| `"664 "` | 97 / 84-13-0 / -43978.47524328000080 / -74403.512874940000 | 97 / 84-13-0 / -43978.47524328000080 / -74403.512874940000 | 0 / 0E-14 / 0 / 0E-12 |
| `"665 "` | 173 / 163-10-0 / 28276.47563295000139 / -50088.385631969999 | 173 / 163-10-0 / 28276.47563295000139 / -50088.385631969999 | 0 / 0E-14 / 0 / 0E-12 |

Affected-signal **token membership** within this portfolio (not disjoint): a mixed full enter_tag can count toward more than one signal. Do not sum these cohorts into portfolio PnL.
| Signal token | Native trades / W-L-Z / net PnL / losing subtotal | Modified trades / W-L-Z / net PnL / losing subtotal | Δ trades / net PnL / losses / losing subtotal |
|---|---:|---:|---:|
| 166 | 107 / 96-11-0 / -36282.996128870001538 / -72479.2461502200015 | 107 / 96-11-0 / -36282.996128870001538 / -72479.2461502200015 | 0 / 0E-15 / 0 / 0E-13 |
| 169 | 45 / 43-2-0 / 9766.61215564999996 / -10638.21428631 | 45 / 43-2-0 / 9766.61215564999996 / -10638.21428631 | 0 / 0E-14 / 0 / 0E-8 |
| 171 | 20 / 16-4-0 / -14720.37628697000302 / -20094.554474380003 | 20 / 16-4-0 / -14720.37628697000302 / -20094.554474380003 | 0 / 0E-14 / 0 / 0E-12 |
| 664 | 97 / 84-13-0 / -43978.47524328000080 / -74403.512874940000 | 97 / 84-13-0 / -43978.47524328000080 / -74403.512874940000 | 0 / 0E-14 / 0 / 0E-12 |
| 665 | 173 / 163-10-0 / 28276.47563295000139 / -50088.385631969999 | 173 / 163-10-0 / 28276.47563295000139 / -50088.385631969999 | 0 / 0E-14 / 0 / 0E-12 |

| Engine tag | Native tagged candles | Modified tagged candles | Native filled membership | Modified filled membership |
|---|---:|---:|---:|---:|
| 166 | 1190 | 1190 | 107 | 107 |
| 169 | 380 | 380 | 45 | 45 |
| 171 | 335 | 335 | 20 | 20 |
| 664 | 1431 | 1431 | 97 | 97 |
| 665 | 2498 | 2498 | 173 | 173 |

Complete official trade and nested-order arrays are compared in exported sequence with no fields ignored or sorting. Semantic stats, official strategy-comparison summary, embedded config, engine rows, effective parameters, live exchange metadata and leverage tiers are compared exactly. Only official backtest_run_start_ts/backtest_run_end_ts are omitted from semantic stats; exported config_files paths and redacted disabled Telegram credentials are nonsemantic.
Stable official performance: True (trade/order arrays, derived stats and official strategy comparison).
Trade differences: 0; stats: 0; strategy comparison: 0; config: 0; effective: 0; engine: 0; exchange: 0.

## Recovered execution provenance

Explicit [recovery receipt](recovery/RECOVERY.json) and its hashed Docker events, original-state snapshot and fresh post-interruption hash map are verified. This is **not** an ordinary coordinator COMPLETE receipt. The original coordinator remains RUNNING after the 3600-second tool timeout; original Native PASS is intact and Modified has no arm status receipt.
Fresh input hashes: 133 data files, 7 frozen launch inputs and 2 preserved root strategies. Both exact Docker argv arrays retain the pinned image, source/config, read-only market data, no cache, signals export and separate arm userdirs. Both recorded engine containers die exitCode=0; Modified CLI returncode is **null/unknown**, not inferred from Docker exit.

- native: container `nfi-pr1323-native-438449-14a67495` (`af4d3aa12df1d67ff78c6cee82169953d1aa5528455c640164dfce3e88d52b27`), Docker start `2026-09-25T21:36:51.630759+00:00`, die `2026-09-25T22:11:25.806707+00:00`, engine exitCode=0; original CLI returncode `0`.
- modified: container `nfi-pr1323-modified-438449-38db929d` (`9cd82677381e7a12caba0c5e4bbe8afa2470e647c8206a454d9ad7ce8bb858d7`), Docker start `2026-09-25T22:11:26.198519+00:00`, die `2026-09-25T22:44:13.406550+00:00`, engine exitCode=0; original CLI returncode `None`.

Modified arm was recorded starting at `2026-09-25T22:11:25.924586+00:00`; Docker recorded SIGTERM at `2026-09-25T22:36:51.103028+00:00` before its eventual die exitCode=0. Official engine run epoch seconds in both ZIPs fall within their own Docker start/die interval.

**Recovery limits:**
- Original coordinator remains RUNNING; no COMPLETE/final runner rehash receipt
- Modified arm status.json was never written; CLI returncode unknown (null)
- Docker records modified SIGTERM before graceful engine die exitCode=0
- No backtest rerun is asserted by recovery receipt and recorded container lifecycles, not a proof against unrecorded executions

Observer files and exports are SHA256-bound to the later recovery receipt, but the producer did not hash observers at capture time; Docker chronology is not capture-time cryptographic observer attestation.

- native ZIP SHA256 `7ddb40c33375b926710c09688115232f4fae12e43d8709b91a8d590a51f92253`; embedded strategy SHA256 `e7b6af6a7307d822c349f6ed4b1170566cafd2e5aaf6ed9a31c1a2f12c7edd35`; ZIP `/home/turing/project/X8_Project/research/x8_signals/code_review_20260926/matched_backtest/execution/native/backtest_results/backtest-result-2026-09-25_22-11-23.zip`
- modified ZIP SHA256 `f7e8d68bd2842ea380959219d9aafd39536c2c65a04590561b2c36eb93e93a1b`; embedded strategy SHA256 `c903185038e1626e32959a647121a2c04b75a13f0aa6ddc0c7127dd8cc7ea6d3`; ZIP `/home/turing/project/X8_Project/research/x8_signals/code_review_20260926/matched_backtest/execution/modified/backtest_results/backtest-result-2026-09-25_22-44-11.zip`
