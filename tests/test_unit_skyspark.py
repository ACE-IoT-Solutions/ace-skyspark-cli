"""Unit tests for SkySpark entity creation and management."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from ace_skyspark_lib import Equipment, Point, Site


class TestSiteCreation:
    """Test SkySpark site creation."""

    @pytest.mark.unit
    async def test_create_site_success(
        self, mock_skyspark_client: MagicMock, sample_site_model: Site
    ) -> None:
        """Test successful site creation."""
        # Mock response
        mock_response = [{"id": {"val": "p:aceTest:r:site-123"}, "dis": "Test Building"}]
        mock_skyspark_client.create_sites.return_value = mock_response

        # Create site
        result = await mock_skyspark_client.create_sites([sample_site_model])

        # Verify
        assert len(result) == 1
        assert result[0]["id"]["val"] == "p:aceTest:r:site-123"
        mock_skyspark_client.create_sites.assert_called_once()

    @pytest.mark.unit
    async def test_create_multiple_sites(self, mock_skyspark_client: MagicMock) -> None:
        """Test creating multiple sites at once."""
        sites = [
            Site(dis="Building A", tz="America/New_York", refName="site-a"),
            Site(dis="Building B", tz="America/Chicago", refName="site-b"),
            Site(dis="Building C", tz="America/Los_Angeles", refName="site-c"),
        ]

        mock_response = [{"id": {"val": f"p:aceTest:r:site-{i}"}} for i in range(len(sites))]
        mock_skyspark_client.create_sites.return_value = mock_response

        result = await mock_skyspark_client.create_sites(sites)

        assert len(result) == 3
        mock_skyspark_client.create_sites.assert_called_once_with(sites)

    @pytest.mark.unit
    async def test_find_existing_site_by_refname(
        self, mock_skyspark_client: MagicMock, sample_skyspark_site: dict[str, Any]
    ) -> None:
        """Test finding existing site by refName."""
        mock_skyspark_client.read.return_value = [sample_skyspark_site]

        result = await mock_skyspark_client.read('site and refName=="site-abc"')

        assert len(result) == 1
        assert result[0]["refName"] == "site-abc"


class TestEquipmentCreation:
    """Test SkySpark equipment creation."""

    @pytest.mark.unit
    async def test_create_equipment_success(
        self, mock_skyspark_client: MagicMock, sample_equipment_model: Equipment
    ) -> None:
        """Test successful equipment creation."""
        mock_response = [{"id": {"val": "p:aceTest:r:equip-456"}, "dis": "RTU-1"}]
        mock_skyspark_client.create_equipment.return_value = mock_response

        result = await mock_skyspark_client.create_equipment([sample_equipment_model])

        assert len(result) == 1
        assert result[0]["id"]["val"] == "p:aceTest:r:equip-456"

    @pytest.mark.unit
    async def test_create_equipment_with_site_ref(self, mock_skyspark_client: MagicMock) -> None:
        """Test creating equipment with site reference."""
        equipment = Equipment(
            dis="AHU-1",
            site_ref="p:aceTest:r:site-123",
            refName="device-123",
            marker_tags=["ahu", "hvac"],
        )

        mock_response = [{"id": {"val": "p:aceTest:r:equip-456"}}]
        mock_skyspark_client.create_equipment.return_value = mock_response

        result = await mock_skyspark_client.create_equipment([equipment])

        assert len(result) == 1
        mock_skyspark_client.create_equipment.assert_called_once()

    @pytest.mark.unit
    async def test_find_existing_equipment_by_refname(
        self,
        mock_skyspark_client: MagicMock,
        sample_skyspark_equipment: dict[str, Any],
    ) -> None:
        """Test finding existing equipment by refName."""
        mock_skyspark_client.read.return_value = [sample_skyspark_equipment]

        result = await mock_skyspark_client.read('equip and refName=="device-123"')

        assert len(result) == 1
        assert result[0]["refName"] == "device-123"


class TestPointCreation:
    """Test SkySpark point creation."""

    @pytest.mark.unit
    async def test_create_point_success(
        self, mock_skyspark_client: MagicMock, sample_point_model: Point
    ) -> None:
        """Test successful point creation."""
        mock_response = [{"id": {"val": "p:aceTest:r:point-789"}, "dis": "Temperature Sensor"}]
        mock_skyspark_client.create_points.return_value = mock_response

        result = await mock_skyspark_client.create_points([sample_point_model])

        assert len(result) == 1
        assert result[0]["id"]["val"] == "p:aceTest:r:point-789"

    @pytest.mark.unit
    async def test_create_point_with_refs(self, mock_skyspark_client: MagicMock) -> None:
        """Test creating point with site and equipment references."""
        point = Point(
            dis="Temperature Sensor",
            kind="Number",
            unit="°F",
            site_ref="p:aceTest:r:site-123",
            equip_ref="p:aceTest:r:equip-456",
            refName="temp-sensor-1",
            marker_tags=["sensor", "temp"],
        )

        mock_response = [{"id": {"val": "p:aceTest:r:point-789"}}]
        mock_skyspark_client.create_points.return_value = mock_response

        result = await mock_skyspark_client.create_points([point])

        assert len(result) == 1
        mock_skyspark_client.create_points.assert_called_once()

    @pytest.mark.unit
    async def test_create_multiple_points(self, mock_skyspark_client: MagicMock) -> None:
        """Test creating multiple points at once."""
        points = [
            Point(
                dis=f"Point {i}",
                kind="Number",
                unit="°F",
                site_ref="p:aceTest:r:site-123",
                equip_ref="p:aceTest:r:equip-456",
                refName=f"point-{i}",
                marker_tags=["sensor"],  # Required function marker
            )
            for i in range(5)
        ]

        mock_response = [{"id": {"val": f"p:aceTest:r:point-{i}"}} for i in range(len(points))]
        mock_skyspark_client.create_points.return_value = mock_response

        result = await mock_skyspark_client.create_points(points)

        assert len(result) == 5

    @pytest.mark.unit
    async def test_find_existing_point_by_refname(
        self, mock_skyspark_client: MagicMock, sample_skyspark_point: dict[str, Any]
    ) -> None:
        """Test finding existing point by refName."""
        mock_skyspark_client.read.return_value = [sample_skyspark_point]

        result = await mock_skyspark_client.read('point and refName=="flightdeck-point-1"')

        assert len(result) == 1
        assert result[0]["refName"] == "flightdeck-point-1"


class TestPointUpdates:
    """Test SkySpark point update operations."""

    @pytest.mark.unit
    async def test_update_point_tags(
        self, mock_skyspark_client: MagicMock, sample_point_model: Point
    ) -> None:
        """Test updating point tags."""
        # Add new tags
        sample_point_model.marker_tags.append("critical")
        sample_point_model.kv_tags["priority"] = "high"

        mock_response = [{"id": {"val": "p:aceTest:r:point-789"}, "critical": {"_kind": "marker"}}]
        mock_skyspark_client.update_points.return_value = mock_response

        result = await mock_skyspark_client.update_points([sample_point_model])

        assert len(result) == 1
        mock_skyspark_client.update_points.assert_called_once()

    @pytest.mark.unit
    async def test_update_multiple_points(self, mock_skyspark_client: MagicMock) -> None:
        """Test updating multiple points at once."""
        points = [
            Point(
                dis=f"Updated Point {i}",
                kind="Number",
                unit="°F",
                site_ref="p:aceTest:r:site-123",
                equip_ref="p:aceTest:r:equip-456",
                refName=f"point-{i}",
                marker_tags=["sensor"],  # Required function marker
            )
            for i in range(3)
        ]

        mock_response = [{"id": {"val": f"p:aceTest:r:point-{i}"}} for i in range(len(points))]
        mock_skyspark_client.update_points.return_value = mock_response

        result = await mock_skyspark_client.update_points(points)

        assert len(result) == 3


class TestEntityQueries:
    """Test SkySpark entity query operations."""

    @pytest.mark.unit
    async def test_read_all_sites(self, mock_skyspark_client: MagicMock) -> None:
        """Test reading all sites."""
        mock_sites = [
            {"id": {"val": f"p:aceTest:r:site-{i}"}, "dis": f"Site {i}"} for i in range(3)
        ]
        mock_skyspark_client.read_sites.return_value = mock_sites

        result = await mock_skyspark_client.read_sites()

        assert len(result) == 3
        mock_skyspark_client.read_sites.assert_called_once()

    @pytest.mark.unit
    async def test_read_equipment_for_site(self, mock_skyspark_client: MagicMock) -> None:
        """Test reading equipment for a specific site."""
        site_ref = "p:aceTest:r:site-123"
        mock_equipment = [
            {"id": {"val": f"p:aceTest:r:equip-{i}"}, "dis": f"Equip {i}"} for i in range(2)
        ]
        mock_skyspark_client.read_equipment.return_value = mock_equipment

        result = await mock_skyspark_client.read_equipment(site_ref=site_ref)

        assert len(result) == 2
        mock_skyspark_client.read_equipment.assert_called_once_with(site_ref=site_ref)

    @pytest.mark.unit
    async def test_read_points_for_equipment(self, mock_skyspark_client: MagicMock) -> None:
        """Test reading points for specific equipment."""
        equip_ref = "p:aceTest:r:equip-456"
        mock_points = [
            {"id": {"val": f"p:aceTest:r:point-{i}"}, "dis": f"Point {i}"} for i in range(5)
        ]
        mock_skyspark_client.read_points.return_value = mock_points

        result = await mock_skyspark_client.read_points(equip_ref=equip_ref)

        assert len(result) == 5
        mock_skyspark_client.read_points.assert_called_once_with(equip_ref=equip_ref)

    @pytest.mark.unit
    async def test_read_with_custom_filter(self, mock_skyspark_client: MagicMock) -> None:
        """Test reading entities with custom filter."""
        filter_expr = "site and area > 10000"
        mock_results = [{"id": {"val": "p:aceTest:r:site-1"}, "area": {"val": 15000}}]
        mock_skyspark_client.read.return_value = mock_results

        result = await mock_skyspark_client.read(filter_expr)

        assert len(result) == 1
        mock_skyspark_client.read.assert_called_once_with(filter_expr)
