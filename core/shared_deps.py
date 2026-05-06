"""
Shared Dependency Graph for PLAN Registry
==========================================

Single source of truth for the PLAN dependency graph.
Used by plan_registry.py and conflict_detector.py.

We track TWO views:

1. ``DEPENDENCY_GRAPH`` — uses TOP-LEVEL plan_ids (the IDs that appear in
   registry.json). This is what ``plan_registry.get_affected_plans`` and
   ``plan_registry.correlate_incidents`` walk, so they can correlate against
   ACTUAL registered plans.

2. ``COMPONENT_GRAPH`` — uses fine-grained sub-component IDs
   (``arena.ea_bridge``, ``arena.simulator`` …). This is for
   intra-PLAN debugging tools that already know about Arena's data flow.

3. ``COMPONENT_TO_PLAN`` — maps any sub-component ID back to its owning
   top-level plan_id, so a sub-component alert can be lifted up to a
   PLAN-level incident.

If you add a new top-level PLAN, register it in DEPENDENCY_GRAPH.
If you add a new sub-component, register it in COMPONENT_GRAPH AND
COMPONENT_TO_PLAN.
"""

from __future__ import annotations

# parent_plan -> [child plans that depend on parent]
DEPENDENCY_GRAPH = {
    # MT4 EA on Windows feeds Arena and the Trading Server
    "mt4-ea":          ["arena", "trading-server"],
    # Arena owns its full internal pipeline; trading-server reads from arena live_data
    "arena":           ["trading-server"],
    # Watchdog keeps these two alive
    "watchdog":        ["board-bot", "hermes-tg-bot"],
    # Hermes Gateway is the single egress; if it drops, the TG bot can't reach
    "hermes-gateway":  ["hermes-tg-bot"],
}

# Fine-grained component flow inside Arena (A → B → C → D → E → F)
COMPONENT_GRAPH = {
    "mt4-ea":                 ["arena.ea_bridge", "trading-server"],
    "arena.ea_bridge":        ["arena.simulator", "arena.signal_engine"],
    "arena.simulator":        ["arena.referee", "arena.score_publisher"],
    "arena.score_publisher":  ["arena.dashboard"],
}

# Map sub-component IDs back to their top-level plan_id
COMPONENT_TO_PLAN = {
    "arena.ea_bridge":       "arena",
    "arena.simulator":       "arena",
    "arena.signal_engine":   "arena",
    "arena.referee":         "arena",
    "arena.score_publisher": "arena",
    "arena.dashboard":       "arena",
}


def lift_to_plan(component_or_plan_id: str) -> str:
    """Return the owning top-level plan_id for a given component OR pass through if already a plan_id."""
    return COMPONENT_TO_PLAN.get(component_or_plan_id, component_or_plan_id)
