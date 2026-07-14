#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

MOTORS="${MOTORS:-1 4}"
ETA="${ETA:-0.496}"
RESIDUALS="${RESIDUALS:-8000 9000 10000 11000 12000 13000 14000}"
REPS="${REPS:-30}"
BASE_SEED="${BASE_SEED:-70000}"

POST_FAULT_MODE="${POST_FAULT_MODE:-adaptive_ramp_v1}"
EVAL_DURATION="${EVAL_DURATION:-18.0}"
MAX_BRAKE_DURATION="${MAX_BRAKE_DURATION:-6.0}"
LANDING_DESCENT_RATE="${LANDING_DESCENT_RATE:-0.08}"

MAX_TRIAL_ATTEMPTS="${MAX_TRIAL_ATTEMPTS:-3}"
MIN_VALID_FAULT_Z="${MIN_VALID_FAULT_Z:-0.50}"
MAX_VALID_FAULT_ABS_VZ="${MAX_VALID_FAULT_ABS_VZ:-0.25}"


cleanup_sim() {
    pkill -f "sitl_singleagent.sh" 2>/dev/null || true
    pkill -f "cf2" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f "gzserver" 2>/dev/null || true
    pkill -f "gazebo" 2>/dev/null || true
    sleep 3
}


residual_vector() {
    local motor="$1"
    local residual="$2"

    case "$motor" in
        1)
            echo "0 0 $residual 0"
            ;;
        4)
            echo "0 $residual 0 0"
            ;;
        *)
            echo "[ERROR] Unsupported motor: $motor" >&2
            return 1
            ;;
    esac
}


run_one_trial() {
    local motor="$1"
    local residual="$2"
    local rep="$3"

    local eta_tag="${ETA/./p}"
    local seed=$(( BASE_SEED + motor * 10000000 + residual * 100 + rep ))

    read -r r1 r2 r3 r4 <<< "$(residual_vector "$motor" "$residual")"

    local tag="seededdose_m${motor}_eta${eta_tag}_r${residual}_seed${seed}"
    local expected_csv="$PROJECT_DIR/logs/qp_event_allocator_m${motor}_eta${eta_tag}_${tag}.csv"

    if [ -f "$expected_csv" ]; then
        echo "[SKIP] Existing CSV: $expected_csv"
        return 0
    fi

    cd "$PROJECT_DIR" || exit 1

    eval "$(python scripts/seeded_trial_params.py --seed "$seed" --shell)"

    echo "============================================================"
    echo "[SEEDED DOSE RESPONSE]"
    echo "motor=${motor}"
    echo "eta=${ETA}"
    echo "residual=${residual}"
    echo "rep=${rep}"
    echo "seed=${seed}"
    echo "vector=[$r1,$r2,$r3,$r4]"
    echo "spawn=(${SPAWN_X}, ${SPAWN_Y})"
    echo "yaw=${SPAWN_YAW_DEG}"
    echo "hover_z=${HOVER_Z}"
    echo "fault_time=${FAULT_TIME}"
    echo "expected_csv=${expected_csv}"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1

    bash "$SIM_LAUNCH" \
        -m crazyflie \
        -x "$SPAWN_X" \
        -y "$SPAWN_Y" \
        > "$PROJECT_DIR/logs/sim_seededdose_m${motor}_eta${eta_tag}_r${residual}_seed${seed}.log" \
        2>&1 &

    sleep 8

    cd "$PROJECT_DIR" || exit 1

    python scripts/wait_for_cf.py
    if [ "$?" -ne 0 ]; then
        echo "[ERROR] Crazyflie not ready."
        cleanup_sim
        return 1
    fi

    timeout 90s python scripts/fault_triggered_landing_qp_event_allocator.py \
        --motor "$motor" \
        --eta "$ETA" \
        --tag "$tag" \
        --protocol-id "seeded_dose_v1" \
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
        --max-valid-fault-abs-vz "$MAX_VALID_FAULT_ABS_VZ" \
        --manual-residual \
        --manual-name "dose_r${residual}" \
        --r1 "$r1" \
        --r2 "$r2" \
        --r3 "$r3" \
        --r4 "$r4"

    local rc=$?

    cleanup_sim

    return "$rc"
}


cd "$PROJECT_DIR" || exit 1
mkdir -p logs results/tables results/figures

for motor in $MOTORS; do
    for residual in $RESIDUALS; do
        rep=1

        while [ "$rep" -le "$REPS" ]; do
            attempt=1
            success=0

            while [ "$attempt" -le "$MAX_TRIAL_ATTEMPTS" ]; do
                echo "[ATTEMPT] motor=${motor}, residual=${residual}, rep=${rep}, attempt=${attempt}"

                if run_one_trial "$motor" "$residual" "$rep"; then
                    success=1
                    break
                fi

                echo "[WARN] Trial failed. Retrying after simulator cleanup."
                cleanup_sim
                attempt=$((attempt + 1))
            done

            if [ "$success" -ne 1 ]; then
                echo "[ERROR] Trial failed after ${MAX_TRIAL_ATTEMPTS} attempts."
                echo "motor=${motor}, residual=${residual}, rep=${rep}"
                exit 1
            fi

            rep=$((rep + 1))
        done
    done
done

echo "[DONE] Seeded residual dose-response sweep completed."
