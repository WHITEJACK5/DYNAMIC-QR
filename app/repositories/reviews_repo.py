"""Reviews repository (Phase 10)."""
import datetime

from app.models import Review


def create(s, qr_id, user_id, rating, review_text):
    r = Review(qr_id=qr_id, user_id=user_id, rating=rating,
               review_text=review_text,
               created_at=datetime.datetime.utcnow().isoformat())
    s.add(r)
    s.commit()
    return r.id


def get_owned(s, review_id, user_id):
    return s.query(Review).filter(
        Review.id == review_id, Review.user_id == user_id
    ).one_or_none()


def list_for_user(s, user_id, limit=None, offset=0):
    q = s.query(Review).filter(Review.user_id == user_id)
    total = q.count()
    rows = q.order_by(Review.created_at.desc()).limit(limit).offset(offset).all()
    return [_to_dict(r) for r in rows], total


def list_for_qr(s, qr_id, limit=None, offset=0):
    q = s.query(Review).filter(Review.qr_id == qr_id)
    total = q.count()
    rows = q.order_by(Review.created_at.desc()).limit(limit).offset(offset).all()
    return [_to_dict(r) for r in rows], total


def summary_for_user(s, user_id):
    """Aggregate stats for the vendor dashboard."""
    from sqlalchemy import func

    row = s.query(
        func.count(Review.id),
        func.avg(Review.rating),
        func.sum(Review.rating == 1),
        func.sum(Review.rating == 2),
        func.sum(Review.rating == 3),
        func.sum(Review.rating == 4),
        func.sum(Review.rating == 5),
    ).filter(Review.user_id == user_id).one()
    total, avg, r1, r2, r3, r4, r5 = row
    return {
        "total": total or 0,
        "average_rating": round(avg, 2) if avg else 0,
        "distribution": {"1": r1 or 0, "2": r2 or 0, "3": r3 or 0,
                         "4": r4 or 0, "5": r5 or 0},
    }


def flagged_negative(s, user_id, limit=20):
    """Reviews needing attention: rating <= 2 or negative LLM sentiment."""
    rows = s.query(Review).filter(
        Review.user_id == user_id,
        (Review.rating <= 2) | (Review.sentiment == "negative"),
    ).order_by(Review.created_at.desc()).limit(limit).all()
    return [_to_dict(r) for r in rows]


def set_sentiment(s, review_id, sentiment, score, summary):
    s.query(Review).filter(Review.id == review_id).update(
        {"sentiment": sentiment, "sentiment_score": score, "summary": summary}
    )
    s.commit()


def _to_dict(r):
    return {
        "id": r.id, "qr_id": r.qr_id, "user_id": r.user_id,
        "rating": r.rating, "review_text": r.review_text,
        "sentiment": r.sentiment, "sentiment_score": r.sentiment_score,
        "summary": r.summary, "created_at": r.created_at,
    }
