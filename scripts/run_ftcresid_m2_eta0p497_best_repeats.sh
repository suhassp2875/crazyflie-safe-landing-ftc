#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

MOTOR=2
ETA=0.497
BOOST=0
REPS=(1 2 3)

# name r1 r2 r3 r4
PATTERNS=(
  "r1r3_light_r4_heavy 2000 0 2000 12000"
  "r4only_10000 0 0 0 10000"
  "r4dom_5000_11000_5000 5000 0 5000 11000"
  "r3_light_r4_heavy 0 0 2000 12000"
  "r4dom_3000_9000_3000 3000 0 3000 9000"
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
    local name="$1"
    local r1="$2"
    local r2="$3"
    local r3="$4"
    local r4="$5"
    local rep="$6"

    local eta_tag="${ETA/./p}"

    echo "============================================================"
    echo "[M2 ETA0.497 ASYM BEST REPEAT] pattern=${name}, rep=${rep}, r=[$r1,$r2,$r3,$r4]"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_m2_eta${eta_tag}_${name}_rep${rep}.log" 2>&1 &
    sleep 8

    cd "$PROJECT_DIR" || exit 1

    python scripts/wait_for_cf.py
    if [ "$?" -ne 0 ]; then
        echo "[ERROR] Crazyflie not ready"
        cleanup_sim
        return 1
    fi

    timeout 80s python scripts/fault_triggered_landing_motorloss_ftcboost.py \
        --motor "$MOTOR" \
        --eta "$ETA" \
        --boost "$BOOST" \
        --r1 "$r1" \
        --r2 "$r2" \
        --r3 "$r3" \
        --r4 "$r4"

    local status=$?

    local src="$PROJECT_DIR/logs/motorloss_ftcboost_m${MOTOR}_eta${eta_tag}_b${BOOST}_r${r1}_${r2}_${r3}_${r4}.csv"
    local dst="$PROJECT_DIR/logs/motorloss_ftcboost_m${MOTOR}_eta${eta_tag}_b${BOOST}_r${r1}_${r2}_${r3}_${r4}_${name}_repeat_rep${rep}.csv"

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

for item in "${PATTERNS[@]}"; do
    read -r name r1 r2 r3 r4 <<< "$item"
    for rep in "${REPS[@]}"; do
        run_one_trial "$name" "$r1" "$r2" "$r3" "$r4" "$rep"
    done
done

echo "[DONE] Motor 2 eta=0.497 asymmetric best-pattern repeats completed."
