"""Phase 10b: LLM sentiment and summarization.

The directive: "sentiment classification per review, and a short
auto-generated 'what customers are saying' summary on the vendor dashboard.
Use a hosted LLM API behind the background job queue from Phase 2 — do not
call it synchronously from a request handler."

These tests prove the logic with a mock LLM client (no API key needed). What
they cannot prove is delivery to a real LLM provider — that needs an API key.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

from app.services import llm  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_llm_client():
    """Reset the cached client so tests are order-independent."""
    llm._client = None
    yield
    llm._client = None


class FakeLLM:
    """Records calls and returns canned responses."""

    def __init__(self, response="positive"):
        self.response = response
        self.calls = []

    def chat(self, system, user_text, max_tokens=200):
        self.calls.append({"system": system, "user": user_text,
                           "max_tokens": max_tokens})
        return self.response


def test_no_api_key_returns_none(monkeypatch):
    """Without a key the functions must be no-ops, not crashes."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm._api_key() is None
    assert llm._call_llm("s", "u") is None


def test_init_creates_a_client_when_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from app import sentry  # noqa: F401 — importing installs the JSON logger
    from app.services import llm as llm_mod

    llm_mod._client = None
    llm_mod.init()
    assert llm_mod._client is not None


def test_sentiment_classification(monkeypatch):
    fake = FakeLLM("positive")
    monkeypatch.setattr(llm, "_call_llm", fake.chat)
    sentiment, score = llm._classify(1, "Great service", fake.chat)
    assert sentiment == "positive"
    assert score == 1.0
    assert fake.calls[0]["user"] == "Great service"


def test_sentiment_maps_to_known_values(monkeypatch):
    fake = FakeLLM("negative")
    monkeypatch.setattr(llm, "_call_llm", fake.chat)
    sentiment, score = llm._classify(1, "Terrible", fake.chat)
    assert sentiment == "negative"
    assert score == -1.0


def test_unknown_sentiment_falls_back_to_neutral(monkeypatch):
    fake = FakeLLM("confused")
    monkeypatch.setattr(llm, "_call_llm", fake.chat)
    sentiment, score = llm._classify(1, "xyz", fake.chat)
    assert sentiment == "neutral"
    assert score == 0.0


def test_empty_review_text_is_skipped(monkeypatch):
    fake = FakeLLM("positive")
    monkeypatch.setattr(llm, "_call_llm", fake.chat)
    assert llm._classify(1, "", fake.chat) == (None, None)
    assert fake.calls == []


def test_summary_generation(monkeypatch):
    fake = FakeLLM("Customers love the fast service.")
    monkeypatch.setattr(llm, "_call_llm", fake.chat)
    summary = llm._summarize(1, [{"rating": 5, "review_text": "Great"}], fake.chat)
    assert summary == "Customers love the fast service."
    assert "system" in fake.calls[0]


def test_summary_with_no_reviews_returns_none(monkeypatch):
    fake = FakeLLM("x")
    monkeypatch.setattr(llm, "_call_llm", fake.chat)
    assert llm._summarize(1, [], fake.chat) is None
    assert fake.calls == []


def test_the_llm_is_never_called_from_a_request_handler():
    """
    The directive's hard requirement: sentiment runs in a background job.

    Asserted structurally — the route module must not import or call the LLM
    service. If someone wires it into a request handler, this fails.
    """
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "app", "routes", "reviews.py"), encoding="utf-8") as f:
        src = f.read()
    assert "from app.services import llm" not in src
    assert "from app.services.llm import" not in src
    assert "classify_sentiment(" not in src.replace("enqueue_call", "")
    assert "summarize_reviews(" not in src.replace("enqueue_call", "")


def test_the_job_is_enqueued_after_capture():
    """The route enqueues sentiment; it does not await it."""
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "app", "routes", "reviews.py"), encoding="utf-8") as f:
        src = f.read()
    assert "enqueue_call" in src
    assert "classify_sentiment" in src


def test_sentry_sdk_is_a_declared_dependency():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "requirements.txt"), encoding="utf-8") as f:
        assert "sentry-sdk" in f.read()
