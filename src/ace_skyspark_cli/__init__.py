"""ACE SkySpark CLI - Sync points from FlightDeck to SkySpark."""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TYPE_CHECKING

import click
import structlog
from ace_skyspark_lib import SkysparkClient
from aceiot_models.api import APIClient

from ace_skyspark_cli.config import Config
from ace_skyspark_cli.logging import configure_logging, get_logger, log_config

if TYPE_CHECKING:
    from ace_skyspark_cli.sync import PointSyncService

__version__ = "0.9.1"

logger: Any = None


@asynccontextmanager
async def create_clients(config: Config):
    """Create ACE and SkySpark clients with proper lifecycle management.

    This context manager ensures:
    - Clients are created with proper configuration
    - Sessions are logged when created and closed
    - Proper cleanup even on errors

    Args:
        config: Application configuration

    Yields:
        Tuple of (ace_client, skyspark_client)
    """
    if not logger:
        raise RuntimeError("Logger not initialized")

    # Create ACE API client (synchronous)
    ace_client = APIClient(
        base_url=config.flightdeck.api_url,
        api_key=config.flightdeck.jwt,
        timeout=config.flightdeck.timeout,
    )

    logger.info(
        "creating_skyspark_session",
        url=config.skyspark.url,
        project=config.skyspark.project,
        pool_size=config.skyspark.pool_size,
        timeout=config.skyspark.timeout,
    )

    # Create SkySpark client with async context manager
    async with SkysparkClient(
        base_url=config.skyspark.url,
        project=config.skyspark.project,
        username=config.skyspark.user,
        password=config.skyspark.password,
        timeout=config.skyspark.timeout,
        max_retries=config.skyspark.max_retries,
        pool_size=config.skyspark.pool_size,
    ) as skyspark_client:
        logger.info("skyspark_session_created")
        try:
            yield (ace_client, skyspark_client)
        finally:
            logger.info("closing_skyspark_session")

    logger.info("skyspark_session_closed")


@click.group()
@click.option(
    "--env-file",
    type=click.Path(exists=True, path_type=Path),
    default=".env",
    help="Path to .env file with configuration",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False),
    default="INFO",
    help="Logging level",
)
@click.option(
    "--json-logs",
    is_flag=True,
    help="Output logs in JSON format",
)
@click.pass_context
def cli(ctx: click.Context, env_file: Path, log_level: str, json_logs: bool) -> None:
    """ACE SkySpark CLI - Synchronize points from FlightDeck to SkySpark.

    This tool provides idempotent synchronization of points, equipment, and entities
    from ACE FlightDeck to SkySpark using haystackRef tags for tracking.
    """
    global logger

    # Configure logging
    configure_logging(log_level=log_level, json_format=json_logs)
    logger = get_logger(__name__)

    # Load configuration
    try:
        config = Config.from_env(str(env_file) if env_file else None)
        ctx.obj = config

        # Log configuration (with sensitive data masked)
        log_config(config.to_dict())

    except Exception as e:
        logger.error("config_load_failed", error=str(e))
        sys.exit(1)


@cli.command()
@click.option(
    "--site",
    required=True,
    help="Site name to synchronize",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Perform a dry run without making changes",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Limit the number of points to sync (sorted by name for idempotency)",
)
@click.option(
    "--sync-all",
    is_flag=True,
    help="Sync all points including non-configured (default: only configured/collected points)",
)
@click.option(
    "--batch-size",
    type=int,
    default=None,
    help="Override batch size for SkySpark operations (default: 500)",
)
@click.pass_obj
def sync(config: Config, site: str, dry_run: bool, limit: int | None, sync_all: bool, batch_size: int | None) -> None:
    """Synchronize points from FlightDeck to SkySpark for a specific site.

    This command:
    - Fetches configured/collected points from ACE FlightDeck by default
    - Checks for existing SkySpark entities using haystackRef tags
    - Creates new entities or updates existing ones
    - Maintains idempotency by storing SkySpark IDs back to ACE

    RESILIENT SYNC (v0.7.11+):
    - Refs are stored after EACH successful batch (not at end)
    - Continues processing even if a batch fails
    - Safe to re-run after errors - already-synced points are skipped
    - Run sync-refs-from-skyspark to recover orphaned points from old failures

    By default, only configured points (with collect_enabled=True) are synced.
    Use --sync-all to include all discovered points.

    Examples:
        ace-skyspark-cli sync --site "Building A"
        ace-skyspark-cli sync --site "Building A" --dry-run
        ace-skyspark-cli sync --site "Building A" --limit 10
        ace-skyspark-cli sync --site "Building A" --sync-all
        ace-skyspark-cli sync --site "Building A" --batch-size 1000

    Recovery from failures:
        # If sync fails mid-run, re-running is safe (already-synced batches are skipped)
        ace-skyspark-cli sync --site "Building A"

        # To recover orphaned points from old failures (before v0.7.11):
        ace-skyspark-cli sync-refs-from-skyspark --site "Building A"
    """
    if not logger:
        click.echo("Logger not initialized", err=True)
        sys.exit(1)

    logger.info("sync_command_start", site=site, dry_run=dry_run, limit=limit, sync_all=sync_all, batch_size=batch_size)

    try:
        # Run async sync operation
        asyncio.run(_run_sync(config, site, dry_run, limit, sync_all, batch_size))
    except KeyboardInterrupt:
        logger.warning("sync_interrupted")
        sys.exit(130)
    except Exception as e:
        logger.error("sync_failed", error=str(e), exc_info=True)
        sys.exit(1)


