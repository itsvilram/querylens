"""Retry-After for the sliding window: after that wait one more request fits, not before."""

import pytest

from app.store.rate_limit import retry_after_ms

WINDOW = 60_000
LIMIT = 10


def fits(elapsed: float, current: int, previous: int) -> bool:
    """Would one more request be allowed at `elapsed` ms, with no new requests meanwhile?"""
    if elapsed >= WINDOW:  # rolled into the next window: today's count becomes "previous"
        previous, current, elapsed = current, 0, elapsed - WINDOW
    return previous * (WINDOW - elapsed) / WINDOW + current + 1 <= LIMIT


@pytest.mark.parametrize(
    ("elapsed", "current", "previous"),
    [
        (0, 10, 0),  # the whole limit used in this window
        (30_000, 10, 5),
        (30_000, 0, 20),  # the previous window was very busy
        (40_000, 6, 12),
        (59_000, 9, 30),
        (10_000, 12, 0),  # over the limit (e.g. the limit was lowered)
    ],
)
def test_retry_after_is_the_first_moment_that_fits(
    elapsed: int, current: int, previous: int
) -> None:
    assert not fits(elapsed, current, previous)  # denied now

    wait = retry_after_ms(LIMIT, WINDOW, elapsed, current, previous)

    assert fits(elapsed + wait + 1, current, previous)
    assert not fits(elapsed + wait - 1_000, current, previous)


def test_full_window_waits_past_its_end() -> None:
    # 10 of 10 used at the start of a window: the next window must be 10% in
    # before the old count has slid out enough.
    assert retry_after_ms(LIMIT, WINDOW, 0, 10, 0) == 60_000 + 6_000
