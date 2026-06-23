"""Multi-instance coordination so a primary + failover never double-alert.

Two strategies, picked by config:

* ``RoleCoordinator`` (default, no dependencies) – each instance has a role.
  The ``primary`` emits alerts; a ``standby`` runs the full pipeline but stays
  silent. Failover is *manual*: if the primary host dies, flip the standby's
  ``TRACKER_ROLE`` to ``primary`` (or just let it keep running as primary).

* ``RedisCoordinator`` (set ``REDIS_URL``) – *automatic*. Instances share a
  Redis (e.g. a free Upstash database). A short-lived **leader lease** elects
  one active sender; if it dies, a standby takes over within the lease TTL. A
  per-event **dedup key** (``signal.fingerprint()``) guarantees exactly one
  alert per event even during a leadership handover overlap. Safe active/active.

Both expose the same tiny interface: ``claim(signal) -> bool`` (True => this
instance should send the alert) plus ``start()`` / ``role()``.
"""

from __future__ import annotations

import abc
import logging
import os
import socket
import threading
import time
from typing import Optional

from .models import Signal

log = logging.getLogger("stock_tracker.coordination")


def default_instance_id() -> str:
    return os.environ.get("INSTANCE_ID") or f"{socket.gethostname()}-{os.getpid()}"


class Coordinator(abc.ABC):
    instance_id: str = "local"

    @abc.abstractmethod
    def claim(self, signal: Signal) -> bool:
        """Return True if *this* instance should dispatch the alert."""

    def start(self) -> None:
        """Optional background work (e.g. lease renewal)."""

    def role(self) -> str:
        return "standalone"


class RoleCoordinator(Coordinator):
    """Static primary/standby. Zero external dependencies."""

    def __init__(self, role: str = "primary", instance_id: Optional[str] = None):
        self._role = (role or "primary").lower()
        self.instance_id = instance_id or default_instance_id()
        if self._role not in ("primary", "standby"):
            log.warning("unknown TRACKER_ROLE=%r; treating as primary", role)
            self._role = "primary"

    def claim(self, signal: Signal) -> bool:
        return self._role == "primary"

    def role(self) -> str:
        return self._role


class RedisCoordinator(Coordinator):
    """Leader-lease + shared dedup via Redis. Automatic failover."""

    LEADER_KEY = "tracker:leader"

    def __init__(
        self,
        url: str,
        instance_id: Optional[str] = None,
        lease_ttl: int = 30,
        dedup_window: int = 900,
        namespace: str = "tracker",
        client=None,
    ):
        if client is not None:
            self.r = client
        else:
            import redis  # optional dependency

            self.r = redis.Redis.from_url(url, decode_responses=True, socket_timeout=5)
        self.instance_id = instance_id or default_instance_id()
        self.lease_ttl = lease_ttl
        self.dedup_window = dedup_window
        self.ns = namespace
        self._stop = threading.Event()
        self._is_leader = False

    # -- leadership -----------------------------------------------------
    def _acquire_or_renew(self) -> bool:
        try:
            if self.r.set(self.LEADER_KEY, self.instance_id, nx=True, px=self.lease_ttl * 1000):
                self._is_leader = True
            elif self.r.get(self.LEADER_KEY) == self.instance_id:
                self.r.set(self.LEADER_KEY, self.instance_id, xx=True, px=self.lease_ttl * 1000)
                self._is_leader = True
            else:
                self._is_leader = False
        except Exception as exc:  # Redis unreachable -> fail safe (don't send)
            log.warning("redis leadership check failed: %s", exc)
            self._is_leader = False
        return self._is_leader

    def _renew_loop(self) -> None:
        interval = max(2, self.lease_ttl // 3)
        while not self._stop.wait(interval):
            was = self._is_leader
            now = self._acquire_or_renew()
            if now != was:
                log.info("leadership change: %s is now %s", self.instance_id, "LEADER" if now else "standby")

    def start(self) -> None:
        self._acquire_or_renew()
        t = threading.Thread(target=self._renew_loop, name="redis-lease", daemon=True)
        t.start()
        log.info("redis coordinator started (instance=%s, leader=%s)", self.instance_id, self._is_leader)

    # -- claim ----------------------------------------------------------
    def claim(self, signal: Signal) -> bool:
        if not self._acquire_or_renew():
            return False
        key = f"{self.ns}:dedup:{signal.fingerprint()}"
        try:
            # NX => only the first instance to claim this event wins.
            won = self.r.set(key, self.instance_id, nx=True, ex=self.dedup_window)
            return bool(won)
        except Exception as exc:
            log.warning("redis dedup claim failed: %s", exc)
            return False  # fail safe: skip rather than risk a duplicate

    def role(self) -> str:
        return "leader" if self._is_leader else "standby"


def build_coordinator(cfg) -> Coordinator:
    """Construct a coordinator from config (REDIS_URL wins if present)."""
    instance_id = cfg.instance_id or default_instance_id()
    if cfg.redis_url:
        try:
            coord = RedisCoordinator(
                cfg.redis_url,
                instance_id=instance_id,
                lease_ttl=cfg.lease_ttl,
                dedup_window=cfg.dedup_window,
            )
            coord.start()
            return coord
        except Exception as exc:
            log.warning("could not init RedisCoordinator (%s); falling back to role=%s", exc, cfg.tracker_role)
    return RoleCoordinator(role=cfg.tracker_role, instance_id=instance_id)
