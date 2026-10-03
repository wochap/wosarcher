"""Login rate limit per client IP: 5 failures a minute, then pauses from 30 s doubling to 15 min."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field

MAX_FAILURES = 5
WINDOW = 60.0
FIRST_PAUSE = 30.0
MAX_PAUSE = 900.0
FORGET_AFTER = 900.0
"""Seconds without a failure after which an IP starts over."""


@dataclass
class Client:
    failures: list[float] = field(default_factory=list[float])
    paused_until: float = 0.0
    next_pause: float = FIRST_PAUSE
    last_failure: float = 0.0


class LoginLimiter:
    """In memory only; the clock is injected so tests do not sleep."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.clients: dict[str, Client] = {}

    def client(self, ip: str, now: float) -> Client:
        found = self.clients.get(ip)
        if found is None or now - found.last_failure > FORGET_AFTER:
            found = self.clients[ip] = Client()
        return found

    def check(self, ip: str) -> int | None:
        """Whole seconds until this IP may try again, or None when it may try now."""
        now = self.clock()
        client = self.client(ip, now)
        return math.ceil(client.paused_until - now) if client.paused_until > now else None

    def fail(self, ip: str) -> int:
        """Record a failure; the failures left before a pause (0: paused now)."""
        now = self.clock()
        client = self.client(ip, now)
        client.last_failure = now
        client.failures = [at for at in client.failures if now - at < WINDOW] + [now]
        if len(client.failures) < MAX_FAILURES:
            return MAX_FAILURES - len(client.failures)
        client.paused_until = now + client.next_pause
        client.next_pause = min(client.next_pause * 2, MAX_PAUSE)
        client.failures = []
        return 0

    def succeed(self, ip: str) -> None:
        self.clients.pop(ip, None)
