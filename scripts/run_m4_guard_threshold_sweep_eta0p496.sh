#!/usr/bin/env bash
set -uo pipefail

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"

SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

LANDING_RUNNER="$PROJECT_DIR/scripts/fault_triggered_landing_qp_event_allocator.py"

ETA="${ETA:-0.496}"
THRESHOLDS="${THRESHOLDS:-0.16 0.18 0.20}"
REPS="${REPS:-30}"
BASE_SEED="${BASE_SEED:-820000}"
SCHEDULE_SEED="${SCHEDULE_SEED:-20260728}"
RUN_ID="${RUN_ID:-fresh30}"

MAX_TRIAL_ATTEMPTS="${MAX_TRIAL_ATTEMPTS:-3}"

OUTPUT_ROOT="$PROJECT_DIR/results/final/pinv_baseline/seeded_eta0p496/m4_guard/threshold_sweep/$RUN_ID"

SCHEDULE="$OUTPUT_ROOT/schedule.csv"

cleanup_sim() {
    pkill -f "sitl_singleagent.sh" 2>/dev/null || true
    pkill -f "cf2" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f "gzserver" 2>/dev/null || true
    pkill -f "gazebo" 2>/dev/null || true
    sleep 3
}

trap cleanup_sim EXIT

test -s "$LANDING_RUNNER" || {
    echo "[FAIL] Missing landing runner: $LANDING_RUNNER"
    exit 1
}

mkdir -p \
    "$OUTPUT_ROOT" \
    "$PROJECT_DIR/logs"

THRESHOLDS_ENV="$THRESHOLDS" \
python - \
    "$SCHEDULE" \
    "$ETA" \
    "$REPS" \
    "$BASE_SEED" \
    "$SCHEDULE_SEED" \
    "$RUN_ID" <<'PY'
import csv
import os
import random
import sys
from pathlib import Path

schedule_path = Path(sys.argv[1])
eta = float(sys.argv[2])
reps = int(sys.argv[3])
base_seed = int(sys.argv[4])
schedule_seed = int(sys.argv[5])
run_id = sys.argv[6]

thresholds = [
    float(value)
    for value in os.environ[
        "THRESHOLDS_ENV"
    ].split()
]

if reps <= 0:
    raise SystemExit("[FAIL] REPS must be positive.")

if len(thresholds) < 2:
    raise SystemExit(
        "[FAIL] At least two guard thresholds are required."
    )

if len(set(thresholds)) != len(thresholds):
    raise SystemExit(
        "[FAIL] Duplicate guard thresholds supplied."
    )

eta_code = int(round(eta * 10000))
eta_tag = str(eta).replace(".", "p")

rows = []

for threshold in thresholds:
    threshold_tag = (
        f"{threshold:.3f}"
        .rstrip("0")
        .rstrip(".")
        .replace(".", "p")
    )

    for repetition in range(1, reps + 1):
        # Identical seed across thresholds gives a paired design.
        trial_seed = (
            base_seed
            + 4 * 10_000_000
            + eta_code * 1000
            + repetition
        )

        tag = (
            f"m4guardsweep_{run_id}_"
            f"g{threshold_tag}_"
            f"seed{trial_seed}"
        )

        expected_csv = (
            "logs/"
            "qp_event_allocator_m4_"
            f"eta{eta_tag}_{tag}.csv"
        )

        rows.append(
            {
                "guard_threshold_mps": threshold,
                "repetition": repetition,
                "trial_seed": trial_seed,
                "tag": tag,
                "expected_csv": expected_csv,
            }
        )

random.Random(schedule_seed).shuffle(rows)

for sequence_index, row in enumerate(
    rows,
    start=1,
):
    row["sequence_index"] = sequence_index

fieldnames = [
    "sequence_index",
    "guard_threshold_mps",
    "repetition",
    "trial_seed",
    "tag",
    "expected_csv",
]

schedule_path.parent.mkdir(
    parents=True,
    exist_ok=True,
)

with schedule_path.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=fieldnames,
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)

print(f"[SAVED] {schedule_path}")
print(
    f"[SCHEDULE] thresholds={thresholds} "
    f"reps={reps} trials={len(rows)} "
    f"schedule_seed={schedule_seed}"
)
PY

date --iso-8601=seconds \
    > "$OUTPUT_ROOT/start_time.txt"

while IFS=',' read -r \
    sequence_index \
    guard_threshold \
    repetition \
    trial_seed \
    tag \
    expected_csv
