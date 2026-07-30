#!/usr/bin/env python3
"""The guarantee that matters: a publish never freezes its caller's loop.

Freezes the atServer (docker pause = no FIN/RST, like a network change), then:
  1. a publish must RAISE within its deadline instead of blocking forever
  2. a planner-style loop must keep iterating throughout the outage
  3. once the peer returns, publishing must heal by itself
"""
import subprocess
import sys
import threading
import time

sys.path.insert(0, "/Users/cconstab/scratch/Intel-route/smart-route-planning-agent/src")
from atsign.atsign_io import AtPublisher, PUBLISH_DEADLINE_S  # noqa: E402

ROOT = "vip.ve.atsign.zone:64"
NS = "smartroute"
results = []


def docker(*a):
    subprocess.run(["docker", *a], capture_output=True)


def check(name, ok, detail=""):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)


def timed_notify(pub, value):
    start = time.time()
    try:
        pub.notify("@alpha", "dl", value, namespace=NS)
        return "ok", time.time() - start
    except Exception as e:
        return type(e).__name__, time.time() - start


def main():
    pub = AtPublisher("@bravo", root=ROOT)
    outcome, secs = timed_notify(pub, "BASELINE")
    check("baseline publish succeeds", outcome == "ok", f"({secs:.1f}s)")

    print("\noutage: pausing atsign-ee", flush=True)
    docker("pause", "atsign-ee")
    time.sleep(2)

    # 1. bounded: must raise, not hang
    outcome, secs = timed_notify(pub, "DURING_OUTAGE")
    bounded = outcome != "ok" and secs < PUBLISH_DEADLINE_S * 3
    check("publish is bounded during the outage", bounded,
          f"({outcome} after {secs:.0f}s, deadline {PUBLISH_DEADLINE_S:.0f}s)")

    # 2. a planner-style loop keeps turning
    iterations = 0
    loop_start = time.time()
    while time.time() - loop_start < 70:
        timed_notify(pub, f"TICK{iterations}")
        iterations += 1
    check("planner-style loop keeps iterating while down", iterations >= 2,
          f"({iterations} iterations in 70s)")

    # 3. heals on its own once the peer is back
    print("\nrestore: unpausing atsign-ee", flush=True)
    docker("unpause", "atsign-ee")
    healed, deadline = False, time.time() + 120
    while time.time() < deadline and not healed:
        outcome, secs = timed_notify(pub, "AFTER_OUTAGE")
        healed = outcome == "ok"
        if not healed:
            time.sleep(5)
    check("publishing heals after the peer returns", healed)

    print(f"\nRESULT: {sum(results)}/{len(results)} passed", flush=True)
    return 0 if all(results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        docker("unpause", "atsign-ee")
