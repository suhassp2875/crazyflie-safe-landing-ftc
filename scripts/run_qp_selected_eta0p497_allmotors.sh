#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

ETA=0.497
BOOST=0
REPS=(1 2 3 4 5)

cleanup_sim() {
    pkill -f "sitl_singleagent.sh" 2>/dev/null || true
    pkill -f "cf2" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f "gzserver" 2>/dev/null || true
    pkill -f "gazebo" 2>/dev/null || true
    sleep 3
}

select_residual() {
    local motor="$1"

    python - "$motor" "$ETA" << 'PY'
import sys
from src.controllers.residual_allocator_qp import AllocatorState, allocate_residual_qp

motor = int(sys.argv[1])
eta = float(sys.argv[2])

# Fault is triggered after nominal hover, so this is the event-time nominal state.
state = AllocatorState(z=0.70, vz=0.0, x=0.0, y=0.0, vx=0.0, vy=0.0)

res = allocate_residual_qp(motor, eta, state)
print(res.candidate_name, *res.residual)
PY
}

run_one_trial() {
    local motor="$1"
    local rep="$2"
    local eta_tag="${ETA/./p}"

    read -r candidate r1 r2 r3 r4 <<< "$(select_residual "$motor")"

    echo "============================================================"
    echo "[QP-SELECTED ETA0.497] motor=${motor}, candidate=${candidate}, rep=${rep}, r=[$r1,$r2,$r3,$r4]"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_qp_m${motor}_${candidate}_rep${rep}.log" 2>&1 &
    sleep 8

    cd "$PROJECT_DIR" || exit 1

    python scripts/wait_for_cf.py
    if [ "$?" -ne 0 ]; then
        echo "[ERROR] Crazyflie not ready"
        cleanup_sim
        return 1
    fi

    timeout 90s python scripts/fault_triggered_landing_motorloss_ftcboost.py \
        --motor "$motor" \
        --eta "$ETA" \
        --boost "$BOOST" \
        --r1 "$r1" \
        --r2 "$r2" \
        --r3 "$r3" \
        --r4 "$r4"

    local status=$?

    local src="$PROJECT_DIR/logs/motorloss_ftcboost_m${motor}_eta${eta_tag}_b${BOOST}_r${r1}_${r2}_${r3}_${r4}.csv"
    local dst="$PROJECT_DIR/logs/motorloss_ftcboost_m${motor}_eta${eta_tag}_b${BOOST}_r${r1}_${r2}_${r3}_${r4}_${candidate}_qpselected_rep${rep}.csv"

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

for motor in 1 2 3 4; do
    for rep in "${REPS[@]}"; do
        run_one_trial "$motor" "$rep"
    done
done

echo "[DONE] QP-selected residual eta=0.497 all-motor sweep completed."
