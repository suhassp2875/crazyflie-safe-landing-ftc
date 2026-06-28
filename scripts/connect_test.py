import cflib.crtp
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

URI = "udp://127.0.0.1:19850"

def main():
    print(f"Initializing CFLib drivers...")
    cflib.crtp.init_drivers()

    print(f"Trying to connect to {URI}...")
    with SyncCrazyflie(URI) as scf:
        print("Connected successfully.")
        print(f"Link URI: {scf.cf.link_uri}")

if __name__ == "__main__":
    main()
