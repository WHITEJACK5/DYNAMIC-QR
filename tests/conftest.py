"""Shared test helpers.

Phase 4d gates dynamic QR creation behind a verified email address. Most
suites here are testing something else entirely, so they need a *verified*
account without repeating the setup. Suites that are specifically about the
verification gate (test_email_verification.py) must NOT use this helper.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def mark_verified(email):
    """Confirm an address directly in the database.

    This is a test shortcut, not a bypass that exists in the product: the
    only production path to `email_verified = 1` is POST /api/verify-email
    with a valid emailed token, which test_email_verification.py covers.
    """
    from app.extensions import get_session
    from app.repositories import users_repo

    s = get_session()
    try:
        users_repo.mark_email_verified(s, email)
    finally:
        s.close()
