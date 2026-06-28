import time
import cflib.crtp
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

URI = "udp://127.0.0.1:19850"

def main():
    cflib.crtp.init_drivers()

    with SyncCrazyflie(URI) as scf:
        cf = scf.cf
        print("[INFO] Connected.")

        print("[INFO] Setting fault params...")
        cf.param.set_value("sitlFault.enable", "0")
        cf.param.set_value("sitlFault.motor", "1")
        cf.param.set_value("sitlFault.eta", "1.0")
        time.sleep(0.5)

        print("[OK] sitlFault params are available and writable.")

if __name__ == "__main__":
    main()
