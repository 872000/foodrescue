"""Tests for the claim-workflow state machine."""
import pytest

from foodrescue import db
from foodrescue.state import InvalidTransition, transition

NOW = 1_750_000_000


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    lid = db.add_listing(
        conn=c, title="T", donor="D", meals=10,
        expires_at=NOW + 6 * 3600, x=0, y=0, tags=[], now=NOW,
    )
    yield c, lid
    c.close()


def test_full_claim_chain(conn):
    c, lid = conn
    for nxt in ("matched", "claimed", "picked_up", "completed"):
        listing = transition(c, lid, nxt)
        assert listing["status"] == nxt
    assert db.get_listing(c, lid)["status"] == "completed"


def test_match_row_follows_listing_status(conn):
    c, lid = conn
    sid = db.add_shelter(c, name="S", x=0, y=0, capacity=10, needs=[], hours="0-24")
    mid = db.record_match(c, listing_id=lid, shelter_id=sid, score=0.9,
                          breakdown={}, now=NOW)
    transition(c, lid, "matched")
    transition(c, lid, "claimed")
    row = c.execute("SELECT status FROM matches WHERE id = ?", (mid,)).fetchone()
    assert row["status"] == "claimed"


def test_skipping_a_stage_is_rejected(conn):
    c, lid = conn
    with pytest.raises(InvalidTransition):
        transition(c, lid, "claimed")  # open -> claimed skips 'matched'


def test_terminal_states_reject_everything(conn):
    c, lid = conn
    for nxt in ("matched", "claimed", "picked_up", "completed"):
        transition(c, lid, nxt)
    for nxt in ("open", "matched", "claimed", "picked_up"):
        with pytest.raises(InvalidTransition):
            transition(c, lid, nxt)


def test_cancellation_steps_back_one_stage(conn):
    c, lid = conn
    transition(c, lid, "matched")
    transition(c, lid, "claimed")
    assert transition(c, lid, "matched")["status"] == "matched"  # claim cancelled
    assert transition(c, lid, "open")["status"] == "open"        # released


def test_unknown_listing_rejected(conn):
    c, _ = conn
    with pytest.raises(InvalidTransition):
        transition(c, 9999, "matched")
