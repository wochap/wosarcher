"""Admin password, API tokens, session cookies, and `auth.json`; standard library cryptography only.

Shared by the `wosarcher auth` commands and the server, so it never imports FastAPI.
"""

import base64
import fcntl
import hashlib
import hmac
import os
import secrets
import string
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from wosarcher.config import Settings

FILE_NAME = "auth.json"
TOKEN_PREFIX = "wosarcher_"
TOKEN_LENGTH = 36
BASE62 = string.digits + string.ascii_letters
# n = 2**15 with r = 8 needs 32 MiB, exactly the default limit, which fails.
SCRYPT_N_LOG2, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 15, 8, 1, 32
SCRYPT_MAXMEM = 64 * 1024 * 1024
LAST_USED_EVERY = timedelta(seconds=60)


def b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# Password


def scrypt(password: str, salt: bytes, n_log2: int, r: int, p: int, dklen: int) -> bytes:
    data = password.encode()
    return hashlib.scrypt(data, salt=salt, n=2**n_log2, r=r, p=p, dklen=dklen, maxmem=SCRYPT_MAXMEM)


def hash_password(password: str) -> str:
    """`scrypt$15$8$1$<salt>$<key>`, salt and key base64url."""
    salt = secrets.token_bytes(16)
    key = scrypt(password, salt, SCRYPT_N_LOG2, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN)
    return f"scrypt${SCRYPT_N_LOG2}${SCRYPT_R}${SCRYPT_P}${b64encode(salt)}${b64encode(key)}"


def verify_password(password: str, stored: str) -> bool:
    """Check against a stored hash, with the parameters read from the hash itself."""
    try:
        scheme, n_log2, r, p, salt, key = stored.split("$")
        expected = b64decode(key)
        if scheme != "scrypt":
            return False
        actual = scrypt(password, b64decode(salt), int(n_log2), int(r), int(p), len(expected))
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


# API tokens


def new_token() -> str:
    return TOKEN_PREFIX + "".join(secrets.choice(BASE62) for _ in range(TOKEN_LENGTH))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def masked(last4: str) -> str:
    return f"{TOKEN_PREFIX}••••{last4}"


# Session cookie: token "." issued "." expires "." sig


@dataclass(frozen=True)
class Session:
    issued: datetime
    expires: datetime


def session_key(secret: bytes, password_hash: str) -> bytes:
    """Bound to the password hash, so a password change ends every session."""
    return hmac.new(secret, password_hash.encode(), hashlib.sha256).digest()


def signature(key: bytes, payload: str) -> str:
    return b64encode(hmac.new(key, payload.encode(), hashlib.sha256).digest())


def sign_session(secret: bytes, password_hash: str, now: datetime, days: int) -> str:
    issued = int(now.timestamp())
    expires = issued + days * 86400
    payload = f"{b64encode(secrets.token_bytes(16))}.{issued}.{expires}"
    return f"{payload}.{signature(session_key(secret, password_hash), payload)}"


def verify_session(value: str, secret: bytes, password_hash: str, now: datetime) -> Session | None:
    payload, _, sig = value.rpartition(".")
    if not hmac.compare_digest(sig, signature(session_key(secret, password_hash), payload)):
        return None
    try:
        _, issued, expires = payload.split(".")
        session = Session(datetime.fromtimestamp(int(issued), UTC), datetime.fromtimestamp(int(expires), UTC))
    except ValueError:
        return None
    return session if session.expires > now else None


# auth.json


class StoredToken(BaseModel):
    id: str
    name: str
    sha256: str
    last4: str
    created: datetime
    last_used: datetime | None = None


class AuthFile(BaseModel):
    password_hash: str | None = None
    secret: str | None = None
    tokens: list[StoredToken] = []


class AuthStore:
    """`auth.json`, reloaded when its mtime changes so CLI changes reach a running server.

    `env_hash` (`Settings.auth.password_hash`) wins over the stored hash.
    """

    def __init__(self, path: Path, env_hash: str | None = None) -> None:
        self.path = path
        self.env_hash = env_hash
        self.data = AuthFile()
        self.mtime: int | None = None

    @classmethod
    def from_settings(cls, settings: Settings, config_dir: Path) -> "AuthStore":
        env_hash = settings.auth.password_hash
        return cls(config_dir / FILE_NAME, env_hash.get_secret_value() if env_hash else None)

    def current(self) -> AuthFile:
        try:
            mtime = self.path.stat().st_mtime_ns
        except FileNotFoundError:
            self.data, self.mtime = AuthFile(), None
            return self.data
        if mtime != self.mtime:
            self.data = AuthFile.model_validate_json(self.path.read_bytes())
            self.mtime = mtime
        return self.data

    def update(self, change: Callable[[AuthFile], None]) -> AuthFile:
        """Lock, re-read, change, and write atomically with mode 0600."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(self.path.name + ".lock")
        with lock.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            self.mtime = None
            data = self.current().model_copy(deep=True)
            change(data)
            temporary = self.path.with_name(self.path.name + ".tmp")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as out:
                out.write(data.model_dump_json(indent=2) + "\n")
            os.chmod(temporary, 0o600)
            temporary.replace(self.path)
        return data

    def password_hash(self) -> str | None:
        return self.env_hash or self.current().password_hash

    def enabled(self) -> bool:
        return self.password_hash() is not None

    def secret(self) -> bytes:
        stored = self.current().secret
        if stored is None:

            def add(data: AuthFile) -> None:
                data.secret = data.secret or b64encode(secrets.token_bytes(32))

            stored = self.update(add).secret
            assert stored is not None
        return b64decode(stored)

    def set_password(self, password_hash: str) -> None:
        """Store the hash with a new session secret, which ends every session."""

        def change(data: AuthFile) -> None:
            data.password_hash = password_hash
            data.secret = b64encode(secrets.token_bytes(32))

        self.update(change)

    def tokens(self) -> list[StoredToken]:
        return list(self.current().tokens)

    def add_token(self, name: str, now: datetime) -> tuple[StoredToken, str]:
        token = new_token()
        stored = StoredToken(
            id=secrets.token_hex(4), name=name, sha256=hash_token(token), last4=token[-4:], created=now
        )
        self.update(lambda data: data.tokens.append(stored))
        return stored, token

    def revoke(self, token_id: str) -> bool:
        """False for an unknown ID."""
        if all(token.id != token_id for token in self.tokens()):
            return False
        self.update(lambda data: setattr(data, "tokens", [t for t in data.tokens if t.id != token_id]))
        return True

    def find(self, token: str) -> StoredToken | None:
        digest = hash_token(token)
        found = None
        for stored in self.tokens():
            if hmac.compare_digest(stored.sha256, digest):
                found = stored
        return found

    def touch(self, stored: StoredToken, now: datetime) -> None:
        """Record use, at most once per minute so requests rarely write the file."""
        if stored.last_used is not None and now - stored.last_used <= LAST_USED_EVERY:
            return

        def change(data: AuthFile) -> None:
            for token in data.tokens:
                if token.id == stored.id:
                    token.last_used = now

        self.update(change)
