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

# Each service is registered by name so the check below can report it and tail its log
# (name.log). A service that dies at startup used to be invisible: the script announced
# "stack up" regardless, and a dead policy engine means no policy is ever applied.
declare -a STARTED=()
start() { echo "$!" >> "$LOG/pids"; STARTED+=("$1:$!"); }

python -u -m atsign.policy_engine --repeat 100000 --interval 30 > "$LOG/policy_engine.log" 2>&1 & start policy_engine
ENGINE_PID=$!  # checked below: without the engine there is no policy at all
python -u "$APP/scripts/planner_service.py" > "$LOG/planner.log" 2>&1 & start planner

for r in intxn_market_st intxn_5th_ave intxn_broadway; do
  python -u -m atsign.publishers.intersection --role "$r" --count 100000 --interval 8 > "$LOG/$r.log" 2>&1 & start "$r"
done

for r in weather_feed traffic_trends_feed events_feed; do
  ( while true; do python -u -m atsign.publishers.feed --role "$r" --count 0 --interval 2 >> "$LOG/$r.log" 2>&1; sleep 30; done ) & start "$r"
done

# operator console (Gradio) -> http://127.0.0.1:7865
python -u -m atsign.operator_console > "$LOG/operator.log" 2>&1 & start operator
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
     > "$LOG/policy_admin.log" 2>&1) & start policy_admin
  echo "policy admin    -> http://127.0.0.1:8090  ($ADMIN_AT)"
else
  echo "note: dart not on PATH — policy admin web UI not started"
fi

# Give each service long enough to authenticate before judging it.
sleep 12
failed=0
echo ""
echo "startup check:"
for entry in "${STARTED[@]}"; do
  name="${entry%%:*}"; pid="${entry##*:}"
  if kill -0 "$pid" 2>/dev/null; then
    echo "  ok      $name"
  else
    failed=$((failed + 1))
    echo "  FAILED  $name — last lines of $LOG/$name.log:"
    tail -6 "$LOG/$name.log" 2>/dev/null | sed 's/^/            /'
  fi
done
if [ "$failed" != "0" ]; then
  echo ""
  echo "WARNING: $failed service(s) did not survive startup (see above)." >&2
  if ! kill -0 "$ENGINE_PID" 2>/dev/null; then
    echo "  The policy engine is one of them, so no rule set is being published: the" >&2
    echo "  planner keeps whatever policy it last had, and the admin page waits forever." >&2
  fi
fi
echo ""
echo "stack up — ${#STARTED[@]} services, $((${#STARTED[@]} - failed)) alive."
echo "logs: $LOG/*.log ; pids: $LOG/pids  (blocks; run with '&')"
wait
