#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$HOME/crazysim_ws/safe-landing-ftc"
CF_FW_DIR="$HOME/crazysim_ws/CrazySim/crazyflie-firmware"

SIM_LAUNCH="tools/crazyflie-simulation/simulator_files/gazebo/launch/sitl_singleagent.sh"
LANDING_RUNNER="$PROJECT_DIR/scripts/fault_triggered_landing_qp_event_allocator.py"

SEED=45680003
ETA=0.496
GUARDS="0.16 0.18 0.20"

RESULT_ROOT="$PROJECT_DIR/results/final/pinv_baseline/seeded_eta0p496/m4_guard/catastrophic_seed_pilot"

cleanup_sim() {
    pkill -f "sitl_singleagent.sh" 2>/dev/null || true
    pkill -f "cf2" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f "gzserver" 2>/dev/null || true
    pkill -f "gazebo" 2>/dev/null || true
    sleep 3
}

trap cleanup_sim EXIT

mkdir -p \
    "$PROJECT_DIR/logs" \
    "$RESULT_ROOT"

cd "$PROJECT_DIR"

eval "$(
    python scripts/seeded_trial_params.py \
        --seed "$SEED" \
        --shell
)"

if [ "$TRIAL_SEED" != "$SEED" ]; then
    echo "[FAIL] Seed mismatch: $TRIAL_SEED != $SEED"
    exit 1
fi

echo "guard,trial_seed,expected_csv" \
    > "$RESULT_ROOT/manifest.csv"

for GUARD in $GUARDS; do
    GUARD_TAG="${GUARD/./p}"
    TAG="m4_guard_seed${SEED}_g${GUARD_TAG}"

    EXPECTED_CSV="$PROJECT_DIR/logs/qp_event_allocator_m4_eta0p496_${TAG}.csv"

    echo "${GUARD},${SEED},${EXPECTED_CSV#$PROJECT_DIR/}" \
        >> "$RESULT_ROOT/manifest.csv"

    echo
    echo "============================================================"
    echo "[M4 GUARDED CATASTROPHIC-SEED PILOT]"
    echo "seed=$SEED"
    echo "guard=$GUARD"
    echo "initial_r2=14000"
    echo "fallback_r2=12000"
    echo "expected_csv=$EXPECTED_CSV"
    echo "============================================================"

    if [ -s "$EXPECTED_CSV" ]; then
        echo "[SKIP] Existing CSV: $EXPECTED_CSV"
        continue
    fi

    cleanup_sim

    cd "$CF_FW_DIR"

    bash "$SIM_LAUNCH" \
        -m crazyflie \
        -x "$SPAWN_X" \
        -y "$SPAWN_Y" \
        > "$PROJECT_DIR/logs/sim_${TAG}.log" \
        2>&1 &

    sleep 8

    cd "$PROJECT_DIR"

    python scripts/wait_for_cf.py

    set +e

    timeout 90s \
    python "$LANDING_RUNNER" \
        --controller qplite \
        --motor 4 \
        --eta "$ETA" \
        --tag "$TAG" \
        --protocol-id "$PROTOCOL_ID" \
        --trial-seed "$TRIAL_SEED" \
        --spawn-x "$SPAWN_X" \
        --spawn-y "$SPAWN_Y" \
        --spawn-yaw-deg "$SPAWN_YAW_DEG" \
        --fault-time "$FAULT_TIME" \
        --hover-z "$HOVER_Z" \
        --post-fault-mode adaptive_ramp_v1 \
        --eval-duration 18.0 \
        --max-brake-duration 6.0 \
        --landing-descent-rate 0.08 \
        --min-valid-fault-z 0.50 \
        --max-valid-fault-abs-vz 0.25 \
        --manual-residual \
        --manual-name \
          guarded_opp_m2_14000_to_12000_v1 \
        --r1 0 \
        --r2 14000 \
        --r3 0 \
        --r4 0 \
        --m4-vz-guard "$GUARD" \
        --m4-guard-fallback-r2 12000 \
        2>&1 \
        | tee "$RESULT_ROOT/guard_${GUARD_TAG}_console.txt"

    RUN_STATUS=${PIPESTATUS[0]}

    set -e

    cleanup_sim

    if [ "$RUN_STATUS" -ne 0 ]; then
        echo "[FAIL] Guard $GUARD exited with $RUN_STATUS"
        exit "$RUN_STATUS"
    fi

    if [ ! -s "$EXPECTED_CSV" ]; then
        echo "[FAIL] Missing expected CSV: $EXPECTED_CSV"
        exit 1
    fi

    echo "[PASS] Guard $GUARD trial completed."
done

echo "pilot_exit_status=0" \
    | tee "$RESULT_ROOT/runner_status.txt"

echo "[PASS] Catastrophic-seed guard pilot complete."
