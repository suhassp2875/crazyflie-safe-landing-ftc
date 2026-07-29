#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"

SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

ROOT="$PROJECT_DIR/results/final/model_sensitivity/nominal_m2_boundary/phase_validation"
SCHEDULE="$ROOT/phase_validation_schedule.csv"

TRIAL_DIR="$ROOT/trials"
SUMMARY_DIR="$ROOT/summaries"
CONSOLE_DIR="$ROOT/consoles"
SIM_LOG_DIR="$ROOT/simulator_logs"

STATUS_FILE="$ROOT/run_status.csv"
RUNNER_STATUS="$ROOT/runner_status.txt"

CEM_CONFIG="$PROJECT_DIR/configs/allocator_weights/cem_tuned_boundary.json"

NOMINAL_SHA256="849b83459d1c2d9ea365d7e743ed7fe5a00151aa39505ec9f6294777881dfee9"

POST_FAULT_MODE="${POST_FAULT_MODE:-adaptive_ramp_v1}"
EVAL_DURATION="${EVAL_DURATION:-18.0}"
MAX_BRAKE_DURATION="${MAX_BRAKE_DURATION:-6.0}"
LANDING_DESCENT_RATE="${LANDING_DESCENT_RATE:-0.08}"

MIN_VALID_FAULT_Z="${MIN_VALID_FAULT_Z:-0.50}"
MAX_VALID_FAULT_ABS_VZ="${MAX_VALID_FAULT_ABS_VZ:-0.25}"

MAX_TRIAL_ATTEMPTS="${MAX_TRIAL_ATTEMPTS:-3}"

# PILOT=1 selects trial_index=1 from each
# of the six selector phases: six trials total.
PILOT="${PILOT:-0}"

mkdir -p \
  "$TRIAL_DIR" \
  "$SUMMARY_DIR" \
  "$CONSOLE_DIR" \
  "$SIM_LOG_DIR"

test -f "$SCHEDULE" || {
  echo "[FAIL] Missing schedule: $SCHEDULE"
  exit 1
}

