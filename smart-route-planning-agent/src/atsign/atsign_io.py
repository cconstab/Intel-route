# Copyright (C) 2026 / Atsign migration
# SPDX-License-Identifier: Apache-2.0
"""
Thin wrappers over the Python atSign SDK (atsdk) for this app's pub/sub.

Requires atsdk >= 0.2.71. What remains here is RESILIENCE the SDK does not provide:
bounded socket reads, publisher rebuild-and-retry, a monitor liveness watchdog, and
first-contact shared-key pre-warm.

Why bounded reads and a watchdog: the SDK connects with `settimeout(None)` and reads
a byte at a time, so when a peer goes silent WITHOUT closing the connection — a
network change, NAT/firewall timeout, laptop sleep, a frozen server — reads block
forever and no exception is ever raised. Reconnect logic that waits for an error
therefore never runs: a publisher hangs mid-notify (freezing its caller's loop) and
a monitor stops delivering without ever reporting a failure.
"""
import socket
import threading
import time
from queue import Queue, Empty
from typing import Callable

from at_client import AtClient
from at_client.common import AtSign
from at_client.common.keys import SharedKey
from at_client.connections import Address
from at_client.connections.atconnection import AtConnection
from at_client.connections.notification.atevents import AtEventType

from atsign import roles


def _discard_connection_on_abandoned_read() -> None:
    """Never leave a connection holding a reply nobody read.

    If a command is sent and its reply is not fully read — a read timeout, or any error
    while reading — that reply stays queued on the socket. The next command then gets
    the PREVIOUS command's answer, and every command after it is one reply behind. That
    is worse than an error: a lookup can return a different record's value and succeed,
    so we could encrypt to the wrong recipient's shared key without anything raising.

    This is at_python PR #545, merged upstream on 2026-07-30 but not in a release yet
    (v0.2.71 predates it). Applied here until a release > v0.2.71 ships; removing it
    afterwards is safe either way, because disconnecting twice is a no-op.
    """
    if getattr(AtConnection, "_discards_on_abandoned_read", False):
        return
    original_read = AtConnection.read

    def read(self):
        try:
            return original_read(self)
        except Exception:
            try:
                self.disconnect()
            except Exception:
                pass
            raise

    AtConnection.read = read
    AtConnection._discards_on_abandoned_read = True


_discard_connection_on_abandoned_read()

# Command/response round trips are fast; well past this the socket is not coming back.
COMMAND_READ_TIMEOUT_S = 15.0
# Creating a client does a root lookup, a TLS connect and PKAM auth. Against an
# unresponsive peer each of those would otherwise block forever.
CONNECT_TIMEOUT_S = 15.0
# A publish must never freeze its caller's loop: the SDK can block indefinitely in
# code we cannot bound from here (see AtPublisher.notify).
PUBLISH_DEADLINE_S = 25.0
# The SDK heartbeats the monitor every ~30s and its acks arrive as queue events, so
# silence across several heartbeats means the connection is dead even if the socket
# never said so.
MONITOR_SILENCE_TIMEOUT_S = 90.0
WATCHDOG_INTERVAL_S = 15.0


def _bound_socket_reads(client: AtClient, seconds: float) -> None:
    """Give a client's command socket a read timeout (the SDK leaves it unbounded).

    Turns an indefinite hang into a socket timeout, which the callers below already
    treat as a reconnect trigger. Touches a private attribute deliberately: there is
    no public way to set this, and failing to harden must never break the client.
    """
    try:
        sock = client.secondary_connection._secure_root_socket
        if sock is not None:
            sock.settimeout(seconds)
    except Exception:
        pass


def _new_bounded_client(atsign: AtSign, root: str, queue: Queue | None = None,
                        verbose: bool = False) -> AtClient:
    """Create an AtClient whose setup and command socket cannot block forever.

    The constructor's root lookup, TLS connect and PKAM auth all read from sockets
    that do not exist yet, so they can't be bounded afterwards. A process-wide default
    timeout, applied only for the duration of construction, bounds them — and the
    sockets created inside inherit it, which is what we want for command traffic.

    It is deliberately restored immediately: the monitor socket is created later and
    must be free to idle between heartbeats. Its liveness is handled by the watchdog.
    """
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(CONNECT_TIMEOUT_S)
    try:
        client = AtClient(atsign, root_address=Address.from_string(root),
                          queue=queue, verbose=verbose)
    finally:
        socket.setdefaulttimeout(previous)
    _bound_socket_reads(client, COMMAND_READ_TIMEOUT_S)
    return client


