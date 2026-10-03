import hashlib

from tests.conftest import PASSWORD
from wosarcher.auth import b64encode, hash_password, verify_password


def test_round_trip(password_hash: str) -> None:
    assert password_hash.startswith("scrypt$15$8$1$")
    assert verify_password(PASSWORD, password_hash)


def test_wrong_password(password_hash: str) -> None:
    assert not verify_password("hunter23", password_hash)
    assert not verify_password(PASSWORD, "not a hash")


def test_params_read_from_hash() -> None:
    salt = b"0123456789abcdef"
    key = hashlib.scrypt(b"x", salt=salt, n=2**10, r=4, p=2, dklen=32)
    stored = f"scrypt$10$4$2${b64encode(salt)}${b64encode(key)}"
    assert verify_password("x", stored)
    assert not verify_password("x", stored.replace("scrypt$10$", "scrypt$11$"))


def test_salt_differs(password_hash: str) -> None:
    other = hash_password(PASSWORD)
    assert other.split("$")[4] != password_hash.split("$")[4]
