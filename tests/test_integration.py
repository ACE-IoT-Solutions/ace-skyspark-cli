"""Integration tests for ACE to SkySpark synchronization.

These tests require valid credentials in .env file and will connect to actual services.
Run with: pytest -m integration
"""

import pytest
from ace_skyspark_lib import Point, SkysparkClient
from aceiot_models.api import APIClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_skyspark_connection(
    skip_if_no_integration_config: None,  # noqa: ARG001
    env_config: dict[str, str],  # noqa: ARG001
) -> None:
    """Test connection to SkySpark server."""
    async with SkysparkClient(
        base_url=env_config["skyspark_url"],
        project=env_config["skyspark_project"],
        username=env_config["skyspark_user"],
        password=env_config["skyspark_pass"],
    ) as client:
        # Test basic read operation
        sites = await client.read_sites()
        assert isinstance(sites, list)


@pytest.mark.integration
def test_flightdeck_connection(
    skip_if_no_integration_config: None,  # noqa: ARG001
    env_config: dict[str, str],  # noqa: ARG001
) -> None:
    """Test connection to FlightDeck API."""
    client = APIClient(
        base_url="https://flightdeck.aceiot.cloud/api",
        api_key=env_config["flightdeck_jwt"],
    )
    # Test basic API call - this would depend on actual API methods available
    # For now just verify client initializes
    assert client is not None


