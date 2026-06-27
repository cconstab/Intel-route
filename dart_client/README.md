# dart_client — pure Dart `at_client` programs

The same encrypted JSON wire contract as the Python services (`smartroute` namespace).
Run from this directory with the EE keystore on `HOME`:

```bash
HOME=/tmp/eehome dart pub get   # first time
HOME=/tmp/eehome dart run bin/<program>.dart --atsign @bravo --root-domain vip.ve.atsign.zone
```

| Program | Role |
|---------|------|
| `bin/change_route.dart` | **Demo tool** — publishes a `live_traffic` incident to reroute the planner (`--density` >10 reroutes, `<=10` clears). The Dart twin of `scripts/trigger_incident.py`. |
| `bin/dart_publisher.dart` | Interop test — Dart → Python notify. |
| `bin/dart_subscriber.dart` | Interop test — receives + decrypts Python-published records. |

The two interop-test programs proved Python `atsdk` ⇄ Dart `at_client` encryption
interoperability (see `../validation/README.md`); `change_route.dart` is the live demo tool.
