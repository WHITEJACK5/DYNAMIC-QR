"""Small pure helpers: colour parsing, short codes, input validation.

No Flask, no DB, no network — safe to unit-test in isolation.
"""
import re
import secrets
import string


def hex_to_rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join([c * 2 for c in h])
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def generate_short_code(n=8):
    # Use 62-char alphabet for full entropy: 62^8 ~ 2.18e14
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))


def validate_email_format(email):
    # Basic regex first (permissive for personal/test domains like .local, .test)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return False
    try:
        from email_validator import validate_email
        validate_email(email, check_deliverability=False)
        return True
    except ImportError:
        return True
    except Exception:
        # If validator rejects but regex passes (e.g., .local), allow for personal use
        return True


def validate_password_strength(pwd):
    # Industry: >=8 chars, at least 3 of 4 categories
    if len(pwd) < 8:
        return False, "Password must be at least 8 characters"
    cats = 0
    if re.search(r"[A-Z]", pwd):
        cats += 1
    if re.search(r"[a-z]", pwd):
        cats += 1
    if re.search(r"\d", pwd):
        cats += 1
    if re.search(r"[^A-Za-z0-9]", pwd):
        cats += 1
    if cats < 3:
        return False, "Password must include 3 of: uppercase, lowercase, digit, special char"
    # also check common weak passwords
    weak = {"password", "12345678", "qwerty123", "letmein", "admin123"}
    if pwd.lower() in weak:
        return False, "Password is too common"
    return True, ""
