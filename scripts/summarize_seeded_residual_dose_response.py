#!/usr/bin/env python3

from pathlib import Path
import math
import re

import matplotlib.pyplot as plt
import pandas as pd
from statsmodels.stats.proportion import proportion_confint


LOG_DIR = Path("logs")

OUT_TABLE = Path(
    "results/final/tables/"
    "seeded_residual_dose_response.csv"
)
OUT_AGG = Path(
    "results/final/tables/"
    "seeded_residual_dose_response_aggregate.csv"
)
OUT_DIR = Path("results/final/figures")

ETA_TARGET = 0.496
PRODUCTION_BASE_SEED = 70000
EXPECTED_REPS = 30

VERTICAL_SPEED_LIMIT = 0.35
HORIZONTAL_SPEED_LIMIT = 0.25
TILT_LIMIT_DEG = 12.0
ANGULAR_RATE_LIMIT_RADPS = 1.5
DRIFT_LIMIT_M = 0.75

PATTERN = re.compile(
    r"qp_event_allocator_m(?P<motor>\d+)"
    r"_eta(?P<eta>[0-9p]+)"
    r"_seededdose_m\d+"
    r"_eta[0-9p]+"
    r"_r(?P<residual>\d+)"
    r"_seed(?P<seed>\d+)\.csv"
)


def parse_eta(text: str) -> float:
    return float(text.replace("p", "."))


def expected_rep(
    motor: int,
    residual: int,
    seed: int,
) -> int:
    """
    Production runner used:

    seed = BASE_SEED
           + motor * 10000000
           + residual * 100
           + rep
    """
    return (
        seed
        - PRODUCTION_BASE_SEED
        - motor * 10_000_000
        - residual * 100
    )


def first_contact_row(df: pd.DataFrame):
    fault_indices = df.index[
        df["phase"] == "fault_event"
    ].tolist()

    if not fault_indices:
        return None, None, False

    fault_idx = fault_indices[0]
    fault_t = float(df.loc[fault_idx, "t"])

    post_fault = df.loc[fault_idx:]
    contact_indices = post_fault.index[
        post_fault["z"] <= 0.03
    ].tolist()

    if not contact_indices:
        return None, fault_t, False

    return df.loc[contact_indices[0]], fault_t, True


def evaluate_contact(row, found_contact: bool):
    if not found_contact or row is None:
        return {
            "contact_found": False,
            "safe_touchdown": False,
            "vertical_speed_mps": math.nan,
            "horizontal_speed_mps": math.nan,
            "max_tilt_deg": math.nan,
            "angular_rate_radps": math.nan,
            "horizontal_drift_m": math.nan,
        }

    vertical_speed = abs(float(row["vz"]))

    horizontal_speed = math.hypot(
        float(row["vx"]),
        float(row["vy"]),
    )

    max_tilt = max(
        abs(float(row["roll_deg"])),
        abs(float(row["pitch_deg"])),
    )

    angular_rate = math.radians(
        math.sqrt(
            float(row["gyro_x_deg_s"]) ** 2
            + float(row["gyro_y_deg_s"]) ** 2
            + float(row["gyro_z_deg_s"]) ** 2
        )
    )

    drift = math.hypot(
        float(row["x"]),
        float(row["y"]),
    )

    safe = (
        vertical_speed <= VERTICAL_SPEED_LIMIT
        and horizontal_speed <= HORIZONTAL_SPEED_LIMIT
        and max_tilt <= TILT_LIMIT_DEG
        and angular_rate <= ANGULAR_RATE_LIMIT_RADPS
        and drift <= DRIFT_LIMIT_M
    )

    return {
        "contact_found": True,
        "safe_touchdown": bool(safe),
        "vertical_speed_mps": vertical_speed,
        "horizontal_speed_mps": horizontal_speed,
        "max_tilt_deg": max_tilt,
        "angular_rate_radps": angular_rate,
        "horizontal_drift_m": drift,
    }


