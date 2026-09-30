"""AnswerCache on real Redis: hits, misses, and coalescing of identical questions in flight."""

import asyncio
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from app.store.answer_cache import STATS_KEY, AnswerCache

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

TEST_REDIS_URL = "redis://127.0.0.1:6379/15"  # a separate Redis database, only for tests
KEY = "answer:test:q1"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client: Redis = Redis.from_url(TEST_REDIS_URL)
    keys = [KEY, f"lock:{KEY}", STATS_KEY]
    await client.delete(*keys)
    try:
        yield client
    finally:
        await client.delete(*keys)
        await client.aclose()


def cache(redis: Redis, **overrides: float) -> AnswerCache:
    options: dict[str, float] = {"poll_s": 0.01, "wait_max_s": 2.0} | overrides
    return AnswerCache(redis, ttl_s=60, **options)  # type: ignore[arg-type]


class Work:
    """A stand-in for the pipeline: counts runs, can be held open or made to fail."""

    def __init__(self, answer: str = '{"sql": "SELECT 1"}') -> None:
        self.answer = answer
        self.runs = 0
        self.started = asyncio.Event()  # set once a run has begun (so it holds the lock)
        self.release = asyncio.Event()
        self.release.set()  # by default, finish at once
        self.fail = False

    async def __call__(self) -> str:
        self.runs += 1
        self.started.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("the LLM call failed")
        return self.answer


async def test_first_call_computes_and_second_is_a_hit(redis: Redis) -> None:
    answers, work = cache(redis), Work()

    first = await answers.get_or_compute(KEY, work)
    second = await answers.get_or_compute(KEY, work)

    assert first == (work.answer, "miss")
    assert second == (work.answer, "hit")
    assert work.runs == 1
    assert 0 < await redis.ttl(KEY) <= 60  # kept, but not forever


class Waiters:
    """Counts the requests that said they are waiting; `all_in` fires at the expected count."""

    def __init__(self, expected: int) -> None:
        self.count = 0
        self.expected = expected
        self.all_in = asyncio.Event()

    async def on_wait(self) -> None:
        self.count += 1
        if self.count == self.expected:
            self.all_in.set()


# These tests wait for events, not fixed sleeps, so a slow machine can't break them.
TIMEOUT_S = 5


async def test_identical_questions_in_flight_share_one_run(redis: Redis) -> None:
    answers, work, waiters = cache(redis), Work(), Waiters(expected=5)
    work.release.clear()  # hold the first run open while the others arrive

    leader = asyncio.create_task(answers.get_or_compute(KEY, work))
    await asyncio.wait_for(work.started.wait(), TIMEOUT_S)  # the leader holds the lock
    followers = [
        asyncio.create_task(answers.get_or_compute(KEY, work, waiters.on_wait)) for _ in range(5)
    ]
    await asyncio.wait_for(waiters.all_in.wait(), TIMEOUT_S)
    work.release.set()

    assert await leader == (work.answer, "miss")
    assert [await f for f in followers] == [(work.answer, "coalesced")] * 5
    assert work.runs == 1  # one LLM call for six requests
    assert waiters.count == 5  # each follower said once that it was waiting


async def test_if_the_first_run_fails_a_waiting_request_tries_itself(redis: Redis) -> None:
    answers, failing, working, waiters = cache(redis), Work(), Work(), Waiters(expected=1)
    failing.release.clear()
    failing.fail = True

    leader = asyncio.create_task(answers.get_or_compute(KEY, failing))
    await asyncio.wait_for(failing.started.wait(), TIMEOUT_S)
    follower = asyncio.create_task(answers.get_or_compute(KEY, working, waiters.on_wait))
    await asyncio.wait_for(waiters.all_in.wait(), TIMEOUT_S)
    assert working.runs == 0  # still waiting for the leader

    failing.release.set()

    with pytest.raises(RuntimeError):
        await leader
    assert await follower == (working.answer, "miss")
    assert working.runs == 1
    assert await redis.get(f"lock:{KEY}") is None  # no lock left behind


async def test_a_failed_run_caches_nothing_and_leaves_no_lock(redis: Redis) -> None:
    answers, work = cache(redis), Work()
    work.fail = True

    with pytest.raises(RuntimeError):
        await answers.get_or_compute(KEY, work)

    assert await redis.get(KEY) is None
    assert await redis.get(f"lock:{KEY}") is None


async def test_waiting_gives_up_after_the_limit_and_answers_itself(redis: Redis) -> None:
    answers, work = cache(redis, wait_max_s=0.1), Work()
    await redis.set(f"lock:{KEY}", "someone-else", px=5_000)  # a stuck request holds the lock

    assert await answers.get_or_compute(KEY, work) == (work.answer, "miss")
    assert work.runs == 1


async def test_someone_elses_lock_is_never_deleted(redis: Redis) -> None:
    """Our lock expired during a slow run and another request took it: leave theirs alone."""
    answers = cache(redis, lock_ttl_s=0.05)

    async def slow() -> str:
        await asyncio.sleep(0.1)  # longer than our lock lives
        await redis.set(f"lock:{KEY}", "theirs", px=5_000)
        return "{}"

    await answers.get_or_compute(KEY, slow)

    assert await redis.get(f"lock:{KEY}") == b"theirs"


async def test_answers_too_large_to_keep_are_returned_but_not_cached(redis: Redis) -> None:
    answers, work = cache(redis, max_entry_bytes=10), Work(answer='{"rows": "' + "x" * 100 + '"}')

    assert await answers.get_or_compute(KEY, work) == (work.answer, "miss")
    assert await redis.get(KEY) is None


async def test_hits_misses_and_coalesced_requests_are_counted(redis: Redis) -> None:
    answers, work = cache(redis), Work()
    await answers.get_or_compute(KEY, work)
    await answers.get_or_compute(KEY, work)
    await answers.get_or_compute(KEY, work)

    assert await answers.stats() == {"miss": 1, "hit": 2}
