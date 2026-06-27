# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Thin wrappers over the Python atSign SDK (atsdk) for this app's pub/sub.

AtPublisher.notify() and AtSubscriber.start() encapsulate the two Beta-SDK fixes
proven in the spike:
  1. set `metadata.iv_nonce` per notify (else AES-CTR crashes on a None nonce);
  2. pass a fresh `session_id` per notify (the SDK default is evaluated once at
     import, so the server would dedup identical-id notifications).
"""
import threading
import time
import uuid
from queue import Queue, Empty
from typing import Callable

from at_client import AtClient
from at_client.common import AtSign
from at_client.common.keys import SharedKey
from at_client.connections import Address
from at_client.connections.notification.atevents import AtEventType
from at_client.util.encryptionutil import EncryptionUtil

from atsign import roles


class AtPublisher:
    """Publishes encrypted records (notifications) to another atSign."""

    def __init__(self, atsign: str, root: str | None = None, verbose: bool = False):
        self.atsign = AtSign(atsign)
        self.client = AtClient(
            self.atsign,
            root_address=Address.from_string(root or roles.root()),
            verbose=verbose,
        )

    def notify(self, to: str, key_name: str, value: str,
               namespace: str | None = None, ttl_ms: int = 60_000) -> str:
        sk = SharedKey(key_name, self.atsign, AtSign(to))
        sk.set_namespace(namespace or roles.namespace())
        sk.set_time_to_live(ttl_ms)
        sk.metadata.iv_nonce = EncryptionUtil.generate_iv_nonce()   # fix #1
        return self.client.notify(sk, value, session_id=str(uuid.uuid4()))  # fix #2


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
                self.client.start_monitor(self.regex)  # blocks until the monitor dies
                print(f"[subscriber {self.atsign_str}] monitor ended; reconnecting in 3s", flush=True)
            except Exception as e:
                print(f"[subscriber {self.atsign_str}] monitor error: {e}; reconnecting in 3s", flush=True)
            time.sleep(3)

    def _consume(self):
        while self._running:
            try:
                ev = self.q.get(timeout=1.0)
            except Empty:
                continue
            client = self.client
            if client is None:
                continue
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