def main():
    rows = []
    skipped_nonproduction = []
    malformed = []

    paths = sorted(
        LOG_DIR.glob(
            "qp_event_allocator_m*_eta0p496_"
            "seededdose_*.csv"
        )
    )

    print(f"[INFO] Found {len(paths)} dose-response CSV files.")

    for path in paths:
        match = PATTERN.fullmatch(path.name)

        if match is None:
            malformed.append(path.name)
            continue

        motor = int(match.group("motor"))
        eta = parse_eta(match.group("eta"))
        residual = int(match.group("residual"))
        seed = int(match.group("seed"))

        rep = expected_rep(
            motor=motor,
            residual=residual,
            seed=seed,
        )

        # Exclude smoke tests and any unrelated dose runs.
        if not 1 <= rep <= EXPECTED_REPS:
            skipped_nonproduction.append(path.name)
            continue

        if not math.isclose(
            eta,
            ETA_TARGET,
            abs_tol=1e-9,
        ):
            continue

        df = pd.read_csv(path)

        contact, fault_t, found = first_contact_row(df)
        metrics = evaluate_contact(contact, found)

        if found:
            contact_t = float(contact["t"])
            contact_phase = str(contact["phase"])
            contact_z = float(contact["z"])
            fault_to_contact = contact_t - fault_t
        else:
            contact_t = math.nan
            contact_phase = ""
            contact_z = math.nan
            fault_to_contact = math.nan

        # Residual and candidate should be constant after allocation.
        allocated = df[
            df["selected_candidate"].notna()
            & (df["selected_candidate"].astype(str) != "")
        ]

        if allocated.empty:
            candidate = ""
            r1 = r2 = r3 = r4 = math.nan
        else:
            allocation_row = allocated.iloc[-1]
            candidate = str(
                allocation_row["selected_candidate"]
            )
            r1 = int(allocation_row["r1"])
            r2 = int(allocation_row["r2"])
            r3 = int(allocation_row["r3"])
            r4 = int(allocation_row["r4"])

        rows.append({
            "motor": motor,
            "eta": eta,
            "residual": residual,
            "rep": rep,
            "trial_seed": seed,
            "candidate": candidate,
            "r1": r1,
            "r2": r2,
            "r3": r3,
            "r4": r4,
            "contact_found": metrics["contact_found"],
            "safe_touchdown": metrics["safe_touchdown"],
            "contact_t": contact_t,
            "contact_phase": contact_phase,
            "contact_z": contact_z,
            "fault_to_contact_s": fault_to_contact,
            "vertical_speed_mps":
                metrics["vertical_speed_mps"],
            "horizontal_speed_mps":
                metrics["horizontal_speed_mps"],
            "max_tilt_deg":
                metrics["max_tilt_deg"],
            "angular_rate_radps":
                metrics["angular_rate_radps"],
            "horizontal_drift_m":
                metrics["horizontal_drift_m"],
            "file": path.name,
        })

    if not rows:
        raise SystemExit(
            "[ERROR] No production dose-response trials found."
        )

    summary = pd.DataFrame(rows).sort_values(
        ["motor", "residual", "rep"]
    )

    OUT_TABLE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    OUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary.to_csv(OUT_TABLE, index=False)

    aggregate = (
        summary.groupby(["motor", "eta", "residual"])
        .agg(
            n=("trial_seed", "count"),
            contact_count=("contact_found", "sum"),
            safe_count=("safe_touchdown", "sum"),
            mean_vz=("vertical_speed_mps", "mean"),
            std_vz=("vertical_speed_mps", "std"),
            min_vz=("vertical_speed_mps", "min"),
            max_vz=("vertical_speed_mps", "max"),
            mean_fault_to_contact_s=(
                "fault_to_contact_s",
                "mean",
            ),
            std_fault_to_contact_s=(
                "fault_to_contact_s",
                "std",
            ),
            mean_hspeed=(
                "horizontal_speed_mps",
                "mean",
            ),
            max_hspeed=(
                "horizontal_speed_mps",
                "max",
            ),
            mean_tilt=("max_tilt_deg", "mean"),
            max_tilt=("max_tilt_deg", "max"),
            mean_drift=(
                "horizontal_drift_m",
                "mean",
            ),
            max_drift=(
                "horizontal_drift_m",
                "max",
            ),
        )
        .reset_index()
    )

    aggregate["safe_rate"] = (
        aggregate["safe_count"] / aggregate["n"]
    )

    ci_low = []
    ci_high = []

    for _, row in aggregate.iterrows():
        low, high = proportion_confint(
            count=int(row["safe_count"]),
            nobs=int(row["n"]),
            alpha=0.05,
            method="wilson",
        )
        ci_low.append(float(low))
        ci_high.append(float(high))

    aggregate["safe_rate_ci_low"] = ci_low
    aggregate["safe_rate_ci_high"] = ci_high

    aggregate = aggregate.sort_values(
        ["motor", "residual"]
    )

    aggregate.to_csv(OUT_AGG, index=False)

    print("\n[SEEDED RESIDUAL DOSE-RESPONSE AGGREGATE]")
    print(aggregate.to_string(index=False))

    print("\n[DATASET CHECK]")
    print(f"production_trials: {len(summary)}")
    print(
        "expected_trials:   "
        f"{2 * 7 * EXPECTED_REPS}"
    )
    print(
        "nonproduction_files_skipped: "
        f"{len(skipped_nonproduction)}"
    )
    print(f"malformed_files: {len(malformed)}")

    if len(summary) != 2 * 7 * EXPECTED_REPS:
        print(
            "[WARN] Production trial count is not 420."
        )

    for motor in sorted(aggregate["motor"].unique()):
        sub = aggregate[
            aggregate["motor"] == motor
        ].copy()

        lower = (
            sub["safe_rate"]
            - sub["safe_rate_ci_low"]
        ).clip(lower=0)

        upper = (
            sub["safe_rate_ci_high"]
            - sub["safe_rate"]
        ).clip(lower=0)

        plt.figure(figsize=(8, 5.5))
        plt.errorbar(
            sub["residual"],
            sub["safe_rate"],
            yerr=[lower, upper],
            marker="o",
            capsize=4,
        )
        plt.xlabel("Opposite-motor residual [PWM]")
        plt.ylabel("Safe-touchdown probability")
        plt.title(
            f"Residual-strength dose response — "
            f"motor {motor}, eta={ETA_TARGET}"
        )
        plt.ylim(-0.05, 1.05)
        plt.grid(True)
        plt.tight_layout()

        figure_path = (
            OUT_DIR /
            f"seeded_residual_dose_motor{motor}.png"
        )
        plt.savefig(figure_path, dpi=220)
        plt.close()

        print(f"Saved plot: {figure_path}")

        plt.figure(figsize=(8, 5.5))
        plt.errorbar(
            sub["residual"],
            sub["mean_vz"],
            yerr=sub["std_vz"],
            marker="o",
            capsize=4,
        )
        plt.axhline(
            VERTICAL_SPEED_LIMIT,
            linestyle="--",
            label="vertical-speed safety limit",
        )
        plt.xlabel("Opposite-motor residual [PWM]")
        plt.ylabel(
            "First-contact vertical speed [m/s]"
        )
        plt.title(
            f"Touchdown-speed dose response — "
            f"motor {motor}, eta={ETA_TARGET}"
        )
        plt.grid(True)
        plt.legend()
        plt.tight_layout()

        figure_path = (
            OUT_DIR /
            f"seeded_residual_dose_vz_motor{motor}.png"
        )
        plt.savefig(figure_path, dpi=220)
        plt.close()

        print(f"Saved plot: {figure_path}")

    print(f"\nSaved summary:   {OUT_TABLE}")
    print(f"Saved aggregate: {OUT_AGG}")


if __name__ == "__main__":
    main()
