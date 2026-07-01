#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

ETA="${ETA:-0.497}"
MOTOR="${MOTOR:-2}"
SEEDS=(1001 1002 1003)

cleanup_sim() {
    pkill -f "sitl_singleagent.sh" 2>/dev/null || true
    pkill -f "cf2" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f "gzserver" 2>/dev/null || true
    pkill -f "gazebo" 2>/dev/null || true
    sleep 3
}

run_one_trial() {
    local seed="$1"
    local eta_tag="${ETA/./p}"
    local tag="seeded_smoke_m${MOTOR}_eta${eta_tag}_seed${seed}"

    cd "$PROJECT_DIR" || exit 1
    eval "$(python scripts/seeded_trial_params.py --seed "$seed" --shell)"

    echo "============================================================"
    echo "[SEEDED SMOKE] motor=${MOTOR}, eta=${ETA}, seed=${seed}"
    echo "protocol=${PROTOCOL_ID}"
    echo "spawn=(${SPAWN_X}, ${SPAWN_Y}), yaw=${SPAWN_YAW_DEG}"
    echo "hover_z=${HOVER_Z}, fault_time=${FAULT_TIME}"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x "$SPAWN_X" -y "$SPAWN_Y" > "$PROJECT_DIR/logs/sim_seeded_smoke_m${MOTOR}_seed${seed}.log" 2>&1 &
    sleep 8

    cd "$PROJECT_DIR" || exit 1

    python scripts/wait_for_cf.py
    if [ "$?" -ne 0 ]; then
        echo "[ERROR] Crazyflie not ready"
        cleanup_sim
        return 1
    fi

    timeout 90s python scripts/fault_triggered_landing_qp_event_allocator.py \
        --motor "$MOTOR" \
        --eta "$ETA" \
        --tag "$tag" \
        --protocol-id "$PROTOCOL_ID" \
        --trial-seed "$TRIAL_SEED" \
        --spawn-x "$SPAWN_X" \
        --spawn-y "$SPAWN_Y" \
        --spawn-yaw-deg "$SPAWN_YAW_DEG" \
        --fault-time "$FAULT_TIME" \
        --hover-z "$HOVER_Z"

    cleanup_sim
}

cd "$PROJECT_DIR" || exit 1
mkdir -p logs results/tables results/figures

for seed in "${SEEDS[@]}"; do
    run_one_trial "$seed"
done

echo "[DONE] Seeded QP event smoke test completed."
