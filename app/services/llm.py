"""LLM sentiment and summarization (Phase 10b).

The directive: "sentiment classification per review, and a short
auto-generated 'what customers are saying' summary on the vendor dashboard.
Use a hosted LLM API (Anthropic/OpenAI/Gemini) behind the background job queue
from Phase 2 — do not call it synchronously from a request handler."

These functions are called by RQ workers, never by request handlers. They are
fail-safe: if no API key is configured, they return None and the review simply
has no sentiment annotation. A failed LLM call is logged, not raised — a
sentiment job must never take down the worker or lose the review.
"""
import logging
import os

logger = logging.getLogger("nare")

SENTIMENT_SYSTEM = (
    "Classify the sentiment of this customer review as exactly one of: "
    "positive, neutral, negative. Respond with only the word."
)
SUMMARY_SYSTEM = (
    "You are summarizing customer feedback for a business owner. "
    "Write 2-3 sentences capturing the overall theme, specific praises or "
    "complaints, and any recurring issues. Be concise and factual."
)


def _api_key():
    return os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("ANTHROPIC_API_KEY", "").strip()


def _call_llm(system, user_text, max_tokens=200):
    """Call a hosted LLM API. Returns text, or None on any failure."""
    if not _api_key():
        return None
    try:
        import openai
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        r = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user_text}],
            max_tokens=max_tokens,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return None


def classify_sentiment(review_id):
    """
    Sentiment for one review. Called by an RQ worker.

    Returns (sentiment, score) or (None, None) when LLM is unavailable.
    """
    from app.extensions import get_session
    from app.repositories import reviews_repo

    s = get_session()
    try:
        row = s.query(reviews_repo.Review).filter_by(id=review_id).one_or_none()
        if row is None:
            return None, None
        text = row.review_text or ""
        if not text.strip():
            return None, None
        result = _call_llm(SENTIMENT_SYSTEM, text, max_tokens=10)
        if not result:
            return None, None
        sentiment = result.lower().strip()
        if sentiment not in ("positive", "neutral", "negative"):
            sentiment = "neutral"
        score = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}[sentiment]
        reviews_repo.set_sentiment(s, review_id, sentiment, score, None)
        return sentiment, score
    finally:
        s.close()


def summarize_reviews(user_id):
    """
    'What customers are saying' for the vendor dashboard. Called by an RQ worker.

    Returns the summary text, or None when LLM is unavailable.
    """
    from app.extensions import get_session
    from app.repositories import reviews_repo

    s = get_session()
    try:
        rows, _ = reviews_repo.list_for_user(s, user_id, limit=100)
        if not rows:
            return None
        combined = "\n".join(
            f"Rating {r['rating']}/5: {r['review_text']}" for r in rows if r["review_text"]
        )
        if not combined.strip():
            return None
        return _call_llm(SUMMARY_SYSTEM, combined, max_tokens=300)
    finally:
        s.close()
