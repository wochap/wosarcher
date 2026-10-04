"""Stored provider checks: the last result per profile and block, merged with the configuration on read."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from wosarcher.config import Provider, Settings
from wosarcher.doctor import BUILT_IN, blocks
from wosarcher.models import DoctorReport, HealthReport, ProviderCheck, ProviderHealth

SLOW_MS = 1000

Fingerprint = tuple[str, str, str]


def fingerprint(cfg: Provider) -> Fingerprint:
    """The configured provider, base URL, and model a check ran against; the probe's model can differ."""
    return (cfg.provider, cfg.base_url, cfg.model)


@dataclass(frozen=True)
class Stored:
    check: ProviderCheck
    fingerprint: Fingerprint


@dataclass
class HealthCache:
    """Lives as long as the server process; `lock` keeps two checks from loading models at once."""

    checks: dict[tuple[str, str], Stored] = field(default_factory=dict)
    warnings: dict[str, list[str]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def store(self, profile: str, settings: Settings, doctor: DoctorReport, checked_at: datetime) -> None:
        configured = blocks(settings)
        for row in doctor.providers:
            if row.block in configured and row.status != "built-in":
                check = provider_check(row).model_copy(update={"checked_at": checked_at})
                self.checks[(profile, row.block)] = Stored(check, fingerprint(configured[row.block]))
        self.warnings[profile] = list(doctor.warnings)

    def report(self, profile: str, settings: Settings) -> HealthReport:
        checks = [self.entry(profile, name, cfg) for name, cfg in blocks(settings).items()]
        warnings = self.warnings.get(profile, [])
        return HealthReport(profile=profile, gpu_policy=settings.run.gpu_policy, checks=checks, warnings=warnings)

    def entry(self, profile: str, name: str, cfg: Provider) -> ProviderCheck:
        configured = ProviderCheck(
            role=name,
            provider=cfg.provider,
            url=cfg.base_url,
            model=cfg.model or None,
            device=cfg.device,
            release=cfg.release,
            status="unchecked",
        )
        if cfg.provider in BUILT_IN:
            return configured.model_copy(update={"status": "skipped", "detail": "built in, no endpoint"})
        stored = self.checks.get((profile, name))
        if stored is None or stored.fingerprint != fingerprint(cfg):
            return configured
        return stored.check.model_copy(update={"device": cfg.device, "release": cfg.release})


def provider_check(row: ProviderHealth) -> ProviderCheck:
    if row.status == "failed":
        status, detail = "down", row.error or "probe failed"
    elif row.status == "built-in":
        status, detail = "skipped", "built in, no endpoint"
    elif row.unload == "no":
        status, detail = "degraded", "model cannot be unloaded"
    elif row.latency_ms is not None and row.latency_ms > SLOW_MS:
        status, detail = "degraded", "slow response"
    else:
        status, detail = "ok", row.note or ""
    return ProviderCheck(
        role=row.block,
        provider=row.provider,
        url=row.base_url,
        model=row.model,
        device=row.device,
        release=row.release,
        status=status,
        latency_ms=row.latency_ms,
        detail=detail,
    )
