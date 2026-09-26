# PR #1323: fresh matched market-data evidence

Native is unmodified X8 v18.0.82 at `fe76d7aeaeb785eb6f6a145d86fda7b7eaffcadd`; modified is PR head `79a210275f76755c15c23490f129ad26cbb3959f`. The strategy PR still changes only its 47 implied protection clauses and associated comments. This separate evidence branch does not add artifacts to that PR diff.

## Result

Two fresh official Freqtrade runs: 2026-01-01 through 2026-08-06 exclusive, 19 Binance futures pairs, 5m, six slots, 100,000 USDT, fee 0.0005 per side. Only affected signals 166/169/171/664/665 enabled in both arms; other entry signals disabled. Native PA, grinding, de-risk and exits retained; requested leverage 3x with actual exchange tier caps.

- Exact equality: 441 complete trades, 1,712 nested order records, all economic statistics, 1,187,424 engine rows per arm, effective settings, exchange pricing metadata and leverage tiers.
- Both arms: 401 wins / 40 losses; official net PnL -59,146.010779790005 USDT; closed-trade drawdown 66.48884926669492%; captured-wallet-balance drawdown 63.61143013155454%.
- All five signals have nonzero engine and filled-trade coverage. The single mixed `166 169` trade is its own disjoint cohort, not counted twice in portfolio totals.
- No profitability, live-safety, activation, or wall-clock speed claim. This five-experimental-signal portfolio is **not** the default-fleet configuration, and its substantial loss is present in both arms.

See [full comparison](COMPARISON.md), [machine-readable comparison](COMPARISON.json), and [independent accounting](validation/INDEPENDENT_ACCOUNTING.json). Drawdowns are closed-trade cumulative-profit and wallet-balance statistics respectively, not marked-to-market open-trade equity. Losing-trade PnL is already included in net PnL.

## Verify archived results without Freqtrade

From this directory, using Python 3.11 or newer and its standard library:

```sh
python3 compare_results.py --recovery-receipt recovery/RECOVERY.json --output-dir /tmp/pr1323-recheck
```

This reads both original, unmodified official ZIPs and their embedded strategies/configurations, checks full trade/order and semantic-stat equality, checks all five signal memberships, verifies locked inputs and Docker completion evidence, and reconciles exact serialized-trade Decimal totals. Official binary-float aggregate PnL can differ from that Decimal sum by serialization-scale rounding; **between-arm equality is exact**, not tolerance-based. Only the two wall-clock run timestamps and documented nonsemantic config/redaction fields are excluded.

The archive contains original result ZIPs, logs, observers, configuration, sources, commands and receipts. `SHA256SUMS.json` hashes the published files. Market candle data is not included; `DATA_LOCKS.json` records all 133 input hashes and reused date-coverage information. No earlier trade backtest is reused.

## Interrupted coordinator, completed engines

The host tool stopped its coordinator at the 3,600-second limit. Native had already finished; Modified received SIGTERM but subsequently completed its full-period export and Docker recorded exitCode 0. Both actual Docker start/die events are preserved in `recovery/DOCKER_EVENTS.json`. No backtest was restarted.

Original `execution/STATUS.json` remains the historical RUNNING receipt, and Modified has no fabricated `status.json` or CLI return code. The explicit opt-in recovery path checks actual Docker completion, export run intervals, original commands, and fresh post-interruption hashes of all 133 data files, seven launch inputs and both root strategies. Modified **container** exit code is observed as 0; its original **CLI** return code is unknown. Observer hashes were captured during recovery, not cryptographically attested at capture time. Read `recovery/RECOVERY.json` and `COMPARISON.md` for the complete limits. The failed first consumer attempt is retained: it rejected incidental wording (`timed out` versus `timeout`); this prose-based gate was removed, without changing data, strategy, or results.

## Repeating the market-data run

`PLAN.json`, `config.json`, `sources/`, `observe_backtest.py` and each arm's `COMMAND.json` preserve the exact executed inputs and argv. `run_matched.py` is retained as original provenance; its workspace-global lease helper comes from the separately installed NFI Signal Tools and is not bundled here. Do not run it as a standalone public runner or overwrite the archived executions.

For an independent rerun, use the immutable image below, the same hashed data in a directory containing `futures/`, this read-only evidence directory at `/study`, and **fresh separate writable userdirs** for each arm. Adapt host mount paths from `COMMAND.json`, retaining `/study/sources/native` versus `/study/sources/modified`, `--timerange 20260101-20260806 --cache none --export signals`, the shared config, and `PARITY_OUTPUT` pointing to that arm's writable userdir. Keep all other recorded command options unchanged. Exchange market metadata is fetched live, not silently frozen; compare its captured values with the archived `exchange_inputs.json`. Changed future exchange metadata or different candle hashes do not constitute the same-input comparison. The original recovery receipt certifies only these archived outputs, not a new run.

Image: `freqtradeorg/freqtrade@sha256:4d23160b501d2b34579e76f57ad75edfa274967cd0dd824ff1c1b86d8c166ab4` (Freqtrade 2026.8).

Pinned reporting/engine source files under `runtime_sources/` were extracted from that image, with SHA receipts. They originate from [Freqtrade](https://github.com/freqtrade/freqtrade/tree/2026.8), GPL-3.0; NFI snapshots remain subject to the repository's existing license.
