"""Tests for synchronization service with idempotency."""

from unittest.mock import MagicMock

import pytest
from ace_skyspark_lib import Point
from aceiot_models.points import Point as ACEPoint

from ace_skyspark_cli.config import Config
from ace_skyspark_cli.sync import PointSyncService, SyncResult


class TestSyncResult:
    """Test SyncResult data class."""

    @pytest.mark.unit
    def test_sync_result_initialization(self) -> None:
        """Test SyncResult initializes with zero counts."""
        result = SyncResult()
        assert result.points_created == 0
        assert result.points_updated == 0
        assert result.points_skipped == 0
        assert result.errors == []

    @pytest.mark.unit
    def test_sync_result_add_error(self) -> None:
        """Test adding errors to sync result."""
        result = SyncResult()
        result.add_error("Test error 1")
        result.add_error("Test error 2")
        assert len(result.errors) == 2
        assert "Test error 1" in result.errors
        assert "Test error 2" in result.errors

    @pytest.mark.unit
    def test_sync_result_to_dict(self) -> None:
        """Test converting sync result to dictionary."""
        result = SyncResult()
        result.points_created = 5
        result.points_updated = 3
        result.points_skipped = 2
        result.add_error("test error")

        result_dict = result.to_dict()
        assert result_dict["points"]["created"] == 5
        assert result_dict["points"]["updated"] == 3
        assert result_dict["points"]["skipped"] == 2
        assert len(result_dict["errors"]) == 1


class TestPointSyncService:
    """Test PointSyncService with mocked clients."""

    @pytest.mark.unit
    def test_build_ref_map_empty(
        self, mock_flightdeck_client: MagicMock, mock_skyspark_client: MagicMock
    ) -> None:
        """Test building ref map with empty list."""
        config = MagicMock(spec=Config)
        service = PointSyncService(mock_flightdeck_client, mock_skyspark_client, config)

        ref_map = service._build_ref_map([])
        assert ref_map == {}

    @pytest.mark.unit
    def test_build_ref_map_with_refs(
        self, mock_flightdeck_client: MagicMock, mock_skyspark_client: MagicMock
    ) -> None:
        """Test building ref map with points containing haystackRef."""
        config = MagicMock(spec=Config)
        service = PointSyncService(mock_flightdeck_client, mock_skyspark_client, config)

        skyspark_points = [
            {
                "id": {"val": "@point-1"},
                "dis": "Point 1",
                "haystackRef": "ace-point-1",
            },
            {
                "id": {"val": "@point-2"},
                "dis": "Point 2",
                "haystackRef": "ace-point-2",
            },
            {
                "id": {"val": "@point-3"},
                "dis": "Point 3",
                # No haystackRef
            },
        ]

        ref_map = service._build_ref_map(skyspark_points)
        assert len(ref_map) == 2
        assert "ace-point-1" in ref_map
        assert "ace-point-2" in ref_map
        assert ref_map["ace-point-1"]["dis"] == "Point 1"

    @pytest.mark.unit
    def test_get_haystack_ref_none(
        self, mock_flightdeck_client: MagicMock, mock_skyspark_client: MagicMock
    ) -> None:
        """Test getting haystackRef when none exists."""
        config = MagicMock(spec=Config)
        service = PointSyncService(mock_flightdeck_client, mock_skyspark_client, config)

        ace_point = ACEPoint(
            name="Test Point",
            site_id=1,
            client_id=1,
            kv_tags={},
        ).model_dump()

        ref = service._get_haystack_ref(ace_point)
        assert ref is None

    @pytest.mark.unit
    def test_get_haystack_ref_exists(
        self, mock_flightdeck_client: MagicMock, mock_skyspark_client: MagicMock
    ) -> None:
        """Test getting haystackRef when it exists."""
        config = MagicMock(spec=Config)
        service = PointSyncService(mock_flightdeck_client, mock_skyspark_client, config)

        ace_point = ACEPoint(
            name="Test Point",
            site_id=1,
            client_id=1,
            kv_tags={"haystackRef": "sky-123"},
        ).model_dump()

        ref = service._get_haystack_ref(ace_point)
        assert ref == "sky-123"

    @pytest.mark.unit
    def test_prepare_point_create(
        self, mock_flightdeck_client: MagicMock, mock_skyspark_client: MagicMock
    ) -> None:
        """Test preparing a point for creation."""
        config = MagicMock(spec=Config)
        service = PointSyncService(mock_flightdeck_client, mock_skyspark_client, config)

        ace_point = ACEPoint(
            name="Temperature Sensor",
            site_id=1,
            client_id=1,
            marker_tags=["sensor", "temp"],
            kv_tags={"unit": "degF", "kind": "Number"},
        ).model_dump()

        site_ref = "@site-123"
        equipment_ref_map = {}
        site_tz = "America/New_York"

        sky_point = service._prepare_point_create(ace_point, site_ref, equipment_ref_map, site_tz)
        assert sky_point.dis == "Temperature Sensor"
        assert "point" in sky_point.marker_tags
        assert "sensor" in sky_point.marker_tags
        assert "temp" in sky_point.marker_tags

    @pytest.mark.unit
    def test_prepare_point_update(
        self, mock_flightdeck_client: MagicMock, mock_skyspark_client: MagicMock
    ) -> None:
        """Test preparing a point for update."""
        config = MagicMock(spec=Config)
        service = PointSyncService(mock_flightdeck_client, mock_skyspark_client, config)

        ace_point = ACEPoint(
            name="Temperature Sensor Updated",
            site_id=1,
            client_id=1,
            marker_tags=["sensor", "temp", "updated"],
            kv_tags={"unit": "degC"},
        ).model_dump()

        existing_sky_point = {
            "id": {"val": "@point-123"},
            "dis": "Temperature Sensor",
        }

        site_ref = "@site-123"
        equipment_ref_map = {}
        site_tz = "America/New_York"

        sky_point = service._prepare_point_update(
            ace_point, existing_sky_point, site_ref, equipment_ref_map, site_tz
        )
        assert sky_point.id == "point-123"
        assert sky_point.dis == "Temperature Sensor Updated"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_points_batch_empty(
        self, mock_flightdeck_client: MagicMock, mock_skyspark_client: MagicMock
    ) -> None:
        """Test creating empty batch of points."""
        config = MagicMock(spec=Config)
        config.app = MagicMock()
        config.app.batch_size = 100
        service = PointSyncService(mock_flightdeck_client, mock_skyspark_client, config)

        result = await service._create_points_batch([])
        assert result == []
        mock_skyspark_client.create_points.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_points_batch_single(
        self, mock_flightdeck_client: MagicMock, mock_skyspark_client: MagicMock
    ) -> None:
        """Test creating single batch of points."""
        config = MagicMock(spec=Config)
        config.app = MagicMock()
        config.app.batch_size = 100
        service = PointSyncService(mock_flightdeck_client, mock_skyspark_client, config)

        point = Point(
            dis="Test Point",
            refName="test-point",
            siteRef="test-site",
            equipRef="test-equip",
            kind="Number",
            marker_tags=["sensor"],  # Need at least one function marker
        )
        mock_skyspark_client.create_points.return_value = [{"id": {"val": "@test-1"}}]

        result = await service._create_points_batch([point])
        assert len(result) == 1
        mock_skyspark_client.create_points.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_points_batch(
        self, mock_flightdeck_client: MagicMock, mock_skyspark_client: MagicMock
    ) -> None:
        """Test updating batch of points."""
        config = MagicMock(spec=Config)
        config.app = MagicMock()
        config.app.batch_size = 100
        service = PointSyncService(mock_flightdeck_client, mock_skyspark_client, config)

        point = Point(
            id="test-1",
            dis="Test Point",
            refName="test-point",
            siteRef="test-site",
            equipRef="test-equip",
            kind="Number",
            marker_tags=["sensor"],  # Need at least one function marker
        )
        mock_skyspark_client.update_points.return_value = [
            {"id": {"val": "@test-1"}, "dis": "Test Point"}
        ]

        result = await service._update_points_batch([point])
        assert len(result) == 1
        mock_skyspark_client.update_points.assert_called_once()


