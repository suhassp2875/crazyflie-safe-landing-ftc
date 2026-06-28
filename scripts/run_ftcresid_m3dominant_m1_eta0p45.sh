#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

MOTOR=1
ETA=0.45

# name:r1:r2:r3:r4
# Refine around the two best patterns:
# [0,0,16000,0] and [0,8000,18000,8000]
PATTERNS=(
  "r3only_12000:0:0:12000:0"
  "r3only_16000:0:0:16000:0"
  "r3only_18000:0:0:18000:0"
  "r3only_20000:0:0:20000:0"
  "r3only_22000:0:0:22000:0"
  "r3only_24000:0:0:24000:0"

  "m3dom_2000_18000:0:2000:18000:2000"
  "m3dom_4000_18000:0:4000:18000:4000"
  "m3dom_6000_18000:0:6000:18000:6000"
  "m3dom_8000_18000:0:8000:18000:8000"

  "m3dom_2000_22000:0:2000:22000:2000"
  "m3dom_4000_22000:0:4000:22000:4000"
  "m3dom_6000_22000:0:6000:22000:6000"
  "m3dom_8000_22000:0:8000:22000:8000"
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

    echo "============================================================"
    echo "[M3-DOMINANT RESIDUAL] ${name}: r=[$r1,$r2,$r3,$r4]"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_m3dom_${name}.log" 2>&1 &
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
        --boost 0 \
        --r1 "$r1" \
        --r2 "$r2" \
        --r3 "$r3" \
        --r4 "$r4"

    local status=$?

    cleanup_sim
    return "$status"
}

cd "$PROJECT_DIR" || exit 1
mkdir -p logs results/tables results/figures

for pattern in "${PATTERNS[@]}"; do
    IFS=":" read -r name r1 r2 r3 r4 <<< "$pattern"
    run_one_trial "$name" "$r1" "$r2" "$r3" "$r4"
done

echo "[DONE] M3-dominant residual sweep completed."
