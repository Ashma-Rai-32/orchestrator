"""What Alembic autogenerate may touch.

LangGraph's checkpointer creates and migrates its own tables. Without this filter,
autogenerate proposes DROPPING them, which would wipe all saved run state.
"""

EXTERNALLY_MANAGED = frozenset(
    {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}
)


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Alembic `include_object` hook: skip tables (and their indexes) we don't own."""
    table = getattr(obj, "table", obj) if type_ == "index" else obj
    return getattr(table, "name", name) not in EXTERNALLY_MANAGED
