"""Is the desync actually prevented now? Re-run the experiment that proved it:
abandon a read, then ask a DIFFERENT question and see whether we get the stale reply."""
import subprocess, sys, time
sys.path.insert(0, "/Users/cconstab/scratch/Intel-route/smart-route-planning-agent/src")
from atsign.atsign_io import AtPublisher   # importing applies the guard

def docker(*a): subprocess.run(["docker", *a], capture_output=True)

pub = AtPublisher("@bravo", root="vip.ve.atsign.zone:64")
conn = pub.client.secondary_connection
shared = conn.execute_command("llookup:shared_key.alpha@bravo", True).get_raw_data_response()
print(f"shared_key reply starts: {shared[:16]}", flush=True)

docker("pause", "atsign-ee")
conn._secure_root_socket.settimeout(3.0)
try:
    conn.execute_command("llookup:shared_key.alpha@bravo", True)
except Exception as e:
    print(f"abandoned read: {type(e).__name__}", flush=True)
docker("unpause", "atsign-ee"); time.sleep(2)

print("connection still marked usable?", conn.is_connected(), flush=True)
print("\nasking a DIFFERENT question on that connection:", flush=True)
try:
    reply = conn.execute_command("llookup:publickey@bravo", True).get_raw_data_response()
    if reply == shared:
        print("   >>> STALE REPLY — still desynchronised", flush=True); sys.exit(1)
    print("   correct answer for the new command (no stale reply)", flush=True)
except Exception as e:
    print(f"   refused: {type(e).__name__} — cannot serve a stale reply", flush=True)

print("\nand the publisher still recovers:", flush=True)
pub.notify("@alpha", "guard", "OK", namespace="smartroute")
print("   published OK", flush=True)
docker("unpause", "atsign-ee")
