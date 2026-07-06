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
# Fail fast if the keystore is empty — the #1 post-reboot trap: a fresh shell has no
# ATSIGN_PROFILE, so we default to ee -> HOME=/tmp/eehome, which reboots wipe.
KEYS_DIR="$HOME/.atsign/keys"
KEY_COUNT=$(ls "$KEYS_DIR"/*.atKeys 2>/dev/null | wc -l | tr -d ' ')
echo "profile=${ATSIGN_PROFILE:-ee}  keystore=$KEYS_DIR  (${KEY_COUNT} .atKeys)"
if [ "$KEY_COUNT" = "0" ]; then
  echo "ERROR: no .atKeys in $KEYS_DIR — refusing to start a stack that cannot authenticate." >&2
  echo "  production:  export ATSIGN_PROFILE=vanity   (keys live in ~/.atsign/keys)" >&2
  echo "  local EE:    start the EE container and re-onboard (reboot wiped /tmp/eehome)" >&2
  exit 1
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

# operator console (Gradio) -> http://127.0.0.1:7865
python -u -m atsign.operator_console > "$LOG/operator.log" 2>&1 & start
echo "operator console -> http://127.0.0.1:7865"

# policy admin web UI (Dart) -> http://127.0.0.1:8090 — skipped if dart isn't installed
if command -v dart >/dev/null 2>&1; then
  PROFILE="${ATSIGN_PROFILE:-ee}"
  read -r ADMIN_AT ROOT_DOM < <(python3 -c "
import json
c = json.load(open('$APP/config/ee_atsigns.json'))
print(c['roles']['policy_admin']['$PROFILE'], c['rootDomains']['$PROFILE'].split(':')[0])")
  (cd "$APP/dart_client" && \
   dart run bin/policy_admin.dart --atsign "$ADMIN_AT" --root-domain "$ROOT_DOM" \
     > "$LOG/policy_admin.log" 2>&1) & start
  echo "policy admin    -> http://127.0.0.1:8090  ($ADMIN_AT)"
else
  echo "note: dart not on PATH — policy admin web UI not started"
fi

echo "stack up — 10 services. logs: $LOG/*.log ; pids: $LOG/pids  (blocks; run with '&')"
wait