class AtPublisher:
    """Publishes encrypted records (notifications) to another atSign.

    Resilient: reads are bounded (so a silently dead socket raises instead of hanging
    the caller's loop), and on any notify failure the AtClient is rebuilt once — fresh
    connection and key cache — and the send retried.
    """

    def __init__(self, atsign: str, root: str | None = None, verbose: bool = False):
        self.atsign = AtSign(atsign)
        self._root = root or roles.root()
        self._verbose = verbose
        self._stale = False  # set when a send was abandoned; forces a fresh client
        # One publisher owns one TLS socket carrying one command stream, so two threads
        # sending at once interleave writes and read each other's replies. That surfaces
        # as [SSL: WRONG_VERSION_NUMBER] or "Read on closed or unwrapped SSL socket" and
        # leaves the publisher wedged. Services do share a publisher across threads — the
        # policy engine publishes from both its heartbeat and its admin callback — so
        # serialise every send here rather than relying on each caller to remember.
        self._send_lock = threading.Lock()
        self.client = self._new_client()

    def _new_client(self) -> AtClient:
        return _new_bounded_client(self.atsign, self._root, verbose=self._verbose)

    def notify(self, to: str, key_name: str, value: str,
               namespace: str | None = None, ttl_ms: int = 60_000,
               deadline_s: float = PUBLISH_DEADLINE_S) -> str:
        """Send one record, guaranteed to return (or raise) within `deadline_s`.

        The send runs on a worker thread because the SDK can block indefinitely in
        places we cannot bound from here: `AtConnection.connect()` sets
        `settimeout(None)` explicitly and reads the server's greeting inside connect,
        so a client rebuild against an unresponsive peer has no timeout of its own.
        Abandoning a stuck worker (it exits when the socket finally resolves) keeps a
        caller's loop — e.g. the planner's 8s cycle — alive no matter what.
        """
        # Held across the join so a second thread cannot start a send while this one is
        # mid-exchange. A send abandoned at the deadline marks the client stale, so the
        # waiting thread rebuilds rather than inheriting a half-read socket.
        if not self._send_lock.acquire(timeout=deadline_s):
            raise TimeoutError(
                f"notify to {to} waited {deadline_s:.0f}s for another send on this "
                "publisher; abandoned")
        try:
            return self._notify_bounded(to, key_name, value, namespace, ttl_ms, deadline_s)
        finally:
            self._send_lock.release()

    def _notify_bounded(self, to: str, key_name: str, value: str,
                        namespace: str | None, ttl_ms: int, deadline_s: float) -> str:
        outcome: dict = {}

        def send():
            try:
                outcome["result"] = self._notify_once(to, key_name, value, namespace, ttl_ms)
            except Exception as e:  # noqa: BLE001 — reported to the caller below
                outcome["error"] = e

        worker = threading.Thread(target=send, daemon=True)
        worker.start()
        worker.join(deadline_s)

        if worker.is_alive():
            # Stuck in the SDK. Drop this client; the next call builds a fresh one.
            self._stale = True
            raise TimeoutError(
                f"notify to {to} exceeded {deadline_s:.0f}s (peer unresponsive); abandoned")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["result"]

    def _notify_once(self, to: str, key_name: str, value: str,
                     namespace: str | None, ttl_ms: int) -> str:
        """One send, retrying once on a fresh client.

        A read timeout leaves the abandoned reply queued on the socket, so any later
        command on that connection reads the PREVIOUS command's answer — which is why
        a failed send must never be retried on the same client, and why a wedged
        publisher recovered as soon as it was restarted.
        """
        last: Exception | None = None
        for attempt in range(2):
            try:
                if self._stale:
                    self._stale = False
                    self.client = self._new_client()
                sk = SharedKey(key_name, self.atsign, AtSign(to))
                sk.set_namespace(namespace or roles.namespace())
                sk.set_time_to_live(ttl_ms)
                # atsdk >= 0.2.70 generates a fresh iv_nonce and session_id per call.
                return self.client.notify(sk, value)
            except Exception as e:
                last = e
                if attempt == 1:
                    break
                print(f"[publisher {self.atsign}] notify to {to} failed ({e}); "
                      f"rebuilding client and retrying", flush=True)
                time.sleep(1)  # let the old connection settle before a fresh one
                try:
                    self.client = self._new_client()
                except Exception as ce:
                    # The old client may be desynchronised; never hand it back for
                    # reuse, or every later send repeats this failure until a restart.
                    self._stale = True
                    print(f"[publisher {self.atsign}] reconnect failed: {ce}", flush=True)
                    raise
        raise last  # type: ignore[misc]


