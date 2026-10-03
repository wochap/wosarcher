from datetime import UTC, datetime, timedelta

from wosarcher.auth import sign_session, verify_session

NOW = datetime(2026, 1, 1, 9, 12, tzinfo=UTC)
SECRET = b"s" * 32
HASH = "scrypt$15$8$1$salt$key"


def test_valid() -> None:
    session = verify_session(sign_session(SECRET, HASH, NOW, 30), SECRET, HASH, NOW)
    assert session is not None
    assert (session.issued, session.expires) == (NOW, NOW + timedelta(days=30))


def test_tampered_expiry() -> None:
    token, issued, expires, sig = sign_session(SECRET, HASH, NOW, 30).split(".")
    tampered = ".".join([token, issued, str(int(expires) + 86400), sig])
    assert verify_session(tampered, SECRET, HASH, NOW) is None
    assert verify_session("garbage", SECRET, HASH, NOW) is None


def test_expired() -> None:
    value = sign_session(SECRET, HASH, NOW, 30)
    assert verify_session(value, SECRET, HASH, NOW + timedelta(days=30)) is None


def test_new_hash_invalidates() -> None:
    value = sign_session(SECRET, HASH, NOW, 30)
    assert verify_session(value, SECRET, HASH + "x", NOW) is None


def test_new_secret_invalidates() -> None:
    value = sign_session(SECRET, HASH, NOW, 30)
    assert verify_session(value, b"t" * 32, HASH, NOW) is None


def test_non_ascii_cookie_rejected() -> None:
    assert verify_session("é.1.2.x", SECRET, HASH, NOW) is None
    assert verify_session("a.1.2.é", SECRET, HASH, NOW) is None
