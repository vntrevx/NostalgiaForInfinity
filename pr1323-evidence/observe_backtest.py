"""Run official Freqtrade; observe effective settings and its actual entry rows.

No strategy source, callback result, order handling, price or engine row is changed.
"""
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
import sys

from freqtrade.main import main
from freqtrade.optimize.backtesting import Backtesting, DATE_IDX, ENTER_TAG_IDX

OUT = Path(os.environ["PARITY_OUTPUT"])
OUT.mkdir(parents=True, exist_ok=True)
original_set_strategy = Backtesting._set_strategy
original_get_rows = Backtesting._get_ohlcv_as_lists
AFFECTED = {"166", "169", "171", "664", "665"}


def set_strategy(self, strategy):
  result = original_set_strategy(self, strategy)
  names = [name for name in dir(strategy) if any(part in name for part in ("derisk", "bad_trade", "buyback", "grind"))]
  names += ["position_adjustment_enable", "grinding_enable", "timeframe", "use_exit_signal",
            "exit_profit_only", "ignore_roi_if_entry_signal", "system_name_use", "futures_mode_leverage",
            "long_entry_signal_params", "short_entry_signal_params", "num_cores_indicators_calc"]
  effective = {name: getattr(strategy, name) for name in sorted(set(names))
               if not callable(getattr(strategy, name))}
  enabled = {key.rsplit("_", 2)[1] for side in ("long", "short")
             for key, value in getattr(strategy, f"{side}_entry_signal_params").items() if value}
  assert enabled == AFFECTED, enabled
  (OUT / "effective_parameters.json").write_text(json.dumps(effective, indent=2, default=str) + "\n")
  fields = ("symbol", "base", "quote", "settle", "type", "active", "contractSize",
            "linear", "inverse", "precision", "limits")
  pairs = strategy.config["exchange"]["pair_whitelist"]
  exchange_inputs = {
    "precision_mode": self.exchange.precisionMode,
    "precision_mode_price": self.exchange.precision_mode_price,
    "markets": {pair: {key: self.exchange.markets[pair].get(key) for key in fields} for pair in pairs},
    "leverage_tiers": {pair: self.exchange._leverage_tiers[pair] for pair in pairs},
  }
  (OUT / "exchange_inputs.json").write_text(json.dumps(exchange_inputs, indent=2, default=str) + "\n")
  return result


def get_rows(self, processed):
  rows_by_pair = original_get_rows(self, processed)
  records = {}
  for pair, rows in rows_by_pair.items():
    digest = hashlib.sha256()
    counts = Counter()
    for row in rows:
      digest.update(json.dumps(row, default=str, separators=(",", ":")).encode())
      digest.update(b"\n")
      counts.update(str(row[ENTER_TAG_IDX] or "").split())
    records[pair] = {"rows": len(rows), "first": str(rows[0][DATE_IDX]) if rows else None,
                     "last": str(rows[-1][DATE_IDX]) if rows else None,
                     "engine_rows_sha256": digest.hexdigest(), "tagged_candles": dict(sorted(counts.items()))}
  (OUT / "engine_entry_rows.json").write_text(json.dumps(records, indent=2) + "\n")
  return rows_by_pair


Backtesting._set_strategy = set_strategy
Backtesting._get_ohlcv_as_lists = get_rows
if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
