"""Tests for the RescueScore matching engine."""
import time

import pytest

from foodrescue import db
from foodrescue.match import diet_score, greedy_match, score_pair, urgency_score

NOW = 1_750_000_000  # fixed clock for determinism


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _listing(conn, **kw):
    base = dict(
        title="T", donor="D", meals=10, expires_at=NOW + 6 * 3600, x=0, y=0, tags=["veg"]
    )
    base.update(kw)
    return db.add_listing(conn, now=NOW, **base)


def _shelter(conn, **kw):
    base = dict(name="S", x=1, y=0, capacity=100, needs=["veg"], hours="0-24")
    base.update(kw)
    return db.add_shelter(conn, **base)


def test_nearer_shelter_scores_higher(conn):
    lid = _listing(conn)
    near = _shelter(conn, name="near", x=2, y=0)
    far = _shelter(conn, name="far", x=80, y=0)
    listing = db.get_listing(conn, lid)
    s_near, _ = score_pair(listing, db.list_shelters(conn)[0], NOW)
    shelters = {s["name"]: s for s in db.list_shelters(conn)}
    s_near, b_near = score_pair(listing, shelters["near"], NOW)
    s_far, b_far = score_pair(listing, shelters["far"], NOW)
    assert s_near > s_far
    assert b_near["distance_score"] > b_far["distance_score"]


def test_more_urgent_listing_scores_higher(conn):
    """Less time until expiry ('less-expired' in the urgent sense) wins."""
    sid = _shelter(conn)
    soon = _listing(conn, title="soon", expires_at=NOW + 2 * 3600)
    later = _listing(conn, title="later", expires_at=NOW + 40 * 3600)
    shelter = db.list_shelters(conn)[0]
    s_soon, _ = score_pair(db.get_listing(conn, soon), shelter, NOW)
    s_later, _ = score_pair(db.get_listing(conn, later), shelter, NOW)
    assert urgency_score(2) > urgency_score(40)
    assert s_soon > s_later


def test_diet_compatible_shelter_scores_higher(conn):
    lid = _listing(conn, tags=["halal", "veg"])
    _shelter(conn, name="fits", needs=["halal", "veg"])
    _shelter(conn, name="misses", needs=["gluten-free"])
    listing = db.get_listing(conn, lid)
    shelters = {s["name"]: s for s in db.list_shelters(conn)}
    assert diet_score(["halal", "veg"], ["halal", "veg"]) == 1.0
    s_fit, _ = score_pair(listing, shelters["fits"], NOW)
    s_miss, _ = score_pair(listing, shelters["misses"], NOW)
    assert s_fit > s_miss


def test_expired_listing_never_matches(conn):
    _listing(conn, title="old", expires_at=NOW - 3600)
    _shelter(conn)
    results = greedy_match(conn, now=NOW)
    assert results == []
    listing = db.get_listing(conn, 1)
    score, breakdown = score_pair(listing, db.list_shelters(conn)[0], NOW)
    assert score == 0.0
    assert breakdown["eligible"] is False
    # sweep marks it expired
    assert db.get_listing(conn, 1)["status"] == "expired"


def test_greedy_respects_capacity_and_picks_best(conn):
    # One small shelter: only the most urgent listing should get it.
    _shelter(conn, name="tiny", x=5, y=0, capacity=10)
    urgent = _listing(conn, title="urgent", meals=10, expires_at=NOW + 1 * 3600)
    calm = _listing(conn, title="calm", meals=10, expires_at=NOW + 30 * 3600)
    results = greedy_match(conn, now=NOW)
    assert len(results) == 1
    assert results[0]["listing"]["id"] == urgent
    assert db.get_listing(conn, urgent)["status"] == "matched"
    assert db.get_listing(conn, calm)["status"] == "open"


def test_greedy_matches_most_urgent_first(conn):
    _shelter(conn, name="a", x=1, y=0, capacity=1000)
    _shelter(conn, name="b", x=2, y=0, capacity=1000)
    l1 = _listing(conn, title="l1", expires_at=NOW + 3 * 3600)
    l2 = _listing(conn, title="l2", expires_at=NOW + 20 * 3600)
    results = greedy_match(conn, now=NOW)
    assert len(results) == 2
    assert results[0]["listing"]["id"] == l1  # most urgent processed first
    assert results[0]["match_id"] is not None
