# Getting Started — running on real (production) atSigns

How to run the Smart Route Planning system on **real, registered atSigns** against the
production root (`root.atsign.org`), instead of the local ephemeral environment (EE).

The good news: **the application code does not change.** You switch *which identities* and
*which root server* via one environment variable. This guide covers the operational steps
that differ from the EE.

> For the EE/dev path see [README.md](README.md). For why/what, see [RESULTS.md](RESULTS.md).

---

## EE vs production — what actually differs

| | EE / dev | Production |
|---|---|---|
| Profile | `ATSIGN_PROFILE=ee` (default) | `ATSIGN_PROFILE=vanity` |
| Root server | `vip.ve.atsign.zone:64` (local) | `root.atsign.org:64` (auto via profile) |
| atSigns | NATO test atSigns minted by the EE | **your registered atSigns** |
| Onboarding | `scripts/onboard_all_ee.py` (CRAM from container) | `at_activate` per atSign (OTP from registrar) |
| Keystore | isolated `HOME=/tmp/eehome` | real `~/.atsign/keys/` |
| TLS relax (`/tmp/ee_site`) | required (EE self-signed cert) | **DO NOT USE** (real cert validates) |
| `--add-host` / EE container | required | not used |

---

## 1. Prerequisites

- **Python 3.13** — create the venv and install deps (one time, from the repo root):
  ```bash
  cd /path/to/Intel-route
  python3 -m venv .venv
  . .venv/bin/activate
  pip install "atsdk>=0.2.70" pydantic "langgraph==1.0.9" gpxpy "folium==0.14.0" "gradio>=6.7.0"
  ```
- **Dart ≥ 3.5 / Flutter ≥ 3.41** (for the commuter app, the policy admin, and route tooling).
- **The Atsign onboarding CLI** (provides `at_activate`):
  ```bash
  dart pub global activate at_onboarding_cli
  # ensure it's on PATH:  export PATH="$PATH:$HOME/.pub-cache/bin"
  ```

> In later steps `. .venv/bin/activate` reuses the venv created here.

## 2. Obtain your atSigns

Get atSigns at **https://my.atsign.com** (free starter-pack atSigns are random words;
paid atSigns can be custom). You need **one atSign per role you intend to run**. The full
set is 12 (see the role table below) — but you can start smaller and scale up:

> Minimum useful set: planner, one intersection, operator, commuter, policy, policy-admin.

## 3. Activate each atSign → `.atKeys`

Activate every atSign **once** to produce its `.atKeys` file (CRAM/OTP comes from the email
you registered with):

```bash
at_activate -a @your_planner_atsign           # root.atsign.org is the default
# enter the OTP from the registration email when prompted
# → writes ~/.atsign/keys/@your_planner_atsign_key.atKeys
```

Repeat for each atSign. Keys land in `~/.atsign/keys/` (the real keystore — **not**
`/tmp/eehome`). The headless services and the policy admin read from there automatically.

## 4. Map roles → your atSigns

Edit the **`vanity`** entries in [`config/ee_atsigns.json`](config/ee_atsigns.json) to your
actual registered atSigns (the `ee` column is for the local test env — leave it):

```jsonc
"roles": {
  "planner":        { "ee": "@alpha",  "vanity": "@your_planner_atsign" },
  "intxn_market_st":{ "ee": "@bravo",  "vanity": "@your_intersection_1" },
  ...
}
```
`rootDomains.vanity` is already `root.atsign.org:64`, so the production root is selected
automatically when you run with `ATSIGN_PROFILE=vanity`.

## 5. Run the services (production)

Set the profile and use the real keystore — **no EE hacks** (no `/tmp/ee_site`, no
`HOME=/tmp/eehome`, no `--add-host`, no EE container):

```bash
. .venv/bin/activate
export ATSIGN_PROFILE=vanity
export PYTHONPATH=$PWD/smart-route-planning-agent/src
# HOME stays your normal home so keys resolve from ~/.atsign/keys

# bring the stack up — includes the operator console and (if dart is installed)
# the policy admin web UI:
bash scripts/start_stack.sh &
# operator console -> http://127.0.0.1:7865 · policy admin -> http://127.0.0.1:8090
```

The script prints `profile=vanity keystore=... (N .atKeys)` on startup and **refuses to
start** if the keystore is empty (the usual cause: `ATSIGN_PROFILE` not exported — e.g.
after a reboot).

### After a reboot

A fresh shell has **none** of the exports above — rerun all of them, every time:

