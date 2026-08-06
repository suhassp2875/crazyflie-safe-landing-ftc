#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"

SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

ROOT="$PROJECT_DIR/results/final/model_sensitivity/ofat/pinv_boundary_bisection/round2"
SCHEDULE="$ROOT/ofat_bisection_schedule.csv"
CONDITION_MANIFEST="$PROJECT_DIR/results/final/model_sensitivity/ofat/pinv_boundary_localization/ofat_condition_manifest.json"

TRIAL_DIR="$ROOT/trials"
SUMMARY_DIR="$ROOT/summaries"
CONSOLE_DIR="$ROOT/consoles"
SIM_LOG_DIR="$ROOT/simulator_logs"
PLANT_STATE_DIR="$ROOT/plant_states"

STATUS_FILE="$ROOT/run_status.csv"
RUNNER_STATUS="$ROOT/runner_status.txt"

POST_FAULT_MODE="${POST_FAULT_MODE:-adaptive_ramp_v1}"
EVAL_DURATION="${EVAL_DURATION:-18.0}"
MAX_BRAKE_DURATION="${MAX_BRAKE_DURATION:-6.0}"
LANDING_DESCENT_RATE="${LANDING_DESCENT_RATE:-0.08}"

MIN_VALID_FAULT_Z="${MIN_VALID_FAULT_Z:-0.50}"
MAX_VALID_FAULT_ABS_VZ="${MAX_VALID_FAULT_ABS_VZ:-0.25}"

MAX_TRIAL_ATTEMPTS="${MAX_TRIAL_ATTEMPTS:-3}"

# PILOT=1 runs one paired seed at the midpoint
# of each perturbation: 10 trials.
PILOT="${PILOT:-0}"

mkdir -p \
  "$TRIAL_DIR" \
  "$SUMMARY_DIR" \
  "$CONSOLE_DIR" \
  "$SIM_LOG_DIR" \
  "$PLANT_STATE_DIR"

test -f "$SCHEDULE" || {
  echo "[FAIL] Missing schedule: $SCHEDULE"
  exit 1
}

test -f "$CONDITION_MANIFEST" || {
  echo "[FAIL] Missing condition manifest: $CONDITION_MANIFEST"
  exit 1
}

cleanup_sim() {
  pkill -f "sitl_singleagent.sh" \
    2>/dev/null || true

  pkill -x cf2 \
    2>/dev/null || true

  pkill -f "[g]z sim" \
    2>/dev/null || true

  pkill -f "[g]zserver" \
    2>/dev/null || true

  pkill -f "[g]azebo" \
    2>/dev/null || true

  sleep 3

  pkill -9 -x cf2 \
    2>/dev/null || true

  pkill -9 -f "[g]z sim" \
    2>/dev/null || true
}

restore_nominal_plant() {
  cd "$PROJECT_DIR"

  python scripts/plant_ofat.py restore
  python scripts/plant_ofat.py verify
}

cleanup_all() {
  cleanup_sim

  cd "$PROJECT_DIR" || true

  python scripts/plant_ofat.py restore \
    >/dev/null 2>&1 || true
}

trap cleanup_all EXIT INT TERM

verify_condition_state() {
  local state_json="$1"
  local condition_id="$2"
  local parameter="$3"
  local factor="$4"

  python - \
    "$state_json" \
    "$CONDITION_MANIFEST" \
    "$condition_id" \
    "$parameter" \
    "$factor" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path


state_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
condition_id = sys.argv[3]
parameter = sys.argv[4]
factor = float(sys.argv[5])

state_payload = json.loads(
    state_path.read_text()
)

manifest = json.loads(
    manifest_path.read_text()
)

lookup = {
    row["condition_id"]: row
    for row in manifest["conditions"]
}

if condition_id not in lookup:
    raise SystemExit(
        "[FAIL] Condition missing from manifest."
    )

expected = lookup[condition_id]
active = state_payload.get("active_state")

if not isinstance(active, dict):
    raise SystemExit(
        "[FAIL] Active perturbation missing."
    )

if state_payload.get("is_nominal"):
    raise SystemExit(
        "[FAIL] Active plant is nominal."
    )

if expected["parameter"] != parameter:
    raise SystemExit(
        "[FAIL] Scheduled parameter does not "
        "match manifest."
    )

if abs(
    float(expected["factor"]) - factor
) > 1.0e-12:
    raise SystemExit(
        "[FAIL] Scheduled factor does not "
        "match manifest."
    )

if active.get("parameter") != parameter:
    raise SystemExit(
        "[FAIL] Active parameter mismatch."
    )

if abs(
    float(active.get("factor")) - factor
) > 1.0e-12:
    raise SystemExit(
        "[FAIL] Active factor mismatch."
    )

if (
    state_payload["template_sha256"]
    != expected["template_sha256"]
):
    raise SystemExit(
        "[FAIL] Active checksum does not "
        "match manifest."
    )

if (
    state_payload["template_sha256"]
    != active["perturbed_sha256"]
):
    raise SystemExit(
        "[FAIL] Active checksum does not "
        "match state metadata."
    )

print(
    "[PASS] Active OFAT plant verified: "
    f"{condition_id}"
)
PY
}

