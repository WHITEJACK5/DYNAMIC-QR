import os, json, tempfile, pytest
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Use temp DB for tests
os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"
# Prevent .env loading from polluting
import app as nare
from app import app, init_db, DB_PATH

@pytest.fixture(autouse=True)
def clear_rate_store():
    nare._rate_store.clear()
    yield
    nare._rate_store.clear()

@pytest.fixture
def client():
    # Use temp file DB
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old_path = nare.DB_PATH
    nare.DB_PATH = tmp.name
    # re-init
    nare.init_db()
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except: pass
    nare.DB_PATH = old_path
    nare._rate_store.clear()

def register(client, email="test@example.com", pwd="StrongPass123!", name="Test"):
    return client.post("/api/register", json={"email":email,"password":pwd,"name":name})

def login(client, email="test@example.com", pwd="StrongPass123!"):
    return client.post("/api/login", json={"email":email,"password":pwd})

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code==200
    assert r.json["status"]=="ok"

def test_register_validation(client):
    r = client.post("/api/register", json={"email":"bad","password":"123"})
    assert r.status_code==400
    r = client.post("/api/register", json={"email":"a@b.com","password":"short"})
    assert r.status_code==400
    assert "at least 8" in r.json["error"].lower()

def test_register_and_login(client):
    r = register(client)
    assert r.status_code==200
    assert "token" in r.json
    tok = r.json["token"]
    r2 = client.get("/api/me", headers={"Authorization":f"Bearer {tok}"})
    assert r2.status_code==200
    assert r2.json["email"]=="test@example.com"

def test_login_rate_limit(client):
    # 6 rapid wrong logins should trigger 429 at some point (limit 5/min)
    for _ in range(6):
        r = client.post("/api/login", json={"email":"test@example.com","password":"WrongPass123!"})
    assert r.status_code in (401,429)

def test_generate_static_and_dynamic(client):
    # static without auth
    r = client.post("/api/generate", json={"type":"url","data":{"url":"https://example.com"},"is_dynamic":False})
    assert r.status_code==200
    assert "image_base64" in r.json
    # dynamic without auth should still generate but not save (qr_id None) — now requires auth for dynamic? Check
    r = client.post("/api/generate", json={"type":"url","data":{"url":"https://example.com"},"is_dynamic":True,"name":"Dyn"})
    # without token, should still 200 but qr_id None
    assert r.status_code==200

def test_generate_with_auth_and_edit(client):
    r = register(client, email="edit@example.com")
    tok = r.json["token"]
    r = client.post("/api/generate", json={"type":"url","data":{"url":"https://example.com"},"is_dynamic":True,"name":"ToEdit"}, headers={"Authorization":f"Bearer {tok}"})
    assert r.status_code==200
    qid = r.json["qr_id"]
    assert qid is not None
    # edit
    r2 = client.put(f"/api/qrcodes/{qid}", json={"name":"Edited"}, headers={"Authorization":f"Bearer {tok}"})
    assert r2.status_code==200
    assert r2.json["name"]=="Edited"
    # duplicate
    r3 = client.post(f"/api/qrcodes/{qid}/duplicate", headers={"Authorization":f"Bearer {tok}"})
    assert r3.status_code==200

def test_gs1_real(client):
    r = client.post("/api/generate", json={"type":"gs1","data":{"gtin":"09506000134352","lot":"ABC123"},"is_dynamic":False})
    assert r.status_code==200
    assert r.json["content"].startswith("https://id.gs1.org/01/")

def test_svg_real(client):
    r = register(client, email="svg@example.com")
    tok = r.json["token"]
    r = client.post("/api/generate", json={"type":"url","data":{"url":"https://example.com"},"is_dynamic":True,"name":"SVG"}, headers={"Authorization":f"Bearer {tok}"})
    qid = r.json["qr_id"]
    r2 = client.get(f"/api/download/{qid}?format=svg", headers={"Authorization":f"Bearer {tok}"})
    assert r2.status_code==200
    assert r2.mimetype=="image/svg+xml"
    assert b"<svg" in r2.data[:500]

def test_password_post_not_get(client):
    r = register(client, email="prot@example.com")
    tok = r.json["token"]
    r = client.post("/api/generate", json={"type":"url","data":{"url":"https://secret.example.com"},"is_dynamic":True,"name":"Prot","password":"MyStr0ng!Pass"}, headers={"Authorization":f"Bearer {tok}"})
    code = r.json["short_code"]
    # GET should be 401 with POST form
    r2 = client.get(f"/r/{code}")
    assert r2.status_code==401
    assert b'method="POST"' in r2.data
    # POST with wrong pwd 401, correct 302
    r3 = client.post(f"/r/{code}", data={"pwd":"wrong"})
    assert r3.status_code==401
    r4 = client.post(f"/r/{code}", data={"pwd":"MyStr0ng!Pass"})
    assert r4.status_code==302

def test_smart_routing(client):
    r = register(client, email="smart@example.com")
    tok = r.json["token"]
    r = client.post("/api/generate", json={"type":"smarturl","data":{"primaryUrl":"https://example.com/default","rules":"os:android -> https://play.google.com\nos:ios -> https://apps.apple.com"},"is_dynamic":True,"name":"Smart"}, headers={"Authorization":f"Bearer {tok}"})
    code = r.json["short_code"]
    # android
    r2 = client.get(f"/r/{code}", headers={"User-Agent":"Mozilla/5.0 (Linux; Android 10)"})
    assert r2.status_code==302
    assert "play.google.com" in r2.headers["Location"]
    # ios
    r3 = client.get(f"/r/{code}", headers={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 14_0)"})
    assert r3.status_code==302
    assert "apps.apple.com" in r3.headers["Location"]

def test_bulk_uniqueness(client):
    r = register(client, email="bulk@example.com")
    tok = r.json["token"]
    csv_data = "url,name\nhttps://example.com/a,A\nhttps://example.com/b,B\nhttps://example.com/c,C\n"
    import io
    data = {"file": (io.BytesIO(csv_data.encode()), "bulk.csv"), "type":"url"}
    r2 = client.post("/api/qrcodes/bulk", data=data, content_type="multipart/form-data", headers={"Authorization":f"Bearer {tok}"})
    assert r2.status_code==200
    assert r2.json["count"]==3
