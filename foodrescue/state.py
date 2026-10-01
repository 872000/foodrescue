"""Claim workflow state machine.

Listing lifecycle::

    open -> matched -> claimed -> picked_up -> completed

Plus cancellations that step back one stage, and an automatic
open -> expired sweep for listings past their expiry time.
"""
from __future__ import annotations

from . import db

TRANSITIONS: dict[str, set[str]] = {
    "open": {"matched", "expired"},
    "matched": {"claimed", "open"},        # "open" = unmatch / release
    "claimed": {"picked_up", "matched"},   # "matched" = claim cancelled
    "picked_up": {"completed", "claimed"},  # "claimed" = pickup failed, retry
    "completed": set(),
    "expired": set(),
}


class InvalidTransition(ValueError):
    pass


def transition(conn, listing_id: int, to_status: str, now: float | None = None) -> dict:
    """Move a listing to a new status if the transition is legal.

    Keeps the latest match row in sync with the listing status.
    Raises InvalidTransition on illegal moves.
    """
    listing = db.get_listing(conn, listing_id)
    if listing is None:
        raise InvalidTransition(f"no listing with id {listing_id}")
    from_status = listing["status"]
    allowed = TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransition(
            f"cannot move listing {listing_id} from {from_status!r} to {to_status!r}; "
            f"allowed: {sorted(allowed) or 'none'}"
        )
    db.set_listing_status(conn, listing_id, to_status)
    row = conn.execute(
        "SELECT id FROM matches WHERE listing_id = ? ORDER BY id DESC LIMIT 1",
        (listing_id,),
    ).fetchone()
    if row:
        db.set_match_status(conn, row["id"], to_status)
    return db.get_listing(conn, listing_id)
