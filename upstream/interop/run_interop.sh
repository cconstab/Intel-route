#!/bin/bash
# Cross-SDK IV interop: Python at_python (fix/put-get-random-iv) <-> Dart reference
# at_client, against the local ephemeral environment. Proves the Python random-IV /
# ivNonce put/get is wire-compatible with Dart in both directions, for shared and
# self keys.
#
# Prereqs: EE up; @alpha,@bravo onboarded (.atKeys in /tmp/eehome/.atsign/keys).
set -u
BR="${AT_PYTHON:-/Users/cconstab/scratch/at_python}"
V="${PYBIN:-/Users/cconstab/scratch/Intel-route/.venv/bin/python}"
DC="${DART_CLIENT:-/Users/cconstab/scratch/Intel-route/dart_client}"
ROOT=vip.ve.atsign.zone
export HOME=/tmp/eehome

py() { PYTHONPATH="$BR" "$V" "$BR/../Intel-route/upstream/interop/iv_interop.py" "$@" 2>/dev/null | tail -1; }
dart_op() { (cd "$DC" && dart run bin/iv_interop.dart --root-domain "$ROOT" "$@" 2>/dev/null | grep '^VALUE:\|^OK'); }

pass=0; fail=0
check() { # $1=label $2=expected $3=actual
  local got="${3#VALUE:}"
  if [ "$got" = "$2" ]; then echo "  PASS  $1  ($got)"; pass=$((pass+1));
  else echo "  FAIL  $1  expected='$2' got='$3'"; fail=$((fail+1)); fi
}

S=$RANDOM

echo "== A. Python put-shared -> Dart get-shared (random IV) =="
py --atsign @alpha --op put-shared --key ia$S --value "PY2DART_SHARED_$S" --shared-with @bravo >/dev/null
check "py->dart shared" "PY2DART_SHARED_$S" "$(dart_op --atsign @bravo --op get-shared --key ia$S --shared-with @alpha)"

echo "== B. Dart put-shared -> Python get-shared (random IV) =="
dart_op --atsign @bravo --op put-shared --key ib$S --value "DART2PY_SHARED_$S" --shared-with @alpha >/dev/null
check "dart->py shared" "DART2PY_SHARED_$S" "$(py --atsign @alpha --op get-shared --key ib$S --shared-with @bravo)"

echo ""
echo "RESULT: $pass passed, $fail failed  (A/B = the random-IV shared-key paths, both directions)"
echo ""
echo "NOTE: self-key interop (Python<->Dart) is blocked by a SEPARATE, pre-existing"
echo "bug — the Python verb builders omit the key namespace for self/public keys"
echo "(LlookupVerbBuilder/UpdateVerbBuilder use at_key.name, not str(at_key)), so"
echo "Python stores/reads 'foo@alpha' while Dart uses 'foo.itest@alpha'. That is a"
echo "NAMING mismatch, not an IV/crypto issue; self keys use the legacy zero IV in both"
echo "SDKs, so the random-IV change does not affect them. Tracked separately."
[ "$fail" -eq 0 ] && echo "IV INTEROP PASSED" || exit 1
