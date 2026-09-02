"""Entity action compatibility namespace.

The implementation remains in :mod:`kb_harness.entity` so the legacy script
and the Phase 3 action share exactly the same schema and validation behavior.
"""

from ..entity import EntityPlan, EntitySpecError, load_entity_spec, plan_entity_create

__all__ = ["EntityPlan", "EntitySpecError", "load_entity_spec", "plan_entity_create"]
