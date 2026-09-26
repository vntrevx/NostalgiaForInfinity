"""Compare the two official, frozen Freqtrade backtest exports without rerunning them.

Only an archive with one actual result, configuration and strategy source is accepted
per arm. JSON numbers are parsed as Decimal; sequence order and every trade/order
field are compared, without tolerance or omission.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
STRATEGY = "NostalgiaForInfinityX8"
# These record wall-clock execution timing, not market-data or performance.
RUN_METADATA = {"backtest_run_start_ts", "backtest_run_end_ts"}
OFFICIAL_METRICS = (
  "total_trades", "profit_total_abs", "profit_total", "final_balance",
  "max_drawdown_account", "max_drawdown_abs", "wins", "losses", "draws",
)
COHORT_METRICS = ("trades", "wins", "losses", "zero", "net_pnl", "losing_pnl_subtotal")
# Inputs and identifiers are compared, but are not called performance statistics.
SETUP_STATS = {
  "backtest_start", "backtest_start_ts", "backtest_end", "backtest_end_ts",
  "backtest_days", "pairlist", "stake_amount", "stake_currency", "stake_currency_decimals",
  "starting_balance", "dry_run_wallet", "max_open_trades", "max_open_trades_setting",
  "timeframe", "timeframe_detail", "timerange", "enable_protections", "strategy_name",
  "freqaimodel", "freqai_identifier", "stoploss", "trailing_stop", "trailing_stop_positive",
  "trailing_stop_positive_offset", "trailing_only_offset_is_reached", "use_custom_stoploss",
  "minimal_roi", "use_exit_signal", "exit_profit_only", "exit_profit_offset",
  "ignore_roi_if_entry_signal", "trading_mode", "margin_mode",
}


class InvalidStudy(ValueError):
  pass


def require(condition, message):
  if not condition:
    raise InvalidStudy(message)


def sha256(data):
  return hashlib.sha256(data).hexdigest()


def read_json(data):
  return json.loads(data, parse_float=Decimal)


def json_value(value):
  if isinstance(value, Decimal):
    return str(value)
  if isinstance(value, dict):
    return {key: json_value(item) for key, item in value.items()}
  if isinstance(value, (tuple, list)):
    return [json_value(item) for item in value]
  return value


def differences(before, after, path=""):
  """Yield every differing leaf, including missing members and sequence positions."""
  if isinstance(before, dict) and isinstance(after, dict):
    for key in sorted(before.keys() | after.keys()):
      child = f"{path}/{key}"
      if key not in before or key not in after:
        yield {"field": child, "native": json_value(before.get(key, "<missing>")),
               "modified": json_value(after.get(key, "<missing>"))}
      else:
        yield from differences(before[key], after[key], child)
  elif isinstance(before, list) and isinstance(after, list):
    for index in range(max(len(before), len(after))):
      child = f"{path}/{index}"
      if index >= len(before) or index >= len(after):
        yield {"field": child, "native": json_value(before[index]) if index < len(before) else "<missing>",
               "modified": json_value(after[index]) if index < len(after) else "<missing>"}
      else:
        yield from differences(before[index], after[index], child)
  elif type(before) is not type(after) or before != after:
    yield {"field": path or "/", "native": json_value(before), "modified": json_value(after)}


def match_plan(actual, expected, path=""):
  """Validate all frozen configured settings, allowing exported runtime additions."""
  if isinstance(expected, dict):
    require(isinstance(actual, dict), f"Missing config object: {path}")
    for key, value in expected.items():
      require(key in actual, f"Missing frozen config setting: {path}/{key}")
      match_plan(actual[key], value, f"{path}/{key}")
  else:
    # Official exports may redact credentials; neither is a strategy input here.
    if path in ("/telegram/token", "/telegram/chat_id") and expected == "":
      require(actual in ("", "REDACTED"), f"Unexpected exported secret at {path}")
    else:
      require(actual == expected and (type(expected) is not bool or type(actual) is bool),
              f"Frozen config mismatch at {path}: {actual!r} != {expected!r}")


def semantic_export_config(config):
  """Exclude only generated file locations and disabled/redacted credentials."""
  relevant = {key: value for key, value in config.items() if key != "config_files"}
  relevant["telegram"] = dict(relevant["telegram"])
  for key in ("token", "chat_id"):
    relevant["telegram"][key] = "<disabled/redacted>"
  return relevant


def utc_time(value, label):
  timestamp = datetime.fromisoformat(value)
  require(timestamp.tzinfo is not None and timestamp.utcoffset().total_seconds() == 0,
          f"{label}: timestamp must include UTC offset")
  return timestamp.astimezone(timezone.utc)


def option(command, flag):
  require(command.count(flag) == 1, f"Runner command has ambiguous/missing {flag}")
  position = command.index(flag)
  require(position + 1 < len(command), f"Runner command lacks value for {flag}")
  return command[position + 1]


def verify_command(command, arm, directory, plan):
  """Bind actual Docker argv to pinned official image, inputs, mounts, and arm."""
  require(isinstance(command, list) and all(isinstance(arg, str) for arg in command),
          f"{arm}: runner command is not a string argv")
  container = option(command, "--name")
  require(container.startswith(f"nfi-pr1323-{arm}-"), f"{arm}: unexpected container identity")
  docker_user = option(command, "--user")
  require(len(docker_user.split(":")) == 2 and
          all(part.isdecimal() for part in docker_user.split(":")), f"{arm}: malformed Docker user")
  rt = plan["runtime"]
  mounted_study = next((arg for arg in command if arg.endswith(":/study:ro")), None)
  require(mounted_study is not None, f"{arm}: no read-only study mount")
  study_root = mounted_study.removesuffix(":/study:ro")
  require(Path(study_root).is_absolute() and Path(study_root).name == HERE.name,
          f"{arm}: unexpected recorded study mount")
  arm_mount = f"/study/execution/{arm}"
  expected = ["docker", "run", "--rm", "--pull", "never", "--name", container,
              "--cpus", str(rt["cpus"]), "--memory", rt["memory"], "--memory-swap", rt["memory"],
              "--user", docker_user, "--dns", "1.1.1.1", "--dns", "8.8.8.8",
              "-e", "OPENBLAS_NUM_THREADS=1", "-e", "OMP_NUM_THREADS=1",
              "-e", f"PARITY_OUTPUT={arm_mount}",
              "-v", mounted_study, "-v", f"{study_root}/execution/{arm}:{arm_mount}",
              "-v", f"{rt['data_host']}:/market-data:ro", "--entrypoint", "python",
              rt["image"], "/study/observe_backtest.py", "backtesting", "--strategy", STRATEGY,
              "--strategy-path", f"/study/sources/{arm}", "--userdir", arm_mount,
              "--config", "/study/config.json", "--datadir", "/market-data",
              "--timerange", plan["timerange"], "--cache", plan["execution_contract"]["cache"],
              "--export", plan["execution_contract"]["export"]]
  require(command == expected, f"{arm}: runner command differs from pinned matched official backtest")
  require(directory.resolve() == (HERE / "execution" / arm).resolve(),
          f"{arm}: execution directory differs from the official arm receipt")
  return container


def verify_execution_receipts(plan, directories):
  """Reject uncertified/incomplete runs, including a failed final data rehash."""
  locks_path = HERE / "LAUNCH_LOCKS.json"
  locks = read_json(locks_path.read_bytes())
  required = {"PLAN.json", "DATA_LOCKS.json", "config.json", "observe_backtest.py", "run_matched.py"}
  required.update(source["path"] for source in plan["sources"].values())
  require(required <= locks.keys(), "LAUNCH_LOCKS omits frozen input files")
  for relative_path, expected in locks.items():
    input_file = (HERE / relative_path).resolve()
    require(input_file.is_relative_to(HERE) and input_file.is_file(),
            f"Unsafe or missing frozen input: {relative_path}")
    require(sha256(input_file.read_bytes()) == expected, f"Frozen launch input changed: {relative_path}")
  prelaunch_path = HERE / "validation/PRELAUNCH.json"
  prelaunch = read_json(prelaunch_path.read_bytes())
  require(prelaunch["status"] == "PASS" and
          prelaunch["launch_locks_sha256"] == sha256(locks_path.read_bytes()),
          "Frozen-input prelaunch approval does not match launch locks")
  require(plan["execution_contract"]["cache"] == "none" and
          plan["execution_contract"]["export"] == "signals", "Frozen official export contract changed")
  status_path = HERE / "execution/STATUS.json"
  coordinator = read_json(status_path.read_bytes())
  require(coordinator["stage"] == "COMPLETE" and coordinator["completed"] == plan["arms"] and
          coordinator.get("current") is None and not coordinator.get("data_error"),
          "Coordinator not complete after the pinned runner's final data-hash verification")
  start = utc_time(coordinator["started_utc"], "coordinator start")
  finish = utc_time(coordinator["finished_utc"], "coordinator finish")
  require(utc_time(prelaunch["approved_utc"], "prelaunch approval") <= start <= finish,
          "Prelaunch/coordinator chronology is invalid")
  arms = {}
  previous_finish = start
  for arm in plan["arms"]:
    directory = directories[arm]
    command_path = directory / "COMMAND.json"
    arm_status_path = directory / "status.json"
    command = read_json(command_path.read_bytes())
    container = verify_command(command, arm, directory, plan)
    arm_status = read_json(arm_status_path.read_bytes())
    arm_start = utc_time(arm_status["started_utc"], f"{arm} start")
    arm_finish = utc_time(arm_status["finished_utc"], f"{arm} finish")
    require(arm_status["status"] == "PASS" and type(arm_status["returncode"]) is int and
            arm_status["returncode"] == 0, f"{arm}: official runner did not pass")
    require(previous_finish <= arm_start <= arm_finish <= finish,
            f"{arm}: execution order/timestamps disagree with coordinator")
    export = arm_status["export"]
    require(type(export) is str and export.startswith("backtest_results/") and
            len(Path(export).parts) == 2 and Path(export).suffix == ".zip",
            f"{arm}: recorded ZIP is not an official arm backtest export")
    arms[arm] = {
      "status_sha256": sha256(arm_status_path.read_bytes()),
      "command_sha256": sha256(command_path.read_bytes()),
      "started_utc": arm_status["started_utc"], "finished_utc": arm_status["finished_utc"],
      "recorded_export": export, "container": container,
    }
    previous_finish = arm_finish
  return {
    "launch_locks_sha256": sha256(locks_path.read_bytes()),
    "prelaunch_sha256": sha256(prelaunch_path.read_bytes()),
    "execution_status_sha256": sha256(status_path.read_bytes()),
    "final_data_hash_check": "PASS: pinned runner emits COMPLETE only after final data_hashes(plan)",
    "observer_capture": "Fresh independent arm directories/command chronology; no observer-file SHA attestation",
    "arms": arms,
  }


def embedded_archive(arm, directory, plan, frozen_config):
  archives = sorted(directory.rglob("*.zip"))
  require(len(archives) == 1, f"{arm}: expected exactly one official ZIP under {directory}, found {len(archives)}")
  archive = archives[0]
  with ZipFile(archive) as bundle:
    names = bundle.namelist()
    require(len(names) == len(set(names)), f"{arm}: duplicate ZIP members")
    result_names = [name for name in names if name.endswith(".json") and not name.endswith("_config.json")]
    config_names = [name for name in names if name.endswith("_config.json")]
    source_names = [name for name in names if name.endswith(f"_{STRATEGY}.py")]
    require(len(result_names) == len(config_names) == len(source_names) == 1,
            f"{arm}: ZIP must contain one result JSON, one config JSON and one embedded strategy")
    result_name, config_name, source_name = result_names[0], config_names[0], source_names[0]
    stem = result_name[:-5]
    require(config_name == f"{stem}_config.json" and source_name == f"{stem}_{STRATEGY}.py",
            f"{arm}: ZIP members do not belong to the same official export")
    source_bytes = bundle.read(source_name)
    expected_hash = plan["sources"][arm]["sha256"]
    require(sha256(source_bytes) == expected_hash, f"{arm}: embedded strategy source SHA differs from frozen PLAN")
    pinned_source = HERE / plan["sources"][arm]["path"]
    require(sha256(pinned_source.read_bytes()) == expected_hash, f"{arm}: pinned on-disk source differs from PLAN")
    result = read_json(bundle.read(result_name))
    config = read_json(bundle.read(config_name))

  match_plan(config, frozen_config)
  require(set(result) == {"strategy", "strategy_comparison"}, f"{arm}: unexpected top-level result fields")
  require(set(result["strategy"]) == {STRATEGY}, f"{arm}: result has unexpected strategy")
  stats = result["strategy"][STRATEGY]
  require(isinstance(stats["trades"], list), f"{arm}: official trade list is missing")
  require(all(field in stats for field in OFFICIAL_METRICS),
          f"{arm}: expected official portfolio metrics are absent")
  require(stats["timerange"] == plan["timerange"], f"{arm}: official timerange differs from frozen PLAN")
  contract = plan["config_contract"]
  for actual, expected, label in (
    (config["exchange"]["pair_whitelist"], contract["pairs"], "pair whitelist"),
    (config["dry_run_wallet"], contract["wallet"], "wallet"),
    (config["max_open_trades"], contract["max_open_trades"], "slot limit"),
    (config["fee"], contract["fee_per_side"], "per-side fee"),
    (config["timeframe"], contract["timeframe"], "timeframe"),
    (config["trading_mode"], contract["trading_mode"], "trading mode"),
    (config["margin_mode"], contract["margin_mode"], "margin mode"),
    (config["nfi_parameters"]["num_cores_indicators_calc"], contract["num_cores_indicators_calc"],
     "indicator workers"),
  ):
    require(actual == expected, f"{arm}: embedded config {label} differs from frozen PLAN")
  for field, expected in (("max_open_trades_setting", contract["max_open_trades"]),
                          ("timeframe", contract["timeframe"]),
                          ("trading_mode", contract["trading_mode"]),
                          ("margin_mode", contract["margin_mode"]),
                          ("dry_run_wallet", contract["wallet"]),
                          ("pairlist", contract["pairs"])):
    require(stats[field] == expected, f"{arm}: official result {field} differs from frozen PLAN")
  effective_file = directory / "effective_parameters.json"
  engine_file = directory / "engine_entry_rows.json"
  exchange_file = directory / "exchange_inputs.json"
  require(effective_file.is_file() and engine_file.is_file() and exchange_file.is_file(),
          f"{arm}: missing required observer JSON next to execution")
  effective = read_json(effective_file.read_bytes())
  engine = read_json(engine_file.read_bytes())
  exchange = read_json(exchange_file.read_bytes())
  require(set(engine) == set(contract["pairs"]), f"{arm}: observer pair coverage differs from frozen PLAN")
  require(set(exchange) == {"precision_mode", "precision_mode_price", "markets", "leverage_tiers"},
          f"{arm}: exchange observer fields missing")
  for key in ("markets", "leverage_tiers"):
    require(set(exchange[key]) == set(contract["pairs"]),
            f"{arm}: exchange {key} coverage differs from frozen PLAN")
  market_keys = {"symbol", "base", "quote", "settle", "type", "active", "contractSize",
                 "linear", "inverse", "precision", "limits"}
  for pair, market in exchange["markets"].items():
    require(set(market) == market_keys and market["symbol"] == pair,
            f"{arm}: market metadata incomplete or symbol mismatch for {pair}")
    require(isinstance(exchange["leverage_tiers"][pair], list) and exchange["leverage_tiers"][pair],
            f"{arm}: exchange leverage tiers missing for {pair}")
  expected_enabled = {str(signal) for signal in contract["enabled_signals_only"]}
  for side in ("long", "short"):
    key = f"{side}_entry_signal_params"
    declared = frozen_config["nfi_parameters"][key]
    require(effective[key] == declared, f"{arm}: effective {key} differs from frozen config")
    require(all(type(active) is bool for active in effective[key].values()),
            f"{arm}: effective {key} contains nonboolean flags")
  enabled = {key.rsplit("_", 2)[1] for side in ("long", "short")
             for key, active in effective[f"{side}_entry_signal_params"].items() if active}
  require(enabled == expected_enabled, f"{arm}: effective enabled signals do not match PLAN")
  for key, expected in (("position_adjustment_enable", contract["position_adjustment_enable"]),
                        ("grinding_enable", contract["grinding_enable"]),
                        ("derisk_enable", contract["derisk_enable"]),
                        ("futures_mode_leverage", contract["requested_leverage"]),
                        ("system_v4_bad_trade_exit_enable", contract["source_default_risk_exit_preserved"]),
                        ("legacy_system_bad_trade_exit_enable", False),
                        ("num_cores_indicators_calc", contract["num_cores_indicators_calc"]),
                        ("timeframe", contract["timeframe"]),
                        ("use_exit_signal", frozen_config["use_exit_signal"]),
                        ("exit_profit_only", frozen_config["exit_profit_only"]),
                        ("ignore_roi_if_entry_signal", frozen_config["ignore_roi_if_entry_signal"])):
    require(effective[key] == expected and (type(expected) is not bool or type(effective[key]) is bool),
            f"{arm}: effective {key} differs from frozen PLAN/config")
  require(effective["system_name_use"] == "system_v4", f"{arm}: effective source risk system changed")
  return {"zip": str(archive), "zip_sha256": sha256(archive.read_bytes()),
          "source_sha256": sha256(source_bytes), "result_member": result_name, "config_member": config_name,
          "source_member": source_name, "result": result, "config": config,
          "effective": effective, "engine": engine, "exchange": exchange}


def cohort(trades):
  counts = Counter()
  pnl = Decimal(0)
  losing = Decimal(0)
  for trade in trades:
    amount = trade["profit_abs"]
    require(isinstance(amount, (int, Decimal)), "Trade profit_abs is not numeric")
    amount = Decimal(amount)
    pnl += amount
    if amount > 0:
      counts["wins"] += 1
    elif amount < 0:
      counts["losses"] += 1
      losing += amount
    else:
      counts["zero"] += 1
  return {"trades": len(trades), "wins": counts["wins"], "losses": counts["losses"],
          "zero": counts["zero"], "net_pnl": pnl, "losing_pnl_subtotal": losing}


def full_tag_groups(trades):
  """Mutually exclusive cohorts keyed by the verbatim official enter_tag."""
  buckets = {}
  for trade in trades:
    require(isinstance(trade["enter_tag"], str), "Official trade has no full entry-tag string")
    buckets.setdefault(trade["enter_tag"], []).append(trade)
  return {tag: cohort(buckets[tag]) for tag in sorted(buckets)}


def verify_full_tag_partition(arm, groups, whole):
  for field in COHORT_METRICS:
    actual = sum((group[field] for group in groups.values()), Decimal(0))
    require(actual == whole[field], f"{arm}: full entry-tag groups do not partition {field}")


def signal_memberships(trades, signals):
  """A trade may be counted for several signal tokens in a mixed enter_tag."""
  buckets = {str(signal): [] for signal in signals}
  for trade in trades:
    tags = set(trade["enter_tag"].split())
    for tag in tags & buckets.keys():
      buckets[tag].append(trade)
  return {tag: cohort(bucket) for tag, bucket in buckets.items()}

def tagged_loss_ledger(trades, signals):
  """Retain the official trade index and full tag membership for each cohort loss."""
  losses = {str(signal): [] for signal in signals}
  for index, trade in enumerate(trades):
    amount = trade["profit_abs"]
    if amount >= 0:
      continue
    entry_tags = set(trade["enter_tag"].split())
    for tag in entry_tags & losses.keys():
      losses[tag].append({
        "trade_index": index, "pair": trade["pair"], "open_date": trade["open_date"],
        "close_date": trade["close_date"], "enter_tag": trade["enter_tag"],
        "exit_reason": trade["exit_reason"], "profit_abs": amount, "order_count": len(trade["orders"]),
      })
  return losses


def verify_accounting(arm, stats, whole):
  require(stats["total_trades"] == whole["trades"], f"{arm}: official total_trades differs from trade list")
  for field in ("wins", "losses", "draws"):
    check = "zero" if field == "draws" else field
    require(stats[field] == whole[check], f"{arm}: official {field} differs from trade list")
  # The exporter sums binary floats; decimal sum of their JSON representations
  # need not be bit-for-bit identical to the binary-float aggregate.
  total = whole["net_pnl"]
  abs_tolerance = max(Decimal("0.000001"), abs(total) * Decimal("1e-10"))
  require(abs(Decimal(stats["profit_total_abs"]) - total) <= abs_tolerance,
          f"{arm}: official profit_total_abs differs from calculated trade PnL")
  start = Decimal(stats["starting_balance"])
  require(abs(Decimal(stats["final_balance"]) - (start + total)) <= abs_tolerance,
          f"{arm}: official final_balance differs from starting balance plus trade PnL")
  require(abs(Decimal(stats["profit_total"]) - total / start) <= Decimal("1e-9"),
          f"{arm}: official profit_total differs from trade PnL / starting balance")


def number(value):
  return str(value) if isinstance(value, (int, Decimal)) else str(value)


def metric_row(label, before, after):
  delta = Decimal(after) - Decimal(before)
  return f"| {label} | {number(before)} | {number(after)} | {number(delta)} |"


def format_cohort(row):
  return (f"{row['trades']} / {row['wins']}-{row['losses']}-{row['zero']} / "
          f"{row['net_pnl']} / {row['losing_pnl_subtotal']}")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--native-dir", type=Path, default=HERE / "execution/native")
  parser.add_argument("--modified-dir", type=Path, default=HERE / "execution/modified")
  parser.add_argument("--output-dir", type=Path, default=HERE)
  args = parser.parse_args()
  plan = read_json((HERE / "PLAN.json").read_bytes())
  require(plan["status"] == "FROZEN" and plan["arms"] == ["native", "modified"], "Invalid frozen PLAN")
  receipt = read_json((HERE / "runtime_sources/RECEIPT.json").read_bytes())
  require(receipt["image"] == plan["runtime"]["image"], "Drawdown source image differs from frozen PLAN")
  for module in ("freqtrade.data.metrics", "freqtrade.optimize.optimize_reports.optimize_reports"):
    source = receipt["modules"][module]
    require(sha256((HERE / source["path"]).read_bytes()) == source["sha256"],
            f"Pinned official drawdown source differs from receipt: {module}")
  frozen_config = read_json((HERE / plan["config"]).read_bytes())
  execution_gate = verify_execution_receipts(
    plan, {"native": args.native_dir, "modified": args.modified_dir})
  native = embedded_archive("native", args.native_dir, plan, frozen_config)
  modified = embedded_archive("modified", args.modified_dir, plan, frozen_config)
  for arm_name, arm, directory in (("native", native, args.native_dir),
                                   ("modified", modified, args.modified_dir)):
    recorded = execution_gate["arms"][arm_name]
    require(str(Path(arm["zip"]).resolve().relative_to(directory.resolve())) == recorded["recorded_export"],
            f"{arm_name}: selected official ZIP differs from successful arm receipt")
    stats = arm["result"]["strategy"][STRATEGY]
    run_start, run_end = (stats[field] for field in
                          ("backtest_run_start_ts", "backtest_run_end_ts"))
    require(type(run_start) is int and type(run_end) is int, f"{arm_name}: run timestamps are not integer seconds")
    earliest = int(utc_time(recorded["started_utc"], f"{arm_name} start").timestamp())
    latest = int(utc_time(recorded["finished_utc"], f"{arm_name} finish").timestamp())
    require(earliest <= run_start <= run_end <= latest,
            f"{arm_name}: official run timestamps do not fall inside recorded arm execution")
  before, after = (arm["result"]["strategy"][STRATEGY] for arm in (native, modified))
  trades_before, trades_after = before["trades"], after["trades"]
  trade_diffs = list(differences(trades_before, trades_after, "/trades"))
  stats_before = {key: value for key, value in before.items() if key not in RUN_METADATA | {"trades"}}
  stats_after = {key: value for key, value in after.items() if key not in RUN_METADATA | {"trades"}}
  stats_diffs = list(differences(stats_before, stats_after, "/strategy"))
  for item in stats_diffs:
    field = item["field"].split("/")[2]
    item["classification"] = "study setup/identity" if field in SETUP_STATS else "performance/result"
  comparison_diffs = list(differences(native["result"]["strategy_comparison"],
                                    modified["result"]["strategy_comparison"], "/strategy_comparison"))
  config_before = semantic_export_config(native["config"])
  config_after = semantic_export_config(modified["config"])
  config_diffs = list(differences(config_before, config_after, "/config"))
  effective_diffs = list(differences(native["effective"], modified["effective"], "/effective_parameters"))
  engine_diffs = list(differences(native["engine"], modified["engine"], "/engine_entry_rows"))
  exchange_diffs = list(differences(native["exchange"], modified["exchange"], "/exchange_inputs"))
  summary = {arm_name: cohort(arm["result"]["strategy"][STRATEGY]["trades"])
             for arm_name, arm in (("native", native), ("modified", modified))}
  full_tags = {arm_name: full_tag_groups(arm["result"]["strategy"][STRATEGY]["trades"])
               for arm_name, arm in (("native", native), ("modified", modified))}
  tags = {arm_name: signal_memberships(arm["result"]["strategy"][STRATEGY]["trades"],
                                       plan["affected_signals"])
          for arm_name, arm in (("native", native), ("modified", modified))}
  tagged_losses = {arm_name: tagged_loss_ledger(arm["result"]["strategy"][STRATEGY]["trades"],
                                                plan["affected_signals"])
                   for arm_name, arm in (("native", native), ("modified", modified))}
  for arm_name, arm in (("native", native), ("modified", modified)):
    verify_accounting(arm_name, arm["result"]["strategy"][STRATEGY], summary[arm_name])
    verify_full_tag_partition(arm_name, full_tags[arm_name], summary[arm_name])
  engine_coverage = {}
  for arm_name, arm in (("native", native), ("modified", modified)):
    engine_coverage[arm_name] = {
      str(signal): sum(pair["tagged_candles"].get(str(signal), 0) for pair in arm["engine"].values())
      for signal in plan["affected_signals"]
    }
  coverage_gaps = [f"{arm_name} signal {signal}: engine={engine_coverage[arm_name][signal]}, "
                   f"filled={tags[arm_name][signal]['trades']}"
                   for arm_name in ("native", "modified") for signal in engine_coverage[arm_name]
                   if not engine_coverage[arm_name][signal] or not tags[arm_name][signal]["trades"]]
  order_counts = {arm_name: [len(trade["orders"]) for trade in arm["result"]["strategy"][STRATEGY]["trades"]]
                  for arm_name, arm in (("native", native), ("modified", modified))}
  issues = []
  for name, diff in (("complete trade/order arrays", trade_diffs), ("complete semantic strategy statistics", stats_diffs),
                     ("official strategy comparison", comparison_diffs), ("embedded configurations", config_diffs),
                     ("effective parameters", effective_diffs), ("engine row hashes/coverage", engine_diffs),
                     ("live exchange pricing inputs and leverage tiers", exchange_diffs)):
    if diff:
      issues.append(f"{name}: {len(diff)} differing leaf fields")
  issues.extend(f"coverage gap: {gap}" for gap in coverage_gaps)
  report = {
    "status": "PASS" if not issues else "FAIL", "issues": issues,
    "period": plan["timerange"], "end_exclusive": plan["end_exclusive"],
    "execution_provenance": execution_gate,
    "arms": {name: {key: arm[key] for key in ("zip", "zip_sha256", "source_sha256", "result_member",
                                                "config_member", "source_member")}
             for name, arm in (("native", native), ("modified", modified))},
    "trades": {"equal": not trade_diffs, "differences": trade_diffs,
               "complete_order_counts_in_official_trade_order": order_counts},
    "stats": {"equal_excluding_explicit_run_metadata": not stats_diffs,
              "excluded_run_metadata": {name: {field: arm["result"]["strategy"][STRATEGY].get(field)
                                               for field in sorted(RUN_METADATA)}
                                        for name, arm in (("native", native), ("modified", modified))},
              "differences": stats_diffs,
              "stable_performance": not (comparison_diffs or trade_diffs or
                                         any(item["classification"] == "performance/result"
                                             for item in stats_diffs))},
    "strategy_comparison_differences": comparison_diffs, "config_differences": config_diffs,
    "effective_parameters_differences": effective_diffs, "engine_entry_rows_differences": engine_diffs,
    "exchange_inputs_differences": exchange_diffs,
    "engine_tagged_candles": engine_coverage, "coverage_gaps": coverage_gaps,
    "whole_portfolio": summary, "exact_full_entry_tag_groups": full_tags,
    "signal_tag_membership_within_portfolio": tags,
    "tag_matched_losing_trades": tagged_losses,
    "official_metrics": {name: {key: arm["result"]["strategy"][STRATEGY][key]
                                for key in OFFICIAL_METRICS if key in arm["result"]["strategy"][STRATEGY]}
                         for name, arm in (("native", native), ("modified", modified))},
  }
  args.output_dir.mkdir(parents=True, exist_ok=True)
  (args.output_dir / "COMPARISON.json").write_text(json.dumps(json_value(report), indent=2, sort_keys=True) + "\n")
  lines = [f"# Official matched X8 comparison — {plan['timerange']} (exclusive end)", "",
           f"**{report['status']}** — unmodified Native vs PR modified, one portfolio per arm "
           "under the frozen matched-study plan. A tagged cohort is **not** an independent signal-only backtest.", "",
           "| Whole portfolio | Native before | Modified after | Difference (after − before) |",
           "|---|---:|---:|---:|"]
  for field in COHORT_METRICS:
    lines.append(metric_row(field, summary["native"][field], summary["modified"][field]))
  for field in OFFICIAL_METRICS:
    if field in report["official_metrics"]["native"] and field in report["official_metrics"]["modified"]:
      lines.append(metric_row("Official " + field, report["official_metrics"]["native"][field],
                              report["official_metrics"]["modified"][field]))
  lines += ["", "Official strategy-stat max_drawdown_abs is the largest drop of cumulative closed-trade "
            "profit_abs from its running high (floored at zero), in wallet currency, with trades sorted by "
            "close_date. max_drawdown_account is the fraction lost at **that maximum-absolute-DD trough**: "
            "max_drawdown_abs / (starting_balance + cumulative PnL at its peak). The separately maximized "
            "relative metric is max_relative_drawdown. Neither statistic marks open trades to market; "
            "wallet_stats uses a separate wallet-snapshot series. Definition: pinned-image "
            "[report mapping](runtime_sources/optimize_reports.py) and "
            "[drawdown calculation](runtime_sources/metrics.py), "
            "[image/SHA receipt](runtime_sources/RECEIPT.json).",
            "The losing-PnL subtotal is already included in net PnL; zero denotes exactly zero trade profit_abs.", "",
            "Exact full enter_tag strings (JSON-quoted to preserve spaces) form **mutually exclusive** cohorts. "
            "Their counts, wins/losses/zero, net PnL, and losing subtotals reconcile exactly to the whole portfolio.",
            "| Full enter_tag string | Native trades / W-L-Z / net PnL / losing subtotal | "
            "Modified trades / W-L-Z / net PnL / losing subtotal | Δ trades / net PnL / losses / losing subtotal |",
            "|---|---:|---:|---:|"]
  empty_cohort = cohort(())
  for full_tag in sorted(full_tags["native"].keys() | full_tags["modified"].keys()):
    b = full_tags["native"].get(full_tag, empty_cohort)
    a = full_tags["modified"].get(full_tag, empty_cohort)
    lines.append(f"| `{json.dumps(full_tag)}` | {format_cohort(b)} | {format_cohort(a)} | "
                 f"{a['trades'] - b['trades']} / {a['net_pnl'] - b['net_pnl']} / "
                 f"{a['losses'] - b['losses']} / {a['losing_pnl_subtotal'] - b['losing_pnl_subtotal']} |")
  lines += ["", "Affected-signal **token membership** within this portfolio (not disjoint): a mixed full "
            "enter_tag can count toward more than one signal. Do not sum these cohorts into portfolio PnL.",
            "| Signal token | Native trades / W-L-Z / net PnL / losing subtotal | "
            "Modified trades / W-L-Z / net PnL / losing subtotal | Δ trades / net PnL / losses / losing subtotal |",
            "|---|---:|---:|---:|"]
  for signal in plan["affected_signals"]:
    tag = str(signal)
    b, a = tags["native"][tag], tags["modified"][tag]
    lines.append(f"| {tag} | {format_cohort(b)} | {format_cohort(a)} | "
                 f"{a['trades'] - b['trades']} / {a['net_pnl'] - b['net_pnl']} / "
                 f"{a['losses'] - b['losses']} / {a['losing_pnl_subtotal'] - b['losing_pnl_subtotal']} |")
  lines += ["",
            "| Engine tag | Native tagged candles | Modified tagged candles | Native filled membership | Modified filled membership |",
            "|---|---:|---:|---:|---:|"]
  for signal in plan["affected_signals"]:
    tag = str(signal)
    lines.append(f"| {tag} | {engine_coverage['native'][tag]} | {engine_coverage['modified'][tag]} | "
                 f"{tags['native'][tag]['trades']} | {tags['modified'][tag]['trades']} |")
  lines += ["", "Complete official trade and nested-order arrays are compared in exported sequence with no "
            "fields ignored or sorting. Semantic stats, official strategy-comparison summary, embedded config, "
            "engine rows, effective parameters, live exchange metadata and leverage tiers are compared exactly. "
            "Only official backtest_run_start_ts/backtest_run_end_ts are omitted from semantic stats; exported "
            "config_files paths and redacted disabled Telegram credentials are nonsemantic.",
            f"Stable official performance: {report['stats']['stable_performance']} (trade/order arrays, derived "
            "stats and official strategy comparison).",
            f"Trade differences: {len(trade_diffs)}; stats: {len(stats_diffs)}; strategy comparison: "
            f"{len(comparison_diffs)}; config: {len(config_diffs)}; effective: {len(effective_diffs)}; "
            f"engine: {len(engine_diffs)}; exchange: {len(exchange_diffs)}.", ""]
  lines += ["Pinned launch-input SHA locks and their PASS prelaunch receipt are verified; "
            "the frozen runner's COMPLETE stage follows a successful final market-data rehash, "
            "and both arm receipts have PASS/rc=0, official export location and contained engine-run timestamps. "
            "Actual Docker argv binds the pinned image, source/config, read-only market data, no cache, "
            "signals export and distinct fresh arm userdirs. Observer files come from those arm directories; "
            "their capture-time hashes were not recorded by the producer, so chronology is evidence, "
            "not cryptographic observer-file attestation.", ""]
  for name in ("native", "modified"):
    lines.append(f"- {name} ZIP SHA256 `{report['arms'][name]['zip_sha256']}`; embedded strategy "
                 f"SHA256 `{report['arms'][name]['source_sha256']}`; "
                 f"ZIP `{report['arms'][name]['zip']}`")
  if issues:
    lines += ["", "**Unexplained differences / gaps — do not publish a parity claim:**"]
    lines.extend(f"- {issue}" for issue in issues)
    if stats_diffs:
      lines += ["", "All differing official strategy statistic fields (performance vs setup):"]
      lines.extend(f"- `{item['field']}` — {item['classification']}: Native "
                   f"`{item['native']}` → Modified `{item['modified']}`" for item in stats_diffs)
    for label, diff in (("trade/order", trade_diffs), ("strategy comparison", comparison_diffs),
                        ("config", config_diffs), ("effective", effective_diffs), ("engine", engine_diffs),
                        ("exchange", exchange_diffs)):
      if diff:
        lines.append(f"- {label}: {', '.join(item['field'] for item in diff[:20])}" +
                     (f" (and {len(diff) - 20} more; see COMPARISON.json)" if len(diff) > 20 else ""))
  (args.output_dir / "COMPARISON.md").write_text("\n".join(lines) + "\n")
  if issues:
    raise InvalidStudy("Unexplained differences or missing coverage; see COMPARISON.json and COMPARISON.md")
  print(f"PASS: {len(trades_before)} official trades, full trades/orders/stats/engine/parameters equal; "
        f"five tags covered. Reports in {args.output_dir}")


if __name__ == "__main__":
  try:
    main()
  except (InvalidStudy, KeyError, IndexError, TypeError, OSError, ValueError) as exc:
    print(f"Comparison failed: {exc}", file=sys.stderr)
    sys.exit(1)