apply_condition() {
  local condition_id="$1"
  local parameter="$2"
  local factor="$3"
  local state_json="$4"

  cd "$PROJECT_DIR"

  python scripts/plant_ofat.py restore

  python scripts/plant_ofat.py apply \
    --parameter "$parameter" \
    --factor "$factor"

  python scripts/plant_ofat.py verify

  python scripts/plant_ofat.py show \
    --json \
    > "$state_json"

  verify_condition_state \
    "$state_json" \
    "$condition_id" \
    "$parameter" \
    "$factor"
}

append_status() {
  local status="$1"
  local condition_id="$2"
  local parameter="$3"
  local factor="$4"
  local eta="$5"
  local rep="$6"
  local seed="$7"
  local attempt="$8"
  local trial_csv="$9"

  if [ ! -f "$STATUS_FILE" ]; then
    echo \
"status,condition_id,parameter,factor,controller,motor,eta,rep,trial_seed,attempt,trial_csv" \
      > "$STATUS_FILE"
  fi

  echo \
"${status},${condition_id},${parameter},${factor},pinv,2,${eta},${rep},${seed},${attempt},${trial_csv}" \
    >> "$STATUS_FILE"
}

eta_tag() {
  python - "$1" <<'PY'
import sys

print(
    f"{float(sys.argv[1]):.3f}".replace(
        ".",
        "p",
    )
)
PY
}

factor_tag() {
  python - "$1" <<'PY'
import sys

print(
    f"{float(sys.argv[1]):.2f}".replace(
        ".",
        "p",
    )
)
PY
}

validate_trial() {
  local csv_path="$1"
  local eta="$2"
  local seed="$3"
  local condition_id="$4"
  local parameter="$5"
  local factor="$6"
  local state_json="$7"
  local summary_path="$8"

  cd "$PROJECT_DIR"

  python \
    scripts/validate_ofat_m2_pinv_localization_trial.py \
    --csv "$csv_path" \
    --eta "$eta" \
    --seed "$seed" \
    --condition-id "$condition_id" \
    --parameter "$parameter" \
    --factor "$factor" \
    --plant-state-json "$state_json" \
    --condition-manifest "$CONDITION_MANIFEST" \
    --summary-output "$summary_path"
}