class AtSubscriber:
    """Subscribes to a namespace/regex; calls on_record(from_atsign, key, value, raw).

    Resilient in two ways:
      * `start()` loops — when the monitor dies it recreates the AtClient and restarts,
        resuming from the last notification it processed;
      * a liveness watchdog force-closes the connection when the monitor goes silent,
        because a monitor stuck on a dead socket never reports an error and so would
        never trigger that loop. Heartbeat acks arrive as queue events, so "silence"
        means the whole connection is gone, not merely that nobody is publishing.
    """

    def __init__(self, atsign: str, regex: str,
                 on_record: Callable[[str, str, str, dict], None],
                 root: str | None = None, verbose: bool = False,
                 silence_timeout_s: float = MONITOR_SILENCE_TIMEOUT_S):
        self.q: Queue = Queue()
        self.atsign_str = atsign
        self.regex = regex
        self.on_record = on_record
        self.root = root or roles.root()
        self.verbose = verbose
        self._running = False
        self.client: AtClient | None = None
        # Liveness: time of the last event of ANY kind from the monitor (notification,
        # heartbeat ack, stats). Silence beyond the timeout means a dead connection.
        self.silence_timeout_s = silence_timeout_s
        self._last_event_at = time.monotonic()
        self._watchdog_started = False
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

    def stop(self):
        """Stop the loops, the SDK heartbeat, and force-close the monitor socket.

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
                self.client.monitor_connection.stop_heart_beat()  # atsdk >= 0.2.71
                self.client.monitor_connection.disconnect()
        except Exception:
            pass

    def _watchdog_tick(self) -> bool:
        """Force a reconnect if the monitor has gone silent. True if it intervened.

        Closing the monitor connection is what unblocks a read that is stuck on a dead
        socket; the resulting error ends the monitor, and start()'s loop reconnects.
        """
        if time.monotonic() - self._last_event_at <= self.silence_timeout_s:
            return False
        print(f"[subscriber {self.atsign_str}] no monitor activity for "
              f">{self.silence_timeout_s:.0f}s — forcing reconnect", flush=True)
        self._last_event_at = time.monotonic()  # grace period before checking again
        client = self.client
        try:
            if client is not None and client.monitor_connection is not None:
                client.monitor_connection.stop_heart_beat()
                client.monitor_connection.disconnect()
        except Exception:
            pass
        return True

    def _watchdog(self):
        while self._running:
            time.sleep(WATCHDOG_INTERVAL_S)
            try:
                self._watchdog_tick()
            except Exception as e:  # never let the watchdog die
                print(f"[subscriber {self.atsign_str}] watchdog error: {e}", flush=True)

    def start(self):
        """Start the consumer and liveness threads, then (re)connect in a loop forever.

        Each (re)connect resumes from the newest notification epoch we've processed
        (atsdk >= 0.2.71: start_monitor(last_received_time=...)), so nothing is missed
        during the gap and the retained backlog isn't replayed.
        """
        self._running = True
        threading.Thread(target=self._consume, daemon=True).start()
        if not self._watchdog_started:
            self._watchdog_started = True
            threading.Thread(target=self._watchdog, daemon=True).start()
        while self._running:
            try:
                self._last_event_at = time.monotonic()  # don't judge a connection before it starts
                # Bounded setup + command socket; the monitor socket stays free to idle
                # and is policed by the watchdog instead.
                self.client = _new_bounded_client(
                    AtSign(self.atsign_str), self.root, queue=self.q, verbose=self.verbose)
                resume = f" (resuming from epoch {self._last_epoch})" if self._last_epoch else ""
                print(f"[subscriber {self.atsign_str}] monitor starting{resume}", flush=True)
                # blocks until the monitor dies
                self.client.start_monitor(self.regex, last_received_time=self._last_epoch)
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
            # Any event proves the connection is alive — including the heartbeat acks
            # that keep arriving while no one is publishing.
            self._last_event_at = time.monotonic()
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
