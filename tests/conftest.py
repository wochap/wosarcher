import pytest

from wosarcher.auth import hash_password

PASSWORD = "hunter22"


@pytest.fixture(scope="session")
def password_hash() -> str:
    """One real scrypt hash per session, so tests check what production runs."""
    return hash_password(PASSWORD)
