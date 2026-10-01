"""Impact statistics + matplotlib chart rendering (offline, Agg backend).

matplotlib is imported lazily inside the render functions so commands that
don't draw charts never pay the import cost (or risk the import).
"""
from __future__ import annotations

from . import db
from .match import CO2_KG_PER_MEAL, VOLUNTEER_H_PER_MEAL


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def compute_impact(conn) -> dict:
    completed = db.list_listings(conn, status="completed")
    meals_saved = sum(l["meals"] for l in completed)
    active = db.list_matches(conn)
    active = [m for m in active if m["status"] in ("matched", "claimed", "picked_up")]
    return {
        "meals_saved": meals_saved,
        "rescues_completed": len(completed),
        "active_matches": len(active),
        "open_listings": len(db.list_listings(conn, status="open")),
        "co2_kg_avoided": round(meals_saved * CO2_KG_PER_MEAL, 1),
        "volunteer_hours": round(meals_saved * VOLUNTEER_H_PER_MEAL, 1),
    }


def render_chart(stats: dict, out_path: str) -> str:
    plt = _plt()
    labels = ["Meals saved", "CO₂ avoided (kg)", "Volunteer-hours"]
    values = [stats["meals_saved"], stats["co2_kg_avoided"], stats["volunteer_hours"]]
    colors = ["#2e9e5b", "#1f7a8c", "#e9b44c"]

    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.bar(labels, values, color=colors, edgecolor="white", linewidth=1.2)
    ax.set_title("FoodRescue — Impact Dashboard", fontsize=14, fontweight="bold", pad=14)
    ax.set_ylabel("Count")
    ax.spines[["top", "right"]].set_visible(False)
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(values) * 0.02,
            f"{val:g}",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
        )
    fig.text(
        0.5,
        0.01,
        f"{stats['rescues_completed']} rescues completed · "
        f"CO₂ factor {CO2_KG_PER_MEAL} kg/meal (est.)",
        ha="center",
        fontsize=8,
        color="#666",
    )
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def render_map(conn, out_path: str) -> str:
    """Scatter map of the 0-100 grid: shelters vs listings."""
    plt = _plt()
    listings = db.list_listings(conn)
    shelters = db.list_shelters(conn)

    fig, ax = plt.subplots(figsize=(7, 6))
    if shelters:
        ax.scatter(
            [s["x"] for s in shelters],
            [s["y"] for s in shelters],
            s=220,
            c="#1f7a8c",
            marker="s",
            label="Shelters",
            edgecolors="white",
            zorder=3,
        )
        for s in shelters:
            ax.annotate(s["name"].split()[0], (s["x"], s["y"]),
                        xytext=(4, 6), textcoords="offset points", fontsize=8)
    if listings:
        ax.scatter(
            [l["x"] for l in listings],
            [l["y"] for l in listings],
            s=[max(30, l["meals"] * 3) for l in listings],
            c="#2e9e5b",
            alpha=0.75,
            label="Listings (size ∝ meals)",
            edgecolors="white",
            zorder=2,
        )
    ax.set_xlim(-5, 105)
    ax.set_ylim(-5, 105)
    ax.set_xlabel("x (grid)")
    ax.set_ylabel("y (grid)")
    ax.set_title("FoodRescue — Donor & Shelter Map", fontsize=13, fontweight="bold")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.25, linestyle="--")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