class TestIdempotency:
    """Test idempotency behavior of sync operations."""

    @pytest.mark.unit
    def test_haystack_ref_tag_constant(
        self, mock_flightdeck_client: MagicMock, mock_skyspark_client: MagicMock
    ) -> None:
        """Test haystackRef tag is defined as constant."""
        config = MagicMock(spec=Config)
        service = PointSyncService(mock_flightdeck_client, mock_skyspark_client, config)
        assert service.HAYSTACK_REF_TAG == "haystackRef"

    @pytest.mark.idempotent
    @pytest.mark.unit
    def test_point_with_haystack_ref_skipped_for_create(
        self, mock_flightdeck_client: MagicMock, mock_skyspark_client: MagicMock
    ) -> None:
        """Test that points with haystackRef are identified for update, not create."""
        config = MagicMock(spec=Config)
        service = PointSyncService(mock_flightdeck_client, mock_skyspark_client, config)

        # Point with haystackRef should match existing SkySpark point
        ace_point = ACEPoint(
            name="Test Point",
            site_id=1,
            client_id=1,
            kv_tags={"haystackRef": "sky-123"},
        ).model_dump()

        skyspark_points = [
            {
                "id": {"val": "@sky-123"},
                "dis": "Test Point",
                "haystackRef": "sky-123",
            }
        ]

        ref_map = service._build_ref_map(skyspark_points)
        haystack_ref = service._get_haystack_ref(ace_point)

        # Should find match in ref_map
        assert haystack_ref in ref_map
        assert ref_map[haystack_ref]["id"]["val"] == "@sky-123"
