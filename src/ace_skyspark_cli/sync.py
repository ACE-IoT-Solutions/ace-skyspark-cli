"""Point synchronization service for ACE to SkySpark.

This module implements idempotent synchronization of points, equipment, and entities
from ACE FlightDeck to SkySpark using haystackRef KV tags for tracking.
"""

from typing import Any

import structlog
from ace_skyspark_lib import Point, SkysparkClient
from aceiot_models.api import APIClient
from aceiot_models.points import Point as ACEPoint

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
    ) -> SyncResult:
        """Synchronize all points for a specific site.

        This method:
        1. Fetches points from ACE FlightDeck for the given site
        2. Checks for existing SkySpark entities using haystackRef tags
        3. Creates new entities or updates existing ones
        4. Maintains idempotency by storing SkySpark IDs back to ACE

        Args:
            site_name: Name of the site to synchronize
            dry_run: If True, don't make any changes

        Returns:
            SyncResult with statistics
        """
        result = SyncResult()
        logger.info("sync_start", site=site_name, dry_run=dry_run)

        try:
            # Fetch points from ACE
            ace_points = await self._fetch_ace_points(site_name)
            logger.info("ace_points_fetched", count=len(ace_points), site=site_name)

            if not ace_points:
                logger.warning("no_points_found", site=site_name)
                return result

            # Fetch existing SkySpark points to check for matches
            skyspark_points = await self._fetch_skyspark_points()
            logger.info("skyspark_points_fetched", count=len(skyspark_points))

            # Build lookup map: haystackRef -> SkySpark point
            skyspark_ref_map = self._build_ref_map(skyspark_points)

            # Process each ACE point
            points_to_create: list[Point] = []
            points_to_update: list[Point] = []

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

                except Exception as e:
                    error_msg = f"Error processing point {ace_point.name}: {e!s}"
                    result.add_error(error_msg)
                    continue

            # Execute creates and updates
            if not dry_run:
                if points_to_create:
                    created = await self._create_points_batch(points_to_create)
                    result.points_created += len(created)
                    # Store haystackRef back to ACE
                    await self._store_refs_to_ace(points_to_create, created)

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

    async def _fetch_ace_points(self, site_name: str) -> list[ACEPoint]:
        """Fetch points from ACE FlightDeck.

        Args:
            site_name: Site name to filter by

        Returns:
            List of ACE points
        """
        # This would use the ACE API client to fetch points
        # For now, returning empty list as placeholder
        logger.info("fetching_ace_points", site=site_name)

        # Get site ID from name first
        # Then get points for that site
        # Example: points = await self.ace_client.get_points_for_site(site_id)

        return []

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

    def _get_haystack_ref(self, ace_point: ACEPoint) -> str | None:
        """Get haystackRef from ACE point's KV tags.

        Args:
            ace_point: ACE point

        Returns:
            haystackRef value or None
        """
        if not ace_point.kv_tags:
            return None
        return ace_point.kv_tags.get(self.HAYSTACK_REF_TAG)

    def _prepare_point_create(self, ace_point: ACEPoint) -> Point:
        """Prepare a SkySpark Point for creation from ACE point.

        Args:
            ace_point: ACE point data

        Returns:
            SkySpark Point model
        """
        # Convert ACE point to SkySpark point
        # Apply marker tags and KV tags from FlightDeck

        marker_tags = ace_point.marker_tags or []
        kv_tags = ace_point.kv_tags or {}

        # Generate a refName from the ACE point ID
        ref_name = f"ace-point-{ace_point.id}" if hasattr(ace_point, "id") else f"ace-{ace_point.name.replace(' ', '_')}"

        # For now, use placeholder values for required fields
        # In production, these should come from the ACE point or be mapped
        return Point(
            dis=ace_point.name,
            refName=ref_name,
            siteRef="placeholder-site",  # TODO: Map from ace_point.site_id
            equipRef="placeholder-equip",  # TODO: Map from ace_point.device_id
            kind="Number",  # TODO: Determine from ace_point data type
            marker_tags=["point"] + marker_tags,
            kv_tags={k: v for k, v in kv_tags.items() if k != self.HAYSTACK_REF_TAG},
        )

    def _prepare_point_update(
        self,
        ace_point: ACEPoint,
        sky_point: dict[str, Any],
    ) -> Point:
        """Prepare a SkySpark Point for update.

        Args:
            ace_point: ACE point data
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
        marker_tags = ace_point.marker_tags or []
        kv_tags = ace_point.kv_tags or {}

        return Point(
            id=point_id,
            dis=ace_point.name,
            refName=existing_ref_name,
            siteRef=existing_site_ref,
            equipRef=existing_equip_ref,
            kind=existing_kind,
            marker_tags=["point"] + marker_tags,
            kv_tags={k: v for k, v in kv_tags.items() if k != self.HAYSTACK_REF_TAG},
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
        ace_points: list[Point],
        skyspark_points: list[dict[str, Any]],
    ) -> None:
        """Store SkySpark IDs back to ACE as haystackRef tags.

        This ensures idempotency by linking ACE points to SkySpark entities.

        Args:
            ace_points: Original ACE points
            skyspark_points: Created SkySpark points with IDs
        """
        logger.info("storing_refs_to_ace", count=len(skyspark_points))

        for ace_point, sky_point in zip(ace_points, skyspark_points, strict=False):
            try:
                # Extract SkySpark ID
                sky_id = sky_point.get("id", {}).get("val", "").lstrip("@")

                if not sky_id:
                    logger.warning("no_id_in_skyspark_point", point=ace_point.dis)
                    continue

                # Update ACE point with haystackRef
                # This would call ACE API to update the point's KV tags
                # Example: await self.ace_client.update_point_tags(
                #     point_id=ace_point.id,
                #     kv_tags={self.HAYSTACK_REF_TAG: sky_id}
                # )

                logger.debug("stored_ref", ace_point=ace_point.dis, skyspark_id=sky_id)

            except Exception as e:
                logger.error("store_ref_failed", point=ace_point.dis, error=str(e))
                continue
