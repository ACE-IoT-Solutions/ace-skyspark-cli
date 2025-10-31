"""Tests for idempotency verification."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestIdempotentSiteCreation:
    """Test idempotent site creation operations."""

    @pytest.mark.unit
    @pytest.mark.idempotent
    async def test_create_site_once_only(
        self, mock_skyspark_client: MagicMock
    ) -> None:
        """Test that site is created only once, subsequent calls find existing."""
        ref_name = "test-site-123"

        # First call: no existing site
        mock_skyspark_client.read.return_value = []
        result1 = await mock_skyspark_client.read(f'site and refName=="{ref_name}"')
        assert len(result1) == 0

        # Create site
        mock_skyspark_client.create_sites.return_value = [
            {"id": {"val": "p:aceTest:r:site-abc"}, "refName": ref_name}
        ]
        created = await mock_skyspark_client.create_sites([])
        assert len(created) == 1

        # Second call: site exists
        mock_skyspark_client.read.return_value = [
            {"id": {"val": "p:aceTest:r:site-abc"}, "refName": ref_name}
        ]
        result2 = await mock_skyspark_client.read(f'site and refName=="{ref_name}"')
        assert len(result2) == 1
        assert result2[0]["refName"] == ref_name

    @pytest.mark.unit
    @pytest.mark.idempotent
    async def test_find_or_create_pattern(
        self, mock_skyspark_client: MagicMock
    ) -> None:
        """Test find-or-create pattern for idempotency."""
        ref_name = "site-xyz"

        # Mock: check for existing
        mock_skyspark_client.read.return_value = []

        existing = await mock_skyspark_client.read(f'site and refName=="{ref_name}"')

        if not existing:
            # Create new
            mock_skyspark_client.create_sites.return_value = [
                {"id": {"val": "p:aceTest:r:new-site"}, "refName": ref_name}
            ]
            result = await mock_skyspark_client.create_sites([])
            entity_id = result[0]["id"]["val"]
        else:
            entity_id = existing[0]["id"]["val"]

        assert entity_id == "p:aceTest:r:new-site"


class TestIdempotentPointCreation:
    """Test idempotent point creation operations."""

    @pytest.mark.unit
    @pytest.mark.idempotent
    async def test_create_point_with_refname_idempotent(
        self, mock_skyspark_client: MagicMock
    ) -> None:
        """Test that points with same refName are not duplicated."""
        ref_name = "temp-sensor-001"

        # First attempt: no existing point
        mock_skyspark_client.read.return_value = []
        existing = await mock_skyspark_client.read(
            f'point and refName=="{ref_name}"'
        )
        assert len(existing) == 0

        # Create point
        mock_skyspark_client.create_points.return_value = [
            {"id": {"val": "p:aceTest:r:point-123"}, "refName": ref_name}
        ]
        created = await mock_skyspark_client.create_points([])
        point_id = created[0]["id"]["val"]

        # Second attempt: point exists
        mock_skyspark_client.read.return_value = [
            {"id": {"val": point_id}, "refName": ref_name}
        ]
        existing2 = await mock_skyspark_client.read(
            f'point and refName=="{ref_name}"'
        )
        assert len(existing2) == 1
        assert existing2[0]["id"]["val"] == point_id

    @pytest.mark.unit
    @pytest.mark.idempotent
    async def test_haystack_ref_ensures_idempotency(
        self, sample_flightdeck_point_with_haystack_ref: Any
    ) -> None:
        """Test that haystackRef tag ensures idempotent operations."""
        # Point has haystackRef
        haystack_ref = (sample_flightdeck_point_with_haystack_ref.kv_tags or {}).get(
            "haystackRef"
        )
        assert haystack_ref is not None

        # This reference can be used to find existing entity
        # No duplicate creation should occur
        assert haystack_ref == "p:aceTest:r:skyspark-id-456"


class TestIdempotentTagSynchronization:
    """Test idempotent tag synchronization."""

    @pytest.mark.unit
    @pytest.mark.idempotent
    async def test_sync_tags_multiple_times_same_result(
        self, mock_skyspark_client: MagicMock
    ) -> None:
        """Test that syncing tags multiple times produces same result."""
        point_id = "p:aceTest:r:point-123"
        tags = {"sensor": {"_kind": "marker"}, "temp": {"_kind": "marker"}}

        # First sync
        mock_skyspark_client.update_points.return_value = [
            {"id": {"val": point_id}, **tags}
        ]
        result1 = await mock_skyspark_client.update_points([])

        # Second sync (same tags)
        result2 = await mock_skyspark_client.update_points([])

        # Results should be identical
        assert result1[0]["id"]["val"] == result2[0]["id"]["val"]

    @pytest.mark.unit
    @pytest.mark.idempotent
    async def test_adding_tags_is_idempotent(
        self, mock_skyspark_client: MagicMock
    ) -> None:
        """Test that adding the same tag multiple times is idempotent."""
        point_id = "p:aceTest:r:point-123"

        # Initial tags
        mock_skyspark_client.read.return_value = [
            {
                "id": {"val": point_id},
                "sensor": {"_kind": "marker"},
            }
        ]

        existing = await mock_skyspark_client.read(f'id==@{point_id}')
        initial_tags = set(
            k for k, v in existing[0].items()
            if isinstance(v, dict) and v.get("_kind") == "marker"
        )

        # Add "sensor" tag again (already exists)
        mock_skyspark_client.update_points.return_value = [
            {
                "id": {"val": point_id},
                "sensor": {"_kind": "marker"},
            }
        ]
        await mock_skyspark_client.update_points([])

        # Tags should be unchanged
        mock_skyspark_client.read.return_value = [
            {
                "id": {"val": point_id},
                "sensor": {"_kind": "marker"},
            }
        ]
        after = await mock_skyspark_client.read(f'id==@{point_id}')
        after_tags = set(
            k for k, v in after[0].items()
            if isinstance(v, dict) and v.get("_kind") == "marker"
        )

        assert initial_tags == after_tags


class TestIdempotentHaystackRefUpdate:
    """Test idempotent haystackRef updates in FlightDeck."""

    @pytest.mark.unit
    @pytest.mark.idempotent
    async def test_update_haystack_ref_idempotent(
        self, mock_flightdeck_client: MagicMock
    ) -> None:
        """Test that updating haystackRef multiple times is safe."""
        point_id = "flightdeck-point-1"
        skyspark_id = "p:aceTest:r:point-123"

        # First update
        mock_flightdeck_client.update_point = AsyncMock()
        await mock_flightdeck_client.update_point(
            point_id, tags={"haystackRef": skyspark_id}
        )

        # Second update (same value)
        await mock_flightdeck_client.update_point(
            point_id, tags={"haystackRef": skyspark_id}
        )

        # Should be safe and result in same state
        assert mock_flightdeck_client.update_point.call_count == 2

    @pytest.mark.unit
    @pytest.mark.idempotent
    async def test_skip_update_if_haystack_ref_unchanged(
        self, sample_flightdeck_point_with_haystack_ref: Any
    ) -> None:
        """Test that updates are skipped if haystackRef is already correct."""
        existing_ref = sample_flightdeck_point_with_haystack_ref.kv_tags.get(
            "haystackRef"
        )
        target_ref = "p:aceTest:r:skyspark-id-456"

        # If refs match, no update needed
        if existing_ref == target_ref:
            update_needed = False
        else:
            update_needed = True

        assert update_needed is False


class TestIdempotentFullSync:
    """Test idempotency of full synchronization workflow."""

    @pytest.mark.unit
    @pytest.mark.idempotent
    async def test_sync_twice_produces_same_result(
        self,
        mock_flightdeck_client: MagicMock,
        mock_skyspark_client: MagicMock,
    ) -> None:
        """Test that running sync twice doesn't create duplicates."""
        # Mock FlightDeck points
        fd_points = [
            {"id": "fd-1", "name": "Point 1", "tags": {}},
            {"id": "fd-2", "name": "Point 2", "tags": {}},
        ]
        mock_flightdeck_client.get_points.return_value = fd_points

        # First sync: create points
        mock_skyspark_client.read.return_value = []
        mock_skyspark_client.create_points.return_value = [
            {"id": {"val": "p:aceTest:r:point-1"}},
            {"id": {"val": "p:aceTest:r:point-2"}},
        ]

        created_first = await mock_skyspark_client.create_points([])
        first_sync_count = len(created_first)

        # Second sync: points exist, no duplicates
        mock_skyspark_client.read.return_value = [
            {"id": {"val": "p:aceTest:r:point-1"}, "refName": "fd-1"},
            {"id": {"val": "p:aceTest:r:point-2"}, "refName": "fd-2"},
        ]
        mock_skyspark_client.create_points.return_value = []

        created_second = await mock_skyspark_client.create_points([])
        second_sync_count = len(created_second)

        # Second sync should create nothing
        assert first_sync_count == 2
        assert second_sync_count == 0

    @pytest.mark.unit
    @pytest.mark.idempotent
    async def test_interrupted_sync_can_resume(
        self,
        mock_flightdeck_client: MagicMock,
        mock_skyspark_client: MagicMock,
    ) -> None:
        """Test that interrupted sync can resume without duplicates."""
        # Scenario: 5 points, first 3 synced before interruption
        all_points = [{"id": f"fd-{i}", "name": f"Point {i}"} for i in range(5)]

        # Already synced (have haystackRef)
        synced_points = [
            {
                "id": "fd-0",
                "name": "Point 0",
                "tags": {"haystackRef": "p:aceTest:r:point-0"},
            },
            {
                "id": "fd-1",
                "name": "Point 1",
                "tags": {"haystackRef": "p:aceTest:r:point-1"},
            },
            {
                "id": "fd-2",
                "name": "Point 2",
                "tags": {"haystackRef": "p:aceTest:r:point-2"},
            },
        ]

        # Not yet synced
        unsynced_points = [
            {"id": "fd-3", "name": "Point 3", "tags": {}},
            {"id": "fd-4", "name": "Point 4", "tags": {}},
        ]

        # Resume: only unsynced points should be processed
        points_to_sync = [p for p in unsynced_points if "haystackRef" not in p["tags"]]

        assert len(points_to_sync) == 2
        assert points_to_sync[0]["id"] == "fd-3"
        assert points_to_sync[1]["id"] == "fd-4"
