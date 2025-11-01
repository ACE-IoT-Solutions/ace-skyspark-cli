"""Point synchronization service for ACE to SkySpark.

This module implements idempotent synchronization of points, equipment, and entities
from ACE FlightDeck to SkySpark using haystackRef KV tags for tracking.
"""

import asyncio
from typing import Any

import structlog
from ace_skyspark_lib import Equipment, Point, Site, SkysparkClient
from aceiot_models.api import APIClient

from ace_skyspark_cli.config import Config

logger = structlog.get_logger(__name__)


class SyncResult:
    """Result of a synchronization operation."""

    def __init__(self) -> None:
        """Initialize sync result."""
        self.sites_created: int = 0
        self.sites_updated: int = 0
        self.sites_skipped: int = 0
        self.equipment_created: int = 0
        self.equipment_updated: int = 0
        self.equipment_skipped: int = 0
        self.points_created: int = 0
        self.points_updated: int = 0
        self.points_skipped: int = 0
        self.errors: list[str] = []

    def add_error(self, error: str) -> None:
        """Add an error to the result.

        Args:
            error: Error message
        """
        self.errors.append(error)
        logger.error("sync_error", error=error)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary.

        Returns:
            Dictionary representation of the result
        """
        return {
            "sites": {
                "created": self.sites_created,
                "updated": self.sites_updated,
                "skipped": self.sites_skipped,
            },
            "equipment": {
                "created": self.equipment_created,
                "updated": self.equipment_updated,
                "skipped": self.equipment_skipped,
            },
            "points": {
                "created": self.points_created,
                "updated": self.points_updated,
                "skipped": self.points_skipped,
            },
            "errors": self.errors,
        }


class PointSyncService:
    """Service for synchronizing points from ACE to SkySpark."""

    HAYSTACK_REF_TAG = "haystack_entityRef"

    def __init__(
        self,
        ace_client: APIClient,
        skyspark_client: SkysparkClient,
        config: Config,
    ) -> None:
        """Initialize sync service.

        Args:
            ace_client: ACE FlightDeck API client
            skyspark_client: SkySpark client
            config: Application configuration
        """
        self.ace_client = ace_client
        self.skyspark_client = skyspark_client
        self.config = config

    async def sync_points_for_site(
        self,
        site_name: str,
        dry_run: bool = False,
        limit: int | None = None,
        sync_all: bool = False,
    ) -> SyncResult:
        """Synchronize all points for a specific site.

        This method:
        1. Fetches points from ACE FlightDeck for the given site
           - Uses /sites/{site}/configured_points by default (collect_enabled=True)
           - Uses /sites/{site}/points when sync_all=True
        2. Sorts points by name for deterministic ordering
        3. Applies limit if specified
        4. Checks for existing SkySpark entities using haystackRef tags
        5. Creates new entities or updates existing ones
        6. Maintains idempotency by storing SkySpark IDs back to ACE

        Args:
            site_name: Name of the site to synchronize
            dry_run: If True, don't make any changes
            limit: Maximum number of points to sync (sorted by name for idempotency)
            sync_all: If True, sync all points including non-configured (default: False)

        Returns:
            SyncResult with statistics
        """
        result = SyncResult()
        logger.info("sync_start", site=site_name, dry_run=dry_run, limit=limit, sync_all=sync_all)

        try:
            # Get SkySpark project timezone for legacy compatibility
            skyspark_tz = await self.skyspark_client.get_project_timezone()
            logger.info("project_timezone_retrieved", tz=skyspark_tz)

            # Step 1: Sync site entity first
            site_ref, site_created = await self._sync_site(site_name, dry_run, skyspark_tz)
            if not site_ref:
                logger.error("site_sync_failed", site=site_name)
                result.add_error(f"Failed to sync site: {site_name}")
                return result

            if site_created:
                result.sites_created += 1
            else:
                result.sites_skipped += 1

            # Fetch points from ACE (configured/collected only unless sync_all=True)
            ace_points = await self._fetch_ace_points(site_name, configured_only=not sync_all)

            if not ace_points:
                if sync_all:
                    logger.warning("no_points_found", site=site_name)
                else:
                    logger.warning("no_configured_points_found", site=site_name)
                return result

            # Sort points by name for deterministic ordering
            ace_points = sorted(ace_points, key=lambda p: p["name"])
            total_points = len(ace_points)

            # Apply limit if specified
            if limit is not None and limit > 0:
                ace_points = ace_points[:limit]
                logger.info(
                    "points_limited",
                    total=total_points,
                    limited_to=len(ace_points),
                )
            else:
                logger.info("processing_points", count=total_points)

            # Step 2: Sync equipment entities (extract from points)
            (
                equipment_ref_map,
                equip_created_count,
                equip_updated_count,
                equip_skipped_count,
            ) = await self._sync_equipment(site_name, site_ref, ace_points, dry_run, skyspark_tz)
            result.equipment_created += equip_created_count
            result.equipment_updated += equip_updated_count
            result.equipment_skipped += equip_skipped_count

            # Fetch existing SkySpark points to check for matches
            skyspark_points = await self._fetch_skyspark_points()
            logger.info("skyspark_points_fetched", count=len(skyspark_points))

            # Build lookup map: haystackRef -> SkySpark point
            skyspark_ref_map = self._build_ref_map(skyspark_points)

            # Process each ACE point
            points_to_create: list[Point] = []
            points_to_update: list[Point] = []
            ace_points_to_create: list[dict[str, Any]] = []  # Track original ACE dicts for creates
            ace_points_to_update: list[dict[str, Any]] = []  # Track original ACE dicts for updates

            for ace_point in ace_points:
                try:
                    # Check if point already exists in SkySpark
                    haystack_ref = self._get_haystack_ref(ace_point)
                    logger.debug(
                        "checking_point",
                        point=ace_point.get("name"),
                        haystack_ref=haystack_ref,
                        ref_type=type(haystack_ref).__name__,
                    )

                    if haystack_ref and haystack_ref in skyspark_ref_map:
                        # Point exists - prepare update (will fix refs if needed)
                        sky_point = skyspark_ref_map[haystack_ref]
                        logger.debug("point_exists_updating", point=ace_point.get("name"))
                        updated_point = self._prepare_point_update(
                            ace_point, sky_point, site_ref, equipment_ref_map, skyspark_tz
                        )
                        points_to_update.append(updated_point)
                        ace_points_to_update.append(ace_point)  # Keep original ACE dict
                    else:
                        # Point doesn't exist - prepare create
                        logger.debug("point_new_creating", point=ace_point.get("name"))
                        new_point = self._prepare_point_create(ace_point, site_ref, equipment_ref_map, skyspark_tz)
                        points_to_create.append(new_point)
                        ace_points_to_create.append(ace_point)  # Keep original ACE dict

                except Exception as e:
                    import traceback

                    error_msg = f"Error processing point {ace_point.get('name', 'unknown')}: {e!s}"
                    logger.error("point_processing_error", error=str(e), traceback=traceback.format_exc())
                    result.add_error(error_msg)
                    continue

            # Execute creates and updates with batched ref storage for resilience
            if not dry_run:
                if points_to_create:
                    created, failed = await self._create_points_batch_resilient(
                        points_to_create, ace_points_to_create
                    )
                    result.points_created += created
                    if failed > 0:
                        result.add_error(f"Failed to create {failed} points (see logs for details)")

                if points_to_update:
                    updated, failed = await self._update_points_batch_resilient(
                        points_to_update, ace_points_to_update
                    )
                    result.points_updated += updated
                    if failed > 0:
                        result.add_error(f"Failed to update {failed} points (see logs for details)")
            else:
                logger.info(
                    "dry_run_summary",
                    would_create=len(points_to_create),
                    would_update=len(points_to_update),
                )

        except Exception as e:
            error_msg = f"Sync failed for site {site_name}: {e!s}"
            result.add_error(error_msg)

        logger.info("sync_complete", site=site_name, result=result.to_dict())
        return result

    async def _fetch_ace_points(
        self, site_name: str, configured_only: bool = True
    ) -> list[dict[str, Any]]:
        """Fetch all points from ACE FlightDeck with pagination.

        Args:
            site_name: Site name to filter by
            configured_only: If True, fetch only configured/collected points (default: True)

        Returns:
            List of all ACE point dictionaries (paginated)
        """
        logger.info("fetching_ace_points", site=site_name, configured_only=configured_only)

        # ACE API client is synchronous, run in thread pool
        loop = asyncio.get_event_loop()

        # Choose API method based on configured_only flag
        per_page = 500  # FlightDeck API page size (underlying issues fixed)

        all_points: list[dict[str, Any]] = []
        page = 1
        total_pages_expected = None

        # Choose the appropriate endpoint
        if configured_only:
            api_method = self.ace_client.get_site_configured_points
        else:
            api_method = self.ace_client.get_site_points

        while True:
            try:
                # Fetch current page
                response = await loop.run_in_executor(
                    None,
                    api_method,
                    site_name,
                    page,
                    per_page,
                )

                # Extract items
                items = response.get("items", [])
                if not items:
                    break

                all_points.extend(items)

                # Track expected total pages
                if total_pages_expected is None:
                    total_pages_expected = response.get("pages", 1)

                # Check if we've reached the last page
                if page >= total_pages_expected:
                    break

                page += 1
                logger.debug("fetching_page", page=page, total_pages=total_pages_expected)

                # Add delay between pages to avoid rate limiting
                await asyncio.sleep(1.0)

            except Exception as e:
                # Log warning and return what we have so far
                # Note: FlightDeck API has data corruption issues that cause 500 errors
                # when fetching certain pages. This is a known server-side issue.
                logger.warning(
                    "pagination_failed_continuing_with_partial_data",
                    page=page,
                    total_fetched=len(all_points),
                    expected_total=total_pages_expected * per_page if total_pages_expected else "unknown",
                    message="FlightDeck API returned 500 error - likely data corruption on this page",
                )
                break

        logger.info("ace_points_fetched", site=site_name, count=len(all_points))
        return all_points

    async def _fetch_skyspark_points(self) -> list[dict[str, Any]]:
        """Fetch all points from SkySpark.

        Returns:
            List of SkySpark point dictionaries
        """
        logger.info("fetching_skyspark_points")
        try:
            return await self.skyspark_client.read_points()
        except Exception as e:
            logger.error("skyspark_fetch_failed", error=str(e))
            return []

    async def _sync_site(self, site_name: str, dry_run: bool, skyspark_tz: str) -> tuple[str | None, bool]:
        """Synchronize site entity to SkySpark.

        Args:
            site_name: ACE site name
            dry_run: If True, don't make any changes
            skyspark_tz: SkySpark project timezone

        Returns:
            Tuple of (SkySpark site reference ID, was_created)
            Returns (None, False) if failed
        """
        logger.info("syncing_site", site=site_name)

        # Fetch site data from ACE
        loop = asyncio.get_event_loop()
        try:
            ace_site = await loop.run_in_executor(None, self.ace_client.get_site, site_name)
        except Exception as e:
            logger.error("fetch_ace_site_failed", site=site_name, error=str(e))
            return (None, False)

        # Check if site already has haystackRef in ACE (if API supports it in future)
        site_kv_tags = ace_site.get("kv_tags") or {}
        existing_ref = site_kv_tags.get(self.HAYSTACK_REF_TAG)

        if existing_ref:
            logger.info("site_already_synced_from_ace", site=site_name, ref=existing_ref)
            return (existing_ref, False)

        # Check if site already exists in SkySpark by refName
        ref_name = f"ace-site-{site_name}"
        try:
            existing_sites = await self.skyspark_client.read_sites()
            for sky_site in existing_sites:
                if sky_site.get("refName") == ref_name:
                    site_id = sky_site.get("id", {}).get("val", "").lstrip("@")
                    logger.info("site_already_exists_in_skyspark", site=site_name, ref=site_id)
                    return (site_id, False)
        except Exception as e:
            logger.warning("failed_to_check_existing_sites", error=str(e))

        if dry_run:
            logger.info("dry_run_would_create_site", site=site_name)
            return ("dry-run-site-ref", True)

        # Create site in SkySpark
        site_entity = Site(
            dis=ace_site.get("nice_name") or site_name,
            refName=f"ace-site-{site_name}",
            tz=skyspark_tz,  # Use SkySpark project timezone
            geoAddr=ace_site.get("address"),
            tags={
                "ace_site": site_name,
                "skysparkTz": skyspark_tz,  # Store for legacy compatibility
                "geoCoord": f"C({ace_site['latitude']},{ace_site['longitude']})"
                if ace_site.get("latitude") and ace_site.get("longitude")
                else None,
            },
        )

        try:
            created_sites = await self.skyspark_client.create_sites([site_entity])
            if not created_sites:
                logger.error("site_creation_failed", site=site_name)
                return (None, False)

            site_id = created_sites[0].get("id", {}).get("val", "").lstrip("@")
            logger.info("site_created", site=site_name, skyspark_id=site_id)

            # Store haystackRef back to ACE
            await self._store_site_ref_to_ace(ace_site, site_id)

            return (site_id, True)

        except Exception as e:
            logger.error("site_creation_failed", site=site_name, error=str(e))
            return (None, False)

    async def _sync_equipment(
        self,
        site_name: str,
        site_ref: str,
        ace_points: list[dict[str, Any]],
        dry_run: bool,
        skyspark_tz: str,
    ) -> tuple[dict[str, str], int, int, int]:
        """Synchronize equipment entities to SkySpark.

        Extracts unique equipment from points' bacnet_data and creates equipment entities.

        Args:
            site_name: ACE site name
            site_ref: SkySpark site reference ID
            ace_points: List of ACE points
            dry_run: If True, don't make any changes
            skyspark_tz: SkySpark project timezone

        Returns:
            Tuple of (equipment_ref_map, created_count, updated_count, skipped_count)
            - equipment_ref_map: Dictionary mapping equipment identifier to SkySpark equipment ref
            - created_count: Number of equipment entities created
            - updated_count: Number of equipment entities updated
            - skipped_count: Number of equipment entities that already existed and didn't need updates
        """
        logger.info("syncing_equipment", site=site_name)

        # Extract unique equipment from points
        equipment_map: dict[str, dict[str, Any]] = {}

        for point in ace_points:
            bacnet_data = point.get("bacnet_data")
            if not bacnet_data:
                continue

            # Use device_address-device_id as unique identifier
            device_addr = bacnet_data.get("device_address")
            device_id = bacnet_data.get("device_id")
            if not device_addr or device_id is None:
                continue

            equip_key = f"{device_addr}-{device_id}"
            if equip_key not in equipment_map:
                equipment_map[equip_key] = {
                    "key": equip_key,
                    "device_address": device_addr,
                    "device_id": device_id,
                    "device_name": bacnet_data.get("device_name") or equip_key,
                    "device_description": bacnet_data.get("device_description"),
                }

        logger.info("equipment_extracted", count=len(equipment_map))

        if not equipment_map:
            return ({}, 0, 0, 0)

        if dry_run:
            logger.info("dry_run_would_create_equipment", count=len(equipment_map))
            dry_run_map = {key: f"dry-run-equip-{key}" for key in equipment_map}
            return (dry_run_map, len(equipment_map), 0, 0)

        # Check for existing equipment in SkySpark by refName
        try:
            existing_equipment = await self.skyspark_client.read_equipment()
            existing_equip_map: dict[str, str] = {}
            for equip in existing_equipment:
                ref_name = equip.get("refName", "")
                # Extract equipment key from refName: "ace-equip-{key}"
                if ref_name.startswith("ace-equip-"):
                    equip_key = ref_name[10:]  # Remove "ace-equip-" prefix
                    equip_id = equip.get("id", {}).get("val", "").lstrip("@")
                    existing_equip_map[equip_key] = equip_id

            logger.info("existing_equipment_found", count=len(existing_equip_map))
        except Exception as e:
            logger.warning("failed_to_check_existing_equipment", error=str(e))
            existing_equip_map = {}

        # Determine which equipment needs to be created or updated
        equipment_to_create: list[Equipment] = []
        equipment_to_update: list[Equipment] = []
        equip_keys_to_create: list[str] = []
        equip_keys_to_update: list[str] = []
        equip_ref_map: dict[str, str] = {}

        # Also need to check existing equipment's siteRef - may need updating if orphaned
        existing_equipment_full = {equip.get("refName", ""): equip for equip in existing_equipment}

        for equip_info in equipment_map.values():
            equip_key = equip_info["key"]
            ref_name = f"ace-equip-{equip_key}"

            # Check if equipment already exists
            if equip_key in existing_equip_map:
                equip_id = existing_equip_map[equip_key]
                equip_ref_map[equip_key] = equip_id

                # Check if siteRef needs updating (orphaned or wrong site)
                existing_equip = existing_equipment_full.get(ref_name, {})
                existing_site_ref = existing_equip.get("siteRef", {})
                if isinstance(existing_site_ref, dict):
                    existing_site_ref_val = existing_site_ref.get("val", "").lstrip("@")
                else:
                    existing_site_ref_val = str(existing_site_ref).lstrip("@")

                if existing_site_ref_val != site_ref:
                    # Need to update this equipment's siteRef
                    logger.info(
                        "equipment_needs_siteref_update",
                        key=equip_key,
                        old_site=existing_site_ref_val,
                        new_site=site_ref,
                    )
                    # Get existing equipment tags (excluding system fields)
                    existing_tags = {}
                    for key, val in existing_equip.items():
                        # Skip system fields that shouldn't be in updates (keep mod for optimistic locking)
                        if key not in {"id", "dis", "refName", "siteRef", "equipRef", "equip", "tz"}:
                            existing_tags[key] = val

                    # Merge with our required tags
                    updated_tags = {
                        **existing_tags,
                        "ace_device_key": equip_key,
                        "bacnet": True,
                        "device_address": equip_info["device_address"],
                        "device_id": equip_info["device_id"],
                    }

                    equipment_entity = Equipment(
                        id=equip_id,
                        dis=equip_info["device_name"],
                        refName=ref_name,
                        siteRef=site_ref,
                        tz=skyspark_tz,
                        tags={
                            **updated_tags,
                            "skysparkTz": skyspark_tz,  # Store for legacy compatibility
                        },
                    )
                    equipment_to_update.append(equipment_entity)
                    equip_keys_to_update.append(equip_key)
                else:
                    logger.debug("equipment_already_exists", key=equip_key, ref=equip_id)
            else:
                # Need to create this equipment
                equipment_entity = Equipment(
                    dis=equip_info["device_name"],
                    refName=ref_name,
                    siteRef=site_ref,
                    tz=skyspark_tz,
                    tags={
                        "ace_device_key": equip_key,
                        "bacnet": True,
                        "device_address": equip_info["device_address"],
                        "device_id": equip_info["device_id"],
                        "skysparkTz": skyspark_tz,  # Store for legacy compatibility
                    },
                )
                equipment_to_create.append(equipment_entity)
                equip_keys_to_create.append(equip_key)

        # Update equipment with wrong siteRef
        updated_count = 0
        if equipment_to_update:
            try:
                updated_equipment = await self.skyspark_client.update_equipment(equipment_to_update)
                updated_count = len(updated_equipment)
                logger.info("equipment_updated", count=updated_count)
            except Exception as e:
                logger.error("equipment_update_failed", error=str(e))

        # Create new equipment if needed
        created_count = 0
        if equipment_to_create:
            try:
                created_equipment = await self.skyspark_client.create_equipment(equipment_to_create)
                created_count = len(created_equipment)
                logger.info("equipment_created", count=created_count)

                # Add created equipment to the ref map
                for i, equip in enumerate(created_equipment):
                    equip_id = equip.get("id", {}).get("val", "").lstrip("@")
                    equip_key = equip_keys_to_create[i]
                    equip_ref_map[equip_key] = equip_id

            except Exception as e:
                logger.error("equipment_creation_failed", error=str(e))

        # Calculate skipped count: existing equipment that didn't need updates
        skipped_count = len(existing_equip_map) - updated_count

        if not equipment_to_create and not equipment_to_update:
            logger.info("all_equipment_already_exists", count=len(equip_ref_map))

        return (equip_ref_map, created_count, updated_count, skipped_count)

    async def _store_site_ref_to_ace(self, ace_site: dict[str, Any], site_id: str) -> None:
        """Store SkySpark site ID back to ACE site as haystackRef.

        Args:
            ace_site: Original ACE site dictionary
            site_id: SkySpark site ID
        """
        logger.info("storing_site_ref_to_ace", site=ace_site["name"], skyspark_id=site_id)

        # Note: ACE API doesn't have a sites update endpoint with kv_tags
        # We would need to add this to aceiot_models or use a custom request
        # For now, just log - TODO: Implement site kv_tags storage
        logger.warning(
            "site_ref_storage_not_implemented",
            site=ace_site["name"],
            message="ACE API does not support kv_tags on sites yet",
        )

    def _build_ref_map(self, skyspark_points: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Build a map of SkySpark point ID -> SkySpark point.

        The haystackRef is stored in FlightDeck and contains the SkySpark point ID.
        This map allows us to look up SkySpark points by their ID.

        Args:
            skyspark_points: List of SkySpark points

        Returns:
            Dictionary mapping SkySpark point ID to point data
        """
        ref_map: dict[str, dict[str, Any]] = {}

        for point in skyspark_points:
            # Extract SkySpark point ID
            point_id = point.get("id", {})
            if isinstance(point_id, dict):
                point_id_val = point_id.get("val", "").lstrip("@")
            else:
                point_id_val = str(point_id).lstrip("@")

            if point_id_val:
                ref_map[point_id_val] = point

        logger.debug("ref_map_built", count=len(ref_map))
        return ref_map

    def _get_haystack_ref(self, ace_point: dict[str, Any]) -> str | None:
        """Get haystackRef from ACE point's KV tags.

        Args:
            ace_point: ACE point dictionary

        Returns:
            haystackRef value or None
        """
        kv_tags = ace_point.get("kv_tags")
        if not kv_tags:
            return None
        return kv_tags.get(self.HAYSTACK_REF_TAG)

    def _prepare_point_create(
        self,
        ace_point: dict[str, Any],
        site_ref: str,
        equipment_ref_map: dict[str, str],
        skyspark_tz: str,
    ) -> Point:
        """Prepare a SkySpark Point for creation from ACE point.

        Args:
            ace_point: ACE point dictionary
            site_ref: SkySpark site reference ID
            equipment_ref_map: Map of equipment key to SkySpark equipment ref
            skyspark_tz: SkySpark project timezone

        Returns:
            SkySpark Point model
        """
        # Convert ACE point to SkySpark point
        # Apply marker tags and KV tags from FlightDeck

        marker_tags = ace_point.get("marker_tags") or []
        kv_tags = ace_point.get("kv_tags") or {}

        # Generate a refName from the ACE point ID
        point_id = ace_point.get("id")
        point_name = ace_point["name"]
        ref_name = f"ace-point-{point_id}" if point_id else f"ace-{point_name.replace(' ', '_')}"

        # Add ace_topic to track original ACE point name
        # Filter out haystack_* refs from kv_tags as siteRef/equipRef are top-level Point fields
        # Filter out skysparkTz as it's top-level field
        final_kv_tags = {
            "ace_topic": point_name,  # Store original ACE point name
            "skysparkTz": skyspark_tz,  # Store for legacy compatibility
            **{k: v for k, v in kv_tags.items() if k not in {
                self.HAYSTACK_REF_TAG,
                "haystack_siteRef",
                "haystack_equipRef",
                "skysparkTz",  # Don't duplicate
            }},
        }

        # Get equipment ref and display name from bacnet_data
        equip_ref = "placeholder-equip"
        display_name = point_name  # Default to point name
        bacnet_data = ace_point.get("bacnet_data")
        if bacnet_data:
            device_addr = bacnet_data.get("device_address")
            device_id = bacnet_data.get("device_id")
            if device_addr and device_id is not None:
                equip_key = f"{device_addr}-{device_id}"
                equip_ref = equipment_ref_map.get(equip_key, "placeholder-equip")

            # Use object_name for display if available and not empty
            object_name = bacnet_data.get("object_name")
            if object_name and object_name.strip():
                display_name = object_name

        # Build marker tags: ensure exactly one function marker
        function_markers = {"sensor", "cmd", "sp", "synthetic"}
        ace_function_markers = [m for m in marker_tags if m in function_markers]
        ace_other_markers = [m for m in marker_tags if m not in function_markers]

        if ace_function_markers:
            # ACE has function marker(s), use only the first one
            final_marker_tags = ["point", ace_function_markers[0]] + ace_other_markers
        else:
            # No function marker in ACE tags, add default "sensor"
            final_marker_tags = ["point", "sensor"] + ace_other_markers

        return Point(
            dis=display_name,
            refName=ref_name,
            siteRef=site_ref,
            equipRef=equip_ref,
            kind="Number",  # TODO: Determine from ace_point data type
            tz=skyspark_tz,  # Use SkySpark project timezone
            his=True,  # All ACE points are historized
            marker_tags=final_marker_tags,
            kv_tags=final_kv_tags,
        )

    def _prepare_point_update(
        self,
        ace_point: dict[str, Any],
        sky_point: dict[str, Any],
        site_ref: str,
        equipment_ref_map: dict[str, str],
        skyspark_tz: str,
    ) -> Point:
        """Prepare a SkySpark Point for update.

        Args:
            ace_point: ACE point dictionary
            sky_point: Existing SkySpark point
            site_ref: SkySpark site reference ID
            equipment_ref_map: Map of equipment key to SkySpark equipment ref
            skyspark_tz: SkySpark project timezone

        Returns:
            Updated SkySpark Point model
        """
        # Get the SkySpark ID and required fields from existing point
        # Extract point ID (handle both dict and string formats)
        point_id_val = sky_point.get("id", {})
        if isinstance(point_id_val, dict):
            point_id = point_id_val.get("val", "").lstrip("@")
        else:
            point_id = str(point_id_val).lstrip("@")

        # Get existing values for required fields
        existing_ref_name = sky_point.get("refName", "")

        # Extract siteRef (handle both dict and string formats)
        site_ref_val = sky_point.get("siteRef", {})
        if isinstance(site_ref_val, dict):
            existing_site_ref = site_ref_val.get("val", "").lstrip("@")
        else:
            existing_site_ref = str(site_ref_val).lstrip("@")

        # Extract equipRef (handle both dict and string formats)
        equip_ref_val = sky_point.get("equipRef", {})
        if isinstance(equip_ref_val, dict):
            existing_equip_ref = equip_ref_val.get("val", "").lstrip("@")
        else:
            existing_equip_ref = str(equip_ref_val).lstrip("@")

        existing_kind = sky_point.get("kind", "Number")

        # Determine correct equipment ref and display name from bacnet_data
        equip_ref = existing_equip_ref  # Default to existing
        point_name = ace_point["name"]
        display_name = point_name  # Default to point name
        bacnet_data = ace_point.get("bacnet_data")
        if bacnet_data:
            device_addr = bacnet_data.get("device_address")
            device_id = bacnet_data.get("device_id")
            if device_addr and device_id is not None:
                equip_key = f"{device_addr}-{device_id}"
                equip_ref = equipment_ref_map.get(equip_key, existing_equip_ref)

            # Use object_name for display if available and not empty
            object_name = bacnet_data.get("object_name")
            if object_name and object_name.strip():
                display_name = object_name

        # Log if refs are being updated
        if existing_site_ref != site_ref:
            logger.info(
                "point_siteref_updating",
                point=ace_point["name"],
                old_site=existing_site_ref,
                new_site=site_ref,
            )
        if existing_equip_ref != equip_ref:
            logger.info(
                "point_equipref_updating",
                point=ace_point["name"],
                old_equip=existing_equip_ref,
                new_equip=equip_ref,
            )

        # Extract existing marker tags from SkySpark point (especially function markers)
        existing_markers = []
        function_markers = {"sensor", "cmd", "sp", "synthetic"}

        # Log relevant fields from sky_point to understand format
        logger.debug(
            "sky_point_markers",
            point=ace_point.get("name"),
            sensor=sky_point.get("sensor"),
            cmd=sky_point.get("cmd"),
            sp=sky_point.get("sp"),
            synthetic=sky_point.get("synthetic"),
        )

        for key, val in sky_point.items():
            # Marker tags in SkySpark are stored as "m:" or True or with _kind: "marker"
            if key in function_markers:
                if val == "m:" or val is True or (isinstance(val, dict) and val.get("_kind") == "marker"):
                    existing_markers.append(key)

        logger.debug(
            "extracted_markers",
            point=ace_point.get("name"),
            existing_markers=existing_markers,
            has_function_marker=len(existing_markers) > 0,
        )

        # Merge tags from ACE into SkySpark point
        marker_tags = ace_point.get("marker_tags") or []
        kv_tags = ace_point.get("kv_tags") or {}

        # Combine markers intelligently: ensure exactly one function marker
        # ACE marker_tags take precedence over existing SkySpark markers
        function_markers = {"sensor", "cmd", "sp", "synthetic"}
        ace_function_markers = [m for m in marker_tags if m in function_markers]
        ace_other_markers = [m for m in marker_tags if m not in function_markers]

        if ace_function_markers:
            # ACE has function marker(s), use only the first one
            final_marker_tags = ["point", ace_function_markers[0]] + ace_other_markers
        elif existing_markers:
            # ACE has no function markers, preserve SkySpark's (should be only one)
            final_marker_tags = ["point", existing_markers[0]] + ace_other_markers
        else:
            # No function markers anywhere, add default "sensor"
            final_marker_tags = ["point", "sensor"] + ace_other_markers

        # Build kv_tags including mod field for optimistic locking
        # Filter out haystack_* refs from kv_tags as siteRef/equipRef are top-level Point fields
        # Filter out skysparkTz as it's top-level field
        final_kv_tags = {
            "ace_topic": point_name,  # Store original ACE point name
            "skysparkTz": skyspark_tz,  # Store for legacy compatibility
            **{k: v for k, v in kv_tags.items() if k not in {
                self.HAYSTACK_REF_TAG,
                "haystack_siteRef",
                "haystack_equipRef",
                "skysparkTz",  # Don't duplicate
            }},
        }

        # Add mod field from existing point for optimistic locking (required for updates)
        mod_val = sky_point.get("mod")
        if mod_val:
            final_kv_tags["mod"] = mod_val

        return Point(
            id=point_id,
            dis=display_name,  # Use object_name from bacnet_data if available, else point name
            refName=existing_ref_name,
            siteRef=site_ref,
            equipRef=equip_ref,
            kind=existing_kind,
            tz=skyspark_tz,  # Use SkySpark project timezone
            his=True,  # All ACE points are historized
            marker_tags=final_marker_tags,
            kv_tags=final_kv_tags,
        )

    async def _create_points_batch_resilient(
        self,
        points: list[Point],
        ace_points: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Create points in SkySpark in batches with resilient error handling.

        Stores refs back to ACE after each successful batch to enable recovery.
        Continues processing even if a batch fails.

        Args:
            points: List of Point models to create
            ace_points: Corresponding ACE point dicts for ref storage

        Returns:
            Tuple of (successful_count, failed_count)
        """
        batch_size = self.config.app.batch_size
        successful_count = 0
        failed_count = 0

        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            ace_batch = ace_points[i : i + batch_size]
            batch_num = i // batch_size + 1

            logger.info("creating_points_batch", batch_num=batch_num, size=len(batch))

            try:
                # Create batch in SkySpark
                created = await self.skyspark_client.create_points(batch)
                logger.info("points_created", count=len(created))

                # CRITICAL: Store refs back to ACE immediately after successful batch
                # This ensures recovery if next batch fails
                try:
                    await self._store_refs_to_ace(ace_batch, created)
                    successful_count += len(created)
                    logger.info("refs_stored_for_batch", batch_num=batch_num, count=len(created))
                except Exception as ref_error:
                    # Point creation succeeded but ref storage failed
                    # This is recoverable - refs can be synced later with sync-refs-from-skyspark
                    logger.error(
                        "ref_storage_failed_for_batch",
                        batch_num=batch_num,
                        error=str(ref_error),
                        message="Points created but refs not stored - run sync-refs-from-skyspark to fix"
                    )
                    successful_count += len(created)

            except Exception as e:
                logger.error(
                    "create_batch_failed",
                    error=str(e),
                    batch_start=i,
                    batch_num=batch_num,
                    message="Continuing with next batch..."
                )
                failed_count += len(batch)
                # Continue to next batch instead of raising

        logger.info(
            "create_batches_complete",
            successful=successful_count,
            failed=failed_count,
            total=len(points)
        )
        return successful_count, failed_count

    async def _create_points_batch(self, points: list[Point]) -> list[dict[str, Any]]:
        """Create points in SkySpark in batches (legacy - used internally).

        Args:
            points: List of points to create

        Returns:
            List of created point dictionaries
        """
        batch_size = self.config.app.batch_size
        created_points: list[dict[str, Any]] = []

        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            logger.info("creating_points_batch", batch_num=i // batch_size + 1, size=len(batch))

            try:
                created = await self.skyspark_client.create_points(batch)
                created_points.extend(created)
                logger.info("points_created", count=len(created))
            except Exception as e:
                logger.error("create_batch_failed", error=str(e), batch_start=i)
                raise

        return created_points

    async def _update_points_batch_resilient(
        self,
        points: list[Point],
        ace_points: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Update points in SkySpark in batches with resilient error handling.

        Stores refs back to ACE after each successful batch to enable recovery.
        Continues processing even if a batch fails.

        Args:
            points: List of Point models to update
            ace_points: Corresponding ACE point dicts for ref storage

        Returns:
            Tuple of (successful_count, failed_count)
        """
        batch_size = self.config.app.batch_size
        successful_count = 0
        failed_count = 0

        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            ace_batch = ace_points[i : i + batch_size]
            batch_num = i // batch_size + 1

            logger.info("updating_points_batch", batch_num=batch_num, size=len(batch))

            try:
                # Update batch in SkySpark
                updated = await self.skyspark_client.update_points(batch)
                logger.info("points_updated", count=len(updated))

                # Store updated refs back to ACE (fixes orphaned refs)
                try:
                    await self._store_refs_to_ace(ace_batch, updated)
                    successful_count += len(updated)
                    logger.info("refs_stored_for_batch", batch_num=batch_num, count=len(updated))
                except Exception as ref_error:
                    # Point update succeeded but ref storage failed
                    logger.error(
                        "ref_storage_failed_for_batch",
                        batch_num=batch_num,
                        error=str(ref_error),
                        message="Points updated but refs not stored - run sync-refs-from-skyspark to fix"
                    )
                    successful_count += len(updated)

            except Exception as e:
                logger.error(
                    "update_batch_failed",
                    error=str(e),
                    batch_start=i,
                    batch_num=batch_num,
                    message="Continuing with next batch..."
                )
                failed_count += len(batch)
                # Continue to next batch instead of raising

        logger.info(
            "update_batches_complete",
            successful=successful_count,
            failed=failed_count,
            total=len(points)
        )
        return successful_count, failed_count

    async def _update_points_batch(self, points: list[Point]) -> list[dict[str, Any]]:
        """Update points in SkySpark in batches (legacy - used internally).

        Args:
            points: List of points to update

        Returns:
            List of updated point dictionaries
        """
        batch_size = self.config.app.batch_size
        updated_points: list[dict[str, Any]] = []

        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            logger.info("updating_points_batch", batch_num=i // batch_size + 1, size=len(batch))

            try:
                updated = await self.skyspark_client.update_points(batch)
                updated_points.extend(updated)
                logger.info("points_updated", count=len(updated))
            except Exception as e:
                logger.error("update_batch_failed", error=str(e), batch_start=i)
                raise

        return updated_points

    async def sync_refs_from_skyspark(
        self,
        site: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Sync refs from SkySpark back to ACE FlightDeck.

        Reads points from SkySpark that have ace_topic tags and writes
        the SkySpark refs back to ACE as KV tags.

        Args:
            site: Optional site name to filter points
            dry_run: If True, don't make any changes

        Returns:
            Dictionary with results: points_found, refs_updated, points_skipped, errors
        """
        logger.info("sync_refs_from_skyspark_start", site=site, dry_run=dry_run)

        points_found = 0
        refs_updated = 0
        points_skipped = 0
        errors: list[str] = []

        try:
            # Read all points from SkySpark
            skyspark_points = await self._fetch_skyspark_points()
            logger.info("skyspark_points_fetched", count=len(skyspark_points))

            # Filter points that have ace_topic tag
            points_with_topic = []
            for sky_point in skyspark_points:
                ace_topic = sky_point.get("ace_topic")
                if ace_topic:
                    # Optionally filter by site
                    if site:
                        # ace_topic format: client/site/point_name
                        topic_parts = ace_topic.split("/")
                        if len(topic_parts) >= 2:
                            point_site = topic_parts[1]
                            if point_site != site:
                                continue

                    points_with_topic.append(sky_point)

            points_found = len(points_with_topic)
            logger.info("points_with_ace_topic", count=points_found, site_filter=site)

            if not points_with_topic:
                logger.warning("no_points_with_ace_topic_found", site=site)
                return {
                    "points_found": 0,
                    "refs_updated": 0,
                    "points_skipped": 0,
                    "errors": [],
                }

            # Build ACE point updates with refs
            ace_points_to_update: list[dict[str, Any]] = []

            for sky_point in points_with_topic:
                try:
                    # Extract ace_topic (this is the ACE point name)
                    ace_topic = sky_point.get("ace_topic")
                    if not ace_topic:
                        points_skipped += 1
                        continue

                    # Parse ace_topic: client/site/point_name
                    topic_parts = ace_topic.split("/")
                    if len(topic_parts) < 3:
                        logger.warning("invalid_ace_topic_format", topic=ace_topic)
                        points_skipped += 1
                        continue

                    client_name = topic_parts[0]
                    site_name = topic_parts[1]
                    point_name = "/".join(topic_parts[2:])  # Handle slashes in point name

                    # Extract SkySpark refs
                    sky_id = sky_point.get("id", {})
                    if isinstance(sky_id, dict):
                        sky_id_val = sky_id.get("val", "").lstrip("@")
                    else:
                        sky_id_val = str(sky_id).lstrip("@")

                    site_ref = sky_point.get("siteRef", {})
                    if isinstance(site_ref, dict):
                        site_ref_val = site_ref.get("val", "").lstrip("@")
                    else:
                        site_ref_val = str(site_ref).lstrip("@")

                    equip_ref = sky_point.get("equipRef", {})
                    if isinstance(equip_ref, dict):
                        equip_ref_val = equip_ref.get("val", "").lstrip("@")
                    else:
                        equip_ref_val = str(equip_ref).lstrip("@")

                    if not sky_id_val:
                        logger.warning("skyspark_point_missing_id", ace_topic=ace_topic)
                        points_skipped += 1
                        continue

                    # Build KV tags update
                    updated_kv_tags = {
                        self.HAYSTACK_REF_TAG: sky_id_val,
                        "haystack_siteRef": site_ref_val,
                        "haystack_equipRef": equip_ref_val,
                    }

                    # Create minimal point update
                    updated_point = {
                        "name": point_name,
                        "client": client_name,
                        "site": site_name,
                        "kv_tags": updated_kv_tags,
                    }

                    ace_points_to_update.append(updated_point)
                    logger.debug(
                        "prepared_ref_update_from_skyspark",
                        point_name=point_name,
                        skyspark_id=sky_id_val,
                        site_ref=site_ref_val,
                        equip_ref=equip_ref_val,
                    )

                except Exception as e:
                    error_msg = f"Error processing SkySpark point {sky_point.get('dis', 'unknown')}: {e!s}"
                    logger.error("point_processing_error_skyspark", error=str(e))
                    errors.append(error_msg)
                    points_skipped += 1
                    continue

            if not ace_points_to_update:
                logger.warning("no_ace_points_to_update")
                return {
                    "points_found": points_found,
                    "refs_updated": 0,
                    "points_skipped": points_skipped,
                    "errors": errors,
                }

            # Update ACE points with refs
            if not dry_run:
                loop = asyncio.get_event_loop()
                try:
                    await loop.run_in_executor(
                        None,
                        self.ace_client.create_points,
                        ace_points_to_update,
                        False,  # overwrite_m_tags
                        False,  # overwrite_kv_tags (merge mode)
                    )
                    refs_updated = len(ace_points_to_update)
                    logger.info("refs_synced_from_skyspark_to_ace", count=refs_updated)
                except Exception as e:
                    error_msg = f"Failed to update ACE points: {e!s}"
                    logger.error("batch_ref_update_failed", error=str(e))
                    errors.append(error_msg)
            else:
                logger.info(
                    "dry_run_would_update_refs",
                    count=len(ace_points_to_update),
                )
                refs_updated = len(ace_points_to_update)

        except Exception as e:
            error_msg = f"Sync refs from SkySpark failed: {e!s}"
            errors.append(error_msg)
            logger.error("sync_refs_from_skyspark_failed", error=str(e))

        return {
            "points_found": points_found,
            "refs_updated": refs_updated,
            "points_skipped": points_skipped,
            "errors": errors,
        }

    async def _store_refs_to_ace(
        self,
        ace_points: list[dict[str, Any]],
        skyspark_points: list[dict[str, Any]],
    ) -> None:
        """Store SkySpark references back to ACE as KV tags.

        Stores haystackRef (point ID), siteRef, and equipRef to enable:
        - Idempotent syncing (haystackRef lookup)
        - Entity hierarchy tracking (siteRef, equipRef)

        Args:
            ace_points: Original ACE point dictionaries
            skyspark_points: Created SkySpark points with IDs and references
        """
        logger.info("storing_refs_to_ace", count=len(skyspark_points))

        # Build batch of point updates with haystackRef, siteRef, and equipRef tags
        points_to_update: list[dict[str, Any]] = []

        for ace_point, sky_point in zip(ace_points, skyspark_points, strict=False):
            # Extract SkySpark references
            sky_id = sky_point.get("id", {}).get("val", "").lstrip("@")
            site_ref = sky_point.get("siteRef", {})
            equip_ref = sky_point.get("equipRef", {})

            if not sky_id:
                logger.warning("no_id_in_skyspark_point", point=ace_point.get("name", "unknown"))
                continue

            # Extract ref values from dict format
            if isinstance(site_ref, dict):
                site_ref_val = site_ref.get("val", "").lstrip("@")
            else:
                site_ref_val = str(site_ref).lstrip("@")

            if isinstance(equip_ref, dict):
                equip_ref_val = equip_ref.get("val", "").lstrip("@")
            else:
                equip_ref_val = str(equip_ref).lstrip("@")

            # Merge all refs into existing kv_tags
            existing_kv_tags = ace_point.get("kv_tags") or {}
            updated_kv_tags = {
                **existing_kv_tags,
                self.HAYSTACK_REF_TAG: sky_id,
                "haystack_siteRef": site_ref_val,
                "haystack_equipRef": equip_ref_val,
            }

            # Create minimal point update with required fields
            # Note: Do NOT include bacnet_data as it may contain empty strings that cause backend errors
            updated_point = {
                "name": ace_point["name"],
                "client": ace_point["client"],
                "site": ace_point["site"],
                "kv_tags": updated_kv_tags,
            }

            points_to_update.append(updated_point)
            logger.debug(
                "prepared_ref_update",
                ace_point=ace_point["name"],
                skyspark_id=sky_id,
                site_ref=site_ref_val,
                equip_ref=equip_ref_val,
            )

        if not points_to_update:
            logger.warning("no_refs_to_store")
            return

        # Batch update using create_points with overwrite_kv_tags=False to merge
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                self.ace_client.create_points,
                points_to_update,
                False,  # overwrite_m_tags
                False,  # overwrite_kv_tags (merge mode)
            )
            logger.info("refs_stored_to_ace", count=len(points_to_update))
        except Exception as e:
            logger.error("batch_ref_storage_failed", error=str(e), count=len(points_to_update))
            raise
