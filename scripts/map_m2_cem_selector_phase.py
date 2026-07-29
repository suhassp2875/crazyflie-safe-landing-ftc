#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from statistics import mean

from src.controllers.residual_allocator_qp import (
    AllocatorState,
    empirical_prior_candidates,
    nominal_reference,
)
from src.controllers.residual_allocator_tunable import (
    load_weight_config,
    score_candidate_tunable,
)


DEFAULT_ROOT = Path(
    "results/final/model_sensitivity/"
    "nominal_m2_boundary/localization"
)

DEFAULT_CONFIG = Path(
    "configs/allocator_weights/"
    "cem_tuned_boundary.json"
)

EXPECTED_CONFIG_SHA256 = (
    "705310dda32718993a3df38353caa567d4"
    "ca1387b0652b507130c889ea713a5b"
)

FILENAME_PATTERN = re.compile(
    r"eta(?P<eta>[0-9]+p[0-9]+)_seed(?P<seed>[0-9]+)"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def first_selection_row(
    path: Path,
) -> dict[str, str]:
    with path.open(newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            candidate = row.get(
                "selected_candidate",
                "",
            ).strip()

            if candidate not in {
                "",
                "none",
            }:
                return row

    raise RuntimeError(
        f"No selection event in {path}"
    )


def parse_eta_seed(
    path: Path,
) -> tuple[float, int]:
    match = FILENAME_PATTERN.search(
        path.name
    )

    if match is None:
        raise RuntimeError(
            f"Cannot parse eta and seed from {path}"
        )

    source_eta = float(
        match.group("eta").replace(
            "p",
            ".",
        )
    )

    seed = int(match.group("seed"))

    return source_eta, seed


def make_state(
    row: dict[str, str],
) -> AllocatorState:
    gx = float(row["gyro_x_deg_s"])
    gy = float(row["gyro_y_deg_s"])
    gz = float(row["gyro_z_deg_s"])

    angular_rate = math.radians(
        math.sqrt(
            gx * gx
            + gy * gy
            + gz * gz
        )
    )

    return AllocatorState(
        z=float(row["fault_z"]),
        vz=float(row["fault_vz"]),
        x=float(row["fault_x"]),
        y=float(row["fault_y"]),
        vx=float(row["fault_vx"]),
        vy=float(row["fault_vy"]),
        roll_deg=float(
            row["fault_roll_deg"]
        ),
        pitch_deg=float(
            row["fault_pitch_deg"]
        ),
        angular_rate_radps=angular_rate,
        max_motor_pwm=float(
            row["fault_max_motor_pwm"]
        ),
    )


def write_csv(
    path: Path,
    rows: list[dict],
) -> None:
    if not rows:
        raise RuntimeError(
            f"No output rows for {path}"
        )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )

    parser.add_argument(
        "--eta-min",
        type=float,
        default=0.496,
    )

    parser.add_argument(
        "--eta-max",
        type=float,
        default=0.502,
    )

    parser.add_argument(
        "--eta-step",
        type=float,
        default=0.000001,
    )

    args = parser.parse_args()

    if args.eta_step <= 0.0:
        raise SystemExit(
            "[FAIL] --eta-step must be positive."
        )

    if args.eta_max <= args.eta_min:
        raise SystemExit(
            "[FAIL] --eta-max must exceed --eta-min."
        )

    if sha256(args.config) != EXPECTED_CONFIG_SHA256:
        raise SystemExit(
            "[FAIL] CEM configuration checksum mismatch."
        )

    cfg = load_weight_config(
        args.config
    )

    trial_root = args.root / "trials"

    state_paths = []

    for eta_tag in (
        "0p499",
        "0p500",
    ):
        state_paths.extend(
            sorted(
                trial_root.glob(
                    "nominal_m2loc_cem_"
                    f"eta{eta_tag}_seed*.csv"
                )
            )
        )

    if len(state_paths) != 24:
        raise SystemExit(
            "[FAIL] Expected 24 source-state trials "
            f"from eta 0.499 and 0.500; "
            f"found {len(state_paths)}."
        )

    state_records = []

    for path in state_paths:
        source_eta, seed = parse_eta_seed(path)
        event = first_selection_row(path)

        state_records.append(
            {
                "state_id":
                    f"eta{source_eta:.3f}_seed{seed}",
                "source_eta": source_eta,
                "trial_seed": seed,
                "state": make_state(event),
            }
        )

    candidate_items = [
        (
            order,
            name,
            [
                int(value)
                for value in residual
            ],
        )
        for order, (
            name,
            residual,
        ) in enumerate(
            empirical_prior_candidates(2)
        )
        if int(residual[1]) == 0
    ]

    candidate_lookup = {
        name: (
            order,
            residual,
        )
        for order, name, residual
        in candidate_items
    }

    def evaluate_candidates(
        state: AllocatorState,
        eta: float,
    ) -> list[dict]:
        reference = nominal_reference(
            2,
            eta,
        )

        results = []

        for (
            order,
            candidate_name,
            residual,
        ) in candidate_items:
            score, details = (
                score_candidate_tunable(
                    fault_motor=2,
                    eta=eta,
                    state=state,
                    residual=residual,
                    ref=reference,
                    cfg=cfg,
                )
            )

            results.append(
                {
                    "order": order,
                    "candidate":
                        candidate_name,
                    "residual": residual,
                    "score": float(score),
                    "predicted_vz": float(
                        details["predicted_vz"]
                    ),
                }
            )

        results.sort(
            key=lambda item: (
                item["score"],
                item["order"],
            )
        )

        return results

    def candidate_score(
        state: AllocatorState,
        eta: float,
        candidate_name: str,
    ) -> float:
        _, residual = candidate_lookup[
            candidate_name
        ]

        reference = nominal_reference(
            2,
            eta,
        )

        score, _ = score_candidate_tunable(
            fault_motor=2,
            eta=eta,
            state=state,
            residual=residual,
            ref=reference,
            cfg=cfg,
        )

        return float(score)

    number_of_steps = int(
        round(
            (
                args.eta_max
                - args.eta_min
            )
            / args.eta_step
        )
    )

    eta_values = [
        args.eta_min
        + index * args.eta_step
        for index in range(
            number_of_steps + 1
        )
    ]

    grid_rows = []

    for eta in eta_values:
        winners = []
        margins = []

        for record in state_records:
            ranked = evaluate_candidates(
                record["state"],
                eta,
            )

            winners.append(
                ranked[0]["candidate"]
            )

            margins.append(
                ranked[1]["score"]
                - ranked[0]["score"]
            )

        counts = Counter(winners)
        most_common = counts.most_common()

        consensus_winner = (
            most_common[0][0]
            if len(counts) == 1
            else "mixed"
        )

        grid_rows.append(
            {
                "eta": f"{eta:.6f}",
                "n_states": len(
                    state_records
                ),
                "unique_winners":
                    len(counts),
                "consensus_winner":
                    consensus_winner,
                "majority_winner":
                    most_common[0][0],
                "majority_count":
                    most_common[0][1],
                "mean_winner_margin":
                    mean(margins),
                "min_winner_margin":
                    min(margins),
                "max_winner_margin":
                    max(margins),
            }
        )

    interval_rows = []

    interval_start = 0

    for index in range(
        1,
        len(grid_rows) + 1,
    ):
        end_interval = (
            index == len(grid_rows)
            or grid_rows[index][
                "consensus_winner"
            ]
            != grid_rows[
                interval_start
            ]["consensus_winner"]
        )

        if not end_interval:
            continue

        block = grid_rows[
            interval_start:index
        ]

        interval_rows.append(
            {
                "interval_id":
                    len(interval_rows) + 1,
                "eta_start":
                    block[0]["eta"],
                "eta_end":
                    block[-1]["eta"],
                "winner":
                    block[0][
                        "consensus_winner"
                    ],
                "grid_points":
                    len(block),
                "minimum_margin":
                    min(
                        float(
                            row[
                                "min_winner_margin"
                            ]
                        )
                        for row in block
                    ),
            }
        )

        interval_start = index

    transition_rows = []

    for left, right in zip(
        interval_rows,
        interval_rows[1:],
    ):
        old_candidate = left["winner"]
        new_candidate = right["winner"]

        if "mixed" in {
            old_candidate,
            new_candidate,
        }:
            continue

        eta_low = float(left["eta_end"])
        eta_high = float(
            right["eta_start"]
        )

        crossings = []
        third_candidate_margins = []
        top_pair_valid = []

        for record in state_records:
            state = record["state"]

            def difference(
                eta: float,
            ) -> float:
                return (
                    candidate_score(
                        state,
                        eta,
                        old_candidate,
                    )
                    - candidate_score(
                        state,
                        eta,
                        new_candidate,
                    )
                )

            low = eta_low
            high = eta_high

            f_low = difference(low)
            f_high = difference(high)

            if f_low > 1.0e-12:
                raise RuntimeError(
                    "Old candidate does not win "
                    f"at lower bracket: "
                    f"{old_candidate}, eta={low}, "
                    f"difference={f_low}"
                )

            if f_high < -1.0e-12:
                raise RuntimeError(
                    "New candidate does not win "
                    f"at upper bracket: "
                    f"{new_candidate}, eta={high}, "
                    f"difference={f_high}"
                )

            for _ in range(80):
                midpoint = (
                    low + high
                ) / 2.0

                f_mid = difference(
                    midpoint
                )

                if f_mid <= 0.0:
                    low = midpoint
                else:
                    high = midpoint

            crossing = (
                low + high
            ) / 2.0

            crossings.append(crossing)

            ranked = evaluate_candidates(
                state,
                crossing,
            )

            tied_pair = {
                ranked[0]["candidate"],
                ranked[1]["candidate"],
            }

            valid_pair = (
                tied_pair
                == {
                    old_candidate,
                    new_candidate,
                }
            )

            top_pair_valid.append(
                valid_pair
            )

            if len(ranked) >= 3:
                third_candidate_margins.append(
                    ranked[2]["score"]
                    - ranked[0]["score"]
                )

        transition_rows.append(
            {
                "transition_id":
                    len(transition_rows) + 1,
                "old_candidate":
                    old_candidate,
                "new_candidate":
                    new_candidate,
                "grid_eta_low":
                    f"{eta_low:.6f}",
                "grid_eta_high":
                    f"{eta_high:.6f}",
                "crossing_eta_mean":
                    mean(crossings),
                "crossing_eta_min":
                    min(crossings),
                "crossing_eta_max":
                    max(crossings),
                "crossing_spread":
                    max(crossings)
                    - min(crossings),
                "source_state_count":
                    len(crossings),
                "top_pair_valid_count":
                    sum(top_pair_valid),
                "minimum_third_candidate_margin":
                    min(
                        third_candidate_margins
                    ),
            }
        )

    grid_output = (
        args.root
        / "m2_cem_selector_phase_grid.csv"
    )

    interval_output = (
        args.root
        / "m2_cem_selector_phase_intervals.csv"
    )

    transition_output = (
        args.root
        / "m2_cem_selector_phase_transitions.csv"
    )

    write_csv(
        grid_output,
        grid_rows,
    )

    write_csv(
        interval_output,
        interval_rows,
    )

    write_csv(
        transition_output,
        transition_rows,
    )

    print(
        "========== M2 CEM SELECTOR PHASE MAP =========="
    )

    print(
        f"source_states={len(state_records)}"
    )

    print(
        f"candidate_count={len(candidate_items)}"
    )

    print(
        f"eta_grid_points={len(eta_values)}"
    )

    print()
    print(
        "interval_id,eta_start,eta_end,"
        "winner,grid_points,min_margin"
    )

    for row in interval_rows:
        print(
            f"{row['interval_id']},"
            f"{row['eta_start']},"
            f"{row['eta_end']},"
            f"{row['winner']},"
            f"{row['grid_points']},"
            f"{float(row['minimum_margin']):.12f}"
        )

    print()
    print(
        "transition_id,old_candidate,"
        "new_candidate,crossing_mean,"
        "crossing_min,crossing_max,"
        "spread,top_pair_valid,"
        "third_margin"
    )

    for row in transition_rows:
        print(
            f"{row['transition_id']},"
            f"{row['old_candidate']},"
            f"{row['new_candidate']},"
            f"{row['crossing_eta_mean']:.12f},"
            f"{row['crossing_eta_min']:.12f},"
            f"{row['crossing_eta_max']:.12f},"
            f"{row['crossing_spread']:.12e},"
            f"{row['top_pair_valid_count']}/"
            f"{row['source_state_count']},"
            f"{row['minimum_third_candidate_margin']:.12f}"
        )

    print()
    print(f"[SAVED] {grid_output}")
    print(f"[SAVED] {interval_output}")
    print(f"[SAVED] {transition_output}")


if __name__ == "__main__":
    main()
