"""FoodRescue CLI.

    foodrescue seed                  create DB + bundled demo data
    foodrescue listings              show open listings
    foodrescue shelters              show shelter registry
    foodrescue match [--dry-run]     run the greedy RescueScore matcher
    foodrescue claim ID              matched  -> claimed
    foodrescue pickup ID             claimed  -> picked_up
    foodrescue complete ID           picked_up -> completed
    foodrescue impact [--chart P]    print stats + write chart PNG
    foodrescue board [--out P]       write the HTML rescue board
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from . import db
from .board import render_board
from .impact import compute_impact, render_chart, render_map
from .match import CO2_KG_PER_MEAL, VOLUNTEER_H_PER_MEAL, greedy_match, score_pair
from .seed import seed_demo
from .state import InvalidTransition, transition

HERE = Path(__file__).resolve().parent.parent
ASSETS = HERE / "assets"


def _fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def cmd_seed(args, conn) -> int:
    if args.reset:
        for table in ("matches", "listings", "shelters"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    ids = seed_demo(conn)
    print(f"Seeded {len(ids['listings'])} listings and {len(ids['shelters'])} shelters.")
    return 0


def cmd_listings(args, conn) -> int:
    rows = db.list_listings(conn, status=None if args.all else "open")
    if not rows:
        print("No listings.")
        return 0
    for l in rows:
        left = (l["expires_at"] - time.time()) / 3600
        tags = ",".join(l["tags"]) or "-"
        print(
            f"#{l['id']:>2} [{l['status']:>9}] {l['meals']:>3} meals  "
            f"exp {_fmt_ts(l['expires_at'])} ({left:+.1f}h)  tags:{tags}  "
            f"{l['title']} — {l['donor']} @({l['x']:.0f},{l['y']:.0f})"
        )
    return 0


def cmd_shelters(args, conn) -> int:
    for s in db.list_shelters(conn):
        needs = ",".join(s["needs"]) or "-"
        print(
            f"#{s['id']:>2} {s['name']}  cap {s['capacity']} meals  "
            f"needs:{needs}  hours:{s['hours']}  @({s['x']:.0f},{s['y']:.0f})"
        )
    return 0


def cmd_match(args, conn) -> int:
    results = greedy_match(conn, dry_run=args.dry_run)
    if not results:
        print("No new matches.")
        return 0
    for r in results:
        b = r["breakdown"]
        tag = "DRY-RUN " if args.dry_run else ""
        print(
            f"{tag}match #{r['match_id'] or '-'}  "
            f"'{r['listing']['title']}' -> {r['shelter']['name']}  "
            f"score={r['score']:.3f}"
        )
        print(
            f"    breakdown: distance d={b['distance']:.1f} "
            f"(score {b['distance_score']:.3f}, w=0.40) + "
            f"urgency {b['hours_until_expiry']:.1f}h left "
            f"(score {b['urgency_score']:.3f}, w=0.30) + "
            f"diet (score {b['diet_score']:.3f}, w=0.30)"
            + (f" + open-now bonus {b['open_now_bonus']:.2f}" if b["open_now_bonus"] else "")
        )
    return 0


def _advance(args, conn, to_status: str, verb: str) -> int:
    try:
        listing = transition(conn, args.id, to_status)
    except InvalidTransition as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"{verb} listing #{listing['id']} '{listing['title']}' -> {listing['status']}")
    return 0


def cmd_impact(args, conn) -> int:
    stats = compute_impact(conn)
    print("FoodRescue impact")
    print(f"  rescues completed : {stats['rescues_completed']}")
    print(f"  active matches    : {stats['active_matches']}")
    print(f"  open listings     : {stats['open_listings']}")
    print(f"  meals saved       : {stats['meals_saved']}")
    print(f"  CO2 avoided       : {stats['co2_kg_avoided']} kg (est. {CO2_KG_PER_MEAL} kg/meal)")
    print(
        f"  volunteer-hours   : {stats['volunteer_hours']} "
        f"(equiv., {VOLUNTEER_H_PER_MEAL} h/meal)"
    )
    chart = args.chart or str(ASSETS / "impact.png")
    Path(chart).parent.mkdir(parents=True, exist_ok=True)
    render_chart(stats, chart)
    print(f"  chart             : {chart}")
    return 0


def cmd_board(args, conn) -> int:
    out = args.out or str(ASSETS / "board.html")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    render_board(conn, out)
    print(f"Board written to {out}")
    return 0


def cmd_map(args, conn) -> int:
    out = args.out or str(ASSETS / "map.png")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    render_map(conn, out)
    print(f"Map written to {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="foodrescue", description="Match surplus food with shelters.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seed", help="create DB + demo data")
    s.add_argument("--reset", action="store_true")
    s.set_defaults(func=cmd_seed)

    s = sub.add_parser("listings", help="show listings")
    s.add_argument("--all", action="store_true", help="include non-open listings")
    s.set_defaults(func=cmd_listings)

    s = sub.add_parser("shelters", help="show shelters")
    s.set_defaults(func=cmd_shelters)

    s = sub.add_parser("match", help="run the greedy matcher")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_match)

    for name, to_status, verb in [
        ("claim", "claimed", "Claimed"),
        ("pickup", "picked_up", "Picked up"),
        ("complete", "completed", "Completed"),
    ]:
        s = sub.add_parser(name, help=f"listing -> {to_status}")
        s.add_argument("id", type=int)
        s.set_defaults(func=lambda a, c, t=to_status, v=verb: _advance(a, c, t, v))

    s = sub.add_parser("impact", help="print impact stats + chart")
    s.add_argument("--chart", default=None)
    s.set_defaults(func=cmd_impact)

    s = sub.add_parser("board", help="render HTML board")
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_board)

    s = sub.add_parser("map", help="render donor/shelter map PNG")
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_map)

    p.add_argument("--db", default=None, help="database path (or FOODRESCUE_DB)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    conn = db.connect(args.db)
    try:
        return args.func(args, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
