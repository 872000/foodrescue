"""Render the public HTML rescue board (open listings, active matches, completed)."""
from __future__ import annotations

import html
import time
from datetime import datetime

from . import db

CSS = """
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 0;
       background: #f4f7f4; color: #223; }
header { background: linear-gradient(135deg, #1f7a3a, #2e9e5b); color: white;
         padding: 28px 32px; }
header h1 { margin: 0 0 6px; font-size: 30px; }
header p { margin: 0; opacity: .9; }
main { max-width: 1100px; margin: 0 auto; padding: 24px; }
section { margin-bottom: 36px; }
h2 { border-bottom: 3px solid #2e9e5b; padding-bottom: 6px; }
table { width: 100%; border-collapse: collapse; background: white;
        border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
th { background: #e8f3ec; text-align: left; padding: 10px 12px; font-size: 13px;
     text-transform: uppercase; letter-spacing: .04em; }
td { padding: 10px 12px; border-top: 1px solid #eef; font-size: 14px; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 999px;
         font-size: 12px; font-weight: 600; }
.open { background: #fff3cd; color: #856404; }
.matched { background: #cce5ff; color: #004085; }
.claimed { background: #d4b8ff; color: #3d1a78; }
.picked_up { background: #ffd9b3; color: #7a3c00; }
.completed { background: #d4edda; color: #155724; }
.tag { display: inline-block; background: #eef4ff; color: #2456a6; border-radius: 4px;
       padding: 1px 7px; margin: 1px 2px; font-size: 12px; }
.score { font-weight: 700; color: #1f7a3a; }
footer { text-align: center; color: #888; font-size: 12px; padding: 18px; }
.empty { color: #888; font-style: italic; }
"""

STATUS_CLASS = {
    "open": "open", "matched": "matched", "claimed": "claimed",
    "picked_up": "picked_up", "completed": "completed",
}


def _tags(tags) -> str:
    return " ".join(
        f'<span class="tag">{html.escape(t)}</span>' for t in (tags or [])
    ) or '<span class="empty">—</span>'


def _badge(status: str) -> str:
    cls = STATUS_CLASS.get(status, "open")
    return f'<span class="badge {cls}">{html.escape(status.replace("_", " "))}</span>'


def _expiry(ts: int) -> str:
    dt = datetime.fromtimestamp(ts)
    left_h = (ts - time.time()) / 3600
    when = dt.strftime("%b %d, %H:%M")
    if left_h <= 0:
        return f"{when} (expired)"
    return f"{when} ({left_h:.1f}h left)"


def render_board(conn, out_path: str) -> str:
    open_l = db.list_listings(conn, status="open")
    matches = db.list_matches(conn)
    active = [m for m in matches if m["status"] in ("matched", "claimed", "picked_up")]
    done = [m for m in matches if m["status"] == "completed"]

    def listing_rows(rows):
        out = []
        for l in rows:
            out.append(
                "<tr>"
                f"<td><strong>{html.escape(l['title'])}</strong><br>"
                f"<small>{html.escape(l['donor'])}</small></td>"
                f"<td>{l['meals']}</td>"
                f"<td>{_expiry(l['expires_at'])}</td>"
                f"<td>{_tags(l['tags'])}</td>"
                f"<td>{_badge(l['status'])}</td>"
                "</tr>"
            )
        return "\n".join(out) or '<tr><td colspan="5" class="empty">Nothing here yet.</td></tr>'

    def match_rows(rows):
        out = []
        for m in rows:
            br = m.get("breakdown") or {}
            detail = (
                f"d={br.get('distance_score', '?')} · "
                f"u={br.get('urgency_score', '?')} · "
                f"🍽={br.get('diet_score', '?')}"
                if br else ""
            )
            out.append(
                "<tr>"
                f"<td><strong>{html.escape(m['listing_title'])}</strong> → "
                f"{html.escape(m['shelter_name'])}</td>"
                f"<td>{m['meals']}</td>"
                f"<td class=\"score\">{m['score']:.3f}<br><small>{detail}</small></td>"
                f"<td>{_badge(m['status'])}</td>"
                "</tr>"
            )
        return "\n".join(out) or '<tr><td colspan="4" class="empty">Nothing here yet.</td></tr>'

    page = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">
<title>FoodRescue — Live Rescue Board</title>
<style>{CSS}</style></head>
<body>
<header>
  <h1>🍲 FoodRescue — Live Rescue Board</h1>
  <p>Matching surplus food with shelters before it expires · SDG 2 &amp; 12</p>
</header>
<main>
  <section><h2>📦 Open Listings ({len(open_l)})</h2>
  <table><tr><th>Listing</th><th>Meals</th><th>Expires</th><th>Dietary tags</th><th>Status</th></tr>
  {listing_rows(open_l)}</table></section>

  <section><h2>🤝 Active Matches ({len(active)})</h2>
  <table><tr><th>Route</th><th>Meals</th><th>RescueScore</th><th>Status</th></tr>
  {match_rows(active)}</table></section>

  <section><h2>✅ Completed Rescues ({len(done)})</h2>
  <table><tr><th>Route</th><th>Meals</th><th>RescueScore</th><th>Status</th></tr>
  {match_rows(done)}</table></section>
</main>
<footer>Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · FoodRescue demo · offline, no APIs</footer>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    return out_path
