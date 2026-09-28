"""Phase 3d: logo object storage.

The directive requires that local disk storage NOT survive the refactor, so
S3 is the system of record and there is no silent fallback:

  * unconfigured  -> StorageNotConfigured (503 on upload)
  * call failure  -> StorageUnavailable (503, nothing written locally)
  * ALLOW_LOCAL_STORAGE=1 -> local, explicitly opted in, dev/test only
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

from PIL import Image

from app.services import storage

STORAGE_ENV = ("S3_BUCKET", "S3_ENDPOINT_URL", "AWS_REGION", "ALLOW_LOCAL_STORAGE")


@pytest.fixture(autouse=True)
def _clean():
    for k in STORAGE_ENV:
        os.environ.pop(k, None)
    storage.reset_state()
    yield
    for k in STORAGE_ENV:
        os.environ.pop(k, None)
    storage.reset_state()


def _png(color=(255, 0, 0)):
    buf = io.BytesIO()
    Image.new("RGBA", (40, 40), color).save(buf, format="PNG")
    return buf.getvalue()


def test_unconfigured_storage_refuses_instead_of_using_disk():
    """The headline requirement: no implicit local disk."""
    assert storage.s3_configured() is False
    assert storage.local_allowed() is False
    with pytest.raises(storage.StorageNotConfigured) as e:
        storage.get_store()
    msg = str(e.value)
    assert "S3_BUCKET" in msg and "ALLOW_LOCAL_STORAGE" in msg, msg


def test_save_and_load_refuse_when_unconfigured():
    with pytest.raises(storage.StorageNotConfigured):
        storage.save_logo(_png())
    with pytest.raises(storage.StorageNotConfigured):
        storage.load_logo("/some/legacy/path/logo.png")


def test_local_disk_requires_explicit_opt_in(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "LOCAL_DIR", str(tmp_path))
    with pytest.raises(storage.StorageNotConfigured):
        storage.get_store()          # not yet enabled
    os.environ["ALLOW_LOCAL_STORAGE"] = "1"
    storage.reset_state()
    assert storage.local_allowed() is True
    assert isinstance(storage.get_store(), storage.LocalLogoStore)
    ref = storage.save_logo(_png())
    assert os.path.exists(ref)
    assert storage.load_logo(ref) == _png()
    storage.get_store().delete(ref)
    assert not os.path.exists(ref)


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_local_opt_in_spellings(value):
    os.environ["ALLOW_LOCAL_STORAGE"] = value
    assert storage.local_allowed() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "  "])
def test_local_is_off_unless_explicitly_enabled(value):
    os.environ["ALLOW_LOCAL_STORAGE"] = value
    assert storage.local_allowed() is False


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


def test_s3_failure_raises_and_writes_nothing_locally(monkeypatch, tmp_path):
    """A failed S3 write must be visible, never quietly kept on disk."""
    class BoomClient:
        def put_object(self, **kw):
            raise RuntimeError("network down")

    os.environ["S3_BUCKET"] = "my-bucket"
    store = storage.S3LogoStore(bucket="my-bucket")
    store.client = BoomClient()
    storage.reset_state()
    monkeypatch.setattr(storage, "S3LogoStore", lambda bucket, endpoint=None, region=None: store)
    monkeypatch.setattr(storage, "LOCAL_DIR", str(tmp_path))

    with pytest.raises(storage.StorageUnavailable):
        storage.save_logo(_png())
    # the crucial part: nothing was written to local disk as a "safety net"
    assert not os.path.exists(tmp_path) or not list(tmp_path.iterdir())


def test_unusable_s3_credentials_do_not_fall_back(monkeypatch):
    """A bad bucket/client must surface, not silently degrade to disk."""
    monkeypatch.setenv("S3_BUCKET", "nare-logos")

    def boom(**kwargs):
        raise RuntimeError("no credentials")

    monkeypatch.setattr(storage, "S3LogoStore", boom)
    storage.reset_state()
    with pytest.raises(storage.StorageNotConfigured) as e:
        storage.get_store()
    assert "credentials" in str(e.value)


def test_new_key_is_unpredictable_and_sanitized():
    keys = {storage.new_key(".png") for _ in range(200)}
    assert len(keys) == 200
    assert all(k.endswith(".png") and "/" not in k for k in keys)


def test_renderer_accepts_logo_bytes_and_storage_ref(monkeypatch, tmp_path):
    import server as nare

    img = nare.create_qr_image("https://example.com", logo_bytes=_png(), size=300)
    assert img.size == (300, 300)

    # and via a stored reference (opt-in local mode for this dev loop)
    monkeypatch.setenv("ALLOW_LOCAL_STORAGE", "1")
    monkeypatch.setattr(storage, "LOCAL_DIR", str(tmp_path))
    storage.reset_state()
    ref = storage.save_logo(_png())
    img2 = nare.create_qr_image("https://example.com", logo_path=ref, size=300)
    assert img2.size == (300, 300)
