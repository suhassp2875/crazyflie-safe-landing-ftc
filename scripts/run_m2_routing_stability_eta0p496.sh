#!/usr/bin/env bash

set -Eeuo pipefail


PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"

FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"

SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

PLANT_TEMPLATE="$FW_DIR/tools/crazyflie-simulation/simulator_files/gazebo/models/crazyflie/model.sdf.jinja"


ROOT="$PROJECT_DIR/results/final/model_sensitivity/ofat/m2_routing_stability_eta0p496"

SCHEDULE="$ROOT/routing_stability_schedule.csv"

TRIAL_DIR="$ROOT/trials"
SUMMARY_DIR="$ROOT/summaries"
CONSOLE_DIR="$ROOT/consoles"
SIM_LOG_DIR="$ROOT/simulator_logs"

STATUS_FILE="$ROOT/run_status.csv"
RUNNER_STATUS="$ROOT/runner_status.txt"

CEM_CONFIG="$PROJECT_DIR/configs/allocator_weights/cem_tuned_boundary.json"


POST_FAULT_MODE="${POST_FAULT_MODE:-adaptive_ramp_v1}"

EVAL_DURATION="${EVAL_DURATION:-18.0}"

MAX_BRAKE_DURATION="${MAX_BRAKE_DURATION:-6.0}"

LANDING_DESCENT_RATE="${LANDING_DESCENT_RATE:-0.08}"

MIN_VALID_FAULT_Z="${MIN_VALID_FAULT_Z:-0.50}"

MAX_VALID_FAULT_ABS_VZ="${MAX_VALID_FAULT_ABS_VZ:-0.25}"

MAX_TRIAL_ATTEMPTS="${MAX_TRIAL_ATTEMPTS:-3}"

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


restore_plant() {
  cd "$PROJECT_DIR"

  python scripts/plant_ofat.py restore \
    >/dev/null

  python scripts/plant_ofat.py verify
}


cleanup_all() {
  cleanup_sim

  cd "$PROJECT_DIR" || true

  python scripts/plant_ofat.py restore \
    >/dev/null 2>&1 || true
}


trap cleanup_all EXIT INT TERM


apply_condition() {
  local condition_id="$1"
  local parameter="$2"
  local factor="$3"
  local expected_sha="$4"

  cleanup_sim

  cd "$PROJECT_DIR"

  python scripts/plant_ofat.py restore \
    >/dev/null

  if [ "$condition_id" = "nominal" ]; then
    python scripts/plant_ofat.py verify
  else
    python scripts/plant_ofat.py apply \
      --parameter "$parameter" \
      --factor "$factor"

    python scripts/plant_ofat.py verify
  fi

  local observed_sha

  observed_sha=$(
    sha256sum "$PLANT_TEMPLATE" \
      | awk '{print $1}'
  )

  if [ "$observed_sha" != "$expected_sha" ]; then
    echo "[FAIL] Plant checksum mismatch."
    echo "condition=$condition_id"
    echo "expected=$expected_sha"
    echo "observed=$observed_sha"
    return 1
  fi

  echo \
    "[PASS] Plant condition verified: $condition_id"
}


append_status() {
  local status="$1"
  local condition_id="$2"
  local parameter="$3"
  local factor="$4"
  local controller="$5"
  local eta="$6"
  local rep="$7"
  local seed="$8"
  local attempt="$9"
  local trial_csv="${10}"

  if [ ! -f "$STATUS_FILE" ]; then
    echo \
"status,condition_id,parameter,factor,controller,motor,eta,rep,trial_seed,attempt,trial_csv" \
      > "$STATUS_FILE"
  fi

  echo \
"${status},${condition_id},${parameter},${factor},${controller},2,${eta},${rep},${seed},${attempt},${trial_csv}" \
    >> "$STATUS_FILE"
}


eta_tag() {
  python - "$1" <<'ETA_TAG_PY'
import sys

print(
    f"{float(sys.argv[1]):.3f}".replace(
        ".",
        "p",
    )
)
ETA_TAG_PY
}


validate_trial() {
  local csv_path="$1"
  local controller="$2"
  local eta="$3"
  local seed="$4"
  local summary_path="$5"

  cd "$PROJECT_DIR"

  python \
    scripts/validate_nominal_m2_boundary_trial.py \
    --csv "$csv_path" \
    --controller "$controller" \
    --eta "$eta" \
    --seed "$seed" \
    --summary-output "$summary_path"
}


