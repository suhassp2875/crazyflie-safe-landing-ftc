import argparse
import time

import cflib.crtp
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie


URI = "udp://127.0.0.1:19850"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default=URI)
    parser.add_argument("--r1", type=float, default=0.0)
    parser.add_argument("--r2", type=float, default=0.0)
    parser.add_argument("--r3", type=float, default=0.0)
    parser.add_argument("--r4", type=float, default=0.0)
    args = parser.parse_args()

    cflib.crtp.init_drivers()

    with SyncCrazyflie(args.uri) as scf:
        cf = scf.cf
        print("[INFO] Connected.")
        cf.param.set_value("sitlFtc.r1", str(args.r1))
        cf.param.set_value("sitlFtc.r2", str(args.r2))
        cf.param.set_value("sitlFtc.r3", str(args.r3))
        cf.param.set_value("sitlFtc.r4", str(args.r4))
        time.sleep(0.2)

        print("[OK] Set residuals:")
        print(f"sitlFtc.r1 = {args.r1}")
        print(f"sitlFtc.r2 = {args.r2}")
        print(f"sitlFtc.r3 = {args.r3}")
        print(f"sitlFtc.r4 = {args.r4}")


if __name__ == "__main__":
    main()