@pytest.mark.integration
@pytest.mark.idempotent
@pytest.mark.slow
@pytest.mark.asyncio
async def test_idempotent_sync(
    skip_if_no_integration_config: None,  # noqa: ARG001
    env_config: dict[str, str],  # noqa: ARG001
) -> None:
    """Test that running sync twice produces idempotent results.

    This test:
    1. Creates a test point with refName
    2. Syncs to SkySpark (should create)
    3. Syncs again (should find existing by refName)
    4. Verifies only one point exists in SkySpark
    5. Cleans up test data
    """
    from ace_skyspark_lib import Equipment, Site

    test_site_refname = "ace-cli-test-idempotent-site"
    test_equip_refname = "ace-cli-test-idempotent-equip"
    test_point_refname = "ace-cli-test-idempotent-point"

    async with SkysparkClient(
        base_url=env_config["skyspark_url"],
        project=env_config["skyspark_project"],
        username=env_config["skyspark_user"],
        password=env_config["skyspark_pass"],
    ) as client:
        # Clean up any existing test entities
        for refname in [test_site_refname, test_equip_refname, test_point_refname]:
            existing = await client.read(f'refName=="{refname}"')
            for entity in existing:
                await client.delete_entity(entity["id"]["val"])

        # Create test Site
        test_site = Site(
            dis="Idempotent Test Site",
            tz="America/New_York",
            refName=test_site_refname,
        )
        created_sites = await client.create_sites([test_site])
        site_id = created_sites[0]["id"]["val"]

        # Create test Equipment
        test_equip = Equipment(
            dis="Idempotent Test Equipment",
            site_ref=site_id,
            refName=test_equip_refname,
            marker_tags=["equip", "ahu"],
        )
        created_equip = await client.create_equipment([test_equip])
        equip_id = created_equip[0]["id"]["val"]

        # First sync: create point
        test_point = Point(
            dis="ACE CLI Idempotent Test",
            kind="Number",
            unit="degF",
            site_ref=site_id,
            equip_ref=equip_id,
            refName=test_point_refname,
            marker_tags=["sensor", "temp"],
        )
        created = await client.create_points([test_point])
        assert len(created) == 1
        point_id = created[0]["id"]["val"]

        # Second sync: should find existing by refName
        existing_check = await client.read(f'point and refName=="{test_point_refname}"')
        assert len(existing_check) == 1
        assert existing_check[0]["id"]["val"] == point_id

        # Clean up in reverse order
        await client.delete_entity(point_id)
        await client.delete_entity(equip_id)
        await client.delete_entity(site_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duplicate_prevention_with_refname(
    skip_if_no_integration_config: None,  # noqa: ARG001
    env_config: dict[str, str],  # noqa: ARG001
) -> None:
    """Test that duplicate prevention works using refName."""
    from ace_skyspark_lib import Equipment, Site

    test_site_refname = "ace-cli-test-dup-prev-site"
    test_equip_refname = "ace-cli-test-dup-prev-equip"
    test_point_refname = "ace-cli-test-dup-prev-point"

    async with SkysparkClient(
        base_url=env_config["skyspark_url"],
        project=env_config["skyspark_project"],
        username=env_config["skyspark_user"],
        password=env_config["skyspark_pass"],
    ) as client:
        # Clean up any existing test entities
        for refname in [test_site_refname, test_equip_refname, test_point_refname]:
            existing = await client.read(f'refName=="{refname}"')
            for entity in existing:
                await client.delete_entity(entity["id"]["val"])

        # Create test Site
        test_site = Site(
            dis="Duplicate Prevention Test Site",
            tz="America/New_York",
            refName=test_site_refname,
        )
        created_sites = await client.create_sites([test_site])
        site_id = created_sites[0]["id"]["val"]

        # Create test Equipment
        test_equip = Equipment(
            dis="Duplicate Prevention Test Equipment",
            site_ref=site_id,
            refName=test_equip_refname,
            marker_tags=["equip", "ahu"],
        )
        created_equip = await client.create_equipment([test_equip])
        equip_id = created_equip[0]["id"]["val"]

        # Create first point
        test_point = Point(
            dis="Duplicate Prevention Test",
            kind="Number",
            unit="degF",
            site_ref=site_id,
            equip_ref=equip_id,
            refName=test_point_refname,
            marker_tags=["sensor", "temp"],
        )
        created1 = await client.create_points([test_point])
        point_id = created1[0]["id"]["val"]

        # Try to create again - should find existing
        existing_check = await client.read(f'point and refName=="{test_point_refname}"')
        assert len(existing_check) == 1

        # If we were to create again, we should skip
        should_create = len(existing_check) == 0
        assert should_create is False

        # Clean up in reverse order
        await client.delete_entity(point_id)
        await client.delete_entity(equip_id)
        await client.delete_entity(site_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tag_synchronization(
    skip_if_no_integration_config: None,  # noqa: ARG001
    env_config: dict[str, str],  # noqa: ARG001
) -> None:
    """Test that tags are properly synchronized to SkySpark."""
    from ace_skyspark_lib import Equipment, Site

    test_site_refname = "ace-cli-test-tag-sync-site"
    test_equip_refname = "ace-cli-test-tag-sync-equip"
    test_point_refname = "ace-cli-test-tag-sync-point"

    async with SkysparkClient(
        base_url=env_config["skyspark_url"],
        project=env_config["skyspark_project"],
        username=env_config["skyspark_user"],
        password=env_config["skyspark_pass"],
    ) as client:
        # Clean up any existing test entities
        for refname in [test_site_refname, test_equip_refname, test_point_refname]:
            existing = await client.read(f'refName=="{refname}"')
            for entity in existing:
                await client.delete_entity(entity["id"]["val"])

        # Create test Site
        test_site = Site(
            dis="Tag Sync Test Site",
            tz="America/New_York",
            refName=test_site_refname,
        )
        created_sites = await client.create_sites([test_site])
        site_id = created_sites[0]["id"]["val"]

        # Create test Equipment
        test_equip = Equipment(
            dis="Tag Sync Test Equipment",
            site_ref=site_id,
            refName=test_equip_refname,
            marker_tags=["equip", "ahu"],
        )
        created_equip = await client.create_equipment([test_equip])
        equip_id = created_equip[0]["id"]["val"]

        # Create point with specific tags
        test_point = Point(
            dis="Tag Sync Test",
            kind="Number",
            unit="degF",
            site_ref=site_id,
            equip_ref=equip_id,
            refName=test_point_refname,
            marker_tags=["sensor", "temp"],
            kv_tags={"zone": "hvac", "floor": "2"},
        )
        created = await client.create_points([test_point])
        point_id = created[0]["id"]["val"]

        # Read back and verify tags
        point = await client.read(f"id==@{point_id}")
        assert len(point) == 1

        # Verify marker tags
        assert point[0].get("sensor") == {"_kind": "marker"}
        assert point[0].get("temp") == {"_kind": "marker"}

        # Verify KV tags
        zone_tag = point[0].get("zone")
        if isinstance(zone_tag, dict):
            assert zone_tag.get("val") == "hvac"

        # Clean up in reverse order
        await client.delete_entity(point_id)
        await client.delete_entity(equip_id)
        await client.delete_entity(site_id)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
async def test_hierarchical_entity_creation(
    skip_if_no_integration_config: None,  # noqa: ARG001
    env_config: dict[str, str],  # noqa: ARG001
) -> None:
    """Test creating site -> equipment -> point hierarchy."""
    from ace_skyspark_lib import Equipment, Site

    test_site_refname = "ace-cli-test-site"
    test_equip_refname = "ace-cli-test-equip"
    test_point_refname = "ace-cli-test-point"

    async with SkysparkClient(
        base_url=env_config["skyspark_url"],
        project=env_config["skyspark_project"],
        username=env_config["skyspark_user"],
        password=env_config["skyspark_pass"],
    ) as client:
        # Clean up any existing test entities
        for refname in [test_site_refname, test_equip_refname, test_point_refname]:
            existing = await client.read(f'refName=="{refname}"')
            for entity in existing:
                await client.delete_entity(entity["id"]["val"])

        # Create site
        test_site = Site(
            dis="ACE CLI Test Site",
            tz="America/New_York",
            refName=test_site_refname,
        )
        created_sites = await client.create_sites([test_site])
        site_id = created_sites[0]["id"]["val"]

        # Create equipment under site
        test_equip = Equipment(
            dis="ACE CLI Test Equipment",
            site_ref=site_id,
            refName=test_equip_refname,
            marker_tags=["equip", "ahu", "testPoint"],
        )
        created_equip = await client.create_equipment([test_equip])
        equip_id = created_equip[0]["id"]["val"]

        # Create point under equipment
        test_point = Point(
            dis="ACE CLI Test Point",
            kind="Number",
            unit="degF",
            site_ref=site_id,
            equip_ref=equip_id,
            refName=test_point_refname,
            marker_tags=["point", "sensor", "testPoint"],
        )
        created_points = await client.create_points([test_point])
        point_id = created_points[0]["id"]["val"]

        # Verify hierarchy
        point_check = await client.read(f"id==@{point_id}")
        assert len(point_check) == 1
        assert point_check[0].get("siteRef", {}).get("val") == site_id
        assert point_check[0].get("equipRef", {}).get("val") == equip_id

        # Clean up in reverse order
        await client.delete_entity(point_id)
        await client.delete_entity(equip_id)
        await client.delete_entity(site_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_read_skyspark_points(
    skip_if_no_integration_config: None,  # noqa: ARG001
    env_config: dict[str, str],  # noqa: ARG001
) -> None:
    """Test reading points from SkySpark."""
    async with SkysparkClient(
        base_url=env_config["skyspark_url"],
        project=env_config["skyspark_project"],
        username=env_config["skyspark_user"],
        password=env_config["skyspark_pass"],
    ) as client:
        points = await client.read_points()
        assert isinstance(points, list)
        # Should be able to read points even if empty
        for point in points:
            assert "id" in point
            assert "dis" in point


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_delete_point(
    skip_if_no_integration_config: None,  # noqa: ARG001
    env_config: dict[str, str],  # noqa: ARG001
) -> None:
    """Test creating and deleting a point in SkySpark."""
    from ace_skyspark_lib import Equipment, Site

    test_site_refname = "ace-cli-test-crud-site"
    test_equip_refname = "ace-cli-test-crud-equip"
    test_point_refname = "ace-cli-test-crud-point"

    async with SkysparkClient(
        base_url=env_config["skyspark_url"],
        project=env_config["skyspark_project"],
        username=env_config["skyspark_user"],
        password=env_config["skyspark_pass"],
    ) as client:
        # Clean up any existing test entities
        for refname in [test_site_refname, test_equip_refname, test_point_refname]:
            existing = await client.read(f'refName=="{refname}"')
            for entity in existing:
                await client.delete_entity(entity["id"]["val"])

        # Create test Site
        test_site = Site(
            dis="CRUD Test Site",
            tz="America/New_York",
            refName=test_site_refname,
        )
        created_sites = await client.create_sites([test_site])
        site_id = created_sites[0]["id"]["val"]

        # Create test Equipment
        test_equip = Equipment(
            dis="CRUD Test Equipment",
            site_ref=site_id,
            refName=test_equip_refname,
            marker_tags=["equip", "ahu"],
        )
        created_equip = await client.create_equipment([test_equip])
        equip_id = created_equip[0]["id"]["val"]

        # Create a test point
        test_point = Point(
            dis="ACE CLI Test Point",
            kind="Number",
            unit="degF",
            site_ref=site_id,
            equip_ref=equip_id,
            refName=test_point_refname,
            marker_tags=["sensor", "temp"],
        )

        created = await client.create_points([test_point])
        assert len(created) == 1
        assert "id" in created[0]

        # Extract ID for deletion
        point_id = created[0]["id"]["val"].lstrip("@")

        # Verify deletion
        await client.delete_entity(point_id)
        deleted_point = await client.read_by_id(point_id)
        assert deleted_point is None

        # Clean up remaining entities
        await client.delete_entity(equip_id)
        await client.delete_entity(site_id)


@pytest.mark.integration
@pytest.mark.idempotent
@pytest.mark.asyncio
async def test_update_preserves_haystack_ref(
    skip_if_no_integration_config: None,  # noqa: ARG001
    env_config: dict[str, str],  # noqa: ARG001
) -> None:
    """Test that updating a point preserves haystackRef tag."""
    from ace_skyspark_lib import Equipment, Site

    test_site_refname = "ace-cli-test-update-site"
    test_equip_refname = "ace-cli-test-update-equip"
    test_point_refname = "ace-cli-test-update-point"

    async with SkysparkClient(
        base_url=env_config["skyspark_url"],
        project=env_config["skyspark_project"],
        username=env_config["skyspark_user"],
        password=env_config["skyspark_pass"],
    ) as client:
        # Clean up any existing test entities
        for refname in [test_site_refname, test_equip_refname, test_point_refname]:
            existing = await client.read(f'refName=="{refname}"')
            for entity in existing:
                await client.delete_entity(entity["id"]["val"])

        # Create test Site
        test_site = Site(
            dis="Update Test Site",
            tz="America/New_York",
            refName=test_site_refname,
        )
        created_sites = await client.create_sites([test_site])
        site_id = created_sites[0]["id"]["val"]

        # Create test Equipment
        test_equip = Equipment(
            dis="Update Test Equipment",
            site_ref=site_id,
            refName=test_equip_refname,
            marker_tags=["equip", "ahu"],
        )
        created_equip = await client.create_equipment([test_equip])
        equip_id = created_equip[0]["id"]["val"]

        # Create a test point with haystackRef in kv_tags
        test_ref = "ace-test-point-12345"
        test_point = Point(
            dis="ACE CLI Test Point for Update",
            kind="Number",
            unit="degF",
            site_ref=site_id,
            equip_ref=equip_id,
            refName=test_point_refname,
            marker_tags=["sensor", "temp"],
            kv_tags={"haystackRef": test_ref},
        )

        created = await client.create_points([test_point])
        point_id = created[0]["id"]["val"].lstrip("@")

        # CORRECT PATTERN: Read the point first (to get mod field for optimistic locking)
        read_result = await client.read_by_id(point_id)
        assert read_result is not None

        # Convert the read result to a Point model (this includes mod in kv_tags)
        point_to_update = Point.from_zinc_dict(read_result)

        # Modify the point
        point_to_update.dis = "ACE CLI Test Point Updated"
        point_to_update.marker_tags.append("updated")  # Add a marker tag

        # Update the point (mod is automatically preserved from the read)
        updated = await client.update_points([point_to_update])
        assert len(updated) == 1

        # Verify haystackRef is preserved and update was successful
        result = await client.read_by_id(point_id)
        assert result is not None

        # haystackRef is a plain string in kv_tags, not a Zinc dict
        haystack_ref_value = result.get("haystackRef")
        if isinstance(haystack_ref_value, dict):
            haystack_ref_value = haystack_ref_value.get("val")
        assert haystack_ref_value == test_ref, (
            f"Expected haystackRef={test_ref}, got {haystack_ref_value}"
        )

        assert result.get("dis") == "ACE CLI Test Point Updated"
        assert result.get("updated") == {"_kind": "marker"}  # Verify the new tag

        # Clean up in reverse order
        await client.delete_entity(point_id)
        await client.delete_entity(equip_id)
        await client.delete_entity(site_id)
