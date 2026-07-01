#!/bin/bash
# Bring the whole system up live against the local ephemeral environment.
# Long-running services: policy engine, planner subscriber, 3 intersections, 3 feeds.
# Trigger an on-demand reroute+push with: python scripts/planner_run.py
# Stop everything with: scripts/stop_stack.sh
set +e
APP="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${ATSIGN_VENV:-$APP/.venv}"
SRC="$APP/smart-route-planning-agent/src"
# EE keystore lives in /tmp/eehome; production (vanity) uses the real ~/.atsign/keys.
# Only override HOME for the ee profile so vanity finds the real @intc_* keys.
if [ "${ATSIGN_PROFILE:-ee}" = "ee" ]; then
  export HOME="${HOME_OVERRIDE:-/tmp/eehome}"
fi
source "$VENV/bin/activate"
export PYTHONPATH="$SRC"
LOG=/tmp/stack; mkdir -p "$LOG"; : > "$LOG/pids"
cd "$SRC"

start() { echo "$!" >> "$LOG/pids"; }

python -u -m atsign.policy_engine --repeat 100000 --interval 30 > "$LOG/policy.log" 2>&1 & start
python -u "$APP/scripts/planner_service.py" > "$LOG/planner.log" 2>&1 & start

for r in intxn_market_st intxn_5th_ave intxn_broadway; do
  python -u -m atsign.publishers.intersection --role "$r" --count 100000 --interval 8 > "$LOG/$r.log" 2>&1 & start
done

for r in weather_feed traffic_trends_feed events_feed; do
  ( while true; do python -u -m atsign.publishers.feed --role "$r" --count 0 --interval 2 >> "$LOG/$r.log" 2>&1; sleep 30; done ) & start
done

echo "stack up — 8 services. logs: $LOG/*.log ; pids: $LOG/pids"
wait
