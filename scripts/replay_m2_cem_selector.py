#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
from collections import Counter, defaultdict
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
        rows = list(csv.DictReader(file))

    selected = [
        row
        for row in rows
        if row.get(
            "selected_candidate",
            "",
        ).strip() not in {
            "",
            "none",
        }
    ]

    if not selected:
        raise RuntimeError(
            f"No candidate-selection row in {path}"
        )

    return selected[0]


def parse_eta_seed(
    path: Path,
) -> tuple[float, int]:
    match = FILENAME_PATTERN.search(
        path.name
    )

    if match is None:
        raise RuntimeError(
            f"Cannot parse eta/seed from {path.name}"
        )

    eta = float(
        match.group("eta").replace(
            "p",
            ".",
        )
    )

    seed = int(match.group("seed"))

    return eta, seed


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
            f"No rows available for {path}"
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

    args = parser.parse_args()

    trial_root = args.root / "trials"

    all_output = (
        args.root
        / "m2_cem_selector_all_candidates.csv"
    )

    margin_output = (
        args.root
        / "m2_cem_selector_margin_summary.csv"
    )

    eta_output = (
        args.root
        / "m2_cem_selector_eta_summary.csv"
    )

    if not args.config.is_file():
        raise SystemExit(
            f"[FAIL] Missing {args.config}"
        )

    observed_sha = sha256(args.config)

    if observed_sha != EXPECTED_CONFIG_SHA256:
        raise SystemExit(
            "[FAIL] CEM config checksum mismatch.\n"
            f"expected={EXPECTED_CONFIG_SHA256}\n"
            f"observed={observed_sha}"
        )

    cfg = load_weight_config(
        args.config
    )

    paths = sorted(
        trial_root.glob(
            "nominal_m2loc_cem_*.csv"
        )
    )

    if len(paths) != 72:
        raise SystemExit(
            "[FAIL] Expected 72 CEM trials; "
            f"found {len(paths)}."
        )

    all_rows: list[dict] = []
    margin_rows: list[dict] = []

    for path in paths:
        eta, seed = parse_eta_seed(path)
        event = first_selection_row(path)
        state = make_state(event)

        logged_candidate = event[
            "selected_candidate"
        ]

        logged_score = float(
            event["qp_score"]
        )

        reference = nominal_reference(
            2,
            eta,
        )

        replayed = []

        for order, (
            candidate_name,
            residual,
        ) in enumerate(
            empirical_prior_candidates(2)
        ):
            if residual[1] != 0:
                continue

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

            vertical_penalty = (
                cfg.vertical_weight
                * details[
                    "vertical_violation"
                ] ** 2
            )

            hard_vertical_penalty = (
                cfg.hard_vertical_weight
                * details[
                    "hard_vertical_violation"
                ] ** 2
            )

            drift_violation = max(
                0.0,
                details["predicted_drift"]
                - 0.65,
            )

            tilt_violation = max(
                0.0,
                details["predicted_tilt"]
                - 8.0,
            )

            drift_penalty = (
                cfg.drift_weight
                * drift_violation ** 2
            )

            tilt_penalty = (
                cfg.tilt_weight
                * tilt_violation ** 2
            )

            effort_penalty = (
                cfg.effort_weight
                * details["total_effort"]
            )

            reference_penalty = (
                cfg.reference_weight
                * details["ref_error"]
            )

            support_penalty = (
                cfg.support_weight
                * details[
                    "support_resid"
                ] ** 2
            )

            saturation_penalty = (
                cfg.saturation_weight
                * (
                    details[
                        "saturation_excess"
                    ]
                    / 10000.0
                ) ** 2
            )

            motor2_overboost_penalty = (
                cfg.motor2_overboost_penalty
                if residual[3] > 12500
                else 0.0
            )

            recomputed_score = sum(
                [
                    vertical_penalty,
                    hard_vertical_penalty,
                    drift_penalty,
                    tilt_penalty,
                    effort_penalty,
                    reference_penalty,
                    support_penalty,
                    saturation_penalty,
                    motor2_overboost_penalty,
                ]
            )

            if not math.isclose(
                score,
                recomputed_score,
                rel_tol=1.0e-12,
                abs_tol=1.0e-12,
            ):
                raise RuntimeError(
                    "Score decomposition mismatch: "
                    f"eta={eta}, seed={seed}, "
                    f"candidate={candidate_name}, "
                    f"score={score}, "
                    f"recomputed={recomputed_score}"
                )

            replayed.append(
                {
                    "candidate_order": order,
                    "candidate":
                        candidate_name,
                    "residual":
                        tuple(
                            int(value)
                            for value in residual
                        ),
                    "score": float(score),
                    "details": details,
                    "vertical_penalty":
                        vertical_penalty,
                    "hard_vertical_penalty":
                        hard_vertical_penalty,
                    "drift_penalty":
                        drift_penalty,
                    "tilt_penalty":
                        tilt_penalty,
                    "effort_penalty":
                        effort_penalty,
                    "reference_penalty":
                        reference_penalty,
                    "support_penalty":
                        support_penalty,
                    "saturation_penalty":
                        saturation_penalty,
                    "motor2_overboost_penalty":
                        motor2_overboost_penalty,
                }
            )

        # Runtime selection is a strict score comparison.
        # Candidate order resolves exact ties.
        replayed.sort(
            key=lambda item: (
                item["score"],
                item["candidate_order"],
            )
        )

        winner = replayed[0]
        runner_up = replayed[1]

        if (
            winner["candidate"]
            != logged_candidate
        ):
            raise RuntimeError(
                "Winner mismatch: "
                f"eta={eta}, seed={seed}, "
                f"logged={logged_candidate}, "
                f"replayed={winner['candidate']}"
            )

        if not math.isclose(
            winner["score"],
            logged_score,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ):
            raise RuntimeError(
                "Winner-score mismatch: "
                f"eta={eta}, seed={seed}, "
                f"logged={logged_score}, "
                f"replayed={winner['score']}"
            )

        for rank, item in enumerate(
            replayed,
            start=1,
        ):
            residual = item["residual"]
            details = item["details"]

            all_rows.append(
                {
                    "eta": f"{eta:.6f}",
                    "trial_seed": seed,
                    "logged_winner":
                        logged_candidate,
                    "rank": rank,
                    "candidate":
                        item["candidate"],
                    "r1": residual[0],
                    "r2": residual[1],
                    "r3": residual[2],
                    "r4": residual[3],
                    "score": item["score"],
                    "margin_to_winner":
                        item["score"]
                        - winner["score"],
                    "predicted_vz":
                        details[
                            "predicted_vz"
                        ],
                    "predicted_drift":
                        details[
                            "predicted_drift"
                        ],
                    "predicted_tilt":
                        details[
                            "predicted_tilt"
                        ],
                    "vertical_violation":
                        details[
                            "vertical_violation"
                        ],
                    "hard_vertical_violation":
                        details[
                            "hard_vertical_violation"
                        ],
                    "vertical_penalty":
                        item[
                            "vertical_penalty"
                        ],
                    "hard_vertical_penalty":
                        item[
                            "hard_vertical_penalty"
                        ],
                    "drift_penalty":
                        item[
                            "drift_penalty"
                        ],
                    "tilt_penalty":
                        item[
                            "tilt_penalty"
                        ],
                    "effort_penalty":
                        item[
                            "effort_penalty"
                        ],
                    "reference_penalty":
                        item[
                            "reference_penalty"
                        ],
                    "support_penalty":
                        item[
                            "support_penalty"
                        ],
                    "saturation_penalty":
                        item[
                            "saturation_penalty"
                        ],
                    "motor2_overboost_penalty":
                        item[
                            "motor2_overboost_penalty"
                        ],
                    "fault_z": state.z,
                    "fault_vz": state.vz,
                    "fault_roll_deg":
                        state.roll_deg,
                    "fault_pitch_deg":
                        state.pitch_deg,
                    "fault_angular_rate_radps":
                        state.angular_rate_radps,
                    "fault_max_motor_pwm":
                        state.max_motor_pwm,
                }
            )

        margin_rows.append(
            {
                "eta": f"{eta:.6f}",
                "trial_seed": seed,
                "winner":
                    winner["candidate"],
                "winner_score":
                    winner["score"],
                "runner_up":
                    runner_up["candidate"],
                "runner_up_score":
                    runner_up["score"],
                "winner_margin":
                    runner_up["score"]
                    - winner["score"],
                "logged_score":
                    logged_score,
                "replay_error":
                    winner["score"]
                    - logged_score,
            }
        )

    write_csv(
        all_output,
        all_rows,
    )

    write_csv(
        margin_output,
        margin_rows,
    )

    grouped = defaultdict(list)

    for row in margin_rows:
        grouped[
            float(row["eta"])
        ].append(row)

    eta_rows = []

    for eta, rows in sorted(
        grouped.items()
    ):
        winners = Counter(
            row["winner"]
            for row in rows
        )

        runner_ups = Counter(
            row["runner_up"]
            for row in rows
        )

        margins = [
            float(row["winner_margin"])
            for row in rows
        ]

        eta_rows.append(
            {
                "eta": f"{eta:.6f}",
                "n": len(rows),
                "winner":
                    winners.most_common(1)[0][0],
                "winner_count":
                    winners.most_common(1)[0][1],
                "unique_winners":
                    len(winners),
                "runner_up":
                    runner_ups.most_common(1)[0][0],
                "mean_winner_margin":
                    mean(margins),
                "min_winner_margin":
                    min(margins),
                "max_winner_margin":
                    max(margins),
            }
        )

    write_csv(
        eta_output,
        eta_rows,
    )

    print(
        "========== EXACT M2 CEM SELECTOR REPLAY =========="
    )
    print(f"trials={len(margin_rows)}")
    print(
        "winner_mismatches=0"
    )
    print(
        "score_mismatches=0"
    )
    print(
        "eta,n,winner,winner_count,"
        "runner_up,mean_margin,"
        "min_margin,max_margin"
    )

    for row in eta_rows:
        print(
            f"{row['eta']},"
            f"{row['n']},"
            f"{row['winner']},"
            f"{row['winner_count']},"
            f"{row['runner_up']},"
            f"{row['mean_winner_margin']:.9f},"
            f"{row['min_winner_margin']:.9f},"
            f"{row['max_winner_margin']:.9f}"
        )

    print()
    print(f"[SAVED] {all_output}")
    print(f"[SAVED] {margin_output}")
    print(f"[SAVED] {eta_output}")


if __name__ == "__main__":
    main()