test -f "$CEM_CONFIG" || {
  echo "[FAIL] Missing CEM config: $CEM_CONFIG"
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

cleanup_all() {
  cleanup_sim

  cd "$PROJECT_DIR" || true

  python scripts/plant_ofat.py restore \
    >/dev/null 2>&1 || true
}

trap cleanup_all EXIT INT TERM

verify_nominal_plant() {
  cd "$PROJECT_DIR"

  python scripts/plant_ofat.py verify

  local template
  template="$FW_DIR/tools/crazyflie-simulation/simulator_files/gazebo/models/crazyflie/model.sdf.jinja"

  local observed
  observed=$(
    sha256sum "$template" \
      | awk '{print $1}'
  )

  if [ "$observed" != "$NOMINAL_SHA256" ]; then
    echo "[FAIL] Plant template is not nominal."
    echo "expected=$NOMINAL_SHA256"
    echo "observed=$observed"
    return 1
  fi
}

append_status() {
  local status="$1"
  local controller="$2"
  local eta="$3"
  local rep="$4"
  local seed="$5"
  local attempt="$6"
  local trial_csv="$7"

  if [ ! -f "$STATUS_FILE" ]; then
    echo \
"status,controller,motor,eta,rep,trial_seed,attempt,trial_csv" \
      > "$STATUS_FILE"
  fi

  echo \
"${status},${controller},2,${eta},${rep},${seed},${attempt},${trial_csv}" \
    >> "$STATUS_FILE"
}

runner_eta_tag() {
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

condition_eta_tag() {
  python - "$1" <<'PY'
import sys

print(
    f"{float(sys.argv[1]):.5f}".replace(
        ".",
        "p",
    )
)
PY
}

validate_trial() {
  local csv_path="$1"
  local controller="$2"
  local eta="$3"
  local seed="$4"
  local condition_id="$5"
  local expected_candidate="$6"
  local expected_r1="$7"
  local expected_r2="$8"
  local expected_r3="$9"
  local expected_r4="${10}"
  local summary_path="${11}"

  cd "$PROJECT_DIR"

  python \
    scripts/validate_nominal_m2_phase_trial.py \
    --csv "$csv_path" \
    --controller "$controller" \
    --eta "$eta" \
    --seed "$seed" \
    --condition-id "$condition_id" \
    --expected-candidate "$expected_candidate" \
    --expected-r1 "$expected_r1" \
    --expected-r2 "$expected_r2" \
    --expected-r3 "$expected_r3" \
    --expected-r4 "$expected_r4" \
    --summary-output "$summary_path"
}

run_trial() {
  local condition_id="$1"
  local controller="$2"
  local eta="$3"
  local rep="$4"
  local seed="$5"
  local expected_candidate="$6"
  local expected_r1="$7"
  local expected_r2="$8"
  local expected_r3="$9"
  local expected_r4="${10}"

  local generated_eta_tag
  generated_eta_tag=$(
    runner_eta_tag "$eta"
  )

  local file_eta_tag
  file_eta_tag=$(
    condition_eta_tag "$eta"
  )

  local tag
  tag="nominal_m2phase_${condition_id}_eta${file_eta_tag}_seed${seed}"

  local generated_csv
  generated_csv="$PROJECT_DIR/logs/qp_event_allocator_m2_eta${generated_eta_tag}_${tag}.csv"

  local trial_csv
  trial_csv="$TRIAL_DIR/${tag}.csv"

  local summary_csv
  summary_csv="$SUMMARY_DIR/${tag}_summary.csv"

  if [ -f "$trial_csv" ]; then
    if validate_trial \
      "$trial_csv" \
      "$controller" \
      "$eta" \
      "$seed" \
      "$condition_id" \
      "$expected_candidate" \
      "$expected_r1" \
      "$expected_r2" \
      "$expected_r3" \
      "$expected_r4" \
      "$summary_csv"
    then
      echo "[SKIP] Valid completed trial: $trial_csv"
      return 0
    fi

    local invalid_existing
    invalid_existing="${trial_csv}.invalid_$(date +%s)"

    mv \
      "$trial_csv" \
      "$invalid_existing"

    echo \
      "[WARN] Existing invalid trial moved to $invalid_existing"
  fi

  local attempt=1

  while [ "$attempt" -le "$MAX_TRIAL_ATTEMPTS" ]; do
    echo
    echo "======================================================================"
    echo "[TRIAL] condition=$condition_id controller=$controller eta=$eta rep=$rep seed=$seed attempt=$attempt"
    echo "======================================================================"

    verify_nominal_plant
    cleanup_sim

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
        "$controller" \
        "$eta" \
        "$rep" \
        "$seed" \
        "$attempt" \
        ""

      cleanup_sim
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

    if [ "$controller" = "pinv" ]; then
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

    elif [ "$controller" = "cem" ]; then
      timeout 100s \
      python \
        scripts/fault_triggered_landing_qp_event_allocator.py \
        "${common_args[@]}" \
        --controller qplite \
        --weight-config "$CEM_CONFIG" \
        > "$controller_log" 2>&1 \
        || runner_rc=$?

    else
      echo "[FAIL] Unknown controller: $controller"
      return 1
    fi

    cleanup_sim

    if [ "$runner_rc" -ne 0 ]; then
      echo \
        "[WARN] Runner failed with code $runner_rc"

      tail -80 "$controller_log" || true

      append_status \
        "RUNNER_FAILED" \
        "$controller" \
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
        "$controller" \
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
      "$controller" \
      "$eta" \
      "$seed" \
      "$condition_id" \
      "$expected_candidate" \
      "$expected_r1" \
      "$expected_r2" \
      "$expected_r3" \
      "$expected_r4" \
      "$summary_csv"
    then
      append_status \
        "PASS" \
        "$controller" \
        "$eta" \
        "$rep" \
        "$seed" \
        "$attempt" \
        "$trial_csv"

      echo "[PASS] Completed $tag"
      return 0
    fi

    invalid_csv="${trial_csv}.invalid_attempt${attempt}"

    mv \
      "$trial_csv" \
      "$invalid_csv"

    append_status \
      "VALIDATION_FAILED" \
      "$controller" \
      "$eta" \
      "$rep" \
      "$seed" \
      "$attempt" \
      "$invalid_csv"

    attempt=$((attempt + 1))
  done

  echo \
    "[FAIL] Trial failed after $MAX_TRIAL_ATTEMPTS attempts: condition=$condition_id controller=$controller eta=$eta seed=$seed"

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

with schedule_path.open(newline="") as file:
    rows = list(csv.DictReader(file))

if len(rows) != 180:
    raise SystemExit(
        f"[FAIL] Expected 180 schedule rows; "
        f"found {len(rows)}."
    )

required = {
    "condition_id",
    "controller",
    "motor",
    "eta",
    "expected_candidate",
    "expected_r1",
    "expected_r2",
    "expected_r3",
    "expected_r4",
    "trial_index",
    "trial_seed",
    "protocol_id",
}

missing_columns = required - set(
    rows[0]
)

if missing_columns:
    raise SystemExit(
        "[FAIL] Missing schedule columns: "
        f"{sorted(missing_columns)}"
    )

condition_counts = Counter(
    row["condition_id"]
    for row in rows
)

if len(condition_counts) != 6:
    raise SystemExit(
        "[FAIL] Expected six conditions."
    )

if set(condition_counts.values()) != {30}:
    raise SystemExit(
        "[FAIL] Every condition must contain "
        "30 trials."
    )

seed_sets = defaultdict(set)

for row in rows:
    if row["controller"] != "cem":
        raise SystemExit(
            "[FAIL] Phase schedule must use "
            "controller=cem."
        )

    if int(row["motor"]) != 2:
        raise SystemExit(
            "[FAIL] Phase schedule must use M2."
        )

    if row["protocol_id"] != "seeded_ic_v1":
        raise SystemExit(
            "[FAIL] Unexpected protocol."
        )

    seed_sets[
        row["condition_id"]
    ].add(
        int(row["trial_seed"])
    )

reference_seeds = next(
    iter(seed_sets.values())
)

for condition, seeds in seed_sets.items():
    if len(seeds) != 30:
        raise SystemExit(
            f"[FAIL] {condition} has "
            f"{len(seeds)} seeds."
        )

    if seeds != reference_seeds:
        raise SystemExit(
            "[FAIL] Seed sets differ across "
            f"conditions at {condition}."
        )

if pilot:
    rows = [
        row
        for row in rows
        if int(row["trial_index"]) == 1
    ]

for row in rows:
    values = [
        row["condition_id"],
        row["controller"],
        row["eta"],
        row["trial_index"],
        row["trial_seed"],
        row["expected_candidate"],
        row["expected_r1"],
        row["expected_r2"],
        row["expected_r3"],
        row["expected_r4"],
    ]

    print("\t".join(values))
PY
}

cd "$PROJECT_DIR"

verify_nominal_plant

if [ "$PILOT" -eq 1 ]; then
  expected_run_count=6
  echo "RUNNING_PILOT" > "$RUNNER_STATUS"
else
  expected_run_count=180
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
  controller \
  eta \
  rep \
  seed \
  expected_candidate \
  expected_r1 \
  expected_r2 \
  expected_r3 \
  expected_r4
do
  if ! run_trial \
    "$condition_id" \
    "$controller" \
    "$eta" \
    "$rep" \
    "$seed" \
    "$expected_candidate" \
    "$expected_r1" \
    "$expected_r2" \
    "$expected_r3" \
    "$expected_r4"
  then
    failures=$((failures + 1))
  fi
done < <(emit_schedule)

if [ "$failures" -ne 0 ]; then
  echo \
    "[FAIL] Phase validation had $failures failed trials."

  echo \
    "FAILED_${failures}" \
    > "$RUNNER_STATUS"

  exit 1
fi

cd "$PROJECT_DIR"

if [ "$PILOT" -eq 1 ]; then
  python \
    scripts/summarize_nominal_m2_phase_validation.py \
    --root "$ROOT" \
    --allow-incomplete

  echo "PILOT_COMPLETE" \
    > "$RUNNER_STATUS"
else
  python \
    scripts/summarize_nominal_m2_phase_validation.py \
    --root "$ROOT"

  echo "COMPLETE" \
    > "$RUNNER_STATUS"
fi

verify_nominal_plant

echo
echo "============================================================"
cat "$RUNNER_STATUS"
echo "============================================================"