do
    echo
    echo "============================================================"
    echo "[M4 GUARDED THRESHOLD SWEEP]"
    echo "sequence=$sequence_index"
    echo "guard_threshold=$guard_threshold"
    echo "repetition=$repetition"
    echo "trial_seed=$trial_seed"
    echo "expected_csv=$expected_csv"
    echo "============================================================"

    if [ -s "$PROJECT_DIR/$expected_csv" ]; then
        echo "[SKIP] Existing CSV: $expected_csv"
        continue
    fi

    success=0
    attempt=1

    while [ "$attempt" -le "$MAX_TRIAL_ATTEMPTS" ]; do
        echo "[ATTEMPT] $attempt/$MAX_TRIAL_ATTEMPTS"

        cd "$PROJECT_DIR" || exit 1

        parameter_exports=$(
            python scripts/seeded_trial_params.py \
                --seed "$trial_seed" \
                --shell
        )

        parameter_status=$?

        if [ "$parameter_status" -ne 0 ]; then
            echo "[WARN] Seed parameter generation failed."
            attempt=$((attempt + 1))
            continue
        fi

        eval "$parameter_exports"

        if [ "$TRIAL_SEED" != "$trial_seed" ]; then
            echo "[FAIL] Seed mismatch:"
            echo "       schedule=$trial_seed"
            echo "       generated=$TRIAL_SEED"
            exit 1
        fi

        cleanup_sim

        cd "$CF_FW_DIR" || exit 1

        bash "$SIM_LAUNCH" \
            -m crazyflie \
            -x "$SPAWN_X" \
            -y "$SPAWN_Y" \
            > "$PROJECT_DIR/logs/sim_${tag}.log" \
            2>&1 &

        sleep 8

        cd "$PROJECT_DIR" || exit 1

        python scripts/wait_for_cf.py

        ready_status=$?

        if [ "$ready_status" -ne 0 ]; then
            echo "[WARN] Crazyflie did not become ready."
            cleanup_sim
            attempt=$((attempt + 1))
            continue
        fi

        threshold_tag="${guard_threshold/./p}"

        set +e

        timeout 90s \
        python "$LANDING_RUNNER" \
            --controller qplite \
            --motor 4 \
            --eta "$ETA" \
            --tag "$tag" \
            --protocol-id "$PROTOCOL_ID" \
            --trial-seed "$TRIAL_SEED" \
            --spawn-x "$SPAWN_X" \
            --spawn-y "$SPAWN_Y" \
            --spawn-yaw-deg "$SPAWN_YAW_DEG" \
            --fault-time "$FAULT_TIME" \
            --hover-z "$HOVER_Z" \
            --post-fault-mode adaptive_ramp_v1 \
            --eval-duration 18.0 \
            --max-brake-duration 6.0 \
            --landing-descent-rate 0.08 \
            --min-valid-fault-z 0.50 \
            --max-valid-fault-abs-vz 0.25 \
            --manual-residual \
            --manual-name \
              guarded_opp_m2_14000_to_12000_v1 \
            --r1 0 \
            --r2 14000 \
            --r3 0 \
            --r4 0 \
            --m4-vz-guard "$guard_threshold" \
            --m4-guard-fallback-r2 12000 \
            2>&1 \
            | tee \
              "$OUTPUT_ROOT/trial_${sequence_index}_g${threshold_tag}_console.txt"

        trial_status=${PIPESTATUS[0]}

        set -e

        cleanup_sim

        if [ "$trial_status" -ne 0 ]; then
            echo "[WARN] Trial exited with $trial_status."
            attempt=$((attempt + 1))
            continue
        fi

        if [ ! -s "$PROJECT_DIR/$expected_csv" ]; then
            echo "[WARN] Expected CSV was not created:"
            echo "       $PROJECT_DIR/$expected_csv"
            attempt=$((attempt + 1))
            continue
        fi

        echo "[PASS] Trial CSV verified: $expected_csv"
        success=1
        break
    done

    if [ "$success" -ne 1 ]; then
        echo "[FAIL] Trial failed after all attempts:"
        echo "       sequence=$sequence_index"
        echo "       guard=$guard_threshold"
        echo "       seed=$trial_seed"
        exit 1
    fi

done < <(tail -n +2 "$SCHEDULE")

date --iso-8601=seconds \
    > "$OUTPUT_ROOT/end_time.txt"

echo "runner_exit_status=0" \
    | tee "$OUTPUT_ROOT/runner_status.txt"

echo "[PASS] Fresh M4 guard threshold sweep completed."
