#!/usr/bin/env python3

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


SUMMARY = Path(
    "results/final/tables/seeded_boundary_fine_summary.csv"
)

OUT_DIR = Path("results/final/contact_audit")
TABLE_DIR = OUT_DIR / "tables"
FIG_DIR = OUT_DIR / "figures"

TARGET_ETA = 0.496


def first_contact_index(df):
    fault_rows = df.index[df["phase"] == "fault_event"].tolist()

    if not fault_rows:
        return None, None

    fault_idx = fault_rows[0]
    post = df.loc[fault_idx:]

    contact = post.index[post["z"] <= 0.03].tolist()

    if not contact:
        return None, fault_idx

    return contact[0], fault_idx


def classify_trial(row):
    if row["vertical_speed_mps"] < 0.05:
        return "near_zero"

    if bool(row["safe_touchdown"]):
        return "normal_safe"

    return "normal_unsafe"


def main():
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    s = pd.read_csv(SUMMARY)

    s = s[
        np.isclose(s["eta"], TARGET_ETA)
    ].copy()

    s["trial_class"] = s.apply(
        classify_trial,
        axis=1,
    )

    # Include all near-zero cases.
    audit_rows = [
        r for _, r in
        s[s["trial_class"] == "near_zero"].iterrows()
    ]

    # Add representative normal cases:
    # one QP-lite unsafe and one CEM safe for motors 1 and 4,
    # plus representative normal safe cases for motor 3.
    selections = [
        (1, "qplite", "normal_unsafe"),
        (1, "cem", "normal_safe"),
        (3, "qplite", "normal_safe"),
        (3, "cem", "normal_safe"),
        (4, "qplite", "normal_unsafe"),
        (4, "cem", "normal_safe"),
    ]

    for motor, controller, trial_class in selections:
        sub = s[
            (s["motor"] == motor)
            & (s["controller"] == controller)
            & (s["trial_class"] == trial_class)
        ].copy()

        if sub.empty:
            continue

        # Representative trial closest to class median vertical speed.
        med = sub["vertical_speed_mps"].median()
        idx = (
            sub["vertical_speed_mps"] - med
        ).abs().idxmin()

        audit_rows.append(sub.loc[idx])

    audit_summary = []

    seen = set()

    for row in audit_rows:
        filename = row["file"]

        if filename in seen:
            continue
        seen.add(filename)

        path = Path("logs") / filename

        if not path.exists():
            print(f"[WARN] Missing: {path}")
            continue

        df = pd.read_csv(path)

        contact_idx, fault_idx = first_contact_index(df)

        if contact_idx is None:
            print(f"[WARN] No contact found in {filename}")
            continue

        contact = df.loc[contact_idx]

        # Window around first contact.
        t_contact = float(contact["t"])
        window = df[
            (df["t"] >= t_contact - 2.0)
            & (df["t"] <= t_contact + 0.5)
        ].copy()

        pre_contact = df[
            (df.index >= fault_idx)
            & (df.index <= contact_idx)
        ].copy()

        audit_summary.append({
            "motor": int(row["motor"]),
            "controller": row["controller"],
            "trial_seed": int(row["trial_seed"]),
            "trial_class": row["trial_class"],
            "candidate": row["candidate"],
            "file": filename,
            "contact_t": t_contact,
            "contact_phase": str(contact["phase"]),
            "contact_z": float(contact["z"]),
            "contact_vz": float(contact["vz"]),
            "summary_vertical_speed_mps":
                float(row["vertical_speed_mps"]),
            "min_z_before_contact":
                float(pre_contact["z"].min()),
            "max_z_before_contact":
                float(pre_contact["z"].max()),
            "min_vz_before_contact":
                float(pre_contact["vz"].min()),
            "max_vz_before_contact":
                float(pre_contact["vz"].max()),
            "rows_before_contact":
                int(len(pre_contact)),
        })

        stem = (
            f"m{int(row['motor'])}_"
            f"{row['controller']}_"
            f"seed{int(row['trial_seed'])}_"
            f"{row['trial_class']}"
        )

        # Z trajectory
        plt.figure(figsize=(8, 5.5))
        plt.plot(window["t"], window["z"], label="z")
        plt.axhline(
            0.03,
            linestyle="--",
            label="contact threshold z=0.03",
        )
        plt.axvline(
            t_contact,
            linestyle=":",
            label="detected first contact",
        )
        plt.xlabel("Time [s]")
        plt.ylabel("Altitude z [m]")
        plt.title(
            f"Altitude around detected contact\n"
            f"motor {int(row['motor'])}, "
            f"{row['controller']}, "
            f"seed {int(row['trial_seed'])}"
        )
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.savefig(
            FIG_DIR / f"{stem}_z.png",
            dpi=220,
        )
        plt.close()

        # Vertical speed trajectory
        plt.figure(figsize=(8, 5.5))
        plt.plot(
            window["t"],
            window["vz"].abs(),
            label="|vz|",
        )
        plt.axhline(
            0.35,
            linestyle="--",
            label="safety limit",
        )
        plt.axvline(
            t_contact,
            linestyle=":",
            label="detected first contact",
        )
        plt.xlabel("Time [s]")
        plt.ylabel("Vertical speed magnitude [m/s]")
        plt.title(
            f"Vertical speed around detected contact\n"
            f"motor {int(row['motor'])}, "
            f"{row['controller']}, "
            f"seed {int(row['trial_seed'])}"
        )
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.savefig(
            FIG_DIR / f"{stem}_vz.png",
            dpi=220,
        )
        plt.close()

        # z and commanded z together
        plt.figure(figsize=(8, 5.5))
        plt.plot(window["t"], window["z"], label="z")
        plt.plot(
            window["t"],
            window["z_cmd"],
            label="z_cmd",
        )
        plt.axvline(
            t_contact,
            linestyle=":",
            label="detected first contact",
        )
        plt.xlabel("Time [s]")
        plt.ylabel("Altitude [m]")
        plt.title(
            f"Altitude tracking near contact\n"
            f"motor {int(row['motor'])}, "
            f"{row['controller']}, "
            f"seed {int(row['trial_seed'])}"
        )
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        plt.savefig(
            FIG_DIR / f"{stem}_z_vs_cmd.png",
            dpi=220,
        )
        plt.close()

    out = pd.DataFrame(audit_summary)

    out_path = (
        TABLE_DIR /
        "near_zero_contact_trajectory_audit.csv"
    )
    out.to_csv(out_path, index=False)

    print("\n[TRAJECTORY AUDIT SUMMARY]")
    print(out.to_string(index=False))

    print(f"\nSaved: {out_path}")
    print(f"Figures: {FIG_DIR}")


if __name__ == "__main__":
    main()
