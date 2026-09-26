"""Run the two frozen, official Freqtrade backtests under the shared Docker lease."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "NFI_Signal_Tools_v3.2.16"))
from backtest_lease import acquire_lock, clear_owner, owner_path, update_owner, write_owner


def now():
  return datetime.now(timezone.utc).isoformat()


def load(path):
  return json.loads(path.read_text())


def sha(path):
  with path.open("rb") as stream:
    return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
  temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
  try:
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)
  finally:
    temporary.unlink(missing_ok=True)


def study_file(relative):
  path = HERE / relative
  if path.resolve().is_relative_to(HERE) and path.is_file():
    return path
  raise ValueError(f"Not a study input file: {relative}")


def validate_inputs():
  plan = load(HERE / "PLAN.json")
  assert plan["status"] == "FROZEN" and plan["pr"] == 1323
  assert plan["arms"] == ["native", "modified"]
  assert plan["execution_contract"]["observer"] == "observe_backtest.py"
  assert plan["execution_contract"]["cache"] == "none" and plan["execution_contract"]["export"] == "signals"
  required = {"PLAN.json", "DATA_LOCKS.json", "config.json", "observe_backtest.py", "run_matched.py"}
  required.update(source["path"] for source in plan["sources"].values())
  locks = load(HERE / "LAUNCH_LOCKS.json")
  assert required <= locks.keys(), ("MISSING_LAUNCH_LOCKS", sorted(required - locks.keys()))
  for name, digest in locks.items():
    assert sha(study_file(name)) == digest, ("STUDY_INPUT_CHANGED", name)
  prelaunch = load(HERE / "validation/PRELAUNCH.json")
  assert prelaunch["status"] == "PASS" and prelaunch["launch_locks_sha256"] == sha(HERE / "LAUNCH_LOCKS.json"), "PRELAUNCH_NOT_APPROVED"
  for name, digest in plan["root_preservation"].items():
    assert sha(ROOT / name) == digest, ("ROOT_CHANGED", name)
  for source in plan["sources"].values():
    assert sha(study_file(source["path"])) == source["sha256"], ("SOURCE_CHANGED", source["path"])

  config = load(study_file(plan["config"]))
  contract = plan["config_contract"]
  expected = {
      "dry_run_wallet": "wallet", "max_open_trades": "max_open_trades", "fee": "fee_per_side",
      "timeframe": "timeframe", "trading_mode": "trading_mode", "margin_mode": "margin_mode",
  }
  for config_key, contract_key in expected.items():
    assert config[config_key] == contract[contract_key], ("CONFIG_CHANGED", config_key)
  assert config["exchange"]["pair_whitelist"] == contract["pairs"] and len(contract["pairs"]) == 19
  assert config["nfi_parameters"]["num_cores_indicators_calc"] == contract["num_cores_indicators_calc"]
  flags = {key: value for side in ("long", "short")
           for key, value in config["nfi_parameters"][f"{side}_entry_signal_params"].items()}
  enabled = {int(key.rsplit("_", 2)[1]) for key, value in flags.items() if value is True}
  assert all(type(value) is bool for value in flags.values())
  assert enabled == set(contract["enabled_signals_only"]) == set(plan["affected_signals"])
  assert contract["other_entry_signals_enabled"] is False and len(enabled) == 5
  return plan, config


def data_hashes(plan):
  manifest = load(study_file(plan["data_manifest"]))
  assert manifest["status"] == "PASS_FRESH_HASHES_MATCH_PRIOR_DATE_AUDIT"
  data_root = Path(plan["runtime"]["data_host"])
  for record in manifest["records"]:
    path = data_root / record["relative_path"]
    assert path.resolve().is_relative_to(data_root.resolve()) and str(path) == record["path"]
    assert sha(path) == record["sha256"], ("DATA_CHANGED", record["path"])


def check_effective(directory, config, plan):
  effective = load(directory / "effective_parameters.json")
  contract = plan["config_contract"]
  for name in ("position_adjustment_enable", "grinding_enable", "derisk_enable"):
    assert effective[name] is contract[name], ("EFFECTIVE_PARAMETER_CHANGED", name)
  assert effective["futures_mode_leverage"] == contract["requested_leverage"]
  assert effective["num_cores_indicators_calc"] == contract["num_cores_indicators_calc"]
  assert effective["timeframe"] == contract["timeframe"]
  for side in ("long", "short"):
    name = f"{side}_entry_signal_params"
    assert effective[name] == config["nfi_parameters"][name], ("EFFECTIVE_SIGNALS_CHANGED", name)
  assert (directory / "engine_entry_rows.json").is_file(), "MISSING_ENGINE_ROWS"


def command_for(plan, arm, directory, container):
  rt = plan["runtime"]
  mount = f"/study/execution/{arm}"
  return ["docker", "run", "--rm", "--pull", "never", "--name", container,
          "--cpus", str(rt["cpus"]), "--memory", rt["memory"], "--memory-swap", rt["memory"],
          "--user", f"{os.getuid()}:{os.getgid()}", "--dns", "1.1.1.1", "--dns", "8.8.8.8",
          "-e", "OPENBLAS_NUM_THREADS=1", "-e", "OMP_NUM_THREADS=1", "-e", f"PARITY_OUTPUT={mount}",
          "-v", f"{HERE}:/study:ro", "-v", f"{directory}:{mount}",
          "-v", f"{rt['data_host']}:/market-data:ro", "--entrypoint", "python",
          rt["image"], "/study/observe_backtest.py", "backtesting",
          "--strategy", "NostalgiaForInfinityX8", "--strategy-path", f"/study/sources/{arm}",
          "--userdir", mount, "--config", "/study/config.json", "--datadir", "/market-data",
          "--timerange", plan["timerange"], "--cache", "none", "--export", "signals"]


def run_arm(plan, config, arm, execution, owner, state):
  directory = execution / arm
  directory.mkdir(exist_ok=False)
  container = f"nfi-pr1323-{arm}-{os.getpid()}-{uuid4().hex[:8]}"
  command = command_for(plan, arm, directory, container)
  save(directory / "COMMAND.json", command)
  update_owner(owner_path(), owner["lease_id"], year=arm, container_name=container)
  started = now()
  state.update(stage="RUNNING", current=arm, container=container, current_started_utc=started)
  save(execution / "STATUS.json", state)
  result = {"started_utc": started, "returncode": None}
  try:
    with (directory / "freqtrade.log").open("x") as log:
      proc = None
      try:
        pending_stop = None
        def defer_stop(signum, frame):
          nonlocal pending_stop
          pending_stop = signum
        handlers = {
          signum: signal.signal(signum, defer_stop)
          for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        }
        try:
          proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        finally:
          for signum, handler in handlers.items():
            signal.signal(signum, handler)
        if pending_stop is not None:
          request_stop(pending_stop, None)
        result["returncode"] = proc.wait(timeout=36000)
      except BaseException:
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
          signal.signal(signum, signal.SIG_IGN)
        # Keep the global admission lease until this owned container is stopped.
        while True:
          inspection = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container],
            capture_output=True, text=True,
          )
          child_done = proc is None or proc.poll() is not None
          if inspection.returncode == 0:
            if inspection.stdout.strip() == "true":
              subprocess.run(["docker", "stop", "--time", "20", container], capture_output=True)
            elif inspection.stdout.strip() == "false" and child_done:
              break
          elif "no such object:" in inspection.stderr.lower() and child_done:
            break
          time.sleep(1)
        if proc is not None:
          proc.wait()
        raise
    assert result["returncode"] == 0, ("BACKTEST_FAILED", arm, result["returncode"])
    exports = list((directory / "backtest_results").glob("*.zip"))
    assert len(exports) == 1, ("EXPECTED_ONE_SIGNALS_ZIP", arm, len(exports))
    check_effective(directory, config, plan)
    result["status"] = "PASS"
    result["export"] = str(exports[0].relative_to(directory))
  except BaseException as error:
    result.update(status="FAIL", error=f"{type(error).__name__}: {error}")
    raise
  finally:
    result["finished_utc"] = now()
    save(directory / "status.json", result)
  state["completed"].append(arm)
  state.update(stage="EXPORT_COMPLETE", current=None, container=None)
  save(execution / "STATUS.json", state)


def main():
  execution = HERE / "execution"
  execution.mkdir(exist_ok=True)
  with (execution / "coordinator.lock").open("a") as coordinator:
    fcntl.flock(coordinator, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (execution / "STATUS.json").exists(), "Prior execution exists; never overwrite or retry"
    assert all(not (execution / arm).exists() for arm in ("native", "modified")), "Prior run exists; never overwrite"
    plan, config = validate_inputs()
    os.environ["NFI_GLOBAL_LOCK_DIR"] = plan["runtime"]["lease_directory"]
    data_hashes(plan)
    state = {"stage": "WAITING_FOR_GLOBAL_LEASE", "started_utc": now(), "pid": os.getpid(), "completed": []}
    save(execution / "STATUS.json", state)
    try:
      while True:
        try:
          with acquire_lock():
            owner = write_owner(owner_path(), pid=os.getpid(), workspace=HERE,
                                run_id="pr1323-matched-20260926", tag="matched", backend="docker-run",
                                strategy=HERE / plan["sources"]["native"]["path"], years=plan["arms"])
            try:
              for arm in plan["arms"]:
                validate_inputs()
                run_arm(plan, config, arm, execution, owner, state)
              state.update(stage="VERIFYING_DATA", current=None)
              save(execution / "STATUS.json", state)
              return
            finally:
              clear_owner(owner_path(), owner["lease_id"])
        except BlockingIOError:
          state["last_wait_utc"] = now()
          save(execution / "STATUS.json", state)
          time.sleep(1)
    except BaseException as error:
      state.update(stage="FAILED", error=f"{type(error).__name__}: {error}", finished_utc=now())
      save(execution / "STATUS.json", state)
      raise
    finally:
      try:
        data_hashes(plan)
      except BaseException as error:
        state.update(stage="FAILED", data_error=f"{type(error).__name__}: {error}", finished_utc=now())
        save(execution / "STATUS.json", state)
        raise
      if state["stage"] == "VERIFYING_DATA":
        state.update(stage="COMPLETE", finished_utc=now())
        save(execution / "STATUS.json", state)


def request_stop(signum, frame):
  raise SystemExit(128 + signum)


if __name__ == "__main__":
  for signum in (signal.SIGTERM, signal.SIGHUP):
    signal.signal(signum, request_stop)
  main()
