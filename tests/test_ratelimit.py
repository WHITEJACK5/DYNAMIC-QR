"""Phase 2f: Redis-backed limiter, memory fallback, shared _rate_store."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.pop("REDIS_URL", None)

from core import ratelimit


def setup_function(_):
    os.environ.pop("REDIS_URL", None)
    ratelimit.reset_state()


def test_memory_fallback_limits():
    for _ in range(5):
        assert ratelimit.is_rate_limited("k1", 5, 60) is False
    assert ratelimit.is_rate_limited("k1", 5, 60) is True
    assert ratelimit.is_rate_limited("other", 5, 60) is False  # per-key


def test_shared_store_with_app():
    import app as nare

    assert nare._rate_store is ratelimit.mem_store
    nare._rate_store.clear()
    assert nare._is_rate_limited("k2", 1, 60) is False
    assert nare._is_rate_limited("k2", 1, 60) is True


def test_redis_failure_falls_back():
    os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"  # nothing here
    for _ in range(2):
        assert ratelimit.is_rate_limited("k3", 2, 60) is False
    assert ratelimit.is_rate_limited("k3", 2, 60) is True


def test_redis_success_path(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.counts = {}

        def incr(self, key):
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

        def expire(self, key, window):
            pass

    fake = FakeRedis()
    monkeypatch.setattr(ratelimit, "get_redis_client", lambda: fake)
    assert ratelimit.is_rate_limited("rk", 2, 60) is False
    assert ratelimit.is_rate_limited("rk", 2, 60) is False
    assert ratelimit.is_rate_limited("rk", 2, 60) is True
