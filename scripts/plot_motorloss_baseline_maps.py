from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
summary_path = ROOT / "results" / "motorloss_sweep_summary.csv"
df = pd.read_csv(summary_path)

# Keep the main comparable sweep only
main_etas = [0.60, 0.55, 0.52, 0.50, 0.45]
df_main = df[df["eta"].isin(main_etas)].copy()

# Pivot tables
safe_pivot = df_main.pivot(index="motor", columns="eta", values="safe_touchdown")
vz_pivot = df_main.pivot(index="motor", columns="eta", values="vertical_speed_mps")
tilt_pivot = df_main.pivot(index="motor", columns="eta", values="max_tilt_after_fault_deg")

# Sort eta descending for readability
safe_pivot = safe_pivot[sorted(safe_pivot.columns, reverse=True)]
vz_pivot = vz_pivot[sorted(vz_pivot.columns, reverse=True)]
tilt_pivot = tilt_pivot[sorted(tilt_pivot.columns, reverse=True)]

# 1. Safe/unsafe heatmap
plt.figure()
plt.imshow(safe_pivot.astype(int), aspect="auto")
plt.xticks(range(len(safe_pivot.columns)), safe_pivot.columns)
plt.yticks(range(len(safe_pivot.index)), safe_pivot.index)
plt.xlabel("Motor effectiveness eta")
plt.ylabel("Faulty motor")
plt.title("Scripted emergency landing: safe touchdown map")

for i, motor in enumerate(safe_pivot.index):
    for j, eta in enumerate(safe_pivot.columns):
        val = safe_pivot.loc[motor, eta]
        txt = "SAFE" if val else "FAIL"
        plt.text(j, i, txt, ha="center", va="center")

plt.colorbar(label="safe_touchdown")
plt.tight_layout()
plt.savefig(ROOT / "results" / "safe_touchdown_heatmap.png", dpi=200)

# 2. Vertical touchdown speed vs eta
plt.figure()
for motor in sorted(df_main["motor"].unique()):
    d = df_main[df_main["motor"] == motor].sort_values("eta")
    plt.plot(d["eta"], d["vertical_speed_mps"], marker="o", label=f"motor {motor}")

plt.axhline(0.35, linestyle="--", label="safe limit 0.35 m/s")
plt.xlabel("Motor effectiveness eta")
plt.ylabel("Vertical touchdown speed [m/s]")
plt.title("Touchdown vertical speed under motor loss")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(ROOT / "results" / "vertical_speed_vs_eta.png", dpi=200)

# 3. Max tilt after fault
plt.figure()
for motor in sorted(df_main["motor"].unique()):
    d = df_main[df_main["motor"] == motor].sort_values("eta")
    plt.plot(d["eta"], d["max_tilt_after_fault_deg"], marker="o", label=f"motor {motor}")

plt.xlabel("Motor effectiveness eta")
plt.ylabel("Max tilt after fault [deg]")
plt.title("Attitude disturbance after actuator loss")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(ROOT / "results" / "max_tilt_vs_eta.png", dpi=200)

print("Saved:")
print(ROOT / "results" / "safe_touchdown_heatmap.png")
print(ROOT / "results" / "vertical_speed_vs_eta.png")
print(ROOT / "results" / "max_tilt_vs_eta.png")
