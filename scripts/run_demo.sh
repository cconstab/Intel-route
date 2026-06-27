#!/bin/bash
# Full live demo on the local ephemeral environment.
#
# Prereqs:
#   1. EE running (docker run ... atsigncompany/ephemeral --add-host vip.ve.atsign.zone:127.0.0.1)
#   2. 11 role atSigns onboarded:  HOME=/tmp/eehome python scripts/onboard_all_ee.py
#   3. venv active with deps (atsdk, pydantic, langgraph, gpxpy, folium)
#   4. HOME pointing at the keystore:  export HOME=/tmp/eehome
#
# Shows: policy granted -> intersection pushes high-density at a real trackpoint ->
#        planner reroutes (unmodified LangGraph) -> pushes route to commuter + operator.
set +e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/smart-route-planning-agent/src"
cd "$ROOT"

echo "== starting commuter (@india) and operator (@hotel) receivers =="
python -u scripts/commuter_receiver.py > /tmp/demo_commuter.log 2>&1 &
C=$!
python -u scripts/operator_receiver.py > /tmp/demo_operator.log 2>&1 &
O=$!
sleep 4

echo "== planner: grant policy, inject a pushed high-density record, reroute, push =="
python -u scripts/planner_run.py 2>&1 | grep -E "shortest direct|realtime optimal|REROUTED|triggered|PUSHED"
sleep 6
kill "$C" "$O" 2>/dev/null
pkill -f commuter_receiver 2>/dev/null; pkill -f operator_receiver 2>/dev/null

echo; echo "================ COMMUTER PHONE ================"
grep -E "ALERT|Route received|route|reason|map pts" /tmp/demo_commuter.log | tail -6
echo; echo "================ OPERATOR CONSOLE ================"
grep -E "status update|optimal route|agent status|reason|intersections" /tmp/demo_operator.log | tail -6
