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
   (``gateway.http``, ``notification-bot.sender`` …). This is for
   intra-PLAN debugging tools that already know a PLAN's data flow.

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
    "gateway": ["notification-bot"],
    "registry": ["watchdog"],
    "watchdog": ["notification-bot"],
}

# Fine-grained component flow examples
COMPONENT_GRAPH = {
    "gateway.http": ["gateway.router"],
    "gateway.router": ["notification-bot.sender"],
    "registry.store": ["watchdog.checker"],
}

# Map sub-component IDs back to their top-level plan_id
COMPONENT_TO_PLAN = {
    "gateway.http": "gateway",
    "gateway.router": "gateway",
    "notification-bot.sender": "notification-bot",
    "registry.store": "registry",
    "watchdog.checker": "watchdog",
}


def lift_to_plan(component_or_plan_id: str) -> str:
    """Return the owning top-level plan_id for a given component OR pass through if already a plan_id."""
    return COMPONENT_TO_PLAN.get(component_or_plan_id, component_or_plan_id)
