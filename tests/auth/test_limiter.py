from wosarcher.server.limiter import LoginLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def fail_times(limiter: LoginLimiter, count: int, ip: str = "10.0.0.1") -> list[int]:
    return [limiter.fail(ip) for _ in range(count)]


def test_attempts_left_counts_down() -> None:
    assert fail_times(LoginLimiter(Clock()), 4) == [4, 3, 2, 1]


def test_fifth_failure_pauses_30() -> None:
    limiter = LoginLimiter(Clock())
    assert fail_times(limiter, 5)[-1] == 0
    assert limiter.check("10.0.0.1") == 30


def test_backoff_doubles() -> None:
    clock = Clock()
    limiter = LoginLimiter(clock)
    fail_times(limiter, 5)
    clock.now += 30
    assert limiter.check("10.0.0.1") is None
    fail_times(limiter, 5)
    assert limiter.check("10.0.0.1") == 60


def test_cap_15_minutes() -> None:
    clock = Clock()
    limiter = LoginLimiter(clock)
    pauses: list[int] = []
    for _ in range(7):
        fail_times(limiter, 5)
        pause = limiter.check("10.0.0.1")
        assert pause is not None
        pauses.append(pause)
        clock.now += pause
    assert pauses == [30, 60, 120, 240, 480, 900, 900]


def test_reset_after_quiet_period() -> None:
    clock = Clock()
    limiter = LoginLimiter(clock)
    fail_times(limiter, 5)
    clock.now += 30
    fail_times(limiter, 4)
    clock.now += 901
    assert limiter.fail("10.0.0.1") == 4
    fail_times(limiter, 4)
    assert limiter.check("10.0.0.1") == 30


def test_success_resets() -> None:
    limiter = LoginLimiter(Clock())
    fail_times(limiter, 4)
    limiter.succeed("10.0.0.1")
    assert limiter.fail("10.0.0.1") == 4


def test_ips_independent() -> None:
    limiter = LoginLimiter(Clock())
    fail_times(limiter, 5)
    assert limiter.check("10.0.0.2") is None
    assert limiter.fail("10.0.0.2") == 4
