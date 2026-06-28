#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

MOTORS=(1 2 3 4)
ETA=0.50

# Keep enough values to see threshold and tradeoff.
BOOSTS=(0 3000 4000 5000 6000 7000 8000 10000)

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
    local boost="$2"

    echo "============================================================"
    echo "[FTCBOOST TRIAL] motor=${motor}, eta=${ETA}, boost=${boost}"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_ftcboost_m${motor}_eta0p50_b${boost}.log" 2>&1 &
    sleep 8

    cd "$PROJECT_DIR" || exit 1

    python scripts/wait_for_cf.py
    if [ "$?" -ne 0 ]; then
        echo "[ERROR] Crazyflie not ready"
        cleanup_sim
        return 1
    fi

    timeout 80s python scripts/fault_triggered_landing_motorloss_ftcboost.py \
        --motor "$motor" \
        --eta "$ETA" \
        --boost "$boost"

    local status=$?

    cleanup_sim
    return "$status"
}

cd "$PROJECT_DIR" || exit 1
mkdir -p logs results/tables results/figures

for motor in "${MOTORS[@]}"; do
    for boost in "${BOOSTS[@]}"; do
        run_one_trial "$motor" "$boost"
    done
done

echo "[DONE] FTC boost all-motor eta=0.50 sweep completed."
