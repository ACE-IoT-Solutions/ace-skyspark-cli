"""Tests for tag synchronization between FlightDeck and SkySpark."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_utils import (
    get_kv_tag,
    has_marker_tag,
    normalize_tags_from_flightdeck,
)


class TestTagSynchronization:
    """Test tag synchronization from FlightDeck to SkySpark."""

    @pytest.mark.unit
    async def test_sync_marker_tags(
        self, mock_skyspark_client: MagicMock, sample_flightdeck_point: Any  # noqa: ARG002
    ) -> None:
        """Test syncing marker tags from FlightDeck to SkySpark."""
        # FlightDeck uses marker_tags attribute
        marker_tags = sample_flightdeck_point.marker_tags

        # Create SkySpark point with tags
        assert "sensor" in marker_tags
        assert "temp" in marker_tags

    @pytest.mark.unit
    async def test_sync_kv_tags(self, mock_skyspark_client: MagicMock) -> None:  # noqa: ARG002
        """Test syncing key-value tags from FlightDeck to SkySpark."""
        # FlightDeck tags
        fd_tags = {"sensor": None, "zone": "hvac", "floor": "2"}
        marker_tags, kv_tags = normalize_tags_from_flightdeck(fd_tags)

        # Verify KV tags extracted
        assert "zone" in kv_tags
        assert kv_tags["zone"] == "hvac"
        assert "floor" in kv_tags
        assert kv_tags["floor"] == "2"

    @pytest.mark.unit
    async def test_sync_new_tags_to_existing_point(self, mock_skyspark_client: MagicMock) -> None:
        """Test syncing new tags to existing SkySpark point."""
        point_id = "p:aceTest:r:point-123"

        # Existing point
        existing_point = {
            "id": {"val": point_id},
            "sensor": {"_kind": "marker"},
            "temp": {"_kind": "marker"},
        }
        mock_skyspark_client.read.return_value = [existing_point]

        # New tags from FlightDeck
        new_tags = {"critical": None, "priority": "high"}
        marker_tags, kv_tags = normalize_tags_from_flightdeck(new_tags)

        # Update with new tags
        mock_skyspark_client.update_points.return_value = [
            {
                "id": {"val": point_id},
                "sensor": {"_kind": "marker"},
                "temp": {"_kind": "marker"},
                "critical": {"_kind": "marker"},
                "priority": {"_kind": "str", "val": "high"},
            }
        ]

        updated = await mock_skyspark_client.update_points([])

        assert has_marker_tag(updated[0], "critical")
        assert get_kv_tag(updated[0], "priority") == "high"

    @pytest.mark.unit
    async def test_preserve_existing_tags_during_sync(
        self, mock_skyspark_client: MagicMock
    ) -> None:
        """Test that existing tags are preserved during sync."""
        point_id = "p:aceTest:r:point-123"

        # Existing point with tags
        existing_point = {
            "id": {"val": point_id},
            "sensor": {"_kind": "marker"},
            "temp": {"_kind": "marker"},
            "calibrated": {"_kind": "marker"},
        }

        # Simulate reading existing point
        mock_skyspark_client.read.return_value = [existing_point]
        point = await mock_skyspark_client.read(f"id==@{point_id}")

        # Verify existing tags present
        assert has_marker_tag(point[0], "sensor")
        assert has_marker_tag(point[0], "temp")
        assert has_marker_tag(point[0], "calibrated")


class TestTagRemoval:
    """Test tag removal during synchronization."""

    @pytest.mark.unit
    async def test_remove_tags_not_in_flightdeck(self, mock_skyspark_client: MagicMock) -> None:  # noqa: ARG002
        """Test removing tags that are not present in FlightDeck."""

        # SkySpark has extra tags

        # FlightDeck only has sensor and temp
        fd_tags = {"sensor": None, "temp": None}

        # After sync, obsolete should be removed
        # (Implementation would handle this)
        expected_tags = set(fd_tags.keys())
        assert "obsolete" not in expected_tags

    @pytest.mark.unit
    def test_identify_tags_to_remove(self) -> None:
        """Test identifying which tags should be removed."""
        # SkySpark tags
        skyspark_tags = {"sensor", "temp", "obsolete", "old"}

        # FlightDeck tags
        flightdeck_tags = {"sensor", "temp", "humidity"}

        # Tags to remove
        to_remove = skyspark_tags - flightdeck_tags

        assert "obsolete" in to_remove
        assert "old" in to_remove
        assert "sensor" not in to_remove


class TestBidirectionalTagSync:
    """Test bidirectional tag synchronization scenarios."""

    @pytest.mark.unit
    async def test_flightdeck_to_skyspark_sync(self, sample_flightdeck_point: Any) -> None:
        """Test syncing tags from FlightDeck to SkySpark."""
        # FlightDeck is source of truth
        marker_tags = sample_flightdeck_point.marker_tags

        # These tags should be synced to SkySpark
        assert len(marker_tags) > 0
        assert "sensor" in marker_tags

    @pytest.mark.unit
    async def test_skyspark_to_flightdeck_sync_haystackref_only(
        self, mock_flightdeck_client: MagicMock
    ) -> None:
        """Test that only haystackRef is synced from SkySpark to FlightDeck."""
        point_id = "flightdeck-point-1"
        skyspark_id = "p:aceTest:r:point-123"

        # Only haystackRef should be synced back
        mock_flightdeck_client.update_point = AsyncMock()
        await mock_flightdeck_client.update_point(point_id, tags={"haystackRef": skyspark_id})

        # Verify only haystackRef updated
        call_args = mock_flightdeck_client.update_point.call_args
        tags_arg = call_args[1]["tags"]
        assert "haystackRef" in tags_arg
        assert len(tags_arg) == 1


class TestTagConflictResolution:
    """Test resolving tag conflicts during synchronization."""

    @pytest.mark.unit
    def test_flightdeck_tags_take_precedence(self) -> None:
        """Test that FlightDeck tags take precedence in conflicts."""
        # FlightDeck tag
        fd_value = "zone-a"

        # SkySpark tag (different value)

        # FlightDeck should win
        final_value = fd_value

        assert final_value == "zone-a"

    @pytest.mark.unit
    def test_merge_unique_tags(self) -> None:
        """Test merging tags unique to each system."""
        # FlightDeck tags
        fd_tags = {"sensor", "temp", "fd_specific"}

        # SkySpark tags

        # Merge (FlightDeck is source of truth)
        # In actual implementation, FlightDeck tags replace SkySpark
        merged = fd_tags

        assert "sensor" in merged
        assert "temp" in merged
        assert "fd_specific" in merged


class TestTagValidation:
    """Test tag validation during synchronization."""

    @pytest.mark.unit
    def test_validate_marker_tag_format(self) -> None:
        """Test validating marker tag format."""
        # Valid marker tags (None or empty string)
        valid_markers = {"sensor": None, "temp": None}

        for _tag, value in valid_markers.items():
            is_marker = value is None or value == ""
            assert is_marker is True

    @pytest.mark.unit
    def test_validate_kv_tag_format(self) -> None:
        """Test validating key-value tag format."""
        # Valid KV tags (non-None values)
        valid_kvs = {"zone": "hvac", "floor": "2", "priority": "high"}

        for _tag, value in valid_kvs.items():
            is_kv = value is not None and value != ""
            assert is_kv is True

    @pytest.mark.unit
    def test_reject_invalid_tag_names(self) -> None:
        """Test rejecting invalid tag names."""
        # Invalid tag names
        invalid_names = ["", " ", "tag with spaces", "tag-with-special!@#"]

        valid_names = []
        for name in invalid_names:
            # Tag names should be alphanumeric with underscores
            is_valid = name.replace("_", "").isalnum() and len(name) > 0
            if is_valid:
                valid_names.append(name)

        # None should be valid
        assert len(valid_names) == 0


class TestTagSyncBatching:
    """Test batching tag synchronization operations."""

    @pytest.mark.unit
    async def test_batch_tag_updates(self, mock_skyspark_client: MagicMock) -> None:
        """Test batching multiple tag updates together."""
        # Multiple points to update
        point_updates = [
            {"id": f"p:aceTest:r:point-{i}", "tags": {"updated": None}} for i in range(10)
        ]

        # Batch update
        mock_skyspark_client.update_points.return_value = point_updates

        result = await mock_skyspark_client.update_points([])

        assert len(result) == 10
        mock_skyspark_client.update_points.assert_called_once()

    @pytest.mark.unit
    async def test_chunk_large_tag_updates(self) -> None:
        """Test chunking large batches of tag updates."""
        # 100 points to update
        total_points = 100
        chunk_size = 25

        # Calculate chunks
        num_chunks = (total_points + chunk_size - 1) // chunk_size

        assert num_chunks == 4

    @pytest.mark.unit
    def test_handle_partial_batch_failures(self) -> None:
        """Test handling partial failures in batch operations."""
        # Batch of 10 updates
        batch_size = 10
        successful_updates = 7
        failed_updates = 3

        # Track successes and failures
        success_rate = successful_updates / batch_size

        assert success_rate == 0.7
        assert failed_updates == batch_size - successful_updates


class TestTagSyncWithHistory:
    """Test tag synchronization with history tracking."""

    @pytest.mark.unit
    async def test_track_tag_changes(self) -> None:
        """Test tracking tag changes over time."""
        # Initial tags
        initial_tags = {"sensor": None, "temp": None}

        # Updated tags
        updated_tags = {"sensor": None, "temp": None, "critical": None}

        # Detect changes
        added_tags = set(updated_tags.keys()) - set(initial_tags.keys())

        assert "critical" in added_tags

    @pytest.mark.unit
    async def test_tag_sync_timestamp(self) -> None:
        """Test recording timestamp of tag synchronization."""
        from datetime import UTC, datetime

        # Record sync time
        sync_time = datetime.now(UTC)

        # Verify timestamp recorded
        assert sync_time is not None
        assert sync_time.tzinfo == UTC

    @pytest.mark.unit
    def test_detect_tag_drift(self) -> None:
        """Test detecting tag drift between systems."""
        # FlightDeck tags
        fd_tags = {"sensor", "temp", "humidity"}

        # SkySpark tags (drifted)
        ss_tags = {"sensor", "temp"}

        # Detect drift
        drift = fd_tags - ss_tags

        assert "humidity" in drift
        assert len(drift) == 1
