import sys
import time
import cflib.crtp
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

URI = "udp://127.0.0.1:19850"
TIMEOUT_S = 40

def main():
    cflib.crtp.init_drivers()
    start = time.time()

    while time.time() - start < TIMEOUT_S:
        try:
            print(f"[WAIT] Trying {URI}...")
            with SyncCrazyflie(URI):
                print("[WAIT] Crazyflie is ready.")
                return 0
        except Exception as e:
            print(f"[WAIT] Not ready yet: {e}")
            time.sleep(2)

    print("[WAIT] Timeout waiting for Crazyflie.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
