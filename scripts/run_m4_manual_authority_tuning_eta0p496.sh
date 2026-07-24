#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"

SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"
LANDING_RUNNER="$PROJECT_DIR/scripts/fault_triggered_landing_qp_event_allocator.py"

ETA="${ETA:-0.496}"
STRENGTHS="${STRENGTHS:-12000 13000 14000 15000}"
REPS="${REPS:-30}"
BASE_SEED="${BASE_SEED:-420000}"
SCHEDULE_SEED="${SCHEDULE_SEED:-20260724}"
RUN_ID="${RUN_ID:-m4_authority_tuning}"

POST_FAULT_MODE="${POST_FAULT_MODE:-adaptive_ramp_v1}"
EVAL_DURATION="${EVAL_DURATION:-18.0}"
MAX_BRAKE_DURATION="${MAX_BRAKE_DURATION:-6.0}"
LANDING_DESCENT_RATE="${LANDING_DESCENT_RATE:-0.08}"
MIN_VALID_FAULT_Z="${MIN_VALID_FAULT_Z:-0.50}"
MAX_VALID_FAULT_ABS_VZ="${MAX_VALID_FAULT_ABS_VZ:-0.25}"
MAX_TRIAL_ATTEMPTS="${MAX_TRIAL_ATTEMPTS:-3}"

OUTPUT_ROOT="$PROJECT_DIR/results/final/pinv_baseline/seeded_eta0p496/m4_authority_tuning/$RUN_ID"
SCHEDULE="$OUTPUT_ROOT/schedule.csv"

case "$RUN_ID" in
    *[!A-Za-z0-9_.-]*|"")
        echo "[FAIL] Invalid RUN_ID: $RUN_ID"
        exit 1
        ;;
esac

cleanup_sim() {
    pkill -f "sitl_singleagent.sh" 2>/dev/null || true
    pkill -f "cf2" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f "gzserver" 2>/dev/null || true
    pkill -f "gazebo" 2>/dev/null || true
    sleep 3
}

test -s "$LANDING_RUNNER" || {
    echo "[FAIL] Missing landing runner: $LANDING_RUNNER"
    exit 1
}

HELP_TEXT=$(python "$LANDING_RUNNER" --help 2>&1)

for OPTION in \
    "--manual-residual" \
    "--manual-name" \
    "--r1" \
    "--r2" \
    "--r3" \
    "--r4" \
    "--controller"
do
    grep -q -- "$OPTION" <<< "$HELP_TEXT" || {
        echo "[FAIL] Landing runner does not expose $OPTION"
        exit 1
    }
done

mkdir -p "$OUTPUT_ROOT"

STRENGTHS_ENV="$STRENGTHS" \
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

strengths = [
    int(value)
    for value in os.environ["STRENGTHS_ENV"].split()
]

if reps <= 0:
    raise SystemExit("[FAIL] REPS must be positive.")

if len(strengths) < 2:
    raise SystemExit("[FAIL] At least two strengths are required.")

if len(set(strengths)) != len(strengths):
    raise SystemExit("[FAIL] Duplicate strengths supplied.")

eta_code = int(round(eta * 10000))
eta_tag = str(eta).replace(".", "p")

rows = []

for strength in strengths:
    for repetition in range(1, reps + 1):
        # The seed is independent of strength. Therefore, all
        # residual strengths receive identical initial conditions.
        trial_seed = (
            base_seed
            + 4 * 10_000_000
            + eta_code * 1000
            + repetition
        )

        manual_name = f"opp_m2_{strength}"

        tag = (
            f"seededm4manual_{run_id}_"
            f"r{strength}_eta{eta_tag}_"
            f"seed{trial_seed}"
        )

        expected_csv = (
            f"logs/qp_event_allocator_"
            f"m4_eta{eta_tag}_{tag}.csv"
        )

        rows.append(
            {
                "strength": strength,
                "repetition": repetition,
                "trial_seed": trial_seed,
                "manual_name": manual_name,
                "tag": tag,
                "expected_csv": expected_csv,
            }
        )

