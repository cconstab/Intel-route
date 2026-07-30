"""The user's incident: poison the connection, confirm publishing recovers by itself
and does NOT delete a healthy shared key."""
import subprocess, sys, time
sys.path.insert(0, "/Users/cconstab/scratch/Intel-route/smart-route-planning-agent/src")
from atsign.atsign_io import AtPublisher

def docker(*a): subprocess.run(["docker", *a], capture_output=True)

pub = AtPublisher("@bravo", root="vip.ve.atsign.zone:64")
key_before = pub.client.secondary_connection.execute_command(
    "llookup:shared_key.alpha@bravo", True).get_raw_data_response()
print(f"healthy shared key: {key_before[:16]}...", flush=True)

# poison exactly as a slow/frozen server would
docker("pause", "atsign-ee")
pub.client.secondary_connection._secure_root_socket.settimeout(3.0)
try:
    pub.client.secondary_connection.execute_command("llookup:shared_key.alpha@bravo", True)
except Exception as e:
    print(f"connection poisoned by an abandoned read ({type(e).__name__})", flush=True)
docker("unpause", "atsign-ee"); time.sleep(2)

print("\npublishing on the poisoned publisher:", flush=True)
try:
    pub.notify("@alpha", "desync", "RECOVERED", namespace="smartroute")
    print("   -> published OK", flush=True)
    ok = True
except Exception as e:
    print(f"   -> failed: {type(e).__name__}: {str(e)[:70]}", flush=True)
    ok = False

fresh = AtPublisher("@bravo", root="vip.ve.atsign.zone:64")
key_after = fresh.client.secondary_connection.execute_command(
    "llookup:shared_key.alpha@bravo", True).get_raw_data_response()
kept = key_after == key_before
print(f"\nrecovered without a restart : {ok}", flush=True)
print(f"healthy shared key preserved: {kept}", flush=True)
sys.exit(0 if (ok and kept) else 1)
