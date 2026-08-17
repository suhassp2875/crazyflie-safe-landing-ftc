#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


DEFAULT_INPUT = Path(
    "results/final/model_sensitivity/ofat/"
    "sensitivity_analysis/"
    "ofat_sensitivity_table.csv"
)

DEFAULT_OUTPUT = Path(
    "results/final/model_sensitivity/ofat/"
    "sensitivity_analysis/"
    "ofat_ed50_tornado.png"
)


def pretty_name(parameter: str) -> str:
    names = {
        "mass":
            "Mass",
        "thrust_coefficient":
            "Thrust coefficient",
        "motor_time_constant":
            "Motor time constant",
        "thrust_to_torque_ratio":
            "Thrust-to-torque ratio",
        "arm_length":
            "Arm length",
    }

    return names.get(
        parameter,
        parameter.replace("_", " ").title(),
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(
            f"[FAIL] Missing input: {args.input}"
        )

    with args.input.open(
        newline=""
    ) as file:
        rows = list(csv.DictReader(file))

    if len(rows) != 5:
        raise SystemExit(
            "[FAIL] Expected five OFAT parameter rows; "
            f"found {len(rows)}."
        )

    # Keep the sensitivity ranking already produced by
    # the analyzer: highest max |Delta ED50| first.
    labels = [
        pretty_name(row["parameter"])
        for row in rows
    ]

    minus = np.array(
        [
            float(row["minus10_delta_ed50"])
            for row in rows
        ],
        dtype=float,
    )

    plus = np.array(
        [
            float(row["plus10_delta_ed50"])
            for row in rows
        ],
        dtype=float,
    )

    minus_low = np.array(
        [
            float(row["minus10_delta_ci95_low"])
            for row in rows
        ],
        dtype=float,
    )

    minus_high = np.array(
        [
            float(row["minus10_delta_ci95_high"])
            for row in rows
        ],
        dtype=float,
    )

    plus_low = np.array(
        [
            float(row["plus10_delta_ci95_low"])
            for row in rows
        ],
        dtype=float,
    )

    plus_high = np.array(
        [
            float(row["plus10_delta_ci95_high"])
            for row in rows
        ],
        dtype=float,
    )

    y = np.arange(len(rows), dtype=float)

    fig, ax = plt.subplots(
        figsize=(10.0, 5.8)
    )

    # Connecting span between -10% and +10%.
    for index in range(len(rows)):
        ax.plot(
            [
                minus[index],
                plus[index],
            ],
            [
                y[index],
                y[index],
            ],
            linewidth=3,
            alpha=0.6,
        )

    minus_xerr = np.vstack(
        [
            minus - minus_low,
            minus_high - minus,
        ]
    )

    plus_xerr = np.vstack(
        [
            plus - plus_low,
            plus_high - plus,
        ]
    )

    ax.errorbar(
        minus,
        y - 0.08,
        xerr=minus_xerr,
        fmt="o",
        capsize=3,
        label="-10% perturbation",
    )

    ax.errorbar(
        plus,
        y + 0.08,
        xerr=plus_xerr,
        fmt="o",
        capsize=3,
        label="+10% perturbation",
    )

    ax.axvline(
        0.0,
        linewidth=1.2,
        linestyle="--",
    )

    ax.set_yticks(
        y,
        labels,
    )

    ax.invert_yaxis()

    ax.set_xlabel(
        r"$\Delta ED_{50}$ relative to nominal"
    )

    ax.set_title(
        "M2 PINV model sensitivity under ±10% plant perturbations"
    )

    ax.grid(
        axis="x",
        alpha=0.25,
    )

    ax.legend(
        loc="best",
        frameon=False,
    )

    fig.tight_layout()

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fig.savefig(
        args.output,
        dpi=240,
        bbox_inches="tight",
    )

    plt.close(fig)

    print(f"[SAVED] {args.output}")
    print("[PASS] Tornado plot generated.")


if __name__ == "__main__":
    main()