async def _run_sync(
    config: Config,
    site: str,
    dry_run: bool,
    limit: int | None = None,
    sync_all: bool = False,
    batch_size: int | None = None,
) -> None:
    """Run the synchronization operation.

    Args:
        config: Application configuration
        site: Site name to synchronize
        dry_run: If True, don't make any changes
        limit: Maximum number of points to sync (sorted by name)
        sync_all: If True, sync all points including non-collected
        batch_size: Override batch size for SkySpark operations
    """
    # Import at runtime to avoid circular import issues
    from ace_skyspark_cli.sync import PointSyncService

    if not logger:
        raise RuntimeError("Logger not initialized")

    # Override batch size if provided
    if batch_size is not None:
        logger.info("batch_size_override", default=config.app.batch_size, override=batch_size)
        config.app.batch_size = batch_size

    # Create clients with proper session management
    async with create_clients(config) as (ace_client, skyspark_client):
        # Create sync service
        sync_service = PointSyncService(
            ace_client=ace_client,
            skyspark_client=skyspark_client,
            config=config,
        )

        # Run synchronization
        result = await sync_service.sync_points_for_site(
            site, dry_run=dry_run, limit=limit, sync_all=sync_all
        )

        # Log results
        logger.info("sync_complete", result=result.to_dict())

        # Display summary
        click.echo("\nSynchronization Results:")
        click.echo(f"  Batch Size: {config.app.batch_size}")
        if limit is not None:
            click.echo(f"  Limit Applied: Processing {limit} of available points (sorted by name)")
        click.echo(f"  Sites Created: {result.sites_created}")
        click.echo(f"  Sites Skipped: {result.sites_skipped}")
        click.echo(f"  Equipment Created: {result.equipment_created}")
        click.echo(f"  Equipment Updated: {result.equipment_updated}")
        click.echo(f"  Equipment Skipped: {result.equipment_skipped}")
        click.echo(f"  Points Created: {result.points_created}")
        click.echo(f"  Points Updated: {result.points_updated}")
        click.echo(f"  Points Skipped: {result.points_skipped}")

        if result.errors:
            click.echo(f"\nErrors ({len(result.errors)}):")
            for error in result.errors[:10]:  # Show first 10 errors
                click.echo(f"  - {error}")
            if len(result.errors) > 10:
                click.echo(f"  ... and {len(result.errors) - 10} more errors")


@cli.command()
@click.option(
    "--site",
    required=False,
    help="Optional site filter (only sync refs for points from this site)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Perform a dry run without making changes",
)
@click.pass_obj
def sync_refs_from_skyspark(config: Config, site: str | None, dry_run: bool) -> None:
    """Sync refs from SkySpark back to ACE FlightDeck.

    This command:
    - Reads points from SkySpark that have ace_topic tags
    - Extracts the SkySpark refs (id, siteRef, equipRef)
    - Writes them back to ACE FlightDeck as KV tags
    - Useful for initial setup or re-syncing lost refs

    Examples:
        ace-skyspark-cli sync-refs-from-skyspark
        ace-skyspark-cli sync-refs-from-skyspark --site "Building A"
        ace-skyspark-cli sync-refs-from-skyspark --dry-run
    """
    if not logger:
        click.echo("Logger not initialized", err=True)
        sys.exit(1)

    logger.info("sync_refs_from_skyspark_start", site=site, dry_run=dry_run)

    try:
        # Run async sync operation
        asyncio.run(_run_sync_refs_from_skyspark(config, site, dry_run))
    except KeyboardInterrupt:
        logger.warning("sync_refs_interrupted")
        sys.exit(130)
    except Exception as e:
        logger.error("sync_refs_failed", error=str(e), exc_info=True)
        sys.exit(1)


