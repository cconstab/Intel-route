# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Thin wrappers over the Python atSign SDK (atsdk) for this app's pub/sub.

Requires atsdk >= 0.2.70 (which fixed notify() iv_nonce/session_id, shared-key
notification detection, and disconnect state upstream). What remains here is
RESILIENCE the SDK does not provide: publisher rebuild-and-retry, subscriber
monitor-resume across reconnects, and first-contact shared-key pre-warm.
"""
import threading
import time
from queue import Queue, Empty
from typing import Callable

from at_client import AtClient
from at_client.common import AtSign
from at_client.common.keys import SharedKey
from at_client.connections import Address
from at_client.connections.atmonitorconnection import AtMonitorConnection
from at_client.connections.notification.atevents import AtEventType
from at_client.util.authutil import AuthUtil

from atsign import roles


class AtPublisher:
    """Publishes encrypted records (notifications) to another atSign.

    Resilient: a long-lived publisher's connection/key-cache can go bad after a while
    ("Failed to decrypt shared_key..." on notify). On a notify failure we rebuild the
    AtClient once (fresh connection + key cache) and retry, so the planner keeps
    pushing instead of erroring every cycle until restart.
    """

    def __init__(self, atsign: str, root: str | None = None, verbose: bool = False):
        self.atsign = AtSign(atsign)
        self._root = root or roles.root()
        self._verbose = verbose
        self.client = self._new_client()

    def _new_client(self) -> AtClient:
        return AtClient(
            self.atsign,
            root_address=Address.from_string(self._root),
            verbose=self._verbose,
        )

    def notify(self, to: str, key_name: str, value: str,
               namespace: str | None = None, ttl_ms: int = 60_000) -> str:
        last: Exception | None = None
        for attempt in range(2):
            try:
                sk = SharedKey(key_name, self.atsign, AtSign(to))
                sk.set_namespace(namespace or roles.namespace())
                sk.set_time_to_live(ttl_ms)
                # atsdk >= 0.2.70 generates a fresh iv_nonce and session_id per call.
                return self.client.notify(sk, value)
            except Exception as e:
                last = e
                if attempt == 0:
                    print(f"[publisher {self.atsign}] notify to {to} failed ({e}); "
                          f"rebuilding client and retrying", flush=True)
                    time.sleep(1)  # let the old connection settle before a fresh one
                    try:
                        self.client = self._new_client()
                    except Exception as ce:
                        print(f"[publisher {self.atsign}] reconnect failed: {ce}", flush=True)
                        raise
        raise last  # type: ignore[misc]


class AtSubscriber:
    """Subscribes to a namespace/regex; calls on_record(from_atsign, key, value, raw).

    Resilient: the atsdk monitor can drop (lost heartbeats) and fail to self-recover
    (`Bad file descriptor`). `start()` therefore loops — it recreates the AtClient and
    restarts the monitor whenever it dies, so subscribers keep receiving indefinitely.
    """

    def __init__(self, atsign: str, regex: str,
                 on_record: Callable[[str, str, str, dict], None],
                 root: str | None = None, verbose: bool = False):
        self.q: Queue = Queue()
        self.atsign_str = atsign
        self.regex = regex
        self.on_record = on_record
        self.root = root or roles.root()
        self.verbose = verbose
        self._running = False
        self.client: AtClient | None = None
        # Highest notification epoch (ms) we've processed. On reconnect we resume the
        # monitor from here (monitor:<epoch> <regex>) instead of the SDK default of 0 —
        # so a notification that arrived during the disconnect window is replayed exactly
        # once, and we don't re-stream the entire retained backlog (which caused flapping).
        self._last_epoch = 0
        # First notification from a never-seen sender can arrive before that sender's
        # shared key has propagated to us; the SDK then fails to decrypt (NoneType) and
        # silently drops it. We pre-resolve the shared key with a short retry so the
        # first record from a new publisher isn't lost (no "send it twice to wake it up").
        self._key_retries = 4
        self._key_backoff_s = 1.5

    def _start_monitor_resuming(self):
        """Build the monitor connection with our resume position, then run it (blocks).

        Mirrors AtClient.start_monitor's own construct+connect+auth, but seeds
        `last_received_time` first so the monitor verb resumes from where we left off.
        """
        client = self.client
        mc = AtMonitorConnection(
            queue=self.q, atsign=client.atsign, address=client.secondary_address,
            verbose=self.verbose, regex=self.regex,
        )
        mc.last_received_time = self._last_epoch  # 0 on first connect; last-seen epoch after
        mc.connect()
        AuthUtil.authenticate_with_pkam(mc, client.atsign, client.keys)
        client.monitor_connection = mc
        client.start_monitor(self.regex)  # sees monitor_connection != None -> just runs it; blocks

    def stop(self):
        """Stop the loops and force-close the monitor socket.

        Setting _running=False makes the start()/consume loops exit on their next turn;
        closing the monitor connection unblocks a readline() that's stuck on a silently
        dropped socket. Used by callers (e.g. the operator console watchdog) to retire a
        wedged subscriber before spawning a fresh one, without leaking its threads.
        """
        self._running = False
        try:
            if self.client is not None:
                self.client.stop_monitor()
        except Exception:
            pass
        try:
            if self.client is not None and self.client.monitor_connection is not None:
                self.client.monitor_connection.disconnect()
        except Exception:
            pass

    def start(self):
        """Start one consumer thread, then (re)connect + monitor in a loop forever."""
        self._running = True
        threading.Thread(target=self._consume, daemon=True).start()
        while self._running:
            try:
                self.client = AtClient(
                    AtSign(self.atsign_str),
                    root_address=Address.from_string(self.root),
                    queue=self.q,
                    verbose=self.verbose,
                )
                resume = f" (resuming from epoch {self._last_epoch})" if self._last_epoch else ""
                print(f"[subscriber {self.atsign_str}] monitor starting{resume}", flush=True)
                self._start_monitor_resuming()  # blocks until the monitor dies
                print(f"[subscriber {self.atsign_str}] monitor ended; reconnecting in 3s", flush=True)
            except Exception as e:
                print(f"[subscriber {self.atsign_str}] monitor error: {e}; reconnecting in 3s", flush=True)
            time.sleep(3)

    def _ensure_shared_key(self, client, ev):
        """Resolve (and cache) the sender's shared key, retrying while it propagates.

        handle_event fetches this key via `get_encryption_key_shared_by_other`; if the
        sender's shared key isn't on our server yet (first contact), it raises and the
        SDK swallows the notification. Pre-resolving here populates `client.keys` so the
        subsequent handle_event decrypts on its first attempt.
        """
        try:
            key = ev.event_data.get("key", "")
        except AttributeError:
            return
        if roles.namespace() not in key:
            return
        try:
            sk = SharedKey.from_string(key=key)
        except Exception:
            return  # not a shared-key notification; nothing to pre-resolve
        # Already cached? then there's nothing to do.
        try:
            if client.keys.get(sk.get_shared_shared_key_name()) is not None:
                return
        except Exception:
            pass
        for attempt in range(self._key_retries):
            try:
                client.get_encryption_key_shared_by_other(sk)  # caches into client.keys
                if attempt:
                    print(f"[subscriber {self.atsign_str}] shared key for {key} "
                          f"resolved on retry {attempt}", flush=True)
                return
            except Exception as e:
                if attempt == self._key_retries - 1:
                    print(f"[subscriber {self.atsign_str}] shared key for {key} "
                          f"still unavailable after {self._key_retries} tries: {e}", flush=True)
                    return
                time.sleep(self._key_backoff_s)

    def _consume(self):
        while self._running:
            try:
                ev = self.q.get(timeout=1.0)
            except Empty:
                continue
            client = self.client
            if client is None:
                continue
            # Track the newest epoch we've seen so a reconnect resumes from here.
            # The raw UPDATE/DELETE notification carries epochMillis (the decrypted
            # re-enqueued event may not), so capture it before handling.
            try:
                em = ev.event_data.get("epochMillis") if isinstance(ev.event_data, dict) else None
                if em is not None and int(em) > self._last_epoch:
                    self._last_epoch = int(em)
            except (ValueError, TypeError):
                pass
            # Pre-warm the sender's shared key so handle_event decrypts first-try
            # (avoids the swallowed NoneType decrypt drop on a new sender's first record).
            if ev.event_type == AtEventType.UPDATE_NOTIFICATION:
                self._ensure_shared_key(client, ev)
            try:
                client.handle_event(self.q, ev)  # decrypts -> re-enqueues DECRYPTED_*
                if ev.event_type != AtEventType.DECRYPTED_UPDATE_NOTIFICATION:
                    continue
                d = ev.event_data
                key = d.get("key", "")
                if roles.namespace() not in key:
                    continue
                from_atsign = "@" + key.split("@")[-1] if "@" in key else d.get("from", "")
                self.on_record(from_atsign, key, str(d.get("decryptedValue", "")), d)
            except Exception as e:
                print(f"[subscriber {self.atsign_str}] consume error: {e}", flush=True)
