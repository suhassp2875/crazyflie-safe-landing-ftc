#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"

SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

ETA="${ETA:-0.496}"
REPS_PER_MOTOR="${REPS_PER_MOTOR:-2}"
BASE_SEED="${BASE_SEED:-220000}"
SCHEDULE_SEED="${SCHEDULE_SEED:-20260723}"
RUN_ID="${RUN_ID:-pilot8}"

POST_FAULT_MODE="${POST_FAULT_MODE:-adaptive_ramp_v1}"
EVAL_DURATION="${EVAL_DURATION:-18.0}"
MAX_BRAKE_DURATION="${MAX_BRAKE_DURATION:-6.0}"
LANDING_DESCENT_RATE="${LANDING_DESCENT_RATE:-0.08}"
MIN_VALID_FAULT_Z="${MIN_VALID_FAULT_Z:-0.50}"
MAX_VALID_FAULT_ABS_VZ="${MAX_VALID_FAULT_ABS_VZ:-0.25}"
MAX_TRIAL_ATTEMPTS="${MAX_TRIAL_ATTEMPTS:-3}"

CEM_CONFIG="${CEM_CONFIG:-configs/allocator_weights/cem_tuned_boundary.json}"

OUTPUT_ROOT="$PROJECT_DIR/results/final/pinv_baseline/seeded_eta0p496/randomized_supervisor/$RUN_ID"
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

mkdir -p "$OUTPUT_ROOT"

python - "$SCHEDULE" "$ETA" "$REPS_PER_MOTOR" \
    "$BASE_SEED" "$SCHEDULE_SEED" "$RUN_ID" <<'PY'
import csv
import random
import sys
from pathlib import Path

schedule_path = Path(sys.argv[1])
eta = float(sys.argv[2])
reps_per_motor = int(sys.argv[3])
base_seed = int(sys.argv[4])
schedule_seed = int(sys.argv[5])
run_id = sys.argv[6]

if reps_per_motor <= 0:
    raise SystemExit("[FAIL] REPS_PER_MOTOR must be positive.")

eta_code = int(round(eta * 10000))

schedule = [
    motor
    for motor in (1, 2, 3, 4)
    for _ in range(reps_per_motor)
]

random.Random(schedule_seed).shuffle(schedule)

within_motor = {
    1: 0,
    2: 0,
    3: 0,
    4: 0,
}

rows = []

for sequence_index, motor in enumerate(
    schedule,
    start=1,
):
    within_motor[motor] += 1
    repetition = within_motor[motor]

    trial_seed = (
        base_seed
        + motor * 10_000_000
        + eta_code * 1000
        + repetition
    )

    selected_policy = (
        "pinv_bounded_wls"
        if motor == 2
        else "cem_tuned_qplite"
    )

    eta_tag = str(eta).replace(".", "p")

    tag = (
        f"seededsupervisor_{run_id}_"
        f"m{motor}_eta{eta_tag}_"
        f"seed{trial_seed}"
    )

    expected_csv = (
        f"logs/qp_event_allocator_"
        f"m{motor}_eta{eta_tag}_{tag}.csv"
    )

    rows.append(
        {
            "sequence_index": sequence_index,
            "motor": motor,
            "repetition_within_motor": repetition,
            "trial_seed": trial_seed,
            "selected_policy": selected_policy,
            "tag": tag,
            "expected_csv": expected_csv,
        }
    )

schedule_path.parent.mkdir(
    parents=True,
    exist_ok=True,
)

with schedule_path.open("w", newline="") as file:
    writer = csv.DictWriter(
        file,
        fieldnames=list(rows[0].keys()),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)

print(f"[SAVED] {schedule_path}")
print(
    f"[SCHEDULE] trials={len(rows)} "
    f"reps_per_motor={reps_per_motor} "
    f"schedule_seed={schedule_seed}"
)

for row in rows:
    print(
        f"{row['sequence_index']:03d}: "
        f"M{row['motor']} "
        f"rep={row['repetition_within_motor']} "
        f"seed={row['trial_seed']} "
        f"policy={row['selected_policy']}"
    )
PY

date --iso-8601=seconds \
    > "$OUTPUT_ROOT/start_time.txt"

tail -n +2 "$SCHEDULE" |
while IFS=',' read -r \
    sequence_index \
    motor \
    repetition \
    trial_seed \
    selected_policy \
    tag \
    expected_csv
do
    echo
    echo "============================================================"
    echo "[SUPERVISOR TRIAL]"
    echo "sequence=${sequence_index}"
    echo "motor=M${motor}"
    echo "repetition=${repetition}"
    echo "seed=${trial_seed}"
    echo "selected_policy=${selected_policy}"
    echo "expected_csv=${expected_csv}"
    echo "============================================================"

    if [ -s "$PROJECT_DIR/$expected_csv" ]; then
        echo "[SKIP] Existing trial CSV: $expected_csv"
        continue
    fi

    success=0
    attempt=1

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
            echo "[ERROR] Failed to generate seeded parameters."
            attempt=$((attempt + 1))
            continue
        fi

        eval "$parameter_exports"

        if [ "$TRIAL_SEED" != "$trial_seed" ]; then
            echo "[ERROR] Trial seed mismatch:"
            echo "        schedule=$trial_seed"
            echo "        generated=$TRIAL_SEED"
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
            echo "[ERROR] Crazyflie not ready."
            cleanup_sim
            attempt=$((attempt + 1))
            continue
        fi

        CEM_CONFIG="$CEM_CONFIG" \
        timeout 90s \
        python scripts/fault_triggered_landing_motor_supervisor.py \
            --motor "$motor" \
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
                "$MAX_VALID_FAULT_ABS_VZ"

        trial_status=$?

        cleanup_sim

        if [ "$trial_status" -ne 0 ]; then
            echo "[WARN] Supervisor trial exited with status $trial_status."
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
        echo "       motor=$motor"
        echo "       seed=$trial_seed"
        cleanup_sim
        exit 1
    fi
done

runner_status=$?

date --iso-8601=seconds \
    > "$OUTPUT_ROOT/end_time.txt"

echo "runner_exit_status=$runner_status" \
    | tee "$OUTPUT_ROOT/runner_status.txt"

if [ "$runner_status" -ne 0 ]; then
    exit "$runner_status"
fi

echo "[PASS] Randomized motor-supervisor run completed."