async def _run_sync_refs_from_skyspark(
    config: Config,
    site: str | None = None,
    dry_run: bool = False,
) -> None:
    """Run the sync refs from SkySpark operation.

    Args:
        config: Application configuration
        site: Optional site filter
        dry_run: If True, don't make any changes
    """
    # Import at runtime to avoid circular import issues
    from ace_skyspark_cli.sync import PointSyncService

    if not logger:
        raise RuntimeError("Logger not initialized")

    # Create clients with proper session management
    async with create_clients(config) as (ace_client, skyspark_client):
        # Create sync service
        sync_service = PointSyncService(
            ace_client=ace_client,
            skyspark_client=skyspark_client,
            config=config,
        )

        # Run reverse sync
        result = await sync_service.sync_refs_from_skyspark(site=site, dry_run=dry_run)

        # Log results
        logger.info("sync_refs_complete", **result)

        # Display summary
        click.echo("\nSync Refs from SkySpark Results:")
        click.echo(f"  Points Found: {result['points_found']}")
        click.echo(f"  Refs Updated: {result['refs_updated']}")
        click.echo(f"  Points Skipped: {result['points_skipped']}")

        if result.get("errors"):
            click.echo(f"\nErrors ({len(result['errors'])}):")
            for error in result["errors"][:10]:  # Show first 10 errors
                click.echo(f"  - {error}")
            if len(result["errors"]) > 10:
                click.echo(f"  ... and {len(result['errors']) - 10} more errors")


async def _run_write_history(
    config: Config,
    site: str,
    start: str,
    end: str,
    limit: int | None = None,
    chunk_size: int = 1000,
    dry_run: bool = False,
) -> None:
    """Run the write history operation.

    Args:
        config: Application configuration
        site: Site name to write history for
        start: Start time (ISO format)
        end: End time (ISO format)
        limit: Optional limit on number of points to process
        chunk_size: Number of samples per write chunk
        dry_run: If True, don't write data
    """
    # Import at runtime to avoid circular import issues
    from ace_skyspark_cli.sync import PointSyncService

    if not logger:
        raise RuntimeError("Logger not initialized")

    # Create clients with proper session management
    async with create_clients(config) as (ace_client, skyspark_client):
        # Create sync service
        sync_service = PointSyncService(
            ace_client=ace_client,
            skyspark_client=skyspark_client,
            config=config,
        )

        # Run write history
        result = await sync_service.write_history(
            site=site,
            start_time=start,
            end_time=end,
            limit=limit,
            chunk_size=chunk_size,
            dry_run=dry_run,
        )

        # Display summary
        click.echo("\nWrite History Results:")
        click.echo(f"  Points Processed: {result['points_processed']}")
        click.echo(f"  Samples Read: {result['samples_read']}")
        click.echo(f"  Samples Written: {result['samples_written']}")
        click.echo(f"  Points Skipped: {result['points_skipped']}")
        click.echo(f"  Chunks Written: {result['chunks_written']}")

        if result.get("errors"):
            click.echo(f"\nErrors ({len(result['errors'])}):")
            for error in result["errors"][:10]:  # Show first 10 errors
                click.echo(f"  - {error}")
            if len(result["errors"]) > 10:
                click.echo(f"  ... and {len(result['errors']) - 10} more errors")


