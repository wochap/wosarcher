import re

from wosarcher.auth import hash_token, new_token


def test_format() -> None:
    token = new_token()
    assert re.fullmatch(r"wosarcher_[0-9A-Za-z]{36}", token)
    assert re.fullmatch(r"[0-9a-f]{64}", hash_token(token))


def test_unique() -> None:
    assert len({new_token() for _ in range(100)}) == 100
