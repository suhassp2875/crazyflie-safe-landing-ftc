#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

MOTORS=(1 2 3 4)
ETAS=(0.52 0.50 0.45)

cleanup_sim() {
    echo "[CLEANUP] Killing old CrazySim/Gazebo processes..."
    pkill -f "sitl_singleagent.sh" 2>/dev/null || true
    pkill -f "cf2" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f "gzserver" 2>/dev/null || true
    pkill -f "gazebo" 2>/dev/null || true
    sleep 3
}

run_one_trial() {
    local motor="$1"
    local eta="$2"
    local tag="pwm_m${motor}_eta${eta/./p}"

    echo "============================================================"
    echo "[PWM TRIAL] motor=${motor}, eta=${eta}, tag=${tag}"
    echo "============================================================"

    cleanup_sim

    echo "[SIM] Launching fresh CrazySim..."
    cd "$CF_FW_DIR" || exit 1

    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_${tag}.log" 2>&1 &
    sleep 8

    cd "$PROJECT_DIR" || exit 1

    echo "[WAIT] Waiting for Crazyflie link..."
    python scripts/wait_for_cf.py
    if [ "$?" -ne 0 ]; then
        echo "[ERROR] Crazyflie not ready for ${tag}"
        cleanup_sim
        return 1
    fi

    echo "[RUN] Starting PWM experiment..."
    timeout 70s python scripts/fault_triggered_landing_motorloss_param_pwm.py --motor "$motor" --eta "$eta" --tag "$tag"
    local run_status=$?

    if [ "$run_status" -ne 0 ]; then
        echo "[ERROR] PWM experiment failed or timed out for ${tag}. status=${run_status}"
    else
        echo "[OK] PWM experiment completed for ${tag}"
    fi

    cleanup_sim
    return "$run_status"
}

cd "$PROJECT_DIR" || exit 1
mkdir -p logs results

for m in "${MOTORS[@]}"; do
    for eta in "${ETAS[@]}"; do
        run_one_trial "$m" "$eta"
    done
done

echo "[DONE] PWM sweep completed."
