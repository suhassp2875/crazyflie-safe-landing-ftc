#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

MOTORS=(1 2 3 4)
ETA=0.497
BOOST=10000
REPS=(1 2 3)

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

    echo "============================================================"
    echo "[FTCBOOST ETA0.497] motor=${motor}, eta=${ETA}, boost=${BOOST}, rep=${rep}"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_eta${eta_tag}_m${motor}_b${BOOST}_rep${rep}.log" 2>&1 &
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
        --boost "$BOOST" \
        --r1 0 \
        --r2 0 \
        --r3 0 \
        --r4 0

    local status=$?

    local src="$PROJECT_DIR/logs/motorloss_ftcboost_m${motor}_eta${eta_tag}_b${BOOST}_r0_0_0_0.csv"
    local dst="$PROJECT_DIR/logs/motorloss_ftcboost_m${motor}_eta${eta_tag}_b${BOOST}_r0_0_0_0_rep${rep}.csv"

    if [ -f "$src" ]; then
        mv "$src" "$dst"
        echo "[RENAMED] $dst"
    else
        echo "[WARN] Expected log not found: $src"
    fi

    cleanup_sim
    return "$status"
}

cd "$PROJECT_DIR" || exit 1
mkdir -p logs results/tables results/figures

for motor in "${MOTORS[@]}"; do
    for rep in "${REPS[@]}"; do
        run_one_trial "$motor" "$rep"
    done
done

echo "[DONE] eta=0.497 all-motor repeat sweep completed."