```bash
cd ~/Intel-route
. .venv/bin/activate
export ATSIGN_PROFILE=vanity
export PYTHONPATH=$PWD/smart-route-planning-agent/src
bash scripts/start_stack.sh &      # note the '&' — the script blocks by design
tail -f /tmp/stack/planner.log     # confirm: profile=vanity, then steady planning lines
```

Tip: put the three `export`/`activate` lines in `~/.bashrc` (or a `prod-env.sh` you
source) so a reboot can't silently drop you back into `ee` mode. To start on boot
automatically, run the stack under systemd or cron `@reboot` with the same env.

In production each role typically runs on its **own machine** behind its **own atSign**,
with only that atSign's `.atKeys` present — still zero inbound ports. See
[`deploy/compose.yaml`](deploy/compose.yaml) (one container per role; set
`ATSIGN_PROFILE=vanity`).

## 6. Policy admin (web)

Started automatically by `start_stack.sh` (log: `/tmp/stack/policy_admin.log`). To run
it standalone:

```bash
cd dart_client
export ATSIGN_PROFILE=vanity     # <-- REQUIRED: makes the Dart tools use the vanity atSigns
dart run bin/policy_admin.dart --atsign @your_policy_admin_atsign --root-domain root.atsign.org
# -> http://127.0.0.1:8090  (startup line should read: profile=vanity, engine=@your_policy_atsign)
```

> The Dart tools honor `ATSIGN_PROFILE` too. **Without it they default to `ee`** and will
> target the local test engine (`@juliet`) — which on the production root comes back
> `undelivered`. Always export `ATSIGN_PROFILE=vanity` for production.

## 7. Commuter Flutter app

```bash
cd commuter_app && flutter run
```
At sign-in: pick the **root.atsign.org (production)** root server, enter your commuter
atSign, and load its `.atKeys` (the app's `.atKeys` file login). It will then receive live
routes and reroute alerts.

## 8. Verify

```bash
cd dart_client
export ATSIGN_PROFILE=vanity     # --to defaults to the vanity planner from config
dart run bin/change_route.dart --atsign @your_intersection_1 --root-domain root.atsign.org --density 30
```
The operator console map should reroute within ~8s; the commuter app shows a 🚨 reroute
alert; `--density 0` clears it (auto-clears after ~60s TTL).

---

## Production hardening (do before a real pilot)

- **Key custody:** decide who owns the org atSigns; back up `.atKeys` securely; plan rotation.
  `.atKeys` are the credential — treat them like private keys.
- **Admin authorization:** the engine trusts a record *from* the policy-admin atSign
  (cryptographically sound — only that atSign can send as itself). Add an **allow-list of
  admin atSigns** and use **APKAM enrollment** for the admin's devices.
- **atsdk:** use **>= 0.2.70** — it carries the upstreamed correctness fixes (notify
  iv_nonce/session_id, shared-key detection, disconnect state, random IVs on put/get).
  Keep the resilience hardening in this repo (rebuild-and-retry publisher, monitor-resume
  subscriber, console watchdog) — those failure modes are not yet fixed upstream.
- **Policy store:** swap the atKeys-backed `PolicyStore` for the database-backed
  implementation (interface is in `policy_engine.py`) if you want audit/scale.
- **Legacy bridging:** if real intersection hardware still exposes a REST API, front it with
  **NoPorts** (Path A) so it has no open inbound ports.
- **TTLs:** tune `LIVE_TRAFFIC_TTL_S` / `CONDITIONS_TTL_S` in `cache.py` for your data rates.

## Role → atSign reference

| Role (config key) | Purpose |
|---|---|
| `planner` | Headless route planner (LangGraph) |
| `intxn_market_st` / `intxn_5th_ave` / `intxn_broadway` / `intxn_downtown` | Intersection agents (live traffic) |
| `weather_feed` / `traffic_trends_feed` / `events_feed` | Conditions feeds |
| `operator` | Operator console (web) |
| `policy` | Policy engine (default-deny authorization) |
| `policy_admin` | Policy admin (web; governs access) |
| `commuter01` | Commuter (mobile app) |

## Do NOT carry over from the EE

- ❌ `PYTHONPATH=/tmp/ee_site` (TLS-relax `sitecustomize.py`) — production certs are valid.
- ❌ `HOME=/tmp/eehome` — use the real `~/.atsign/keys`.
- ❌ `--add-host vip.ve.atsign.zone:127.0.0.1` and the `atsigncompany/ephemeral` container.
- ❌ `scripts/onboard_all_ee.py` (CRAM-from-container) — use `at_activate` instead.
