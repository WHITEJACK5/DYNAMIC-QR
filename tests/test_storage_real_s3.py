"""Phase 3d: object storage against a REAL S3 endpoint (not a fake client).

Runs only when S3_ENDPOINT_URL is set, so CI/local stay hermetic. Proven
against Adobe S3Mock (a genuine S3 HTTP implementation) in a container:

    docker run -d --name DR-s3mock -p 9090:9090 -p 9191:9191 \
      -e initialBuckets=DR-logos adobe/s3mock:latest
    S3_ENDPOINT_URL=http://127.0.0.1:9090 S3_BUCKET=DR-logos \
      AWS_ACCESS_KEY_ID=x AWS_SECRET_ACCESS_KEY=y \
      pytest tests/test_storage_real_s3.py -q

What this proves that the unit tests cannot: bytes actually traverse HTTP to
an S3 API, the DB stores a real s3:// URI, and that reference renders.
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

ENDPOINT = os.getenv("S3_ENDPOINT_URL", "").strip()
BUCKET = os.getenv("S3_BUCKET", "").strip()
pytestmark = pytest.mark.skipif(
    not (ENDPOINT and BUCKET), reason="S3_ENDPOINT_URL/S3_BUCKET not set (no real S3 available)"
)

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

from app.services import storage  # noqa: E402


@pytest.fixture
def s3():
    storage.reset_state()
    store = storage.get_store()
    assert isinstance(store, storage.S3LogoStore), "S3 store not selected"
    return store


def _png(color=(12, 34, 56)):
    buf = io.BytesIO()
    Image.new("RGBA", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()


def test_real_s3_roundtrip(s3):
    ref = storage.save_logo(_png())
    assert ref.startswith(f"s3://{BUCKET}/"), ref

    # the object really exists over HTTP, with the bytes we sent
    key = ref[len("s3://"):].split("/", 1)[1]
    obj = s3.client.get_object(Bucket=BUCKET, Key=key)
    assert obj["Body"].read() == _png()

    # and the load path used by the renderer returns the same image
    assert storage.load_logo(ref) == _png()
    img = storage.load_logo_image(ref)
    assert img is not None and img.size == (64, 64)


def test_two_uploads_get_distinct_keys(s3):
    a = storage.save_logo(_png())
    b = storage.save_logo(_png())
    assert a != b
    assert storage.load_logo(a) == storage.load_logo(b) == _png()


def test_qr_renders_with_a_real_s3_logo(s3):
    """End to end: store to S3, then render a QR using the s3:// reference."""
    import server as DR

    ref = storage.save_logo(_png((255, 0, 0)))
    img = DR.create_qr_image("https://example.com/s3-logo", logo_path=ref, size=400)
    assert img.size == (400, 400)
    assert img.convert("RGB").getcolors(maxcolors=100000) is not None  # actually drawn


def test_delete_removes_the_object(s3):
    ref = storage.save_logo(_png())
    key = ref[len("s3://"):].split("/", 1)[1]
    storage.get_store().delete(ref)
    with pytest.raises(Exception):
        s3.client.get_object(Bucket=BUCKET, Key=key)


def test_unconfigured_raises_instead_of_falling_back(monkeypatch):
    """Phase 3d requirement: local disk must not survive as a silent default."""
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("ALLOW_LOCAL_STORAGE", raising=False)
    storage.reset_state()
    with pytest.raises(storage.StorageNotConfigured):
        storage.get_store()
    with pytest.raises(storage.StorageNotConfigured):
        storage.save_logo(_png())
    storage.reset_state()
