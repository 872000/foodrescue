"""Tests for impact stats + chart rendering."""
import pytest

from foodrescue import db
from foodrescue.impact import compute_impact, render_chart
from foodrescue.match import CO2_KG_PER_MEAL, VOLUNTEER_H_PER_MEAL
from foodrescue.state import transition

NOW = 1_750_000_000


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _completed(conn, meals):
    lid = db.add_listing(
        conn=conn, title="T", donor="D", meals=meals,
        expires_at=NOW + 6 * 3600, x=0, y=0, tags=[], now=NOW,
    )
    for nxt in ("matched", "claimed", "picked_up", "completed"):
        transition(conn, lid, nxt)
    return lid


def test_impact_math(conn):
    _completed(conn, 40)
    _completed(conn, 60)
    stats = compute_impact(conn)
    assert stats["meals_saved"] == 100
    assert stats["rescues_completed"] == 2
    assert stats["co2_kg_avoided"] == pytest.approx(100 * CO2_KG_PER_MEAL)
    assert stats["volunteer_hours"] == pytest.approx(100 * VOLUNTEER_H_PER_MEAL)


def test_empty_db_zero_impact(conn):
    stats = compute_impact(conn)
    assert stats["meals_saved"] == 0
    assert stats["co2_kg_avoided"] == 0


def test_chart_png_is_written(conn, tmp_path):
    _completed(conn, 25)
    stats = compute_impact(conn)
    out = str(tmp_path / "impact.png")
    render_chart(stats, out)
    with open(out, "rb") as f:
        header = f.read(8)
    assert header == b"\x89PNG\r\n\x1a\n"  # real PNG bytes
