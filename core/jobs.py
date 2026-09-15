"""Background jobs: RQ when REDIS_URL is set, threads otherwise (Phase 2g).

Pick: RQ (Redis-backed, no extra broker, matches the Redis already added
for rate limiting in Phase 2f). Bulk CSV + future email go through this
same `enqueue_call` — nothing non-essential stays inline in requests.

Fallback keeps local dev / CI zero-infra: a daemon thread runs the same
callable with the same args. Failures are logged, never raised. RQ
serializes the callable by module path, so only enqueue module-level
functions (never closures).
"""
import logging
import os
import threading

logger = logging.getLogger("nare")

_rq_queue = None


def reset_state():
    global _rq_queue
    _rq_queue = None


def get_queue():
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    global _rq_queue
    if _rq_queue is not None:
        return _rq_queue
    try:
        import redis
        from rq import Queue

        conn = redis.Redis.from_url(url, socket_timeout=1)
        conn.ping()
        _rq_queue = Queue("nare", connection=conn)
        logger.info("Job queue using RQ/Redis")
        return _rq_queue
    except Exception as e:
        logger.warning(f"RQ unavailable, jobs on thread fallback: {e}")
        return None


def _run_safe(func, args, kwargs):
    try:
        func(*args, **kwargs)
    except Exception as e:
        logger.warning(f"Background job {getattr(func, '__name__', func)} failed: {e}")


def enqueue_call(func, *args, **kwargs):
    """Run func(*args, **kwargs) async. Returns 'rq' or 'thread'. Never raises."""
    q = get_queue()
    if q is not None:
        try:
            q.enqueue(func, *args, **kwargs)
            return "rq"
        except Exception as e:
            logger.warning(f"RQ enqueue failed, thread fallback: {e}")
    t = threading.Thread(target=_run_safe, args=(func, args, kwargs), daemon=True)
    t.start()
    return "thread"
