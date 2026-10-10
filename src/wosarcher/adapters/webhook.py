"""Webhook hook: one JSON POST per run end, signed with HMAC-SHA256 when a secret is set."""

import hashlib
import hmac

import httpx

from wosarcher.config import HookEntry
from wosarcher.models import RunFinished
from wosarcher.ports import HookError

SIGNATURE_HEADER = "X-Wosarcher-Signature"


def signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class WebhookHook:
    """`entry` must be resolved (`config.resolve_hook`), so its secret and header values are set."""

    def __init__(self, entry: HookEntry) -> None:
        assert entry.url is not None
        self.url = entry.url
        self.entry = entry

    async def fire(self, finished: RunFinished) -> None:
        body = finished.model_dump_json().encode()
        headers = {name: value.value.get_secret_value() for name, value in self.entry.headers.items() if value.value}
        headers["Content-Type"] = "application/json"
        if self.entry.secret is not None:
            headers[SIGNATURE_HEADER] = signature(self.entry.secret.get_secret_value(), body)
        # One client per delivery: one POST per run end needs no pool, and redirects are never followed.
        async with httpx.AsyncClient(follow_redirects=False, timeout=self.entry.timeout) as client:
            response = await client.post(self.url, content=body, headers=headers)
        if not response.is_success:
            raise HookError(f"HTTP {response.status_code}")