run_trial() {
  local condition_id="$1"
  local parameter="$2"
  local factor="$3"
  local eta="$4"
  local rep="$5"
  local seed="$6"

  local eta_file_tag
  eta_file_tag=$(eta_tag "$eta")

  local factor_file_tag
  factor_file_tag=$(factor_tag "$factor")

  local tag
  tag="ofat_${condition_id}_f${factor_file_tag}_eta${eta_file_tag}_seed${seed}"

  local generated_csv
  generated_csv="$PROJECT_DIR/logs/qp_event_allocator_m2_eta${eta_file_tag}_${tag}.csv"

  local trial_csv
  trial_csv="$TRIAL_DIR/${tag}.csv"

  local summary_csv
  summary_csv="$SUMMARY_DIR/${tag}_summary.csv"

  local state_json
  state_json="$PLANT_STATE_DIR/${tag}_plant.json"

  if [ -f "$trial_csv" ] && [ -f "$state_json" ]; then
    if validate_trial \
      "$trial_csv" \
      "$eta" \
      "$seed" \
      "$condition_id" \
      "$parameter" \
      "$factor" \
      "$state_json" \
      "$summary_csv"
    then
      echo "[SKIP] Valid completed trial: $trial_csv"
      return 0
    fi

    local timestamp
    timestamp=$(date +%s)

    mv \
      "$trial_csv" \
      "${trial_csv}.invalid_${timestamp}"

    mv \
      "$state_json" \
      "${state_json}.invalid_${timestamp}"

    echo \
      "[WARN] Existing invalid trial moved aside."
  fi

  local attempt=1

  while [ "$attempt" -le "$MAX_TRIAL_ATTEMPTS" ]; do
    echo
    echo "======================================================================"
    echo "[TRIAL] condition=$condition_id parameter=$parameter factor=$factor eta=$eta rep=$rep seed=$seed attempt=$attempt"
    echo "======================================================================"

    cleanup_sim
    restore_nominal_plant

    apply_condition \
      "$condition_id" \
      "$parameter" \
      "$factor" \
      "$state_json"

    cd "$PROJECT_DIR"

    eval "$(
      python scripts/seeded_trial_params.py \
        --seed "$seed" \
        --shell
    )"

    rm -f "$generated_csv"

    local sim_log
    sim_log="$SIM_LOG_DIR/${tag}_attempt${attempt}.log"

    local controller_log
    controller_log="$CONSOLE_DIR/${tag}_attempt${attempt}.log"

    cd "$FW_DIR"

    bash "$SIM_LAUNCH" \
      -m crazyflie \
      -x "$SPAWN_X" \
      -y "$SPAWN_Y" \
      > "$sim_log" 2>&1 &

    sleep 8

    cd "$PROJECT_DIR"

    if ! python scripts/wait_for_cf.py; then
      echo "[WARN] Crazyflie connection check failed."

      append_status \
        "WAIT_FAILED" \
        "$condition_id" \
        "$parameter" \
        "$factor" \
        "$eta" \
        "$rep" \
        "$seed" \
        "$attempt" \
        ""

      cleanup_sim
      restore_nominal_plant

      attempt=$((attempt + 1))
      continue
    fi

    common_args=(
      --motor 2
      --eta "$eta"
      --tag "$tag"
      --protocol-id "$PROTOCOL_ID"
      --trial-seed "$TRIAL_SEED"
      --spawn-x "$SPAWN_X"
      --spawn-y "$SPAWN_Y"
      --spawn-yaw-deg "$SPAWN_YAW_DEG"
      --fault-time "$FAULT_TIME"
      --hover-z "$HOVER_Z"
      --post-fault-mode "$POST_FAULT_MODE"
      --eval-duration "$EVAL_DURATION"
      --max-brake-duration "$MAX_BRAKE_DURATION"
      --landing-descent-rate "$LANDING_DESCENT_RATE"
      --min-valid-fault-z "$MIN_VALID_FAULT_Z"
      --max-valid-fault-abs-vz "$MAX_VALID_FAULT_ABS_VZ"
    )

    runner_rc=0

    timeout 100s \
    python \
      scripts/fault_triggered_landing_qp_event_allocator.py \
      "${common_args[@]}" \
      --controller pinv \
      --pinv-w-thrust 1.0 \
      --pinv-w-roll 1.0 \
      --pinv-w-pitch 1.0 \
      --pinv-w-yaw 0.2 \
      --pinv-lambda 1.0e-6 \
      > "$controller_log" 2>&1 \
      || runner_rc=$?

    cleanup_sim
    restore_nominal_plant

    if [ "$runner_rc" -ne 0 ]; then
      echo \
        "[WARN] Runner failed with code $runner_rc"

      tail -80 "$controller_log" || true

      append_status \
        "RUNNER_FAILED" \
        "$condition_id" \
        "$parameter" \
        "$factor" \
        "$eta" \
        "$rep" \
        "$seed" \
        "$attempt" \
        ""

      attempt=$((attempt + 1))
      continue
    fi

    if [ ! -f "$generated_csv" ]; then
      echo "[WARN] Runner produced no expected CSV."

      append_status \
        "CSV_MISSING" \
        "$condition_id" \
        "$parameter" \
        "$factor" \
        "$eta" \
        "$rep" \
        "$seed" \
        "$attempt" \
        ""

      attempt=$((attempt + 1))
      continue
    fi

    mv \
      "$generated_csv" \
      "$trial_csv"

    if validate_trial \
      "$trial_csv" \
      "$eta" \
      "$seed" \
      "$condition_id" \
      "$parameter" \
      "$factor" \
      "$state_json" \
      "$summary_csv"
    then
      append_status \
        "PASS" \
        "$condition_id" \
        "$parameter" \
        "$factor" \
        "$eta" \
        "$rep" \
        "$seed" \
        "$attempt" \
        "$trial_csv"

      echo "[PASS] Completed $tag"
      return 0
    fi

    mv \
      "$trial_csv" \
      "${trial_csv}.invalid_attempt${attempt}"

    mv \
      "$state_json" \
      "${state_json}.invalid_attempt${attempt}"

    append_status \
      "VALIDATION_FAILED" \
      "$condition_id" \
      "$parameter" \
      "$factor" \
      "$eta" \
      "$rep" \
      "$seed" \
      "$attempt" \
      "${trial_csv}.invalid_attempt${attempt}"

    attempt=$((attempt + 1))
  done

  echo \
    "[FAIL] Trial failed after $MAX_TRIAL_ATTEMPTS attempts: condition=$condition_id eta=$eta seed=$seed"

  return 1
}

