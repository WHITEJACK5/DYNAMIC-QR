"""Phase 3d: logo object storage — local fallback and S3 semantics tested
with a fake client (no network, no credentials).
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

from PIL import Image

from app.services import storage


@pytest.fixture(autouse=True)
def _clean():
    for k in ("S3_BUCKET", "S3_ENDPOINT_URL", "AWS_REGION"):
        os.environ.pop(k, None)
    storage.reset_state()
    yield
    for k in ("S3_BUCKET", "S3_ENDPOINT_URL", "AWS_REGION"):
        os.environ.pop(k, None)
    storage.reset_state()


def _png(color=(255, 0, 0)):
    buf = io.BytesIO()
    Image.new("RGBA", (40, 40), color).save(buf, format="PNG")
    return buf.getvalue()


def test_default_is_local_disk():
    assert storage.s3_configured() is False
    assert isinstance(storage.get_store(), storage.LocalLogoStore)
    ref = storage.save_logo(_png())
    assert os.path.exists(ref)
    assert storage.load_logo(ref) == _png()
    storage.get_store().delete(ref)
    assert not os.path.exists(ref)


def test_s3_store_roundtrip_with_fake_client(monkeypatch):
    objects = {}

    class FakeClient:
        def put_object(self, Bucket, Key, Body):
            objects[f"{Bucket}/{Key}"] = Body

        def get_object(self, Bucket, Key):
            return {"Body": io.BytesIO(objects[f"{Bucket}/{Key}"])}

        def delete_object(self, Bucket, Key):
            objects.pop(f"{Bucket}/{Key}", None)

    os.environ["S3_BUCKET"] = "my-bucket"
    store = storage.S3LogoStore(bucket="my-bucket")
    store.client = FakeClient()
    storage.reset_state()
    monkeypatch.setattr(storage, "S3LogoStore", lambda bucket, endpoint=None, region=None: store)

    assert storage.s3_configured() is True
    assert storage.get_store() is store
    ref = storage.save_logo(_png())
    assert ref.startswith("s3://my-bucket/")          # DB stores a URI, not a path
    assert any(k.startswith("my-bucket/") for k in objects)  # bytes really hit the bucket
    assert storage.load_logo(ref) == _png()
    img = storage.load_logo_image(ref)
    assert img is not None and img.size == (40, 40)
    store.delete(ref)
    assert ref.split("my-bucket/")[1] not in objects


def test_s3_failure_degrades_to_local(monkeypatch, tmp_path):
    class BoomClient:
        def put_object(self, **kw):
            raise RuntimeError("network down")

    os.environ["S3_BUCKET"] = "my-bucket"
    store = storage.S3LogoStore(bucket="my-bucket")
    store.client = BoomClient()
    storage.reset_state()
    monkeypatch.setattr(storage, "S3LogoStore", lambda bucket, endpoint=None, region=None: store)
    monkeypatch.setattr(storage, "LOCAL_DIR", str(tmp_path))
    ref = storage.save_logo(_png())
    assert not ref.startswith("s3://")               # fell back, no request 500
    assert os.path.exists(ref)


def test_new_key_is_unpredictable_and_sanitized():
    keys = {storage.new_key(".png") for _ in range(200)}
    assert len(keys) == 200
    assert all(k.endswith(".png") and "/" not in k for k in keys)


def test_renderer_accepts_logo_bytes_and_storage_ref(monkeypatch, tmp_path):
    import server as nare

    img = nare.create_qr_image("https://example.com", logo_bytes=_png(), size=300)
    assert img.size == (300, 300)

    # and via a stored local ref
    monkeypatch.setattr(storage, "LOCAL_DIR", str(tmp_path))
    ref = storage.save_logo(_png())
    img2 = nare.create_qr_image("https://example.com", logo_path=ref, size=300)
    assert img2.size == (300, 300)
