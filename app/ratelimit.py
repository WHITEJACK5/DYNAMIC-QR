"""Rate limiting: Redis-backed with in-memory fallback (Phase 2f).

Production sets REDIS_URL (e.g. redis://localhost:6379/0) so limits survive
restarts and are shared across gunicorn workers. Local dev / CI without
Redis keeps the original in-memory sliding window — same call signature,
same behavior. Any Redis error degrades to memory, never 500s.

Key format and semantics are unchanged from app.py's original
`_is_rate_limited(key, limit, window_sec)`.
"""
import datetime
import logging
import os

logger = logging.getLogger("nare")

mem_store = {}  # {key: [timestamps]} — fallback + local dev
_redis_client = None


def reset_state():
    """Clear fallback memory and drop the cached Redis client (tests)."""
    mem_store.clear()
    global _redis_client
    _redis_client = None


def get_redis_client():
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis

        client = redis.Redis.from_url(url, socket_timeout=1)
        client.ping()
        _redis_client = client
        logger.info("Rate limiter using Redis")
        return client
    except Exception as e:
        logger.warning(f"Redis unavailable, rate limiter on memory fallback: {e}")
        return None


def _mem_limited(key, limit, window_sec):
    now = datetime.datetime.utcnow().timestamp()
    lst = [t for t in mem_store.get(key, []) if now - t < window_sec]
    if len(lst) >= limit:
        mem_store[key] = lst
        return True
    lst.append(now)
    mem_store[key] = lst
    return False


def is_rate_limited(key, limit, window_sec):
    client = get_redis_client()
    if client is not None:
        try:
            count = client.incr(key)
            if count == 1:
                client.expire(key, int(window_sec))
            return count > limit
        except Exception as e:
            logger.warning(f"Redis rate-limit failed, memory fallback: {e}")
    return _mem_limited(key, limit, window_sec)
