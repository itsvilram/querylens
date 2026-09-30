"""Every API test starts with an empty test Redis (database 15).

The app keeps answers, rate-limit counters and chats in Redis. Without this,
a cached answer or a used-up rate limit from one test would change the next.
"""

from collections.abc import Iterator

import pytest
from redis import Redis

TEST_REDIS_URL = "redis://127.0.0.1:6379/15"  # never the app's database 0


@pytest.fixture(autouse=True)
def empty_test_redis() -> Iterator[None]:
    client = Redis.from_url(TEST_REDIS_URL)
    client.flushdb()
    yield
    client.close()
