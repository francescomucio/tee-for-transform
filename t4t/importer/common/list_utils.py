"""
Common list utility functions.
"""


def deduplicate_preserve_order[T](items: list[T]) -> list[T]:
    """
    Remove duplicates from a list while preserving order (first occurrence wins).

    Args:
        items: List with potential duplicates

    Returns:
        List with duplicates removed, preserving order of first occurrence
    """
    seen = set()
    unique_items = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique_items.append(item)
    return unique_items
