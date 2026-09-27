"""Read-through cache: Redis when REDIS_URL is set, else in-memory TTL (Phase 2h).

Covers read-heavy endpoints (QR preview for identical inputs, analytics
overview). Any Redis error degrades to memory or to a miss — caching never
changes status codes or response bodies; hits are signalled via the
`X-Cache: HIT/MISS` response header only.
"""
import hashlib
import json
import logging
import os
import time

logger = logging.getLogger("nare")

_mem = {}  # key -> (value_str, expires_at)
_redis_client = None


def reset_state():
    _mem.clear()
    global _redis_client
    _redis_client = None


def get_redis():
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
        return client
    except Exception as e:
        logger.warning(f"Cache Redis unavailable, memory fallback: {e}")
        return None


def key_for(prefix, payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}:{hashlib.sha256(raw.encode()).hexdigest()}"


def cache_get(key):
    client = get_redis()
    if client is not None:
        try:
            val = client.get(key)
            return val.decode() if isinstance(val, bytes) else val
        except Exception as e:
            logger.warning(f"Cache Redis get failed: {e}")
    item = _mem.get(key)
    if item is None:
        return None
    value, exp = item
    if exp < time.time():
        _mem.pop(key, None)
        return None
    return value


def cache_set(key, value, ttl):
    client = get_redis()
    if client is not None:
        try:
            client.setex(key, int(ttl), value)
        except Exception as e:
            logger.warning(f"Cache Redis set failed: {e}")
    _mem[key] = (value, time.time() + ttl)


def cache_delete(key):
    client = get_redis()
    if client is not None:
        try:
            client.delete(key)
        except Exception as e:
            logger.warning(f"Cache Redis delete failed: {e}")
    _mem.pop(key, None)
