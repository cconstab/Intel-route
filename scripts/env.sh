# Source this from the repo root to set up a terminal for running the system:
#     source scripts/env.sh
#
# Sets: the project .venv, the EE keystore (HOME), and PYTHONPATH for the app.
# Tip: use a dedicated terminal — this points HOME at the test keystore.
_REPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
source "$_REPO/.venv/bin/activate"
export HOME=/tmp/eehome                                   # EE test atKeys live here
export PYTHONPATH="$_REPO/smart-route-planning-agent/src"
echo "env ready: .venv active | HOME=$HOME | PYTHONPATH set"
echo "try:  python scripts/planner_run.py   |   bash scripts/run_demo.sh"
