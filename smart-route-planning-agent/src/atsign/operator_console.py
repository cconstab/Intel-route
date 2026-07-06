# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Operator console (runs as the operator atSign, e.g. @route_operator / EE @hotel).

Reuses Intel's Gradio UI patterns + `MapCreator` (Folium) renderer, but its data
source is the planner's pushed `status`/`route` notifications (atSign subscription)
instead of the in-process agent queue. This is the city control-room view.

The Gradio import is guarded so the data + map-render path can be unit-tested
without Gradio installed. Run the full UI with:  python -m atsign.operator_console
"""
import json
import threading
import time
import warnings

# Gradio polls its queue endpoint ~1/s; each poll touches a Starlette symbol that
# now emits a DeprecationWarning (Gradio/Starlette version mismatch, not our code).
# Silence just that message so the console stays readable.
warnings.filterwarnings("ignore", message=r".*HTTP_422_UNPROCESSABLE_ENTITY.*")

import folium
from branca.element import Figure

from atsign import roles, wire
from atsign.atsign_io import AtSubscriber
from utils.map_creator import MapCreator
from utils.logging_config import get_logger

logger = get_logger(__name__)
PLANNER = roles.atsign_for("planner")


class OperatorState:
    """Latest network status + route geometry pushed by the planner."""

    def __init__(self):
        self.status: dict = {}
        self.points: list = []
        self.lock = threading.Lock()

    def update_status(self, d: dict):
        with self.lock:
            self.status = d

    def update_route(self, d: dict):
        with self.lock:
            self.points = d.get("points", [])

    def snapshot(self):
        with self.lock:
            return dict(self.status), list(self.points)


STATE = OperatorState()
_map = MapCreator()


_last_rx = time.monotonic()   # last time ANY record arrived from the planner
_subscriber = None            # the current AtSubscriber (so the watchdog can retire it)

# The operator console is the one component on atsdk's Beta monitor, which can wedge
# (a silently dropped socket leaves readline() blocked, so start()'s reconnect loop
# never fires). The planner pushes every ~8s, so prolonged silence == a dead monitor.
# The watchdog recreates the subscriber on silence, regardless of the failure mode.
SILENCE_S = 45
WATCHDOG_EVERY_S = 15


def _on_record(frm, key, value, raw):
    if frm != PLANNER:
        return
    global _last_rx
    _last_rx = time.monotonic()
    kn = wire.key_name_from_atkey(key)
    if kn == "status":
        d = json.loads(value)
        STATE.update_status(d)
        if d.get("points"):
            STATE.update_route(d)  # status carries the optimal-route geometry
        print(f"[operator] status received: route={d.get('optimal_route')} "
              f"rerouted={d.get('rerouted')} pts={len(d.get('points', []))}", flush=True)
    elif kn == "route":
        STATE.update_route(json.loads(value))
        print("[operator] route geometry received", flush=True)


def _spawn_subscriber(me):
    global _subscriber
    _subscriber = AtSubscriber(me, roles.namespace(), _on_record)
    _subscriber.start()  # blocks (runs in its own thread)


def _recreate_subscriber(me):
    global _last_rx
    old = _subscriber
    if old is not None:
        try:
            old.stop()  # retire the wedged one so we don't leak its threads
        except Exception:
            pass
    _last_rx = time.monotonic()  # grace period before the watchdog checks again
    threading.Thread(target=lambda: _spawn_subscriber(me), daemon=True).start()


def _watchdog_tick(me) -> bool:
    """One watchdog check: recreate the subscriber if it's been silent too long.

    Returns True if it recreated. Split out from the loop so it's unit-testable.
    """
    if time.monotonic() - _last_rx <= SILENCE_S:
        return False
    print(f"[operator] watchdog: no records for >{SILENCE_S}s — recreating subscriber",
          flush=True)
    _recreate_subscriber(me)
    return True


def _watchdog(me):
    while True:
        time.sleep(WATCHDOG_EVERY_S)
        _watchdog_tick(me)


def start_subscriber():
    global _last_rx
    me = roles.atsign_for("operator")
    _last_rx = time.monotonic()
    threading.Thread(target=lambda: _spawn_subscriber(me), daemon=True).start()
    threading.Thread(target=lambda: _watchdog(me), daemon=True).start()
    return me


_MAP_HEIGHT = 660
_last_map_key = None
_last_map_html = ""


def render_map_html() -> str:
    """Render the current route on a tall Folium map that fits the whole route.

    Cached by route signature: when the route hasn't changed the SAME html string is
    returned, so the Gradio refresh doesn't reload/resize the map (no flicker, view
    stays put). Reuses Intel's MapCreator for the styled route line.
    """
    global _last_map_key, _last_map_html
    _, points = STATE.snapshot()
    if not points:
        return (f"<div style='height:{_MAP_HEIGHT}px;display:flex;align-items:center;"
                "justify-content:center;color:#666;font-size:18px'>"
                "Waiting for a route from the planner…</div>")

    key = (len(points), tuple(points[0]), tuple(points[-1]))
    if key == _last_map_key:
        return _last_map_html  # unchanged -> identical html -> no map reload

    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    fig = Figure(height=f"{_MAP_HEIGHT}px")
    m = folium.Map(location=[sum(lats) / len(lats), sum(lons) / len(lons)],
                   zoom_start=10, tiles="OpenStreetMap")
    _map.add_route_line(m, points, "#13B513", "Optimal route (live, pushed)")
    folium.Marker(points[0], tooltip="Start", icon=folium.Icon(color="blue")).add_to(m)
    folium.Marker(points[-1], tooltip="Destination", icon=folium.Icon(color="red")).add_to(m)
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])  # show the whole route
    fig.add_child(m)

    _last_map_key = key
    _last_map_html = fig._repr_html_()
    return _last_map_html


def status_markdown() -> str:
    s, points = STATE.snapshot()
    if not s:
        return "### Operator Console\nWaiting for status from the planner…"
    alert = "## 🚨 REROUTE\n" if s.get("rerouted") else "## ✅ Monitoring\n"
    return (
        f"{alert}"
        f"**Optimal route:** {s.get('optimal_route')} ({s.get('distance_km', 0):.1f} km)\n\n"
        f"**Agent status:** {s.get('agent_status')}\n\n"
        f"**Reason:** {s.get('reason')}\n\n"
        f"**Intersections:** {s.get('intersections')}\n\n"
        f"**Route points:** {len(points)}"
    )


def build_ui():
    import gradio as gr  # guarded — only needed to actually launch the console

    with gr.Blocks(title="Route Operator Console", fill_width=True) as app:
        gr.Markdown("# Route Operator Console — control room (live via atSign)")
        status = gr.Markdown(status_markdown())
        map_html = gr.HTML(render_map_html())  # full width, tall map below the status
        gr.Timer(3).tick(lambda: (status_markdown(), render_map_html()),
                         outputs=[status, map_html])
    return app


def main():
    me = start_subscriber()
    print(f"[operator-console] {me} subscribed; launching Gradio UI…")
    build_ui().launch(server_name="0.0.0.0", server_port=7865)


if __name__ == "__main__":
    main()
