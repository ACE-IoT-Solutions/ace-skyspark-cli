"""Pytest configuration and shared fixtures."""

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aceiot_models import Point as FlightDeckPoint
from ace_skyspark_lib import Point, Equipment, Site
from dotenv import load_dotenv

# Load .env file at the start of test session
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


@pytest.fixture
def env_config() -> dict[str, str]:
    """Load test configuration from environment variables."""
    return {
        "flightdeck_user": os.getenv("TEST_FLIGHTDECK_USER", ""),
        "flightdeck_jwt": os.getenv("TEST_FLIGHTDECK_JWT", ""),
        "flightdeck_site": os.getenv("TEST_FLIGHTDECK_SITE", ""),
        "skyspark_url": os.getenv("TEST_SKYSPARK_URL", ""),
        "skyspark_project": os.getenv("TEST_SKYSPARK_PROJECT", ""),
        "skyspark_user": os.getenv("TEST_SKYSPARK_USER", ""),
        "skyspark_pass": os.getenv("TEST_SKYSPARK_PASS", ""),
    }


@pytest.fixture
def skip_if_no_integration_config(env_config: dict[str, str]) -> None:
    """Skip test if integration configuration is not available."""
    required_keys = [
        "flightdeck_user",
        "flightdeck_jwt",
        "flightdeck_site",
        "skyspark_url",
        "skyspark_project",
        "skyspark_user",
        "skyspark_pass",
    ]
    missing = [k for k in required_keys if not env_config.get(k)]
    if missing:
        pytest.skip(f"Missing integration config: {', '.join(missing)}")


@pytest.fixture
def mock_flightdeck_client() -> MagicMock:
    """Mock FlightDeck client for unit tests."""
    client = MagicMock()
    client.get_points = AsyncMock(return_value=[])
    client.update_point = AsyncMock()
    client.get_site = AsyncMock()
    return client


@pytest.fixture
def mock_skyspark_client() -> MagicMock:
    """Mock SkySpark client for unit tests."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.read_sites = AsyncMock(return_value=[])
    client.read_equipment = AsyncMock(return_value=[])
    client.read_points = AsyncMock(return_value=[])
    client.create_sites = AsyncMock(return_value=[])
    client.create_equipment = AsyncMock(return_value=[])
    client.create_points = AsyncMock(return_value=[])
    client.update_points = AsyncMock(return_value=[])
    client.read = AsyncMock(return_value=[])
    return client


@pytest.fixture
def sample_flightdeck_point() -> FlightDeckPoint:
    """Create a sample FlightDeck point for testing."""
    return FlightDeckPoint(
        id=1,
        name="Temperature Sensor",
        site_id=1,
        client_id=1,
        marker_tags=["sensor", "temp"],
        kv_tags={"zone": "hvac", "unit": "degF"},
    )


@pytest.fixture
def sample_flightdeck_point_with_haystack_ref() -> FlightDeckPoint:
    """Create a sample FlightDeck point with existing haystackRef."""
    return FlightDeckPoint(
        id=2,
        name="Humidity Sensor",
        site_id=1,
        client_id=1,
        marker_tags=["sensor", "humidity"],
        kv_tags={
            "haystackRef": "p:aceTest:r:skyspark-id-456",
            "unit": "%RH",
        },
    )


@pytest.fixture
def sample_skyspark_site() -> dict[str, Any]:
    """Create a sample SkySpark site response."""
    return {
        "id": {"_kind": "ref", "val": "p:aceTest:r:site-123"},
        "dis": "Test Building",
        "site": {"_kind": "marker"},
        "tz": "America/New_York",
        "refName": "site-abc",
        "area": {"_kind": "number", "val": 50000.0, "unit": "ft²"},
    }


@pytest.fixture
def sample_skyspark_equipment() -> dict[str, Any]:
    """Create a sample SkySpark equipment response."""
    return {
        "id": {"_kind": "ref", "val": "p:aceTest:r:equip-456"},
        "dis": "RTU-1",
        "equip": {"_kind": "marker"},
        "siteRef": {"_kind": "ref", "val": "p:aceTest:r:site-123"},
        "refName": "device-123",
        "ahu": {"_kind": "marker"},
        "hvac": {"_kind": "marker"},
    }


@pytest.fixture
def sample_skyspark_point() -> dict[str, Any]:
    """Create a sample SkySpark point response."""
    return {
        "id": {"_kind": "ref", "val": "p:aceTest:r:point-789"},
        "dis": "Temperature Sensor",
        "point": {"_kind": "marker"},
        "kind": "Number",
        "unit": "°F",
        "siteRef": {"_kind": "ref", "val": "p:aceTest:r:site-123"},
        "equipRef": {"_kind": "ref", "val": "p:aceTest:r:equip-456"},
        "refName": "flightdeck-point-1",
        "sensor": {"_kind": "marker"},
        "temp": {"_kind": "marker"},
    }


@pytest.fixture
def sample_site_model() -> Site:
    """Create a sample Site model for testing."""
    return Site(
        dis="Test Building",
        tz="America/New_York",
        refName="site-abc",
        area_sqft=50000.0,
    )


@pytest.fixture
def sample_equipment_model() -> Equipment:
    """Create a sample Equipment model for testing."""
    return Equipment(
        dis="RTU-1",
        site_ref="p:aceTest:r:site-123",
        refName="device-123",
        marker_tags=["ahu", "hvac"],
    )


@pytest.fixture
def sample_point_model() -> Point:
    """Create a sample Point model for testing."""
    return Point(
        dis="Temperature Sensor",
        kind="Number",
        unit="°F",
        site_ref="p:aceTest:r:site-123",
        equip_ref="p:aceTest:r:equip-456",
        refName="flightdeck-point-1",
        marker_tags=["sensor", "temp"],
    )
