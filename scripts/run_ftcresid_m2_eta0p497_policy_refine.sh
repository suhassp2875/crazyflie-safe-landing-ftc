#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

MOTOR=2
ETA=0.497
BOOST=0
REPS=(1 2 3 4 5)

# Format:
# policy_name r1 r2 r3 r4
#
# Motor 2 is faulted, so r2=0.
# These are around the current 4/5-safe policy [2000,0,2000,12000].
POLICIES=(
  "current_2000_0_2000_12000 2000 0 2000 12000"
  "m4only_12000 0 0 0 12000"
  "light_1000_0_1000_13000 1000 0 1000 13000"
  "balanced_2000_0_2000_13000 2000 0 2000 13000"
  "mid_3000_0_3000_12000 3000 0 3000 12000"
  "mid_3000_0_3000_13000 3000 0 3000 13000"
)

cleanup_sim() {
    pkill -f "sitl_singleagent.sh" 2>/dev/null || true
    pkill -f "cf2" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f "gzserver" 2>/dev/null || true
    pkill -f "gazebo" 2>/dev/null || true
    sleep 3
}

run_one_trial() {
    local policy="$1"
    local r1="$2"
    local r2="$3"
    local r3="$4"
    local r4="$5"
    local rep="$6"

    local eta_tag="${ETA/./p}"

    echo "============================================================"
    echo "[M2 POLICY REFINE ETA0.497] policy=${policy}, rep=${rep}, r=[$r1,$r2,$r3,$r4]"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_m2_policy_${policy}_rep${rep}.log" 2>&1 &
    sleep 8

    cd "$PROJECT_DIR" || exit 1

    python scripts/wait_for_cf.py
    if [ "$?" -ne 0 ]; then
        echo "[ERROR] Crazyflie not ready"
        cleanup_sim
        return 1
    fi

    timeout 90s python scripts/fault_triggered_landing_motorloss_ftcboost.py \
        --motor "$MOTOR" \
        --eta "$ETA" \
        --boost "$BOOST" \
        --r1 "$r1" \
        --r2 "$r2" \
        --r3 "$r3" \
        --r4 "$r4"

    local status=$?

    local src="$PROJECT_DIR/logs/motorloss_ftcboost_m${MOTOR}_eta${eta_tag}_b${BOOST}_r${r1}_${r2}_${r3}_${r4}.csv"
    local dst="$PROJECT_DIR/logs/motorloss_ftcboost_m${MOTOR}_eta${eta_tag}_b${BOOST}_r${r1}_${r2}_${r3}_${r4}_${policy}_policy_refine_rep${rep}.csv"

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

for item in "${POLICIES[@]}"; do
    read -r policy r1 r2 r3 r4 <<< "$item"
    for rep in "${REPS[@]}"; do
        run_one_trial "$policy" "$r1" "$r2" "$r3" "$r4" "$rep"
    done
done

echo "[DONE] Motor 2 eta=0.497 policy refinement sweep completed."
