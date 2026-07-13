#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

# Defaults can be overridden from the command line:
#   CONTROLLERS="qplite" MOTORS="2" ETAS="0.48 0.49 0.50" REPS=12 ./scripts/run_seeded_boundary_coarse.sh
CONTROLLERS="${CONTROLLERS:-qplite cem}"
MOTORS="${MOTORS:-1 3 4}"
ETAS="${ETAS:-0.492 0.493 0.494 0.495 0.496 0.497 0.498}"
REPS="${REPS:-30}"
BASE_SEED="${BASE_SEED:-20000}"

CEM_CONFIG="${CEM_CONFIG:-configs/allocator_weights/cem_tuned_boundary.json}"
POST_FAULT_MODE="${POST_FAULT_MODE:-adaptive_ramp_v1}"
EVAL_DURATION="${EVAL_DURATION:-18.0}"
MAX_BRAKE_DURATION="${MAX_BRAKE_DURATION:-6.0}"
LANDING_DESCENT_RATE="${LANDING_DESCENT_RATE:-0.08}"
COMMON_SEEDS="${COMMON_SEEDS:-0}"
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

controller_offset() {
    local controller="$1"
    if [ "$controller" = "qplite" ]; then
        echo 0
    elif [ "$controller" = "cem" ]; then
        echo 5000000
    else
        echo 9000000
    fi
}

run_one_trial() {
    local controller="$1"
    local motor="$2"
    local eta="$3"
    local eta_index="$4"
    local rep="$5"

    local offset
    if [ "$COMMON_SEEDS" = "1" ]; then
        offset=0
    else
        offset=$(controller_offset "$controller")
    fi

    # Stable eta-based seed. This avoids changing seeds when ETAS order changes
    # across resumed/chunked runs.
    local eta_code
    eta_code=$(python - <<PY2
eta = float("$eta")
print(int(round(eta * 10000)))
PY2
)
    local seed=$(( BASE_SEED + offset + motor * 10000000 + eta_code * 1000 + rep ))
    local eta_tag="${eta/./p}"
    local tag="seededfine_${controller}_m${motor}_eta${eta_tag}_seed${seed}"
    local expected_csv="$PROJECT_DIR/logs/qp_event_allocator_m${motor}_eta${eta_tag}_${tag}.csv"

    if [ -f "$expected_csv" ]; then
        echo "[SKIP] Existing CSV: $expected_csv"
        return 0
    fi

    cd "$PROJECT_DIR" || exit 1
    eval "$(python scripts/seeded_trial_params.py --seed "$seed" --shell)"

    echo "============================================================"
    echo "[SEEDED FINE] controller=${controller}, motor=${motor}, eta=${eta}, rep=${rep}, seed=${seed}"
    echo "protocol=${PROTOCOL_ID}"
    echo "spawn=(${SPAWN_X}, ${SPAWN_Y}), yaw=${SPAWN_YAW_DEG}"
    echo "hover_z=${HOVER_Z}, fault_time=${FAULT_TIME}"
    echo "expected_csv=${expected_csv}"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x "$SPAWN_X" -y "$SPAWN_Y" > "$PROJECT_DIR/logs/sim_seededfine_${controller}_m${motor}_eta${eta_tag}_seed${seed}.log" 2>&1 &
    sleep 8

    cd "$PROJECT_DIR" || exit 1

    python scripts/wait_for_cf.py
    if [ "$?" -ne 0 ]; then
        echo "[ERROR] Crazyflie not ready"
        cleanup_sim
        return 1
    fi

    if [ "$controller" = "qplite" ]; then
        timeout 90s python scripts/fault_triggered_landing_qp_event_allocator.py \
            --motor "$motor" \
            --eta "$eta" \
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
            --max-valid-fault-abs-vz "$MAX_VALID_FAULT_ABS_VZ"
    elif [ "$controller" = "cem" ]; then
        timeout 90s python scripts/fault_triggered_landing_qp_event_allocator.py \
            --motor "$motor" \
            --eta "$eta" \
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
            --max-valid-fault-abs-vz "$MAX_VALID_FAULT_ABS_VZ" \
            --weight-config "$CEM_CONFIG"
    else
        echo "[ERROR] Unknown controller: $controller"
        cleanup_sim
        return 1
    fi

    cleanup_sim
}

cd "$PROJECT_DIR" || exit 1
mkdir -p logs results/tables results/figures

eta_index=0
for eta in $ETAS; do
    eta_index=$((eta_index + 1))

    for controller in $CONTROLLERS; do
        for motor in $MOTORS; do
            rep=1
            while [ "$rep" -le "$REPS" ]; do
                attempt=1
                success=0

                while [ "$attempt" -le "$MAX_TRIAL_ATTEMPTS" ]; do
                    echo "[ATTEMPT] controller=${controller}, motor=${motor}, eta=${eta}, rep=${rep}, attempt=${attempt}"

                    if run_one_trial "$controller" "$motor" "$eta" "$eta_index" "$rep"; then
                        success=1
                        break
                    fi

                    echo "[WARN] Trial attempt failed. Cleaning simulator before retry."
                    cleanup_sim
                    attempt=$((attempt + 1))
                done

                if [ "$success" -ne 1 ]; then
                    echo "[ERROR] Trial failed after ${MAX_TRIAL_ATTEMPTS} attempts:"
                    echo "        controller=${controller}, motor=${motor}, eta=${eta}, rep=${rep}"
                    exit 1
                fi

                rep=$((rep + 1))
            done
        done
    done
done

echo "[DONE] Seeded fine boundary sweep completed."

cd "$PROJECT_DIR" || exit 1

python scripts/summarize_seeded_boundary_fine.py

git status
