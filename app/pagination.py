"""Shared limit/offset parsing (Phase 2p).

Same contract as the QR list: no params -> (False, None, None) and the
caller returns the legacy bare array; params present -> envelope values.
Returns (paginated, limit, offset, error) where error is a message string
or None. Unifying the older inline QR-list parsing with this helper is
left as cleanup to keep this PR to the two micro-lists.
"""
MAX_LIMIT = 200
DEFAULT_LIMIT = 50


def parse_pagination(args):
    raw_limit = args.get("limit")
    raw_offset = args.get("offset")
    if raw_limit is None and raw_offset is None:
        return False, None, None, None
    try:
        limit = int(raw_limit) if raw_limit is not None else DEFAULT_LIMIT
        offset = int(raw_offset) if raw_offset is not None else 0
    except (TypeError, ValueError):
        return True, None, None, "limit/offset must be integers"
    if not 1 <= limit <= MAX_LIMIT:
        return True, None, None, "limit must be 1..200"
    if offset < 0:
        return True, None, None, "offset must be >= 0"
    return True, limit, offset, None
