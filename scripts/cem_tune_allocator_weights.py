#!/usr/bin/env python3

"""
Offline CEM tuner for the tunable residual allocator.

This is the first RL/gain-tuning direction:
- The tuner searches allocator scoring weights.
- It does NOT learn direct motor commands.
- Runtime allocation remains constrained to the empirical residual candidate set.
- The output is a JSON weight config that must be validated in CrazySim.

The objective emphasizes near-boundary safety at eta in [0.496, 0.498],
especially the difficult motor-2 and motor-4 cases.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.controllers.residual_allocator_qp import AllocatorState
from src.controllers.residual_allocator_tunable import (
    AllocatorWeightConfig,
    allocate_residual_tunable,
    load_weight_config,
)


PARAMS = [
    # name, scale, low, high
    ("vertical_threshold", "linear", 0.315, 0.345),
    ("hard_vertical_threshold", "linear", 0.345, 0.360),

    ("vertical_weight", "log", 300.0, 20000.0),
    ("hard_vertical_weight", "log", 1000.0, 50000.0),
    ("drift_weight", "log", 5.0, 300.0),
    ("tilt_weight", "log", 0.005, 1.0),
    ("effort_weight", "log", 1.0e-10, 2.0e-8),
    ("reference_weight", "log", 1.0e-9, 2.0e-6),
    ("support_weight", "log", 1.0e-10, 2.0e-7),
    ("saturation_weight", "log", 1.0, 100.0),

    ("motor2_overboost_penalty", "linear", 0.00, 2.00),
    ("motor14_overboost_penalty", "linear", 0.00, 1.00),
    ("motor3_overboost_penalty", "linear", 0.00, 1.00),
]


def unit_to_param(u: float, scale: str, low: float, high: float) -> float:
    u = float(np.clip(u, 0.0, 1.0))
    if scale == "linear":
        return low + u * (high - low)
    if scale == "log":
        return math.exp(math.log(low) + u * (math.log(high) - math.log(low)))
    raise ValueError(scale)


def vector_to_config(vec: np.ndarray, name: str = "cem_candidate") -> AllocatorWeightConfig:
    values = {"name": name}

    for u, (pname, scale, low, high) in zip(vec, PARAMS):
        values[pname] = unit_to_param(u, scale, low, high)

    # Enforce sensible ordering.
    if values["hard_vertical_threshold"] <= values["vertical_threshold"] + 0.005:
        values["hard_vertical_threshold"] = min(0.360, values["vertical_threshold"] + 0.005)

    return AllocatorWeightConfig(**values)


def config_to_dict(cfg: AllocatorWeightConfig) -> dict:
    return {k: getattr(cfg, k) for k in AllocatorWeightConfig.__dataclass_fields__.keys()}


def make_scenarios(seed: int, samples_per_case: int):
    rng = np.random.default_rng(seed)

    etas = [0.4960, 0.4965, 0.4970, 0.4975, 0.4980]
    motors = [1, 2, 3, 4]

    scenarios = []
    for eta in etas:
        for motor in motors:
            for _ in range(samples_per_case):
                # Fault-time state observed in our experiments is close to hover,
                # but we randomize slightly to avoid tuning to one exact row.
                z = float(rng.normal(0.7136, 0.00025))
                vz = float(rng.normal(-0.0038, 0.00035))
                x = float(rng.normal(0.0, 0.015))
                y = float(rng.normal(0.0, 0.015))
                vx = float(rng.normal(0.0, 0.010))
                vy = float(rng.normal(0.0, 0.010))
                roll = float(rng.normal(0.0, 0.20))
                pitch = float(rng.normal(0.0, 0.20))
                max_motor_pwm = float(rng.normal(32500.0, 500.0))

                state = AllocatorState(
                    z=z,
                    vz=vz,
                    x=x,
                    y=y,
                    vx=vx,
                    vy=vy,
                    roll_deg=roll,
                    pitch_deg=pitch,
                    max_motor_pwm=max_motor_pwm,
                )

                scenarios.append((motor, eta, state))

    return scenarios


def empirical_boundary_bias(motor: int, eta: float) -> float:
    """
    Conservative bias term from CrazySim observations.

    At eta=0.496, the surrogate underpredicted impact speed most strongly
    for motor 2. We include a small bias so the tuner prefers extra margin.
    This is NOT a replacement for validation; it only guides offline search.
    """
    if eta <= 0.4965:
        return {
            1: 0.004,
            2: 0.025,
            3: 0.000,
            4: 0.007,
        }[motor]

    if eta <= 0.4970:
        return {
            1: 0.001,
            2: 0.006,
            3: 0.000,
            4: 0.001,
        }[motor]

    return 0.0


def scenario_loss(motor: int, eta: float, state: AllocatorState, cfg: AllocatorWeightConfig):
    result = allocate_residual_tunable(motor, eta, state, cfg)

    pred_vz = float(result.predicted_vz)
    pred_drift = float(result.predicted_drift)
    pred_tilt = float(result.predicted_tilt)
    residual = [float(v) for v in result.residual]

    corrected_vz = pred_vz + empirical_boundary_bias(motor, eta)

    # Higher weight near the boundary and for the difficult motors.
    eta_weight = {
        0.4960: 2.5,
        0.4965: 2.0,
        0.4970: 1.5,
        0.4975: 1.0,
        0.4980: 0.8,
    }.get(round(eta, 4), 1.0)

    motor_weight = {
        1: 1.2,
        2: 2.0,
        3: 0.8,
        4: 1.4,
    }[motor]

    weight = eta_weight * motor_weight

    # Safety metric is strict at 0.35 m/s. We optimize for margin below 0.345.
    soft_vertical = max(0.0, corrected_vz - 0.330)
    near_limit = max(0.0, corrected_vz - 0.345)
    unsafe = max(0.0, corrected_vz - 0.350)

    drift_violation = max(0.0, pred_drift - 0.65)
    tilt_violation = max(0.0, pred_tilt - 8.0)

    effort = sum(v * v for v in residual)
    max_resid = max(residual)

    loss = 0.0
    loss += weight * 1200.0 * soft_vertical ** 2
    loss += weight * 20000.0 * near_limit ** 2
    loss += weight * 250000.0 * unsafe ** 2
    loss += weight * 200.0 * drift_violation ** 2
    loss += weight * 0.10 * tilt_violation ** 2

    # Keep the learned config from becoming purely "always use maximum residual".
    loss += 1.0e-9 * effort
    loss += 1.0e-5 * max(0.0, max_resid - 13000.0) ** 2

    return loss, result, corrected_vz


def evaluate_config(cfg: AllocatorWeightConfig, scenarios):
    total_loss = 0.0
    rows = []

    for motor, eta, state in scenarios:
        loss, result, corrected_vz = scenario_loss(motor, eta, state, cfg)
        total_loss += loss

        rows.append({
            "motor": motor,
            "eta": eta,
            "candidate": result.candidate_name,
            "r1": result.residual[0],
            "r2": result.residual[1],
            "r3": result.residual[2],
            "r4": result.residual[3],
            "predicted_vz": result.predicted_vz,
            "corrected_vz": corrected_vz,
            "loss": loss,
        })

    return total_loss / max(1, len(scenarios)), pd.DataFrame(rows)


def summarize_candidate_choices(df: pd.DataFrame):
    return (
        df.groupby(["motor", "eta", "candidate", "r1", "r2", "r3", "r4"])
        .agg(
            n=("candidate", "count"),
            mean_predicted_vz=("predicted_vz", "mean"),
            mean_corrected_vz=("corrected_vz", "mean"),
            mean_loss=("loss", "mean"),
        )
        .reset_index()
        .sort_values(["eta", "motor", "mean_loss"])
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="configs/allocator_weights/qplite_baseline.json")
    parser.add_argument("--out-config", default="configs/allocator_weights/cem_tuned_boundary.json")
    parser.add_argument("--generations", type=int, default=12)
    parser.add_argument("--population", type=int, default=80)
    parser.add_argument("--elite", type=int, default=12)
    parser.add_argument("--samples-per-case", type=int, default=6)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    out_dir = Path("results/rl_tuning")
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_cfg = load_weight_config(args.baseline)
    scenarios = make_scenarios(args.seed, args.samples_per_case)

    baseline_loss, baseline_rows = evaluate_config(baseline_cfg, scenarios)
    baseline_choices = summarize_candidate_choices(baseline_rows)
    baseline_choices.to_csv(out_dir / "cem_baseline_candidate_choices.csv", index=False)

    print("[BASELINE]")
    print(f"loss: {baseline_loss:.6f}")
    print(baseline_choices.to_string(index=False))

    dim = len(PARAMS)
    mean = np.full(dim, 0.5)
    std = np.full(dim, 0.25)

    history = []
    best_loss = float("inf")
    best_vec = None
    best_cfg = None
    best_rows = None

    for gen in range(args.generations):
        population = []

        for _ in range(args.population):
            vec = rng.normal(mean, std)
            vec = np.clip(vec, 0.0, 1.0)

            cfg = vector_to_config(vec, name=f"cem_gen{gen}")
            loss, rows = evaluate_config(cfg, scenarios)

            population.append((loss, vec, cfg, rows))

        population.sort(key=lambda x: x[0])
        elites = population[:args.elite]

        elite_vecs = np.stack([e[1] for e in elites], axis=0)
        mean = elite_vecs.mean(axis=0)
        std = np.maximum(elite_vecs.std(axis=0), 0.03)

        if elites[0][0] < best_loss:
            best_loss = elites[0][0]
            best_vec = elites[0][1].copy()
            best_cfg = elites[0][2]
            best_rows = elites[0][3].copy()

        print(
            f"[GEN {gen:02d}] best={elites[0][0]:.6f}, "
            f"mean_elite={np.mean([e[0] for e in elites]):.6f}, "
            f"global_best={best_loss:.6f}"
        )

        history.append({
            "generation": gen,
            "generation_best_loss": elites[0][0],
            "elite_mean_loss": float(np.mean([e[0] for e in elites])),
            "global_best_loss": best_loss,
        })

    assert best_cfg is not None
    best_cfg.name = "cem_tuned_boundary"

    out_config = Path(args.out_config)
    out_config.parent.mkdir(parents=True, exist_ok=True)
    out_config.write_text(json.dumps(config_to_dict(best_cfg), indent=2))

    history_df = pd.DataFrame(history)
    history_df.to_csv(out_dir / "cem_tuning_history.csv", index=False)

    best_choices = summarize_candidate_choices(best_rows)
    best_choices.to_csv(out_dir / "cem_tuned_candidate_choices.csv", index=False)

    print("\n[TUNED CONFIG]")
    print(json.dumps(config_to_dict(best_cfg), indent=2))

    print("\n[TUNED CANDIDATE CHOICES]")
    print(best_choices.to_string(index=False))

    print(f"\nSaved tuned config: {out_config}")
    print(f"Saved history: {out_dir / 'cem_tuning_history.csv'}")
    print(f"Saved tuned choices: {out_dir / 'cem_tuned_candidate_choices.csv'}")

    plt.figure()
    plt.plot(history_df["generation"], history_df["generation_best_loss"], marker="o", label="generation best")
    plt.plot(history_df["generation"], history_df["global_best_loss"], marker="x", label="global best")
    plt.xlabel("Generation")
    plt.ylabel("CEM objective loss")
    plt.title("CEM allocator-weight tuning")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "cem_tuning_history.png", dpi=200)

    # Compact comparison table: baseline vs tuned.
    compare_rows = []

    for label, cfg in [("baseline", baseline_cfg), ("cem_tuned", best_cfg)]:
        loss, rows = evaluate_config(cfg, scenarios)
        rows = rows.copy()
        rows["config"] = label
        compare_rows.append(rows)

    compare = pd.concat(compare_rows, ignore_index=True)
    compare.to_csv(out_dir / "cem_baseline_vs_tuned_scenario_rows.csv", index=False)

    comp_summary = (
        compare.groupby(["config", "motor", "eta"])
        .agg(
            mean_predicted_vz=("predicted_vz", "mean"),
            mean_corrected_vz=("corrected_vz", "mean"),
            max_corrected_vz=("corrected_vz", "max"),
            mean_loss=("loss", "mean"),
        )
        .reset_index()
        .sort_values(["eta", "motor", "config"])
    )

    comp_summary.to_csv(out_dir / "cem_baseline_vs_tuned_summary.csv", index=False)

    print("\n[BASELINE VS TUNED SUMMARY]")
    print(comp_summary.to_string(index=False))


if __name__ == "__main__":
    main()
