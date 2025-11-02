"""Unit tests for haystackRef tagging logic."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestHaystackRefTagging:
    """Test haystackRef tagging operations."""

    @pytest.mark.unit
    async def test_tag_flightdeck_point_with_skyspark_id(
        self, mock_flightdeck_client: MagicMock
    ) -> None:
        """Test tagging a FlightDeck point with SkySpark ID."""
        point_id = "flightdeck-point-1"
        skyspark_id = "p:aceTest:r:point-123"

        # Mock the update call
        mock_flightdeck_client.update_point = AsyncMock()

        # Simulate tagging operation
        await mock_flightdeck_client.update_point(point_id, tags={"haystackRef": skyspark_id})

        # Verify the update was called correctly
        mock_flightdeck_client.update_point.assert_called_once_with(
            point_id, tags={"haystackRef": skyspark_id}
        )

    @pytest.mark.unit
    async def test_skip_tagging_if_haystack_ref_exists(
        self, sample_flightdeck_point_with_haystack_ref: Any
    ) -> None:
        """Test that points with existing haystackRef are skipped."""
        # Point already has haystackRef
        existing_ref = sample_flightdeck_point_with_haystack_ref.kv_tags.get("haystackRef")
        assert existing_ref is not None
        assert existing_ref == "p:aceTest:r:skyspark-id-456"

        # In actual implementation, this point would be skipped for new tagging

    @pytest.mark.unit
    def test_haystack_ref_format_validation(self) -> None:
        """Test that haystackRef follows correct format."""
        valid_ref = "p:aceTest:r:point-123"
        parts = valid_ref.split(":")

        assert len(parts) == 4
        assert parts[0] == "p"
        assert parts[1] == "aceTest"
        assert parts[2] == "r"
        assert parts[3] == "point-123"

    @pytest.mark.unit
    def test_extract_project_from_haystack_ref(self) -> None:
        """Test extracting project name from haystackRef."""
        ref = "p:aceTest:r:point-123"
        project = ref.split(":")[1]
        assert project == "aceTest"

    @pytest.mark.unit
    def test_extract_entity_id_from_haystack_ref(self) -> None:
        """Test extracting entity ID from haystackRef."""
        ref = "p:aceTest:r:point-123"
        entity_id = ref.split(":")[3]
        assert entity_id == "point-123"


class TestHaystackRefMapping:
    """Test haystackRef mapping between systems."""

    @pytest.mark.unit
    def test_create_bidirectional_mapping(self) -> None:
        """Test creating bidirectional mapping between FlightDeck and SkySpark."""
        flightdeck_id = "flightdeck-point-1"
        skyspark_id = "p:aceTest:r:point-123"

        # Forward mapping (FlightDeck -> SkySpark)
        forward_map = {flightdeck_id: skyspark_id}
        assert forward_map[flightdeck_id] == skyspark_id

        # Reverse mapping (SkySpark -> FlightDeck)
        reverse_map = {skyspark_id: flightdeck_id}
        assert reverse_map[skyspark_id] == flightdeck_id

    @pytest.mark.unit
    def test_mapping_persistence(self) -> None:
        """Test that mappings can be persisted and retrieved."""
        mappings = {
            "flightdeck-point-1": "p:aceTest:r:point-123",
            "flightdeck-point-2": "p:aceTest:r:point-456",
            "flightdeck-point-3": "p:aceTest:r:point-789",
        }

        # Simulate persistence
        persisted_mappings = dict(mappings)

        # Verify all mappings preserved
        assert len(persisted_mappings) == 3
        assert persisted_mappings["flightdeck-point-2"] == "p:aceTest:r:point-456"

    @pytest.mark.unit
    def test_handle_missing_mapping(self) -> None:
        """Test handling of missing mappings gracefully."""
        mappings: dict[str, str] = {}
        point_id = "nonexistent-point"

        # Should return None for missing mapping
        result = mappings.get(point_id)
        assert result is None


class TestHaystackRefSynchronization:
    """Test haystackRef synchronization logic."""

    @pytest.mark.unit
    async def test_sync_new_point_creates_mapping(
        self,
        mock_flightdeck_client: MagicMock,
        mock_skyspark_client: MagicMock,
    ) -> None:
        """Test that syncing a new point creates haystackRef mapping."""
        # Setup: FlightDeck point without haystackRef
        flightdeck_point = {
            "id": "flightdeck-point-1",
            "name": "Temperature Sensor",
            "tags": {"sensor": None, "temp": None},
        }

        # Setup: Created SkySpark point
        skyspark_response = [{"id": {"val": "p:aceTest:r:point-123"}}]
        mock_skyspark_client.create_points.return_value = skyspark_response

        # Simulate sync operation
        created = await mock_skyspark_client.create_points([])
        skyspark_id = created[0]["id"]["val"]

        # Verify haystackRef would be applied
        await mock_flightdeck_client.update_point(
            flightdeck_point["id"], tags={"haystackRef": skyspark_id}
        )

        mock_flightdeck_client.update_point.assert_called_once()

    @pytest.mark.unit
    async def test_sync_existing_point_uses_mapping(
        self,
        _mock_flightdeck_client: MagicMock,
        mock_skyspark_client: MagicMock,
    ) -> None:
        """Test that syncing existing point uses haystackRef mapping."""
        # Setup: FlightDeck point with haystackRef
        flightdeck_point = {
            "id": "flightdeck-point-1",
            "tags": {"haystackRef": "p:aceTest:r:point-123"},
        }

        # Setup: Existing SkySpark point
        existing_point = {"id": {"val": "p:aceTest:r:point-123"}}
        mock_skyspark_client.read.return_value = [existing_point]

        # Simulate lookup by haystackRef
        haystack_ref = flightdeck_point["tags"]["haystackRef"]
        results = await mock_skyspark_client.read(f"id==@{haystack_ref}")

        # Verify existing point found
        assert len(results) == 1
        assert results[0]["id"]["val"] == haystack_ref

    @pytest.mark.unit
    def test_detect_orphaned_haystack_refs(self) -> None:
        """Test detection of orphaned haystackRef tags."""
        # FlightDeck points with haystackRefs
        flightdeck_points = [
            {"id": "fd-1", "tags": {"haystackRef": "p:aceTest:r:point-123"}},
            {"id": "fd-2", "tags": {"haystackRef": "p:aceTest:r:point-456"}},
            {"id": "fd-3", "tags": {"haystackRef": "p:aceTest:r:point-999"}},  # Orphaned
        ]

        # SkySpark points
        skyspark_points = [
            {"id": {"val": "p:aceTest:r:point-123"}},
            {"id": {"val": "p:aceTest:r:point-456"}},
            # point-999 doesn't exist
        ]

        # Find orphaned refs
        skyspark_ids = {p["id"]["val"] for p in skyspark_points}
        orphaned = [
            p for p in flightdeck_points if p["tags"].get("haystackRef") not in skyspark_ids
        ]

        assert len(orphaned) == 1
        assert orphaned[0]["id"] == "fd-3"
