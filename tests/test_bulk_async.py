"""Phase 2o: bulk sync shape preserved; RQ path 202s with status polling."""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")
os.environ.setdefault("BASE_URL", "http://localhost:5000")
os.environ.pop("REDIS_URL", None)

import pytest

import app as nare
from app import app
from core import jobs


@pytest.fixture(autouse=True)
def _clean():
    os.environ.pop("REDIS_URL", None)
    jobs.reset_state()
    nare._rate_store.clear()
    yield
    jobs.reset_state()
    nare._rate_store.clear()


@pytest.fixture
def client():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old = nare.DB_PATH
    nare.DB_PATH = tmp.name
    nare.init_db()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    nare.DB_PATH = old


def _token(client, email="bulk2@x.com"):
    r = client.post("/api/register", json={"email": email, "password": "StrongPass123!", "name": "B"})
    assert r.status_code == 200
    return r.json["token"]


def _csv(n=3):
    body = "url,name\n" + "".join(f"https://example.com/{i},N{i}\n" for i in range(n))
    return {"file": (io.BytesIO(body.encode()), "bulk.csv"), "type": "url"}


def test_sync_path_unchanged(client):
    tok = _token(client)
    r = client.post("/api/qrcodes/bulk", data=_csv(), content_type="multipart/form-data",
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json["count"] == 3
    assert "Deprecation" in r.headers  # legacy path header intact


def test_enqueue_path_202_and_status(client, monkeypatch):
    seen = {}

    class FakeJob:
        id = "job-1"

    class FakeQueue:
        connection = object()

        def enqueue(self, func, *args, **kwargs):
            seen["func"] = func
            seen["meta"] = kwargs.get("meta")
            return FakeJob()

    monkeypatch.setattr(jobs, "get_queue", lambda: FakeQueue())
    tok = _token(client)
    r = client.post("/api/v1/qrcodes/bulk", data=_csv(2), content_type="multipart/form-data",
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 202
    assert r.json["job_id"] == "job-1" and r.json["status_url"].endswith("/job-1")
    assert seen["func"] is nare._bulk_job
    assert seen["meta"] == {"user_id": 1}

    class FakeDone:
        meta = {"user_id": 1}
        result = {"count": 2, "created": []}

        def get_status(self):
            return "finished"

    import rq.job

    monkeypatch.setattr(rq.job.Job, "fetch", staticmethod(lambda *a, **k: FakeDone()))
    # need the app to see our FakeQueue through jobs.get_queue (already patched)
    import core.jobs as _j

    monkeypatch.setattr(_j, "get_queue", lambda: FakeQueue())
    r = client.get("/api/v1/qrcodes/bulk/job-1", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json["status"] == "finished" and r.json["count"] == 2


def test_status_unknown_or_foreign(client, monkeypatch):
    import rq.job

    class FakeQueue:
        connection = object()

    import core.jobs as _j

    monkeypatch.setattr(_j, "get_queue", lambda: FakeQueue())
    monkeypatch.setattr(rq.job.Job, "fetch", staticmethod(lambda *a, **k: (_ for _ in ()).throw(Exception("gone"))))
    tok = _token(client)
    r = client.get("/api/qrcodes/bulk/nope", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 404
