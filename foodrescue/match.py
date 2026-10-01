"""Matching engine: the "RescueScore".

Each open listing x shelter pair is scored on three components:

* **distance**  (40%) — closer is better.  ``1 / (1 + dist / DISTANCE_SCALE)``
* **urgency**   (30%) — less time until expiry scores higher, so food that
  would spoil soonest gets rescued first.  ``1 - hours_left / HORIZON``.
  Listings already expired (``hours_left <= 0``) are *ineligible* — they
  never match, no matter what.
* **diet**      (30%) — fraction of the shelter's dietary needs covered by
  the listing's tags.  A shelter with no stated needs scores 1.0.

A small bonus (+0.05) applies when the shelter is open at match time.
Total is clipped to [0, 1].  ``greedy_match`` processes the most urgent
listings first and assigns each the best-scoring shelter that still has
capacity left.
"""
from __future__ import annotations

import math
import time
from datetime import datetime

from . import db

WEIGHTS = {"distance": 0.40, "urgency": 0.30, "diet": 0.30}
DISTANCE_SCALE = 25.0      # grid units: score halves roughly every 25 units
URGENCY_HORIZON_H = 48.0   # beyond 48h, urgency contributes ~0
OPEN_HOURS_BONUS = 0.05

# Impact factors (documented estimates, shown as such in the CLI output)
CO2_KG_PER_MEAL = 2.5      # kg CO2e avoided per rescued meal (FAO/WRAP-style est.)
VOLUNTEER_H_PER_MEAL = 0.10  # ~6 min of volunteer effort per meal moved


def hours_until_expiry(expires_at: float, now: float) -> float:
    return (expires_at - now) / 3600.0


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def distance_score(dist: float) -> float:
    return 1.0 / (1.0 + dist / DISTANCE_SCALE)


def urgency_score(hours_left: float) -> float:
    if hours_left <= 0:
        return 0.0
    return max(0.0, 1.0 - hours_left / URGENCY_HORIZON_H)


def diet_score(listing_tags: list[str], shelter_needs: list[str]) -> float:
    if not shelter_needs:
        return 1.0
    tags = {t.lower() for t in listing_tags}
    needs = {n.lower() for n in shelter_needs}
    return len(tags & needs) / len(needs)


def open_now(hours: str, now: float) -> bool:
    """hours like '9-17'. Returns True if `now` falls inside."""
    try:
        start_s, end_s = hours.split("-")
        start, end = int(start_s), int(end_s)
    except (ValueError, AttributeError):
        return True
    hour = datetime.fromtimestamp(now).hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end  # overnight, e.g. "20-2"


def score_pair(listing: dict, shelter: dict, now: float) -> tuple[float, dict]:
    """Return (total_score, breakdown). Expired listings score 0 and are ineligible."""
    hours_left = hours_until_expiry(listing["expires_at"], now)
    dist = distance(listing["x"], listing["y"], shelter["x"], shelter["y"])
    d = distance_score(dist)
    u = urgency_score(hours_left)
    di = diet_score(listing.get("tags") or [], shelter.get("needs") or [])
    bonus = OPEN_HOURS_BONUS if open_now(shelter.get("hours", "0-24"), now) else 0.0

    total = (
        WEIGHTS["distance"] * d + WEIGHTS["urgency"] * u + WEIGHTS["diet"] * di + bonus
    )
    total = max(0.0, min(1.0, total))
    breakdown = {
        "eligible": hours_left > 0,
        "hours_until_expiry": round(hours_left, 2),
        "distance": round(dist, 2),
        "distance_score": round(d, 4),
        "urgency_score": round(u, 4),
        "diet_score": round(di, 4),
        "open_now_bonus": bonus,
        "weights": dict(WEIGHTS),
        "total": round(total, 4),
    }
    if hours_left <= 0:
        return 0.0, breakdown
    return total, breakdown


def sweep_expired(conn, now: float | None = None) -> int:
    """Mark open listings past their expiry as 'expired'. Returns count."""
    now = time.time() if now is None else now
    cur = conn.execute(
        "UPDATE listings SET status = 'expired' WHERE status = 'open' AND expires_at <= ?",
        (int(now),),
    )
    conn.commit()
    return cur.rowcount


def greedy_match(conn, now: float | None = None, dry_run: bool = False) -> list[dict]:
    """Greedily assign open listings to shelters. Returns match dicts.

    Most urgent listings go first; each takes the best-scoring shelter with
    enough remaining capacity. Unless dry_run, matches are recorded and
    listing statuses move open -> matched.
    """
    now = time.time() if now is None else now
    sweep_expired(conn, now)

    listings = db.list_listings(conn, status="open")
    shelters = db.list_shelters(conn)
    remaining = {s["id"]: s["capacity"] for s in shelters}

    # Most urgent first so soon-to-spoil food gets first pick of shelters.
    listings.sort(key=lambda l: hours_until_expiry(l["expires_at"], now))

    results: list[dict] = []
    for listing in listings:
        best = None
        best_score = 0.0
        best_breakdown: dict | None = None
        for shelter in shelters:
            if remaining[shelter["id"]] < listing["meals"]:
                continue
            score, breakdown = score_pair(listing, shelter, now)
            if not breakdown["eligible"]:
                continue
            if score > best_score:
                best, best_score, best_breakdown = shelter, score, breakdown
        if best is None or best_breakdown is None:
            continue
        remaining[best["id"]] -= listing["meals"]
        match_id = None
        if not dry_run:
            match_id = db.record_match(
                conn,
                listing_id=listing["id"],
                shelter_id=best["id"],
                score=best_score,
                breakdown=best_breakdown,
                now=now,
            )
            db.set_listing_status(conn, listing["id"], "matched")
            db.set_match_status(conn, match_id, "matched")
        results.append(
            {
                "match_id": match_id,
                "listing": listing,
                "shelter": best,
                "score": round(best_score, 4),
                "breakdown": best_breakdown,
            }
        )
    return results
