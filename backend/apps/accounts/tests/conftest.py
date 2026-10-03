import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def reset_throttle():
    # The auth throttle counts requests in the cache; start each test with a clean slate.
    cache.clear()
    yield
    cache.clear()
