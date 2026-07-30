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

## How detection works

We own the camera pipeline (`camera` + ML Kit) rather than using a pre-built scanner
widget, because two models have to see each frame:

| Model | Gives us | Used for |
|---|---|---|
| ML Kit **object detector** (stream, multi-object, tracking) | bounding boxes | the **count** → traffic density |
| ML Kit **image labeler** (base model, 400+ labels) | semantic labels — `Vehicle`, `Car`, `Wheel`, `Toy`… | the **gate**: are we even looking at cars? |

The object detector alone was not enough: its base model only returns coarse
categories (`Home good`, `Fashion good`, `Unknown`) and never says "car", so a desk
full of mugs read as congestion. The labeler supplies the missing semantics, and
**"Only count when a vehicle is recognised"** (on by default) makes objects count only
while a vehicle-ish label is present. The readout shows the live gate state and the
top labels, so you can see exactly what the model thinks.

Neither model ships as an asset — nothing to license or bundle. Frames are sampled
(every 6th by default) and skipped while inference is busy, so the preview stays
smooth.

### If you want true per-object car labels

This pipeline makes both upgrades possible, in increasing order of effort:

1. **Custom TFLite classifier** via `LocalObjectDetectorOptions(modelPath: ...)` —
   ML Kit then classifies each detected box with your model, giving per-object "car"
   labels. Choose a permissively licensed model (e.g. an EfficientDet-Lite or
   MobileNet variant, Apache-2.0).
2. **A COCO/YOLO detector** (e.g. `ultralytics_yolo`) — best accuracy, real `car`,
   `truck`, `bus` classes. **Licensing caveat:** Ultralytics YOLOv8/v11 are
   **AGPL-3.0**, which is usually unsuitable for a commercial product without a
   commercial licence. Check before shipping.

Either way only the detector changes: `car_counter.dart` consumes
`List<Detection>(label, confidence)`, and the report/publish path is untouched.

## Layout

| File | Role |
|---|---|
| `lib/main.dart` | App shell + atSign/root-server sign-in gate |
| `lib/sensor_page.dart` | Camera preview, live readout, settings, publish controls |
| `lib/vehicle_detector.dart` | Camera → ML Kit object detection + image labeling |
| `lib/traffic_report.dart` | The wire contract (AtKey + payload) — Flutter-free |
| `lib/car_counter.dart` | Confidence filter, optional label gate, window smoothing |
| `test/traffic_report_test.dart` | Pins the payload/key contract to `change_route.dart` |

`flutter test` runs the contract tests with no device attached.