async def _run_debug_project_tz(config: Config) -> None:
    """Debug project timezone detection.

    Args:
        config: Application configuration
    """
    import json

    if not logger:
        raise RuntimeError("Logger not initialized")

    # Create clients with proper session management
    async with create_clients(config) as (ace_client, skyspark_client):
        # 1. Check what the about endpoint returns via session manager
        click.echo("\n=== About Endpoint ===")
        try:
            # Access the private session manager for debugging
            if skyspark_client._session_manager:
                about_response = await skyspark_client._session_manager.get_json("about")
                click.echo(json.dumps(about_response, indent=2))
            else:
                click.echo("Session manager not available")
        except Exception as e:
            click.echo(f"Error: {e}")

        # 2. Try to get timezone using current method
        click.echo("\n=== Current get_project_timezone() Result ===")
        try:
            current_tz = await skyspark_client.get_project_timezone()
            click.echo(f"Detected timezone: {current_tz}")
        except Exception as e:
            click.echo(f"Error: {e}")

        # 3. Read the project entity itself
        click.echo("\n=== Project Entity (using filter: 'proj') ===")
        try:
            project_entities = await skyspark_client.read("proj")
            if project_entities:
                click.echo(f"Found {len(project_entities)} project entities")
                for proj in project_entities:
                    click.echo(f"\nProject: {proj.get('dis', 'unknown')}")
                    click.echo(f"  ID: {proj.get('id', 'N/A')}")
                    click.echo(f"  tz field: {proj.get('tz', 'N/A')}")
                    click.echo(f"  All fields: {json.dumps(proj, indent=4, default=str)}")
            else:
                click.echo("No project entities found with filter 'proj'")
        except Exception as e:
            click.echo(f"Error reading project: {e}")


async def _run_check_timezones(
    config: Config,
    site_filter: str | None = None,
    fix: bool = False,
    dry_run: bool = False,
) -> None:
    """Check timezone consistency between sites and their points.

    Args:
        config: Application configuration
        site_filter: Optional site name to filter
        fix: If True, warn about fixing (not actually supported)
        dry_run: If True, don't make any changes
    """
    if not logger:
        raise RuntimeError("Logger not initialized")

    # Create clients with proper session management
    async with create_clients(config) as (ace_client, skyspark_client):
        # Read all sites
        all_sites = await skyspark_client.read_sites()
        logger.info("sites_fetched", count=len(all_sites))

        # Build site timezone map
        site_tz_map = {}
        for site in all_sites:
            site_id = site.get("id", {})
            if isinstance(site_id, dict):
                site_id_val = site_id.get("val", "").lstrip("@")
            else:
                site_id_val = str(site_id).lstrip("@")

            site_tz = site.get("tz", "UTC")
            site_tz_map[site_id_val] = {
                "tz": site_tz,
                "dis": site.get("dis", ""),
                "refName": site.get("refName", ""),
            }

        # Read all points
        all_points = await skyspark_client.read_points()
        logger.info("points_fetched", count=len(all_points))

        # Filter by site if specified
        if site_filter:
            # Find site ID by refName or dis
            site_id_filter = None
            for site_id, site_info in site_tz_map.items():
                if site_info["refName"] == f"ace-site-{site_filter}" or site_info["dis"] == site_filter:
                    site_id_filter = site_id
                    break

            if site_id_filter:
                filtered_points = []
                for p in all_points:
                    site_ref = p.get("siteRef")
                    if isinstance(site_ref, dict):
                        site_ref_val = site_ref.get("val", "").lstrip("@")
                    else:
                        site_ref_val = str(site_ref).lstrip("@") if site_ref else ""
                    if site_ref_val == site_id_filter:
                        filtered_points.append(p)
                all_points = filtered_points
                click.echo(f"\nFiltered to site: {site_filter}")
            else:
                click.echo(f"\nWarning: Site '{site_filter}' not found")
                return

        # Helper function to extract ref values
        def get_ref_val(ref: Any) -> str:
            if isinstance(ref, dict):
                return ref.get("val", "").lstrip("@")
            return str(ref).lstrip("@") if ref else ""

        # Check for timezone mismatches
        mismatches_by_site = {}
        points_by_site = {}
        timezone_counts = {}

        for point in all_points:
            point_tz = point.get("tz", "")
            point_site_ref = get_ref_val(point.get("siteRef"))

            # Track counts
            timezone_counts[point_tz] = timezone_counts.get(point_tz, 0) + 1
            points_by_site[point_site_ref] = points_by_site.get(point_site_ref, 0) + 1

            # Get expected timezone from site
            site_info = site_tz_map.get(point_site_ref, {})
            expected_tz = site_info.get("tz", "UTC")
            site_dis = site_info.get("dis", point_site_ref)

            # Check if timezone doesn't match site timezone
            if point_tz != expected_tz:
                if point_site_ref not in mismatches_by_site:
                    mismatches_by_site[point_site_ref] = {
                        "site_dis": site_dis,
                        "site_tz": expected_tz,
                        "points": []
                    }

                point_id = get_ref_val(point.get("id"))
                mismatches_by_site[point_site_ref]["points"].append({
                    "id": point_id,
                    "dis": point.get("dis", ""),
                    "refName": point.get("refName", ""),
                    "current_tz": point_tz,
                })

        # Display results
        click.echo(f"\nTotal Sites: {len(all_sites)}")
        click.echo(f"Total Points: {len(all_points)}")
        click.echo("\nTimezone Distribution:")
        for tz, count in sorted(timezone_counts.items(), key=lambda x: x[1], reverse=True):
            click.echo(f"  {tz}: {count} points")

        if mismatches_by_site:
            total_mismatches = sum(len(info["points"]) for info in mismatches_by_site.values())
            click.echo(f"\n⚠️  Found {total_mismatches} points with timezone mismatch across {len(mismatches_by_site)} sites")

            for site_ref, info in mismatches_by_site.items():
                click.echo(f"\n  Site: {info['site_dis']} (tz={info['site_tz']})")
                click.echo(f"  Mismatched points: {len(info['points'])}")

                # Show first 5 points per site
                for point in info['points'][:5]:
                    click.echo(f"    - {point['dis']} (tz={point['current_tz']})")

                if len(info['points']) > 5:
                    click.echo(f"    ... and {len(info['points']) - 5} more")

            click.echo(f"\n⚠️  IMPORTANT: SkySpark does NOT allow updating the 'tz' field on existing points.")
            click.echo("The 'tz' field is immutable after point creation.")
            click.echo("\nTo fix this, you would need to:")
            click.echo("  1. Delete the points with incorrect timezone (⚠️ LOSES HISTORICAL DATA)")
            click.echo("  2. Re-create them with correct timezone via sync command")
            click.echo("\nThe timezone IS stored in ACE FlightDeck KV tags ('tz' and 'skysparkTz')")
            click.echo("for reference, even if SkySpark point has wrong timezone.")
        else:
            click.echo("\n✓ All points have timezone matching their site!")


