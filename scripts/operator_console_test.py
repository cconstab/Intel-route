#!/usr/bin/env python3
# Headless check of the operator console's atSign->render path (no Gradio launch).
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "smart-route-planning-agent", "src"))

from atsign import operator_console as oc  # noqa: E402

me = oc.start_subscriber()
print(f"[operator-console-test] subscribed as {me}; waiting for planner push...")
for _ in range(60):
    s, pts = oc.STATE.snapshot()
    if s and pts:  # wait for a status that carries the route geometry
        break
    time.sleep(0.5)

s, pts = oc.STATE.snapshot()
if not (s and pts):
    print("[operator-console-test] TIMEOUT — no status+geometry received")
    os._exit(1)

html = oc.render_map_html()
print("---- status panel (rendered) ----")
print(oc.status_markdown())
print("---- map ----")
print(f"map HTML chars: {len(html)} | folium/leaflet present: {'leaflet' in html.lower()} | route pts: {len(pts)}")
os._exit(0)
