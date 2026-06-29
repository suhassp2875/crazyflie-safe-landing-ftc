#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

ETA=0.497
REPS=(1 2 3 4 5)

cleanup_sim() {
    pkill -f "sitl_singleagent.sh" 2>/dev/null || true
    pkill -f "cf2" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f "gzserver" 2>/dev/null || true
    pkill -f "gazebo" 2>/dev/null || true
    sleep 3
}

run_one_trial() {
    local motor="$1"
    local rep="$2"
    local eta_tag="${ETA/./p}"
    local tag="m${motor}_eta${eta_tag}_rep${rep}"

    echo "============================================================"
    echo "[QP EVENT ALLOCATOR ETA0.497] motor=${motor}, rep=${rep}"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_qpevent_m${motor}_rep${rep}.log" 2>&1 &
    sleep 8

    cd "$PROJECT_DIR" || exit 1

    python scripts/wait_for_cf.py
    if [ "$?" -ne 0 ]; then
        echo "[ERROR] Crazyflie not ready"
        cleanup_sim
        return 1
    fi

    timeout 90s python scripts/fault_triggered_landing_qp_event_allocator.py \
        --motor "$motor" \
        --eta "$ETA" \
        --tag "$tag"

    cleanup_sim
}

cd "$PROJECT_DIR" || exit 1
mkdir -p logs results/tables results/figures

for motor in 1 2 3 4; do
    for rep in "${REPS[@]}"; do
        run_one_trial "$motor" "$rep"
    done
done

echo "[DONE] State-aware QP event allocator eta=0.497 all-motor sweep completed."