@cli.command()
@click.option("--site", required=True, help="Site name to write history for")
@click.option(
    "--start",
    required=True,
    help="Start time (ISO format: 2025-11-01T00:00:00Z or 2025-11-01)",
)
@click.option(
    "--end",
    required=True,
    help="End time (ISO format: 2025-11-01T23:59:59Z or 2025-11-01)",
)
@click.option("--limit", type=int, default=None, help="Limit number of points to process")
@click.option("--chunk-size", type=int, default=1000, help="Number of samples per write chunk (default: 1000)")
@click.option("--dry-run", is_flag=True, help="Show what would be written without writing")
@click.pass_obj
def write_history(
    config: Config,
    site: str,
    start: str,
    end: str,
    limit: int | None,
    chunk_size: int,
    dry_run: bool,
) -> None:
    """Write historical timeseries data from ACE to SkySpark.

    This command:
    - Reads timeseries data from ACE FlightDeck for the specified time range
    - Maps point names to SkySpark IDs using haystack_entityRef tags
    - Writes the data to SkySpark history (his) in chunks
    - Requires points to be synced first (run sync command)

    Examples:
        ace-skyspark-cli write-history --site "Building A" --start 2025-11-01 --end 2025-11-02
        ace-skyspark-cli write-history --site "Building A" --start 2025-11-01T00:00:00Z --end 2025-11-01T23:59:59Z
        ace-skyspark-cli write-history --site "Building A" --start 2025-11-01 --end 2025-11-02 --limit 10
        ace-skyspark-cli write-history --site "Building A" --start 2025-11-01 --end 2025-11-02 --dry-run
    """
    if not logger:
        click.echo("Logger not initialized", err=True)
        sys.exit(1)

    logger.info(
        "write_history_command_start",
        site=site,
        start=start,
        end=end,
        limit=limit,
        chunk_size=chunk_size,
        dry_run=dry_run,
    )

    try:
        # Run async write history operation
        asyncio.run(_run_write_history(config, site, start, end, limit, chunk_size, dry_run))
    except KeyboardInterrupt:
        logger.warning("write_history_interrupted")
        sys.exit(130)
    except Exception as e:
        logger.error("write_history_failed", error=str(e), exc_info=True)
        sys.exit(1)


