"""Phase 2g: job queue dispatches async, never raises, thread fallback works."""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.pop("REDIS_URL", None)

from core import jobs


def setup_function(_):
    os.environ.pop("REDIS_URL", None)
    jobs.reset_state()


def test_thread_fallback_runs():
    done = threading.Event()

    def work(x):
        assert x == 41
        done.set()

    assert jobs.enqueue_call(work, 41) == "thread"
    assert done.wait(5) is True


def test_job_failure_never_raises():
    def boom():
        raise RuntimeError("nope")

    assert jobs.enqueue_call(boom) == "thread"
    time.sleep(0.5)  # would raise in-thread if unsafe; just must not propagate


def test_redis_down_falls_back_to_thread():
    os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"
    done = threading.Event()
    assert jobs.enqueue_call(lambda: done.set()) == "thread"
    assert done.wait(5) is True


def test_rq_path_via_fake_queue(monkeypatch):
    seen = {}

    class FakeQueue:
        def enqueue(self, func, *args, **kwargs):
            seen["func"] = func
            seen["args"] = args

    monkeypatch.setattr(jobs, "get_queue", lambda: FakeQueue())

    def work(a, b=0):
        pass

    assert jobs.enqueue_call(work, 1, b=2) == "rq"
    assert seen["func"] is work and seen["args"] == (1,)


def test_enrich_uses_queue():
    import app as nare

    assert callable(nare._geo_enrich_job)  # module-level, RQ-importable
    assert nare._enrich_scan_geo_async.__code__.co_names.count("enqueue_call") >= 1
