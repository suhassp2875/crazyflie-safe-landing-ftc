#!/usr/bin/env python3

from pathlib import Path
import pandas as pd


INVALID_FILES = [
    "qp_event_allocator_m1_eta0p496_seededfine_qplite_m1_eta0p496_seed14980005.csv",
    "qp_event_allocator_m1_eta0p496_seededfine_qplite_m1_eta0p496_seed14980010.csv",
    "qp_event_allocator_m1_eta0p496_seededfine_qplite_m1_eta0p496_seed14980026.csv",
    "qp_event_allocator_m3_eta0p496_seededfine_qplite_m3_eta0p496_seed34980012.csv",
    "qp_event_allocator_m3_eta0p496_seededfine_cem_m3_eta0p496_seed39980011.csv",
    "qp_event_allocator_m3_eta0p496_seededfine_cem_m3_eta0p496_seed39980022.csv",
]

OUT = Path(
    "results/final/contact_audit/tables/"
    "invalid_prefault_trial_audit.csv"
)


def main():
    rows = []

    for filename in INVALID_FILES:
        path = Path("logs") / filename

        if not path.exists():
            print(f"[WARN] Missing {path}")
            continue

        df = pd.read_csv(path)

        fault_rows = df.index[df["phase"] == "fault_event"].tolist()

        if not fault_rows:
            print(f"[WARN] No fault_event in {filename}")
            continue

        fault_idx = fault_rows[0]
        pre = df.loc[:fault_idx].copy()

        first = df.iloc[0]
        fault = df.loc[fault_idx]

        max_z_idx = pre["z"].idxmax()
        max_z_row = pre.loc[max_z_idx]

        airborne_rows = pre[pre["z"] > 0.30]
        hover_rows = pre[pre["z"] > 0.60]

        rows.append({
            "file": filename,
            "rows_total": len(df),
            "rows_prefault": len(pre),
            "first_phase": first["phase"],
            "first_t": first["t"],
            "first_z": first["z"],
            "fault_idx": int(fault_idx),
            "fault_t": fault["t"],
            "fault_phase": fault["phase"],
            "fault_z": fault["z"],
            "fault_vz": fault["vz"],
            "max_prefault_z": pre["z"].max(),
            "max_prefault_z_t": max_z_row["t"],
            "min_prefault_z": pre["z"].min(),
            "mean_prefault_z": pre["z"].mean(),
            "num_rows_z_gt_0p30": len(airborne_rows),
            "num_rows_z_gt_0p60": len(hover_rows),
            "ever_above_0p30": bool(len(airborne_rows) > 0),
            "ever_above_0p60": bool(len(hover_rows) > 0),
            "last_prefault_phase": pre.iloc[-1]["phase"],
            "last_prefault_z": pre.iloc[-1]["z"],
            "last_prefault_vz": pre.iloc[-1]["vz"],
        })

        print("\n============================================================")
        print(filename)
        print("============================================================")

        phase_summary = (
            pre.groupby("phase")
            .agg(
                n=("t", "count"),
                t_min=("t", "min"),
                t_max=("t", "max"),
                z_min=("z", "min"),
                z_max=("z", "max"),
                z_mean=("z", "mean"),
                vz_min=("vz", "min"),
                vz_max=("vz", "max"),
            )
        )

        print("\n[PRE-FAULT PHASE SUMMARY]")
        print(phase_summary.to_string())

        print("\n[LAST 20 PRE-FAULT ROWS]")
        cols = [
            "t",
            "phase",
            "x",
            "y",
            "z",
            "vx",
            "vy",
            "vz",
            "z_cmd",
        ]
        print(pre[cols].tail(20).to_string(index=False))

    out = pd.DataFrame(rows)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    print("\n============================================================")
    print("[INVALID PRE-FAULT AUDIT SUMMARY]")
    print("============================================================")
    print(out.to_string(index=False))
    print(f"\nSaved: {OUT}")


if __name__ == "__main__":
    main()
