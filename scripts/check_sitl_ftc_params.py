import time
import cflib.crtp
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

URI = "udp://127.0.0.1:19850"

cflib.crtp.init_drivers()

with SyncCrazyflie(URI) as scf:
    cf = scf.cf
    print("[INFO] Connected.")

    print("[INFO] Checking sitlFault params...")
    cf.param.set_value("sitlFault.motor", "1")
    cf.param.set_value("sitlFault.eta", "0.50")
    cf.param.set_value("sitlFault.enable", "1")
    time.sleep(0.2)

    print("[INFO] Checking sitlFtc params...")
    cf.param.set_value("sitlFtc.healthyBoost", "5000")
    cf.param.set_value("sitlFtc.enable", "1")
    time.sleep(0.2)

    print("[INFO] Resetting params...")
    cf.param.set_value("sitlFtc.enable", "0")
    cf.param.set_value("sitlFtc.healthyBoost", "0")
    cf.param.set_value("sitlFault.enable", "0")
    cf.param.set_value("sitlFault.eta", "1.0")
    time.sleep(0.2)

    print("[OK] sitlFault and sitlFtc params are available and writable.")
