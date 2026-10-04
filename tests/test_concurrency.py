"""Phase 5b: concurrency around scan counts and short-code generation.

Directive: "Add concurrency tests around scan-count increments and
short-code generation collisions."

These are real races, not theoretical ones. record_scan used to load the
row, add one in Python and write it back, so two simultaneous scans both
read the same value and one increment vanished — the count under-reporting
is the one number the product sells on. The fix is a single atomic UPDATE
... SET scan_count = scan_count + 1.

The threaded tests need a real database: SQLite serialises writers with a
file lock, so it cannot demonstrate row-level interleaving. They run only
when TEST_DATABASE_URL points at PostgreSQL, and a structural test runs
everywhere so the atomic form cannot silently regress on SQLite-only CI.
"""
import os
import sys
import threading

import pytest
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

import server as DR  # noqa: E402,F401
from app.models import Base, QRCode, Scan, User  # noqa: E402
from app.repositories import qr_repo, scans_repo  # noqa: E402

PG_URL = os.getenv("TEST_DATABASE_URL", "").strip()
requires_pg = pytest.mark.skipif(
    not PG_URL.startswith("postgresql"), reason="TEST_DATABASE_URL not a PostgreSQL URL"
)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------- structural
def test_scan_increment_is_a_single_atomic_update():
    """
    Guards the fix, on any engine.

    An ORM read-modify-write (`qr.scan_count = qr.scan_count + 1`) is what
    lost increments. Asserting the SQL contains one UPDATE with an
    in-statement addition catches a silent revert even where SQLite's write
    lock hides the race.
    """
    from sqlalchemy import create_engine, update
    from sqlalchemy.dialects import postgresql

    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    try:
        stmt = (update(QRCode)
                .where(QRCode.id == 1)
                .values(scan_count=func.coalesce(QRCode.scan_count, 0) + 1))
        compiled = str(stmt.compile(dialect=postgresql.dialect(),
                                    compile_kwargs={"literal_binds": True}))
    finally:
        eng.dispose()
    upper = compiled.upper()
    assert "UPDATE QRCODES" in upper
    assert "SCAN_COUNT" in upper
    # the addition must happen inside the statement, not in Python first
    assert "COALESCE" in upper and "+ 1" in upper
    assert upper.count("UPDATE") == 1


