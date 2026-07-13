#!/usr/bin/env python3

from pathlib import Path
import pandas as pd


LOG_DIR = Path("logs")
OUT = Path(
    "results/final/contact_audit/tables/"
    "seededfine_prefault_validity_all.csv"
)

# Conservative validity requirements.
MIN_MAX_PREFAULT_Z = 0.50
MIN_FAULT_Z = 0.50
MAX_ABS_FAULT_VZ = 0.25


def main():
    rows = []

    paths = sorted(
        LOG_DIR.glob(
            "qp_event_allocator_m*_eta*_seededfine_*_m*_eta*_seed*.csv"
        )
    )

    print(f"[INFO] Found {len(paths)} seeded-fine CSV logs.")

    for i, path in enumerate(paths, start=1):
        df = pd.read_csv(path)

        fault_rows = df.index[
            df["phase"] == "fault_event"
        ].tolist()

        if not fault_rows:
            rows.append({
                "file": path.name,
                "valid_prefault": False,
                "invalid_reason": "missing_fault_event",
            })
            continue

        fault_idx = fault_rows[0]
        pre = df.loc[:fault_idx].copy()
        fault = df.loc[fault_idx]

        max_prefault_z = float(pre["z"].max())
        fault_z = float(fault["z"])
        fault_vz = float(fault["vz"])

        reasons = []

        if max_prefault_z < MIN_MAX_PREFAULT_Z:
            reasons.append("never_reached_airborne_altitude")

        if fault_z < MIN_FAULT_Z:
            reasons.append("fault_injected_below_required_altitude")

        if abs(fault_vz) > MAX_ABS_FAULT_VZ:
            reasons.append("fault_state_vertical_speed_too_large")

        valid = len(reasons) == 0

        rows.append({
            "file": path.name,
            "valid_prefault": valid,
            "invalid_reason": ";".join(reasons),
            "fault_idx": int(fault_idx),
            "fault_t": float(fault["t"]),
            "fault_z": fault_z,
            "fault_vz": fault_vz,
            "max_prefault_z": max_prefault_z,
            "min_prefault_z": float(pre["z"].min()),
            "rows_prefault": int(len(pre)),
        })

        if i % 100 == 0:
            print(f"[PROGRESS] {i}/{len(paths)}")

    out = pd.DataFrame(rows)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    print("\n[VALIDITY COUNTS]")
    print(
        out["valid_prefault"]
        .value_counts(dropna=False)
        .to_string()
    )

    invalid = out[
        out["valid_prefault"] == False
    ].copy()

    print("\n[INVALID TRIALS]")
    if invalid.empty:
        print("None")
    else:
        print(
            invalid[
                [
                    "file",
                    "invalid_reason",
                    "fault_z",
                    "fault_vz",
                    "max_prefault_z",
                ]
            ].to_string(index=False)
        )

    print(f"\ninvalid_count: {len(invalid)}")
    print(f"total_count:   {len(out)}")
    print(f"\nSaved: {OUT}")


if __name__ == "__main__":
    main()
