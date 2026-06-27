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
    """Subscribes to a namespace/regex; calls on_record(from_atsign, key, value, raw)."""

    def __init__(self, atsign: str, regex: str,
                 on_record: Callable[[str, str, str, dict], None],
                 root: str | None = None, verbose: bool = False):
        self.q: Queue = Queue()
        self.atsign = AtSign(atsign)
        self.client = AtClient(
            self.atsign,
            root_address=Address.from_string(root or roles.root()),
            queue=self.q,
            verbose=verbose,
        )
        self.regex = regex
        self.on_record = on_record
        self._running = False

    def start(self):
        """Start the consumer thread, then block on the monitor."""
        self._running = True
        threading.Thread(target=self._consume, daemon=True).start()
        self.client.start_monitor(self.regex)  # blocks

    def _consume(self):
        while self._running:
            try:
                ev = self.q.get(timeout=1.0)
            except Empty:
                continue
            self.client.handle_event(self.q, ev)  # decrypts -> re-enqueues DECRYPTED_*
            if ev.event_type != AtEventType.DECRYPTED_UPDATE_NOTIFICATION:
                continue
            d = ev.event_data
            key = d.get("key", "")
            if roles.namespace() not in key:
                continue
            from_atsign = "@" + key.split("@")[-1] if "@" in key else d.get("from", "")
            self.on_record(from_atsign, key, str(d.get("decryptedValue", "")), d)
