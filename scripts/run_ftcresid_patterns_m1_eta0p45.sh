#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

MOTOR=1
ETA=0.45

# Format:
# name:r1:r2:r3:r4
PATTERNS=(
  "m2only_16000:0:16000:0:0"
  "m3only_16000:0:0:16000:0"
  "m4only_16000:0:0:0:16000"

  "m2m3_12000:0:12000:12000:0"
  "m2m4_12000:0:12000:0:12000"
  "m3m4_12000:0:0:12000:12000"

  "opposite_heavy:0:6000:16000:6000"
  "opposite_max:0:3000:18000:3000"
  "m3_dominant:0:8000:18000:8000"

  "equal_12000:0:12000:12000:12000"
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
    echo "[FTC RESIDUAL PATTERN] ${name}: r=[$r1,$r2,$r3,$r4]"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_ftcresid_${name}.log" 2>&1 &
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

echo "[DONE] FTC residual pattern sweep completed."
