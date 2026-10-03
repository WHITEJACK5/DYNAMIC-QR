"""Review capture and vendor dashboard API (Phase 10).

The directive: "scanning a dynamic QR of type `review` should route the
customer to a lightweight review form (rating + free text), not just redirect
to a static link."

Flow:
  1. Customer scans /r/<code>. The redirect route detects type=review and
     serves a review form instead of a 302.
  2. The form POSTs to /api/reviews. The server stores the review, enqueues
     an LLM sentiment job, and returns the redirect URL.
  3. The browser navigates to that URL.

The LLM call happens in a background job, never in the request handler.
"""
import csv
import io
import json

from flask import Blueprint, g, jsonify, request

from app import jobs
from app.extensions import get_session, token_required
from app.repositories import qr_repo, reviews_repo
from app.schemas import ReviewCreateRequest, first_error

reviews = Blueprint("reviews", __name__)


@reviews.route("/api/reviews", methods=["POST"])
def submit_review():
    """Store a review and enqueue sentiment analysis. Returns redirect URL."""
    try:
        req = ReviewCreateRequest.model_validate(request.get_json(silent=True) or {})
    except Exception as e:
        return jsonify({"error": first_error(e)}), 400

    s = get_session()
    try:
        qr = qr_repo.get_by_short(s, req.short_code)
        if not qr:
            return jsonify({"error": "Not found"}), 404
        if qr.type != "review":
            return jsonify({"error": "Not a review QR"}), 400
        rid = reviews_repo.create(s, qr.id, qr.user_id, req.rating, req.review_text)
        # Phase 10b: LLM sentiment runs in the background, never inline
        jobs.enqueue_call("app.services.llm.classify_sentiment", rid)
    finally:
        s.close()

    # where to go after the review
    redirect_url = ""
    if qr.data_json:
        try:
            redirect_url = json.loads(qr.data_json).get("redirectUrl", "")
        except Exception:
            pass
    return jsonify({"status": "recorded", "review_id": rid,
                    "redirect": redirect_url}), 201


@reviews.route("/api/reviews", methods=["GET"])
@token_required
def list_reviews():
    from app import pagination
    paginated, limit, offset, err = pagination.parse_pagination(request.args)
    if err:
        return jsonify({"error": err}), 400
    s = get_session()
    try:
        rows, total = reviews_repo.list_for_user(
            s, g.user_id, limit if paginated else None, offset if paginated else 0)
    finally:
        s.close()
    if paginated:
        return jsonify({"items": rows, "total": total, "limit": limit, "offset": offset})
    return jsonify(rows)


@reviews.route("/api/reviews/summary", methods=["GET"])
@token_required
def review_summary():
    """Aggregate stats for the vendor dashboard."""
    s = get_session()
    try:
        return jsonify(reviews_repo.summary_for_user(s, g.user_id))
    finally:
        s.close()


@reviews.route("/api/reviews/flagged", methods=["GET"])
@token_required
def flagged_reviews():
    """Negative reviews needing a response."""
    s = get_session()
    try:
        return jsonify(reviews_repo.flagged_negative(s, g.user_id))
    finally:
        s.close()


@reviews.route("/api/reviews/export", methods=["GET"])
@token_required
def export_reviews():
    """CSV export of all reviews."""
    s = get_session()
    try:
        rows, _ = reviews_repo.list_for_user(s, g.user_id)
    finally:
        s.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "rating", "review_text", "sentiment", "sentiment_score", "created_at"])
    for r in rows:
        w.writerow([r["id"], r["rating"], r["review_text"], r["sentiment"],
                    r["sentiment_score"], r["created_at"]])
    return buf.getvalue(), 200, {"Content-Type": "text/csv",
                                "Content-Disposition": "attachment; filename=reviews.csv"}