run_trial() {
  local condition_id="$1"
  local parameter="$2"
  local factor="$3"
  local plant_sha="$4"
  local controller="$5"
  local eta="$6"
  local rep="$7"
  local seed="$8"
  local tag="$9"

  local tag_eta

  tag_eta=$(
    eta_tag "$eta"
  )

  local generated_csv

  generated_csv="$PROJECT_DIR/logs/qp_event_allocator_m2_eta${tag_eta}_${tag}.csv"

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
      "$summary_csv"
    then
      echo \
        "[SKIP] Valid completed trial: $trial_csv"

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
    echo \
      "[TRIAL] condition=$condition_id controller=$controller eta=$eta rep=$rep seed=$seed attempt=$attempt"
    echo "======================================================================"

    if ! apply_condition \
      "$condition_id" \
      "$parameter" \
      "$factor" \
      "$plant_sha"
    then
      append_status \
        "PLANT_FAILED" \
        "$condition_id" \
        "$parameter" \
        "$factor" \
        "$controller" \
        "$eta" \
        "$rep" \
        "$seed" \
        "$attempt" \
        ""

      attempt=$((attempt + 1))
      continue
    fi


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
      echo \
        "[WARN] Crazyflie connection check failed."

      append_status \
        "WAIT_FAILED" \
        "$condition_id" \
        "$parameter" \
        "$factor" \
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
      echo \
        "[FAIL] Unknown controller: $controller"

      return 1
    fi


    cleanup_sim


    cd "$PROJECT_DIR"

    python scripts/plant_ofat.py restore \
      >/dev/null

    python scripts/plant_ofat.py verify


    if [ "$runner_rc" -ne 0 ]; then
      echo \
        "[WARN] Runner failed with code $runner_rc"

      tail -80 "$controller_log" || true

      append_status \
        "RUNNER_FAILED" \
        "$condition_id" \
        "$parameter" \
        "$factor" \
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
      echo \
        "[WARN] Runner produced no expected CSV."

      append_status \
        "CSV_MISSING" \
        "$condition_id" \
        "$parameter" \
        "$factor" \
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
      "$summary_csv"
    then
      append_status \
        "PASS" \
        "$condition_id" \
        "$parameter" \
        "$factor" \
        "$controller" \
        "$eta" \
        "$rep" \
        "$seed" \
        "$attempt" \
        "$trial_csv"

      echo \
        "[PASS] Completed $tag"

      return 0
    fi


    local invalid_csv

    invalid_csv="${trial_csv}.invalid_attempt${attempt}"


    mv \
      "$trial_csv" \
      "$invalid_csv"


    append_status \
      "VALIDATION_FAILED" \
      "$condition_id" \
      "$parameter" \
      "$factor" \
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
  python - "$SCHEDULE" "$PILOT" <<'EMIT_SCHEDULE_PY'
from __future__ import annotations

import csv
import sys
from pathlib import Path


schedule_path = Path(
    sys.argv[1]
)

pilot = int(
    sys.argv[2]
)


with schedule_path.open(
    newline=""
) as file:
    rows = list(
        csv.DictReader(file)
    )


if len(rows) != 660:
    raise SystemExit(
        "[FAIL] Expected 660 schedule rows; "
        f"found {len(rows)}."
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
        row["plant_sha256"],
        row["controller"],
        row["eta"],
        row["rep"],
        row["trial_seed"],
        row["tag"],
    ]

    print(
        "\t".join(values)
    )
EMIT_SCHEDULE_PY
}


cd "$PROJECT_DIR"


python scripts/plant_ofat.py restore \
  >/dev/null

python scripts/plant_ofat.py verify


if [ "$PILOT" -eq 1 ]; then
  expected_run_count=22
  echo "RUNNING_PILOT" \
    > "$RUNNER_STATUS"
else
  expected_run_count=660
  echo "RUNNING" \
    > "$RUNNER_STATUS"
fi


emitted_count=0


while IFS=$'\t' read -r \
  condition_id \
  parameter \
  factor \
  plant_sha \
  controller \
  eta \
  rep \
  seed \
  tag

do
  emitted_count=$((emitted_count + 1))

  run_trial \
    "$condition_id" \
    "$parameter" \
    "$factor" \
    "$plant_sha" \
    "$controller" \
    "$eta" \
    "$rep" \
    "$seed" \
    "$tag"

done < <(
  emit_schedule
)


if [ "$emitted_count" -ne "$expected_run_count" ]; then
  echo \
    "[FAIL] Schedule emission mismatch: emitted=$emitted_count expected=$expected_run_count"

  exit 1
fi


restore_plant


if [ "$PILOT" -eq 1 ]; then
  python \
    scripts/summarize_m2_routing_stability.py \
    --root "$ROOT" \
    --allow-incomplete

  echo "PILOT_COMPLETE" \
    > "$RUNNER_STATUS"
else
  python \
    scripts/summarize_m2_routing_stability.py \
    --root "$ROOT"

  echo "COMPLETE" \
    > "$RUNNER_STATUS"
fi


echo
echo "========== FINAL PLANT =========="

python scripts/plant_ofat.py verify

echo
echo "[PASS] Routing-stability runner finished."
