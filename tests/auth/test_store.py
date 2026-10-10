import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from wosarcher.auth import AuthStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_mode_follows_umask(tmp_path: Path) -> None:
    previous = os.umask(0o007)
    try:
        store = AuthStore(tmp_path / "auth.json")
        store.set_password("scrypt$a")
        assert (tmp_path / "auth.json").stat().st_mode & 0o777 == 0o660
        os.umask(0o077)
        store.set_password("scrypt$b")
        assert (tmp_path / "auth.json").stat().st_mode & 0o777 == 0o600
    finally:
        os.umask(previous)
    assert store.password_hash() == "scrypt$b"


def test_reload_on_change(tmp_path: Path) -> None:
    server = AuthStore(tmp_path / "auth.json")
    assert not server.enabled()
    AuthStore(tmp_path / "auth.json").set_password("scrypt$a")
    assert server.password_hash() == "scrypt$a"
    secret = server.secret()
    AuthStore(tmp_path / "auth.json").set_password("scrypt$a")
    assert server.secret() != secret


def test_env_hash_wins(tmp_path: Path) -> None:
    AuthStore(tmp_path / "auth.json").set_password("scrypt$file")
    assert AuthStore(tmp_path / "auth.json", "scrypt$env").password_hash() == "scrypt$env"


def test_last_used_throttled(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.json")
    _, token = store.add_token("laptop", NOW)
    stored = store.find(token)
    assert stored is not None
    store.touch(stored, NOW)
    first = store.find(token)
    assert first is not None
    assert first.last_used == NOW
    mtime = os.stat(tmp_path / "auth.json").st_mtime_ns
    store.touch(first, NOW + timedelta(seconds=30))
    assert os.stat(tmp_path / "auth.json").st_mtime_ns == mtime
    store.touch(first, NOW + timedelta(seconds=61))
    later = store.find(token)
    assert later is not None
    assert later.last_used == NOW + timedelta(seconds=61)


def test_revoke_unknown_id(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.json")
    stored, token = store.add_token("laptop", NOW)
    assert not store.revoke("nope")
    assert store.revoke(stored.id)
    assert store.find(token) is None
