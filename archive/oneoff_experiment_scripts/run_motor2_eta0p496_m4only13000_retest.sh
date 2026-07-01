#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

ETA=0.496
MOTOR=2
NAME="m4only_13000_retest"
R1=0
R2=0
R3=0
R4=13000
REPS=(1 2 3 4 5 6 7 8 9 10)

cleanup_sim() {
    pkill -f "sitl_singleagent.sh" 2>/dev/null || true
    pkill -f "cf2" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f "gzserver" 2>/dev/null || true
    pkill -f "gazebo" 2>/dev/null || true
    sleep 3
}

run_one_trial() {
    local rep="$1"
    local tag="m2_m4only13000_retest_rep${rep}"

    echo "============================================================"
    echo "[M2 ETA0.496 M4ONLY_13000 RETEST] rep=${rep}"
    echo "r=[${R1}, ${R2}, ${R3}, ${R4}]"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_m2_m4only13000_retest_rep${rep}.log" 2>&1 &
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
        --manual-residual \
        --manual-name "$NAME" \
        --r1 "$R1" \
        --r2 "$R2" \
        --r3 "$R3" \
        --r4 "$R4"

    cleanup_sim
}

cd "$PROJECT_DIR" || exit 1
mkdir -p logs results/tables results/figures

for rep in "${REPS[@]}"; do
    run_one_trial "$rep"
done

echo "[DONE] Motor-2 eta=0.496 m4only_13000 retest completed."
