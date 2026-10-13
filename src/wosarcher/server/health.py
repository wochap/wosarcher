"""Stored provider checks: the last result per block and entry, merged with the entries on read."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from wosarcher.models import DoctorReport, HealthStatus, ProviderEntryInfo, ProviderHealth

SLOW_MS = 1000

Fingerprint = tuple[str, str, str]


def fingerprint(info: ProviderEntryInfo) -> Fingerprint:
    """The configured provider, base URL, and model a check ran against; the probe's model can differ."""
    return (info.provider, info.url, info.model)


@dataclass(frozen=True)
class Stored:
    status: HealthStatus
    latency_ms: float | None
    detail: str
    checked_at: datetime
    fingerprint: Fingerprint


@dataclass
class HealthCache:
    """Lives as long as the server process; `lock` keeps two checks from loading models at once."""

    checks: dict[tuple[str, str], Stored] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def store(self, entries: list[ProviderEntryInfo], doctor: DoctorReport, checked_at: datetime) -> None:
        """Keep each checked entry's result against the entry as it is configured now."""
        known = {(info.block, info.name): info for info in entries}
        for row in doctor.providers:
            info = known.get((row.block, row.entry or ""))
            if info is None or row.status == "built-in":
                continue
            status, detail = row_status(row)
            self.checks[(row.block, info.name)] = Stored(status, row.latency_ms, detail, checked_at, fingerprint(info))
        self.warnings = list(doctor.warnings)

    def merge(self, info: ProviderEntryInfo) -> ProviderEntryInfo:
        """The entry with its stored health; built-in entries need no check."""
        if info.error is not None:
            return info
        if info.source == "builtin" or not info.url:
            return info.model_copy(update={"status": "skipped", "detail": "built in, no endpoint"})
        stored = self.checks.get((info.block, info.name))
        if stored is None or stored.fingerprint != fingerprint(info):
            return info
        update = {
            "status": stored.status,
            "latency_ms": stored.latency_ms,
            "detail": stored.detail,
            "checked_at": stored.checked_at,
        }
        return info.model_copy(update=update)


def row_status(row: ProviderHealth) -> tuple[HealthStatus, str]:
    if row.status == "failed":
        return "down", row.error or "probe failed"
    if row.unload == "no" and row.release != "none":
        return "degraded", "model cannot be unloaded"
    if row.latency_ms is not None and row.latency_ms > SLOW_MS:
        return "degraded", "slow response"
    return "ok", row.note or ""
