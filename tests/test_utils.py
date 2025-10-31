"""Test utilities and helper functions."""

from typing import Any


def extract_ref_id(ref_value: str | dict[str, Any]) -> str:
    """
    Extract the ID from a SkySpark reference.

    Args:
        ref_value: Either a string like "p:project:r:id" or a dict with "val" key

    Returns:
        The extracted ID portion
    """
    if isinstance(ref_value, dict):
        ref_value = ref_value.get("val", "")

    if not isinstance(ref_value, str):
        return ""

    # Format: p:project:r:id
    parts = ref_value.split(":")
    if len(parts) == 4 and parts[0] == "p" and parts[2] == "r":
        return parts[3]
    return ref_value


def build_ref_string(project: str, entity_id: str) -> str:
    """
    Build a SkySpark reference string.

    Args:
        project: The SkySpark project name
        entity_id: The entity ID

    Returns:
        Reference string in format "p:project:r:id"
    """
    return f"p:{project}:r:{entity_id}"


def has_marker_tag(entity: dict[str, Any], tag: str) -> bool:
    """
    Check if an entity has a specific marker tag.

    Args:
        entity: The SkySpark entity dict
        tag: The tag name to check

    Returns:
        True if the marker tag exists
    """
    tag_value = entity.get(tag)
    if tag_value is None:
        return False
    if isinstance(tag_value, dict) and tag_value.get("_kind") == "marker":
        return True
    return False


def get_kv_tag(entity: dict[str, Any], tag: str) -> Any:
    """
    Get a key-value tag from an entity.

    Args:
        entity: The SkySpark entity dict
        tag: The tag name

    Returns:
        The tag value, or None if not found
    """
    tag_value = entity.get(tag)
    if tag_value is None:
        return None

    # Handle typed values
    if isinstance(tag_value, dict):
        kind = tag_value.get("_kind")
        if kind in ("number", "str", "bool", "date", "time", "datetime"):
            return tag_value.get("val")
        if kind == "ref":
            return tag_value.get("val")

    return tag_value


def normalize_tags_from_flightdeck(tags: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """
    Normalize FlightDeck tags into marker tags and key-value tags.

    Args:
        tags: FlightDeck tags dictionary

    Returns:
        Tuple of (marker_tags, kv_tags)
    """
    marker_tags = []
    kv_tags = {}

    for key, value in tags.items():
        # Skip haystackRef as it's handled separately
        if key == "haystackRef":
            continue

        if value is None or value == "":
            # Marker tag
            marker_tags.append(key)
        else:
            # Key-value tag
            kv_tags[key] = value

    return marker_tags, kv_tags


def create_haystack_ref_tag(skyspark_id: str) -> str:
    """
    Create a haystackRef tag value for FlightDeck.

    Args:
        skyspark_id: Full SkySpark ID (e.g., "p:project:r:id")

    Returns:
        The haystackRef value
    """
    return skyspark_id


def extract_haystack_ref(flightdeck_point: Any) -> str | None:
    """
    Extract haystackRef from a FlightDeck point.

    Args:
        flightdeck_point: The FlightDeck point object

    Returns:
        The haystackRef value or None
    """
    # Try kv_tags first (aceiot-models Point structure)
    if hasattr(flightdeck_point, "kv_tags") and isinstance(flightdeck_point.kv_tags, dict):
        return flightdeck_point.kv_tags.get("haystackRef")
    # Fallback to tags attribute
    if hasattr(flightdeck_point, "tags") and isinstance(flightdeck_point.tags, dict):
        return flightdeck_point.tags.get("haystackRef")
    return None


def find_by_ref_name(entities: list[dict[str, Any]], ref_name: str) -> dict[str, Any] | None:
    """
    Find an entity by its refName.

    Args:
        entities: List of SkySpark entities
        ref_name: The refName to search for

    Returns:
        The matching entity or None
    """
    for entity in entities:
        if entity.get("refName") == ref_name:
            return entity
    return None


def is_duplicate(entity: dict[str, Any], ref_name: str) -> bool:
    """
    Check if an entity is a duplicate based on refName.

    Args:
        entity: The SkySpark entity
        ref_name: The refName to check

    Returns:
        True if this is a duplicate
    """
    return entity.get("refName") == ref_name
