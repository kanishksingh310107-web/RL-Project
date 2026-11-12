"""Shopping Module & Venue Tier Prior (Person A).

Schedules dedicated shopping time blocks and budget lines:
- Venue tiers: street/flea market, local craft/gift, department store/mall, boutique
- Budget fit vs visible shopping style (bargain markets / local crafts / malls / mix)
- Multi-factor scoring: budget fit, travel time, crowd tolerance, heat sensitivity
- Persists user accept/reject counts per venue type in SQLite as preference priors
"""
import sqlite3
from typing import Dict, Any, List, Optional, Tuple
from app.core.schemas import Place, Block, Provenance
from app.core.assumptions import (
    SHOPPING_TIERS,
    CATEGORY_DURATIONS_MINUTES,
)
from app.database import get_connection

VENUE_TIER_MAPPING = {
    "flea market": "street_flea_market",
    "street market": "street_flea_market",
    "flea": "street_flea_market",
    "bazaar": "street_flea_market",
    "night market": "street_flea_market",
    "craft": "local_market_craft_gift",
    "artisan": "local_market_craft_gift",
    "emporium": "local_market_craft_gift",
    "souvenir": "local_market_craft_gift",
    "mall": "department_store_mall",
    "department store": "department_store_mall",
    "shopping centre": "department_store_mall",
    "boutique": "boutique",
    "designer": "boutique",
}


def ensure_shopping_tables(conn: sqlite3.Connection) -> None:
    """Creates the table for persisting shopping accept/reject priors."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_shopping_priors (
            user_id TEXT NOT NULL,
            venue_type TEXT NOT NULL,
            accept_count INTEGER DEFAULT 0,
            reject_count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, venue_type)
        )
        """
    )


def record_shopping_feedback(user_id: str, venue_type: str, action: str) -> None:
    """Updates user accept or reject count for a shopping venue tier."""
    with get_connection() as conn:
        ensure_shopping_tables(conn)
        col = "accept_count" if action == "accept" else "reject_count"
        conn.execute(
            f"""
            INSERT INTO plan_shopping_priors (user_id, venue_type, {col})
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, venue_type) DO UPDATE SET
                {col} = {col} + 1
            """,
            (user_id, venue_type),
        )
        conn.commit()


def get_shopping_priors(user_id: str) -> Dict[str, Dict[str, int]]:
    """Loads a user's historical accept/reject counts per venue tier."""
    with get_connection() as conn:
        ensure_shopping_tables(conn)
        rows = conn.execute(
            "SELECT venue_type, accept_count, reject_count FROM plan_shopping_priors WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {r[0]: {"accept": r[1], "reject": r[2]} for r in rows}


def classify_shopping_venue(name: str, tags: Optional[List[str]] = None) -> str:
    """Classifies a shopping venue into one of the 4 defined tiers or 'type_unknown'."""
    text = (name + " " + " ".join(tags or [])).lower().replace("_", " ")
    for kw, tier in VENUE_TIER_MAPPING.items():
        if kw in text:
            return tier
    return "type_unknown"


def score_shopping_venue(
    venue: Place,
    profile: Dict[str, Any],
    shopping_style: str = "mix",
    priors: Optional[Dict[str, Dict[str, int]]] = None,
) -> float:
    """Scores a shopping venue based on budget tier, style preference, and feedback priors."""
    tier = classify_shopping_venue(venue.name)
    score = 0.5

    budget_tier = profile.get("budget_tier", "balanced")
    crowd_tolerance = profile.get("crowd_tolerance", 3)
    heat_sensitivity = profile.get("heat_sensitivity", 3)

    # Style alignment
    if shopping_style == "bargain_markets" and tier == "street_flea_market":
        score += 0.3
    elif shopping_style == "local_crafts" and tier == "local_market_craft_gift":
        score += 0.3
    elif shopping_style == "malls_brands" and tier == "department_store_mall":
        score += 0.3
    elif shopping_style == "mix":
        score += 0.1

    # Budget alignment
    if budget_tier == "budget":
        if tier in ("street_flea_market", "local_market_craft_gift"):
            score += 0.2
        elif tier == "boutique":
            score -= 0.3
    elif budget_tier == "luxury":
        if tier in ("boutique", "department_store_mall"):
            score += 0.2
        elif tier == "street_flea_market":
            score -= 0.1

    # Heat & crowd adjustment
    if heat_sensitivity >= 4 and tier == "department_store_mall":
        # Air-conditioned malls preferred for extreme heat
        score += 0.15
    if crowd_tolerance <= 2 and tier == "street_flea_market":
        # Dense flea markets penalized for crowd-averse travelers
        score -= 0.2

    # Prior feedback adjustment
    if priors and tier in priors:
        p = priors[tier]
        net = p.get("accept", 0) - p.get("reject", 0)
        score += net * 0.05

    return max(0.0, min(1.0, score))


def create_shopping_block(
    venue: Place,
    start_time: str,
    end_time: str,
    duration_minutes: int = 60,
) -> Block:
    """Creates a scheduled shopping Block."""
    tier = classify_shopping_venue(venue.name)
    return Block(
        block_id=f"shop_{venue.id}",
        block_type="shopping",
        start_time=start_time,
        end_time=end_time,
        duration_minutes=duration_minutes,
        place=venue,
        notes=f"Shopping stop: {tier.replace('_', ' ').title()}",
        provenance=Provenance(
            source=venue.provenance.source,
            is_live=venue.provenance.is_live,
            is_estimate=True,
            notes=f"Tier: {tier}",
        ),
    )
