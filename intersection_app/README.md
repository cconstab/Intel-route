# Intersection sensor app (Android / iOS)

Turns a phone into a **traffic intersection sensor**: the camera counts model cars
on-device and publishes encrypted `live_traffic.smartroute` reports to the route
planner as the phone's own atSign — the same record
[`dart_client/bin/change_route.dart`](../dart_client/bin/change_route.dart) and the
Python publishers send. The phone opens **no inbound ports**; video never leaves the
device, only a small encrypted count.

```
camera → on-device detection → count → density → notify(encrypted) → @planner
```

## Build / run

```bash
cd intersection_app
flutter pub get
flutter run            # a physical device is required — the camera and ML Kit
                       # do not work in a simulator
```

Sign in with the atSign that represents this intersection (e.g. `@bravo` in the test
environment, or one of your registered `@…intxn_*` atSigns), choosing the matching
**root server** in the sign-in dialog — `root.atsign.org` for production or
`vip.ve.atsign.zone:64` for the local ephemeral environment.

## Making a reroute actually happen

Two settings matter, both under the **tune** icon:

1. **Location** — the planner only reacts to congestion at a **trackpoint of the route
   it is currently planning**. Leave this on the default
   `berkeley-oakland-i880 (midpoint — proven)` preset; a report anywhere else is
   delivered and then ignored.
2. **Density per detected car** (default 6) — the planner reroutes above a density of
   **10**, so a couple of model cars needs a multiplier to cross it. 2 cars × 6 = 12 →
   reroute.

Turn **Reporting** on and the app sends every few seconds. Each report carries a
60 s TTL, so when you take the cars away the planner's cache expires and the route
reverts by itself. **Clear** sends a density of 0 immediately.

Watch the effect on the operator console (`http://127.0.0.1:7865`), the commuter app,
or in `/tmp/stack/planner.log`.

## Detection notes (read before demoing)

Detection uses [`flutter_smart_scanner`](https://pub.dev/packages/flutter_smart_scanner),
a wrapper over Google ML Kit's object detector (stream mode, multiple objects,
tracking). Two honest caveats:

- **ML Kit's base model classifies coarsely** — "Home good", "Fashion good",
  "Unknown" — so it will rarely label a model car *"car"*. The signal we use is
  therefore the **count of tracked objects**, which is exactly what a junction camera
  contributes (vehicle density). "Require a vehicle label" is off by default for this
  reason; turn it on only with a vehicle-aware model (see below).
- **Counts flicker** as the tracker drops and re-acquires objects, so the reported
  count is the **maximum over a 2 s window** — a briefly occluded car still counts.

To get a true `car` class, swap the detector for a COCO/YOLO model (e.g.
`ultralytics_yolo`) and keep everything else: only the input to
`car_counter.dart` changes, and the label filter then becomes meaningful.

## Layout

| File | Role |
|---|---|
| `lib/main.dart` | App shell + atSign/root-server sign-in gate |
| `lib/sensor_page.dart` | Camera, live readout, settings, publish controls |
| `lib/traffic_report.dart` | The wire contract (AtKey + payload) — Flutter-free |
| `lib/car_counter.dart` | Confidence filter, optional label gate, window smoothing |
| `test/traffic_report_test.dart` | Pins the payload/key contract to `change_route.dart` |

`flutter test` runs the contract tests with no device attached.
