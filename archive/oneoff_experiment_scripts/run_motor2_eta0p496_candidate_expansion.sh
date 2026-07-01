#!/usr/bin/env bash
set -u

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"
SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"

ETA=0.496
MOTOR=2
REPS=(1 2 3)

# Format:
# name r1 r2 r3 r4
CANDIDATES=(
  "m4only_11000 0 0 0 11000"
  "m4only_12000 0 0 0 12000"
  "m4only_13000 0 0 0 13000"
  "m4only_14000 0 0 0 14000"

  "sym_1000_12000 1000 0 1000 12000"
  "sym_2000_12000 2000 0 2000 12000"
  "sym_3000_12000 3000 0 3000 12000"
  "sym_4000_12000 4000 0 4000 12000"

  "sym_1000_13000 1000 0 1000 13000"
  "sym_2000_13000 2000 0 2000 13000"
  "sym_3000_13000 3000 0 3000 13000"

  "asym_r1_3000_r3_1000_m4_12000 3000 0 1000 12000"
  "asym_r1_1000_r3_3000_m4_12000 1000 0 3000 12000"
  "asym_r1_4000_r3_1000_m4_12000 4000 0 1000 12000"
  "asym_r1_1000_r3_4000_m4_12000 1000 0 4000 12000"

  "asym_r1_5000_r3_0_m4_12000 5000 0 0 12000"
  "asym_r1_0_r3_5000_m4_12000 0 0 5000 12000"

  "high_m4_sym_2000_14000 2000 0 2000 14000"
  "high_m4_asym_r1_3000_r3_1000_14000 3000 0 1000 14000"
  "high_m4_asym_r1_1000_r3_3000_14000 1000 0 3000 14000"
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
    local tag="m2expand_${name}_rep${rep}"

    echo "============================================================"
    echo "[M2 ETA0.496 CANDIDATE EXPANSION] ${name}, rep=${rep}"
    echo "r=[${r1}, ${r2}, ${r3}, ${r4}]"
    echo "============================================================"

    cleanup_sim

    cd "$CF_FW_DIR" || exit 1
    bash "$SIM_LAUNCH" -m crazyflie -x 0 -y 0 > "$PROJECT_DIR/logs/sim_m2expand_${name}_rep${rep}.log" 2>&1 &
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
        --manual-name "$name" \
        --r1 "$r1" \
        --r2 "$r2" \
        --r3 "$r3" \
        --r4 "$r4"

    cleanup_sim
}

cd "$PROJECT_DIR" || exit 1
mkdir -p logs results/tables results/figures

for cand in "${CANDIDATES[@]}"; do
    read -r name r1 r2 r3 r4 <<< "$cand"

    for rep in "${REPS[@]}"; do
        run_one_trial "$name" "$r1" "$r2" "$r3" "$r4" "$rep"
    done
done

echo "[DONE] Motor-2 eta=0.496 candidate expansion completed."