random.Random(schedule_seed).shuffle(rows)

for sequence_index, row in enumerate(rows, start=1):
    row["sequence_index"] = sequence_index

fieldnames = [
    "sequence_index",
    "strength",
    "repetition",
    "trial_seed",
    "manual_name",
    "tag",
    "expected_csv",
]

schedule_path.parent.mkdir(parents=True, exist_ok=True)

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
    f"[SCHEDULE] strengths={strengths} "
    f"reps={reps} trials={len(rows)} "
    f"schedule_seed={schedule_seed}"
)
PY

date --iso-8601=seconds > "$OUTPUT_ROOT/start_time.txt"

while IFS=',' read -r \
    sequence_index \
    strength \
    repetition \
    trial_seed \
    manual_name \
    tag \
    expected_csv
do
    echo
    echo "============================================================"
    echo "[M4 MANUAL AUTHORITY TRIAL]"
    echo "sequence=${sequence_index}"
    echo "strength=${strength}"
    echo "repetition=${repetition}"
    echo "seed=${trial_seed}"
    echo "manual_name=${manual_name}"
    echo "expected_csv=${expected_csv}"
    echo "============================================================"

    if [ -s "$PROJECT_DIR/$expected_csv" ]; then
        echo "[SKIP] Existing CSV: $expected_csv"
        continue
    fi

    attempt=1
    success=0

    while [ "$attempt" -le "$MAX_TRIAL_ATTEMPTS" ]; do
        echo "[ATTEMPT] ${attempt}/${MAX_TRIAL_ATTEMPTS}"

        cd "$PROJECT_DIR" || exit 1

        parameter_exports=$(
            python scripts/seeded_trial_params.py \
                --seed "$trial_seed" \
                --shell
        )

        parameter_status=$?

        if [ "$parameter_status" -ne 0 ]; then
            echo "[WARN] Seeded-parameter generation failed."
            attempt=$((attempt + 1))
            continue
        fi

        eval "$parameter_exports"

        if [ "$TRIAL_SEED" != "$trial_seed" ]; then
            echo "[FAIL] Trial-seed mismatch."
            echo "       schedule=$trial_seed"
            echo "       generated=$TRIAL_SEED"
            exit 1
        fi

        echo "protocol=${PROTOCOL_ID}"
        echo "spawn=(${SPAWN_X}, ${SPAWN_Y})"
        echo "spawn_yaw_deg=${SPAWN_YAW_DEG}"
        echo "hover_z=${HOVER_Z}"
        echo "fault_time=${FAULT_TIME}"

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
            --post-fault-mode "$POST_FAULT_MODE" \
            --eval-duration "$EVAL_DURATION" \
            --max-brake-duration "$MAX_BRAKE_DURATION" \
            --landing-descent-rate "$LANDING_DESCENT_RATE" \
            --min-valid-fault-z "$MIN_VALID_FAULT_Z" \
            --max-valid-fault-abs-vz \
                "$MAX_VALID_FAULT_ABS_VZ" \
            --manual-residual \
            --manual-name "$manual_name" \
            --r1 0 \
            --r2 "$strength" \
            --r3 0 \
            --r4 0

        trial_status=$?

        cleanup_sim

        if [ "$trial_status" -ne 0 ]; then
            echo "[WARN] Landing process exited with $trial_status."
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
        echo "       strength=$strength"
        echo "       seed=$trial_seed"
        cleanup_sim
        exit 1
    fi
done < <(tail -n +2 "$SCHEDULE")

date --iso-8601=seconds > "$OUTPUT_ROOT/end_time.txt"

echo "runner_exit_status=0" \
    | tee "$OUTPUT_ROOT/runner_status.txt"

echo "[PASS] M4 paired authority sweep completed."
