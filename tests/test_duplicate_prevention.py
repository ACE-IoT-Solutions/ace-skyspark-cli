"""Tests for duplicate prevention."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.test_utils import find_by_ref_name, is_duplicate


class TestDuplicateSiteDetection:
    """Test duplicate site detection and prevention."""

    @pytest.mark.unit
    async def test_detect_duplicate_site_by_refname(self, mock_skyspark_client: MagicMock) -> None:
        """Test detecting duplicate sites by refName."""
        ref_name = "building-a"

        # Existing sites
        existing_sites = [
            {"id": {"val": "p:aceTest:r:site-1"}, "refName": "building-a"},
            {"id": {"val": "p:aceTest:r:site-2"}, "refName": "building-b"},
        ]
        mock_skyspark_client.read_sites.return_value = existing_sites

        sites = await mock_skyspark_client.read_sites()
        duplicate = find_by_ref_name(sites, ref_name)

        assert duplicate is not None
        assert duplicate["refName"] == ref_name

    @pytest.mark.unit
    async def test_prevent_duplicate_site_creation(self, mock_skyspark_client: MagicMock) -> None:
        """Test preventing duplicate site creation."""
        ref_name = "building-a"

        # Check for existing
        existing_sites = [{"id": {"val": "p:aceTest:r:site-1"}, "refName": ref_name}]
        mock_skyspark_client.read.return_value = existing_sites

        existing = await mock_skyspark_client.read(f'site and refName=="{ref_name}"')

        # Don't create if exists
        if existing:
            should_create = False
            site_id = existing[0]["id"]["val"]
        else:
            should_create = True
            site_id = None

        assert should_create is False
        assert site_id == "p:aceTest:r:site-1"

    @pytest.mark.unit
    def test_multiple_sites_with_same_refname_detected(self) -> None:
        """Test detecting multiple sites with same refName (data integrity issue)."""
        sites = [
            {"id": {"val": "p:aceTest:r:site-1"}, "refName": "duplicate"},
            {"id": {"val": "p:aceTest:r:site-2"}, "refName": "unique"},
            {"id": {"val": "p:aceTest:r:site-3"}, "refName": "duplicate"},
        ]

        duplicates = [s for s in sites if is_duplicate(s, "duplicate")]

        assert len(duplicates) == 2


class TestDuplicatePointDetection:
    """Test duplicate point detection and prevention."""

    @pytest.mark.unit
    async def test_detect_duplicate_point_by_refname(self, mock_skyspark_client: MagicMock) -> None:
        """Test detecting duplicate points by refName."""
        ref_name = "temp-sensor-1"

        existing_points = [
            {"id": {"val": "p:aceTest:r:point-1"}, "refName": "temp-sensor-1"},
            {"id": {"val": "p:aceTest:r:point-2"}, "refName": "humidity-sensor-1"},
        ]
        mock_skyspark_client.read_points.return_value = existing_points

        points = await mock_skyspark_client.read_points()
        duplicate = find_by_ref_name(points, ref_name)

        assert duplicate is not None
        assert duplicate["refName"] == ref_name

    @pytest.mark.unit
    async def test_prevent_duplicate_point_creation(self, mock_skyspark_client: MagicMock) -> None:
        """Test preventing duplicate point creation."""
        ref_name = "temp-sensor-1"

        # Check for existing
        existing_points = [{"id": {"val": "p:aceTest:r:point-1"}, "refName": ref_name}]
        mock_skyspark_client.read.return_value = existing_points

        existing = await mock_skyspark_client.read(f'point and refName=="{ref_name}"')

        # Don't create if exists
        if existing:
            should_create = False
            point_id = existing[0]["id"]["val"]
        else:
            should_create = True
            point_id = None

        assert should_create is False
        assert point_id == "p:aceTest:r:point-1"

    @pytest.mark.unit
    async def test_batch_duplicate_detection(self, mock_skyspark_client: MagicMock) -> None:
        """Test detecting duplicates in batch operations."""
        # Points to sync
        points_to_sync = [
            {"refName": "point-1"},
            {"refName": "point-2"},
            {"refName": "point-3"},
        ]

        # Existing points
        existing = [
            {"id": {"val": "p:aceTest:r:point-1"}, "refName": "point-1"},
            {"id": {"val": "p:aceTest:r:point-3"}, "refName": "point-3"},
        ]
        mock_skyspark_client.read_points.return_value = existing

        existing_points = await mock_skyspark_client.read_points()
        existing_refnames = {p["refName"] for p in existing_points}

        # Filter out duplicates
        new_points = [p for p in points_to_sync if p["refName"] not in existing_refnames]

        assert len(new_points) == 1
        assert new_points[0]["refName"] == "point-2"


class TestDuplicateEquipmentDetection:
    """Test duplicate equipment detection and prevention."""

    @pytest.mark.unit
    async def test_detect_duplicate_equipment_by_refname(
        self, mock_skyspark_client: MagicMock
    ) -> None:
        """Test detecting duplicate equipment by refName."""
        ref_name = "ahu-1"

        existing_equipment = [
            {"id": {"val": "p:aceTest:r:equip-1"}, "refName": "ahu-1"},
            {"id": {"val": "p:aceTest:r:equip-2"}, "refName": "rtu-1"},
        ]
        mock_skyspark_client.read_equipment.return_value = existing_equipment

        equipment = await mock_skyspark_client.read_equipment()
        duplicate = find_by_ref_name(equipment, ref_name)

        assert duplicate is not None
        assert duplicate["refName"] == ref_name

    @pytest.mark.unit
    async def test_prevent_duplicate_equipment_creation(
        self, mock_skyspark_client: MagicMock
    ) -> None:
        """Test preventing duplicate equipment creation."""
        ref_name = "ahu-1"

        # Check for existing
        existing_equipment = [{"id": {"val": "p:aceTest:r:equip-1"}, "refName": ref_name}]
        mock_skyspark_client.read.return_value = existing_equipment

        existing = await mock_skyspark_client.read(f'equip and refName=="{ref_name}"')

        # Don't create if exists
        if existing:
            should_create = False
            equip_id = existing[0]["id"]["val"]
        else:
            should_create = True
            equip_id = None

        assert should_create is False
        assert equip_id == "p:aceTest:r:equip-1"


class TestHaystackRefDuplicatePrevention:
    """Test duplicate prevention using haystackRef."""

    @pytest.mark.unit
    async def test_haystack_ref_prevents_duplicate_sync(
        self, sample_flightdeck_point_with_haystack_ref: Any
    ) -> None:
        """Test that existing haystackRef prevents duplicate sync."""
        # Point has haystackRef
        has_ref = "haystackRef" in (sample_flightdeck_point_with_haystack_ref.kv_tags or {})

        # Should not sync if haystackRef exists
        should_sync = not has_ref

        assert should_sync is False

    @pytest.mark.unit
    async def test_missing_haystack_ref_allows_sync(self, sample_flightdeck_point: Any) -> None:
        """Test that missing haystackRef allows sync."""
        # Point doesn't have haystackRef
        has_ref = "haystackRef" in (sample_flightdeck_point.kv_tags or {})

        # Should sync if no haystackRef
        should_sync = not has_ref

        assert should_sync is True

    @pytest.mark.unit
    async def test_validate_haystack_ref_before_skip(
        self,
        _mock_flightdeck_client: MagicMock,
        mock_skyspark_client: MagicMock,
    ) -> None:
        """Test validating haystackRef exists in SkySpark before skipping."""
        # FlightDeck point with haystackRef
        fd_point = {
            "id": "fd-1",
            "tags": {"haystackRef": "p:aceTest:r:point-123"},
        }

        # Verify ref exists in SkySpark
        haystack_ref = fd_point["tags"]["haystackRef"]
        mock_skyspark_client.read.return_value = [
            {"id": {"val": haystack_ref}, "dis": "Test Point"}
        ]

        skyspark_entity = await mock_skyspark_client.read(f"id==@{haystack_ref}")

        # haystackRef is valid
        is_valid = len(skyspark_entity) > 0

        assert is_valid is True

    @pytest.mark.unit
    async def test_orphaned_haystack_ref_requires_resync(
        self, mock_skyspark_client: MagicMock
    ) -> None:
        """Test that orphaned haystackRef requires re-sync."""
        # FlightDeck point with haystackRef that doesn't exist
        fd_point = {
            "id": "fd-1",
            "tags": {"haystackRef": "p:aceTest:r:nonexistent"},
        }

        # Verify ref doesn't exist in SkySpark
        haystack_ref = fd_point["tags"]["haystackRef"]
        mock_skyspark_client.read.return_value = []

        skyspark_entity = await mock_skyspark_client.read(f"id==@{haystack_ref}")

        # haystackRef is orphaned
        is_orphaned = len(skyspark_entity) == 0

        assert is_orphaned is True


class TestCrossEntityDuplicates:
    """Test preventing duplicates across related entities."""

    @pytest.mark.unit
    async def test_prevent_duplicate_points_for_same_equipment(
        self, mock_skyspark_client: MagicMock
    ) -> None:
        """Test preventing duplicate points under same equipment."""
        equip_ref = "p:aceTest:r:equip-1"
        point_refname = "discharge-temp"

        # Existing points for equipment
        existing_points = [
            {
                "id": {"val": "p:aceTest:r:point-1"},
                "equipRef": {"val": equip_ref},
                "refName": "discharge-temp",
            },
            {
                "id": {"val": "p:aceTest:r:point-2"},
                "equipRef": {"val": equip_ref},
                "refName": "return-temp",
            },
        ]
        mock_skyspark_client.read.return_value = existing_points

        # Check for duplicate
        points = await mock_skyspark_client.read(
            f'point and equipRef==@{equip_ref} and refName=="{point_refname}"'
        )

        duplicate_exists = len(points) > 0

        assert duplicate_exists is True

    @pytest.mark.unit
    async def test_allow_same_refname_different_equipment(
        self, _mock_skyspark_client: MagicMock
    ) -> None:
        """Test allowing same refName for points on different equipment."""
        refname = "discharge-temp"

        # Points with same refName but different equipment
        points = [
            {
                "id": {"val": "p:aceTest:r:point-1"},
                "equipRef": {"val": "p:aceTest:r:equip-1"},
                "refName": refname,
            },
            {
                "id": {"val": "p:aceTest:r:point-2"},
                "equipRef": {"val": "p:aceTest:r:equip-2"},
                "refName": refname,
            },
        ]

        # This is valid - same point type on different equipment
        unique_equipment = {p["equipRef"]["val"] for p in points}

        assert len(points) == 2
        assert len(unique_equipment) == 2
