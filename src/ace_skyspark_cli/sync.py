"""Point synchronization service for ACE to SkySpark.

This module implements idempotent synchronization of points, equipment, and entities
from ACE FlightDeck to SkySpark using haystackRef KV tags for tracking.
"""

import asyncio
from typing import Any

import structlog
from ace_skyspark_lib import Point, SkysparkClient
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

    HAYSTACK_REF_TAG = "haystackRef"

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

            # Fetch existing SkySpark points to check for matches
            skyspark_points = await self._fetch_skyspark_points()
            logger.info("skyspark_points_fetched", count=len(skyspark_points))

            # Build lookup map: haystackRef -> SkySpark point
            skyspark_ref_map = self._build_ref_map(skyspark_points)

            # Process each ACE point
            points_to_create: list[Point] = []
            points_to_update: list[Point] = []
            ace_points_to_create: list[dict[str, Any]] = []  # Track original ACE dicts

            for ace_point in ace_points:
                try:
                    # Check if point already exists in SkySpark
                    haystack_ref = self._get_haystack_ref(ace_point)

                    if haystack_ref and haystack_ref in skyspark_ref_map:
                        # Point exists - prepare update
                        sky_point = skyspark_ref_map[haystack_ref]
                        updated_point = self._prepare_point_update(ace_point, sky_point)
                        points_to_update.append(updated_point)
                        result.points_skipped += 1
                    else:
                        # Point doesn't exist - prepare create
                        new_point = self._prepare_point_create(ace_point)
                        points_to_create.append(new_point)
                        ace_points_to_create.append(ace_point)  # Keep original ACE dict

                except Exception as e:
                    error_msg = f"Error processing point {ace_point.get('name', 'unknown')}: {e!s}"
                    result.add_error(error_msg)
                    continue

            # Execute creates and updates
            if not dry_run:
                if points_to_create:
                    created = await self._create_points_batch(points_to_create)
                    result.points_created += len(created)
                    # Store haystackRef back to ACE
                    await self._store_refs_to_ace(ace_points_to_create, created)

                if points_to_update:
                    updated = await self._update_points_batch(points_to_update)
                    result.points_updated += len(updated)
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
        # Note: configured_points endpoint works with per_page=10, all points endpoint crashes
        per_page = 10  # Safe page size that works for all pages

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

    def _build_ref_map(self, skyspark_points: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Build a map of haystackRef -> SkySpark point.

        Args:
            skyspark_points: List of SkySpark points

        Returns:
            Dictionary mapping haystackRef to point data
        """
        ref_map: dict[str, dict[str, Any]] = {}

        for point in skyspark_points:
            # Look for haystackRef in the point's tags
            haystack_ref = point.get(self.HAYSTACK_REF_TAG)
            if haystack_ref:
                ref_map[str(haystack_ref)] = point

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

    def _prepare_point_create(self, ace_point: dict[str, Any]) -> Point:
        """Prepare a SkySpark Point for creation from ACE point.

        Args:
            ace_point: ACE point dictionary

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
        final_kv_tags = {
            "ace_topic": point_name,  # Store original ACE point name
            **{k: v for k, v in kv_tags.items() if k != self.HAYSTACK_REF_TAG},
        }

        # For now, use placeholder values for required fields
        # In production, these should come from the ACE point or be mapped
        return Point(
            dis=point_name,
            refName=ref_name,
            siteRef="placeholder-site",  # TODO: Map from ace_point["site"]
            equipRef="placeholder-equip",  # TODO: Map from ace_point device
            kind="Number",  # TODO: Determine from ace_point data type
            marker_tags=["point", "sensor"] + marker_tags,  # Add sensor as default function marker
            kv_tags=final_kv_tags,
        )

    def _prepare_point_update(
        self,
        ace_point: dict[str, Any],
        sky_point: dict[str, Any],
    ) -> Point:
        """Prepare a SkySpark Point for update.

        Args:
            ace_point: ACE point dictionary
            sky_point: Existing SkySpark point

        Returns:
            Updated SkySpark Point model
        """
        # Get the SkySpark ID and required fields from existing point
        point_id = sky_point.get("id", {}).get("val", "").lstrip("@")

        # Get existing values for required fields
        existing_ref_name = sky_point.get("refName", "")
        existing_site_ref = sky_point.get("siteRef", {}).get("val", "").lstrip("@")
        existing_equip_ref = sky_point.get("equipRef", {}).get("val", "").lstrip("@")
        existing_kind = sky_point.get("kind", "Number")

        # Merge tags from ACE into SkySpark point
        marker_tags = ace_point.get("marker_tags") or []
        kv_tags = ace_point.get("kv_tags") or {}
        point_name = ace_point["name"]

        # Add ace_topic to track original ACE point name
        final_kv_tags = {
            "ace_topic": point_name,  # Store original ACE point name
            **{k: v for k, v in kv_tags.items() if k != self.HAYSTACK_REF_TAG},
        }

        return Point(
            id=point_id,
            dis=point_name,
            refName=existing_ref_name,
            siteRef=existing_site_ref,
            equipRef=existing_equip_ref,
            kind=existing_kind,
            marker_tags=["point"] + marker_tags,
            kv_tags=final_kv_tags,
        )

    async def _create_points_batch(self, points: list[Point]) -> list[dict[str, Any]]:
        """Create points in SkySpark in batches.

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

    async def _update_points_batch(self, points: list[Point]) -> list[dict[str, Any]]:
        """Update points in SkySpark in batches.

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

    async def _store_refs_to_ace(
        self,
        ace_points: list[dict[str, Any]],
        skyspark_points: list[dict[str, Any]],
    ) -> None:
        """Store SkySpark IDs back to ACE as haystackRef tags.

        This ensures idempotency by linking ACE points to SkySpark entities.

        Args:
            ace_points: Original ACE point dictionaries
            skyspark_points: Created SkySpark points with IDs
        """
        logger.info("storing_refs_to_ace", count=len(skyspark_points))

        # Build batch of point updates with haystackRef tags
        points_to_update: list[dict[str, Any]] = []

        for ace_point, sky_point in zip(ace_points, skyspark_points, strict=False):
            # Extract SkySpark ID
            sky_id = sky_point.get("id", {}).get("val", "").lstrip("@")

            if not sky_id:
                logger.warning("no_id_in_skyspark_point", point=ace_point.get("name", "unknown"))
                continue

            # Merge haystackRef into existing kv_tags
            existing_kv_tags = ace_point.get("kv_tags") or {}
            updated_kv_tags = {**existing_kv_tags, self.HAYSTACK_REF_TAG: sky_id}

            # Create minimal point update with required fields
            # Note: Do NOT include bacnet_data as it may contain empty strings that cause backend errors
            updated_point = {
                "name": ace_point["name"],
                "client": ace_point["client"],
                "site": ace_point["site"],
                "kv_tags": updated_kv_tags,
            }

            points_to_update.append(updated_point)
            logger.debug("prepared_ref_update", ace_point=ace_point["name"], skyspark_id=sky_id)

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
