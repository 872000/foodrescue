"""Bundled demo data so FoodRescue runs out of the box.

Coordinates are a simple 0-100 map grid centred on a fictional downtown.
Expiries are relative to seed time so the demo always has live listings.
"""
from __future__ import annotations

import time

from . import db

LISTINGS = [
    # title, donor, meals, expires_in_hours, x, y, tags
    ("Pasta night surplus", "Bistro Verde", 40, 4, 20, 30, ["veg"]),
    ("Chicken & rice trays", "Halal Grill House", 60, 8, 55, 60, ["halal"]),
    ("Morning pastries", "Corner Bakery", 25, 26, 70, 20, []),
    ("Banquet leftovers", "Grand Hotel", 80, 12, 40, 75, ["veg", "gluten-free"]),
    ("Cafe sandwiches", "Main St. Cafe", 30, 2, 15, 15, ["veg", "halal"]),
    ("Pizza slices", "Tony's Pizzeria", 35, 30, 85, 80, ["veg"]),
    ("Sushi sets", "Harbour Sushi", 20, 6, 60, 40, ["gluten-free"]),
    ("Produce boxes", "FreshMart Grocery", 50, 20, 30, 55, ["veg", "gluten-free", "halal"]),
    # Already expired on purpose: must never match.
    ("Deli trays (old)", "Sub Stop", 15, -2, 45, 45, []),
]

SHELTERS = [
    # name, x, y, capacity, needs, hours
    ("Harbourfront Shelter", 18, 28, 60, ["veg"], "8-22"),
    ("North End Community Kitchen", 58, 62, 100, ["halal"], "9-21"),
    ("Eastside Food Bank", 72, 22, 80, ["gluten-free", "veg"], "10-18"),
    ("Westdale Outreach", 38, 72, 50, [], "8-20"),
    ("Mountain View Mission", 88, 82, 40, ["veg", "halal"], "9-17"),
]


def seed_demo(conn, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    listing_ids = [
        db.add_listing(
            conn,
            title=t,
            donor=d,
            meals=m,
            expires_at=int(now + h * 3600),
            x=x,
            y=y,
            tags=tags,
            now=now,
        )
        for t, d, m, h, x, y, tags in LISTINGS
    ]
    shelter_ids = [
        db.add_shelter(conn, name=n, x=x, y=y, capacity=c, needs=needs, hours=hours)
        for n, x, y, c, needs, hours in SHELTERS
    ]
    return {"listings": listing_ids, "shelters": shelter_ids}