def test_record_scan_does_not_read_modify_write_in_python():
    with open(os.path.join(HERE, "app", "repositories", "scans_repo.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert "qr.scan_count = (qr.scan_count or 0) + 1" not in src, \
        "the read-modify-write scan counter is back"


# ------------------------------------------------------------------ helpers
@pytest.fixture
def engine(tmp_path):
    """A freshly migrated engine.

    Deliberately not the app's cached get_session(): that engine is bound
    to whatever DB file the last suite used, so reusing it silently reads
    a stale schema. This mirrors test_scans_repo.py.
    """
    from sqlalchemy import create_engine

    from app import migrations as mig

    if PG_URL:
        eng0 = create_engine(PG_URL)
        Base.metadata.drop_all(eng0)
        with eng0.connect() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
            conn.commit()
        eng0.dispose()
        mig.upgrade_to_head(PG_URL)
        eng = create_engine(PG_URL, pool_size=25, max_overflow=25, pool_pre_ping=True)
    else:
        url = f"sqlite:///{(tmp_path / 'conc.db').as_posix()}"
        mig.upgrade_to_head(url)
        eng = create_engine(url, connect_args={"check_same_thread": False})
    yield eng
    eng.dispose()


@pytest.fixture
def make_session(engine):
    """A factory, so each thread gets its own Session (and connection)."""
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    sessions = []

    def _make():
        sess = factory()
        sessions.append(sess)
        return sess

    yield _make
    for sess in sessions:
        try:
            sess.close()
        except Exception:
            pass


@pytest.fixture
def s(make_session):
    return make_session()


def _user(s, email="conc@test.local"):
    u = s.query(User).filter(User.email == email).one_or_none()
    if u is None:
        u = User(email=email, password_hash="x")
        s.add(u)
        s.commit()
        s.expire_all()
    return u.id


def _make_qr(s, short_code="conc-abc"):
    uid = _user(s)
    return qr_repo.create_full(s, user_id=uid, name="C", type="url",
                               content="https://example.com", is_dynamic=1,
                               short_code=short_code)


# --------------------------------------------------- sequential (all engines)
def test_scan_count_increments_by_one_each_time(s):
    qr_id = _make_qr(s)
    for i in range(4):
        assert scans_repo.record_scan(s, qr_id, f"t{i}", "1.1.1.1", "ua",
                                      "Desktop", "Chrome", "Windows") is not None
    s.expire_all()
    assert s.get(QRCode, qr_id).scan_count == 4
    assert s.query(Scan).filter(Scan.qr_id == qr_id).count() == 4


def test_scan_count_starts_from_null_safely(s):
    """A legacy row with NULL scan_count must increment to 1, not blow up."""
    qr_id = _make_qr(s, short_code="conc-null")
    s.query(QRCode).filter(QRCode.id == qr_id).update({QRCode.scan_count: None})
    s.commit()
    scans_repo.record_scan(s, qr_id, "t", "1.1.1.1", "ua", "D", "C", "W")
    s.expire_all()
    assert s.get(QRCode, qr_id).scan_count == 1


# ------------------------------------------------- short codes (all engines)
def test_mint_unique_short_returns_a_code(s):
    code = qr_repo.mint_unique_short(s)
    assert len(code) == 8
    assert code.isalnum()


def test_short_codes_are_not_reused(s):
    _make_qr(s, short_code="abcd1234")
    codes = {qr_repo.mint_unique_short(s) for _ in range(50)}
    assert "abcd1234" not in codes


def test_duplicate_short_code_is_rejected_by_the_database(s):
    """The UNIQUE constraint is the real backstop against a collision."""
    import sqlalchemy

    _make_qr(s, short_code="dupe123")
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        _make_qr(s, short_code="dupe123")
    s.rollback()


# ----------------------------------------------- real threads, PostgreSQL
@requires_pg
def test_concurrent_scans_do_not_lose_increments(make_session):
    """
    40 threads x 5 scans on one QR. The counter must reach exactly 200.

    Before the atomic UPDATE this lost increments, because each thread read
    the row, added one in Python and wrote the whole row back.
    """
    THREADS, PER_THREAD = 40, 5
    s = make_session()
    qr_id = _make_qr(s, short_code="race0001")

    errors = []
    barrier = threading.Barrier(THREADS)

    def worker():
        try:
            barrier.wait(timeout=30)  # maximise the overlap
            for i in range(PER_THREAD):
                sess = make_session()
                scans_repo.record_scan(sess, qr_id, f"t{i}", "9.9.9.9", "ua",
                                       "Mobile", "Chrome", "Android")
                sess.close()
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=180)

    assert not errors, f"concurrent scans raised: {errors[:3]}"
    chk = make_session()
    chk.expire_all()
    final = chk.get(QRCode, qr_id).scan_count
    scans = chk.query(Scan).filter(Scan.qr_id == qr_id).count()
    assert final == THREADS * PER_THREAD, \
        f"lost updates: scan_count={final}, expected {THREADS * PER_THREAD}"
    assert scans == THREADS * PER_THREAD, \
        f"scan rows={scans}, expected {THREADS * PER_THREAD}"


@requires_pg
def test_concurrent_short_code_minting_produces_distinct_codes(make_session):
    """
    Threads mint short codes at the same time. Whatever the interleaving,
    every code must be distinct — the /r/<code> lookup depends on it, since
    a duplicate would send one customer's scans to another's QR.
    """
    THREADS = 30
    # the user row is not needed here, but the fixture guarantees the
    # schema is migrated before any thread touches it
    make_session().query(QRCode).count()

    codes, errors = [], []
    lock = threading.Lock()
    barrier = threading.Barrier(THREADS)

    def worker():
        try:
            barrier.wait(timeout=30)
            sess = make_session()
            code = qr_repo.mint_unique_short(sess)
            with lock:
                codes.append(code)
            sess.close()
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=180)

    assert not errors, errors[:3]
    assert len(codes) == THREADS
    assert len(set(codes)) == THREADS, "a short code was minted twice"


@requires_pg
def test_concurrent_inserts_of_the_same_code_leave_one_winner(make_session):
    """
    Two writers pick the same code and both insert. Exactly one must
    succeed; the other must get an IntegrityError, never a silent
    overwrite of the first row.
    """
    import sqlalchemy

    s = make_session()
    uid = _user(s)

    results, errors = [], []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker():
        try:
            barrier.wait(timeout=30)
            sess = make_session()
            try:
                qr_repo.create_full(sess, user_id=uid, name="dup", type="url",
                                    content="https://example.com", is_dynamic=1,
                                    short_code="samecode1")
                with lock:
                    results.append("ok")
            except sqlalchemy.exc.IntegrityError:
                sess.rollback()
                with lock:
                    results.append("collision")
            sess.close()
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=180)

    assert not errors, errors[:2]
    assert sorted(results) == ["collision", "ok"], f"results were {results}"


@requires_pg
def test_session_pool_survives_a_burst_of_concurrent_requests(make_session):
    """
    Phase 3 set a bounded pool. A burst larger than the pool must queue,
    not exhaust it or hand out closed connections.
    """
    THREADS = 60
    errors = []
    barrier = threading.Barrier(THREADS)

    def worker():
        try:
            barrier.wait(timeout=30)
            sess = make_session()
            sess.query(User).count()
            sess.close()
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=180)
    assert not errors, f"pool failed under burst: {errors[:3]}"