emit_schedule() {
  python - "$SCHEDULE" "$PILOT" <<'PY'
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


schedule_path = Path(sys.argv[1])
pilot = int(sys.argv[2])

with schedule_path.open(
    newline=""
) as file:
    rows = list(
        csv.DictReader(file)
    )

if len(rows) != 50:
    raise SystemExit(
        f"[FAIL] Expected 50 schedule rows; "
        f"found {len(rows)}."
    )

condition_counts = Counter(
    row["condition_id"]
    for row in rows
)

if len(condition_counts) != 10:
    raise SystemExit(
        "[FAIL] Expected 10 conditions."
    )

if set(condition_counts.values()) != {5}:
    raise SystemExit(
        "[FAIL] Every condition must have "
        "five paired trials."
    )

seed_sets = defaultdict(set)
eta_sets = defaultdict(set)

for row in rows:
    if row["controller"] != "pinv":
        raise SystemExit(
            "[FAIL] Expected controller=pinv."
        )

    if int(row["motor"]) != 2:
        raise SystemExit(
            "[FAIL] Expected failed motor M2."
        )

    if row["protocol_id"] != "seeded_ic_v1":
        raise SystemExit(
            "[FAIL] Unexpected IC protocol."
        )

    seed_sets[
        row["condition_id"]
    ].add(
        int(row["trial_seed"])
    )

    eta_sets[
        row["condition_id"]
    ].add(
        float(row["eta"])
    )

reference_seeds = next(
    iter(seed_sets.values())
)

for condition_id, seeds in seed_sets.items():
    if len(seeds) != 5:
        raise SystemExit(
            f"[FAIL] {condition_id} has "
            f"{len(seeds)} seeds."
        )

    if seeds != reference_seeds:
        raise SystemExit(
            "[FAIL] Seed sets differ across "
            "conditions."
        )

    if len(eta_sets[condition_id]) != 1:
        raise SystemExit(
            f"[FAIL] {condition_id} must "
            "contain one midpoint eta."
        )

if pilot:
    rows = [
        row
        for row in rows
        if int(row["rep"]) == 1
    ]

for row in rows:
    values = [
        row["condition_id"],
        row["parameter"],
        row["factor"],
        row["eta"],
        row["rep"],
        row["trial_seed"],
    ]

    print("\t".join(values))
PY
}

cd "$PROJECT_DIR"

restore_nominal_plant

if [ "$PILOT" -eq 1 ]; then
  expected_run_count=10
  echo "RUNNING_PILOT" > "$RUNNER_STATUS"
else
  expected_run_count=50
  echo "RUNNING" > "$RUNNER_STATUS"
fi

scheduled_count=$(
  emit_schedule | wc -l
)

if [ "$scheduled_count" -ne "$expected_run_count" ]; then
  echo \
    "[FAIL] Expected $expected_run_count emitted rows; got $scheduled_count."

  echo "SCHEDULE_FAILED" > "$RUNNER_STATUS"
  exit 1
fi

echo \
  "[INFO] Emitted schedule rows: $scheduled_count"

failures=0

while IFS=$'\t' read -r \
  condition_id \
  parameter \
  factor \
  eta \
  rep \
  seed
do
  if ! run_trial \
    "$condition_id" \
    "$parameter" \
    "$factor" \
    "$eta" \
    "$rep" \
    "$seed"
  then
    failures=$((failures + 1))
  fi
done < <(emit_schedule)

if [ "$failures" -ne 0 ]; then
  echo \
    "[FAIL] OFAT localization had $failures failed trials."

  echo \
    "FAILED_${failures}" \
    > "$RUNNER_STATUS"

  exit 1
fi

cd "$PROJECT_DIR"

if [ "$PILOT" -eq 1 ]; then
  python \
    scripts/summarize_ofat_m2_pinv_bisection_round.py \
    --root "$ROOT" \
    --allow-incomplete

  echo "PILOT_COMPLETE" \
    > "$RUNNER_STATUS"
else
  python \
    scripts/summarize_ofat_m2_pinv_bisection_round.py \
    --root "$ROOT"

  echo "COMPLETE" \
    > "$RUNNER_STATUS"
fi

restore_nominal_plant

echo
echo "============================================================"
cat "$RUNNER_STATUS"
echo "============================================================"