@cli.command()
@click.pass_obj
def debug_project_tz(config: Config) -> None:
    """Debug project timezone detection.

    Shows what the about endpoint returns and what the project entity's tz tag is.

    Examples:
        ace-skyspark-cli debug-project-tz
    """
    if not logger:
        click.echo("Logger not initialized", err=True)
        sys.exit(1)

    logger.info("debug_project_tz_start")

    try:
        asyncio.run(_run_debug_project_tz(config))
    except KeyboardInterrupt:
        logger.warning("debug_project_tz_interrupted")
        sys.exit(130)
    except Exception as e:
        logger.error("debug_project_tz_failed", error=str(e), exc_info=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--site",
    required=False,
    help="Check specific site (default: check all sites)",
)
@click.option(
    "--fix",
    is_flag=True,
    help="Fix timezone inconsistencies by updating points",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be fixed without making changes",
)
@click.pass_obj
def check_timezones(config: Config, site: str | None, fix: bool, dry_run: bool) -> None:
    """Check for timezone inconsistencies in SkySpark points.

    This command:
    - Reads all sites and points from SkySpark
    - Compares each point's tz field with its site's tz field
    - Reports any mismatches
    - Note: SkySpark doesn't allow updating tz field on existing points

    Examples:
        ace-skyspark-cli check-timezones
        ace-skyspark-cli check-timezones --site "Building A"
    """
    if not logger:
        click.echo("Logger not initialized", err=True)
        sys.exit(1)

    logger.info("check_timezones_start", site=site, fix=fix, dry_run=dry_run)

    try:
        asyncio.run(_run_check_timezones(config, site, fix, dry_run))
    except KeyboardInterrupt:
        logger.warning("check_timezones_interrupted")
        sys.exit(130)
    except Exception as e:
        logger.error("check_timezones_failed", error=str(e), exc_info=True)
        sys.exit(1)


@cli.command()
@click.pass_obj
def version(config: Config) -> None:
    """Display version information."""
    click.echo(f"ACE SkySpark CLI v{__version__}")
    click.echo("\nConfiguration:")
    click.echo(f"  FlightDeck URL: {config.flightdeck.api_url}")
    click.echo(f"  SkySpark URL: {config.skyspark.url}")
    click.echo(f"  SkySpark Project: {config.skyspark.project}")


@cli.command()
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing .env file",
)
def init(force: bool) -> None:
    """Initialize a new .env configuration file.

    Creates a template .env file with all required configuration variables.

    Examples:
        ace-skyspark-cli init
        ace-skyspark-cli init --force
    """
    from pathlib import Path

    env_file = Path(".env")

    # Check if file exists
    if env_file.exists() and not force:
        click.echo(f"Error: {env_file} already exists. Use --force to overwrite.", err=True)
        sys.exit(1)

    # Template .env content
    template = """# ACE SkySpark CLI Configuration
# Generated by: ace-skyspark-cli init

# FlightDeck Configuration
FLIGHTDECK_USER=your-email@example.com
FLIGHTDECK_JWT=your-jwt-token-here
FLIGHTDECK_SITE=your-site-name
FLIGHTDECK_API_URL=https://flightdeck.aceiot.cloud/api

# SkySpark Configuration
SKYSPARK_URL=http://your-skyspark-server:8080
SKYSPARK_PROJECT=your-project-name
SKYSPARK_USER=your-username
SKYSPARK_PASSWORD=your-password

# Optional: Application Settings
# ACE_SKYSPARK_CLI_LOG_LEVEL=INFO
# ACE_SKYSPARK_CLI_BATCH_SIZE=100
# ACE_SKYSPARK_CLI_DRY_RUN=false
"""

    try:
        with env_file.open("w") as f:
            f.write(template)

        click.echo(f"✓ Created {env_file}")
        click.echo("\nNext steps:")
        click.echo("  1. Edit .env and add your credentials")
        click.echo("  2. Run: ace-skyspark-cli version  (to verify configuration)")
        click.echo("  3. Run: ace-skyspark-cli sync --site <site-name> --dry-run")
    except Exception as e:
        click.echo(f"Error creating {env_file}: {e}", err=True)
        sys.exit(1)


def main() -> None:
    """Main entry point for CLI."""
    cli()
