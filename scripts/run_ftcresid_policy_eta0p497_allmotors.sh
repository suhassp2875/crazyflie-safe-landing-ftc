#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

ETA=0.497
BOOST=0
REPS=(1 2 3 4 5)

# Format:
# motor policy_name r1 r2 r3 r4
#
# Policy map:
# m1 fault -> opposite m3 residual
# m2 fault -> best empirical asymmetric residual
# m3 fault -> opposite m1 residual, tuned to 12000
# m4 fault -> opposite m2 residual
POLICIES=(
  "1 m1_opp_m3_10000 0 0 10000 0"
  "2 m2_best_2000_0_2000_12000 2000 0 2000 12000"
  "3 m3_opp_m1_12000 12000 0 0 0"
  "4 m4_opp_m2_10000 0 10000 0 0"
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
    local motor="$1"
    local policy_name="$2"
    local r1="$3"
    local r2="$4"
    local r3="$5"
    local r4="$6"
    local rep="$7"

    local eta_tag="${ETA/./p}"

    echo "============================================================"
    echo "[POLICY MAP ETA0.497] motor=${motor}, policy=${policy_name}, rep=${rep}, r=[$r1,$r2,$r3,$r4]"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_policy_m${motor}_eta${eta_tag}_${policy_name}_rep${rep}.log" 2>&1 &
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
    local dst="$PROJECT_DIR/logs/motorloss_ftcboost_m${motor}_eta${eta_tag}_b${BOOST}_r${r1}_${r2}_${r3}_${r4}_${policy_name}_policy_rep${rep}.csv"

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
    read -r motor policy_name r1 r2 r3 r4 <<< "$item"
    for rep in "${REPS[@]}"; do
        run_one_trial "$motor" "$policy_name" "$r1" "$r2" "$r3" "$r4" "$rep"
    done
done

echo "[DONE] Event-triggered policy-map eta=0.497 all-motor sweep completed."
