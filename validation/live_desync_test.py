import subprocess, sys, time
sys.path.insert(0, "/Users/cconstab/scratch/Intel-route/smart-route-planning-agent/src")
from atsign.atsign_io import AtPublisher

def docker(*a): subprocess.run(["docker", *a], capture_output=True)

pub = AtPublisher("@bravo", root="vip.ve.atsign.zone:64")
conn = pub.client.secondary_connection
sock = conn._secure_root_socket

shared = conn.execute_command("llookup:shared_key.alpha@bravo", True).get_raw_data_response()
print(f"1. shared_key reply  : {len(shared)} chars, starts {shared[:16]}", flush=True)

print("2. freeze server; abandon a shared_key read via timeout", flush=True)
docker("pause", "atsign-ee")
sock.settimeout(3.0)
try:
    conn.execute_command("llookup:shared_key.alpha@bravo", True)
except Exception as e:
    print(f"   timed out: {type(e).__name__}", flush=True)
docker("unpause", "atsign-ee"); time.sleep(2)

print("3. now ask a DIFFERENT question (publickey) — does it answer the OLD one?", flush=True)
sock.settimeout(15.0)
try:
    reply = conn.execute_command("llookup:publickey@bravo", True).get_raw_data_response()
    stale = (reply == shared)
    print(f"   reply starts {str(reply)[:16]}", flush=True)
    print("   >>> DESYNC CONFIRMED: got the abandoned command's reply" if stale
          else "   >>> aligned: got the right answer for the new command", flush=True)
except Exception as e:
    print(f"   raised: {type(e).__name__}: {str(e)[:80]}", flush=True)
finally:
    docker("unpause", "atsign-ee")
