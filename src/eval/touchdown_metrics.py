import math
from dataclasses import dataclass


@dataclass
class TouchdownLimits:
    max_vertical_speed_mps: float = 0.35
    max_horizontal_speed_mps: float = 0.25
    max_roll_pitch_deg: float = 12.0
    max_angular_rate_radps: float = 1.5
    max_horizontal_drift_m: float = 0.75


def rad_to_deg(rad: float) -> float:
    return rad * 180.0 / math.pi


def evaluate_touchdown(
    vx: float,
    vy: float,
    vz: float,
    roll: float,
    pitch: float,
    wx: float,
    wy: float,
    wz: float,
    x: float,
    y: float,
    x0: float = 0.0,
    y0: float = 0.0,
    limits: TouchdownLimits = TouchdownLimits(),
):
    horizontal_speed = math.sqrt(vx * vx + vy * vy)
    vertical_speed = abs(vz)
    max_tilt_deg = max(abs(rad_to_deg(roll)), abs(rad_to_deg(pitch)))
    angular_rate = math.sqrt(wx * wx + wy * wy + wz * wz)
    drift = math.sqrt((x - x0) ** 2 + (y - y0) ** 2)

    checks = {
        "vertical_speed_ok": vertical_speed <= limits.max_vertical_speed_mps,
        "horizontal_speed_ok": horizontal_speed <= limits.max_horizontal_speed_mps,
        "roll_pitch_ok": max_tilt_deg <= limits.max_roll_pitch_deg,
        "angular_rate_ok": angular_rate <= limits.max_angular_rate_radps,
        "drift_ok": drift <= limits.max_horizontal_drift_m,
    }

    return {
        "safe_touchdown": all(checks.values()),
        "vertical_speed_mps": vertical_speed,
        "horizontal_speed_mps": horizontal_speed,
        "max_tilt_deg": max_tilt_deg,
        "angular_rate_radps": angular_rate,
        "horizontal_drift_m": drift,
        "checks": checks,
    }


if __name__ == "__main__":
    result = evaluate_touchdown(
        vx=0.1,
        vy=0.05,
        vz=-0.25,
        roll=0.05,
        pitch=0.04,
        wx=0.2,
        wy=0.1,
        wz=0.4,
        x=0.2,
        y=0.1,
    )
    print(result)
