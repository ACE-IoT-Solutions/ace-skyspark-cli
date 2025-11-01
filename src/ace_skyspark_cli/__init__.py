"""ACE SkySpark CLI - Sync points from FlightDeck to SkySpark."""

import asyncio
import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

import click
import structlog
from ace_skyspark_lib import SkysparkClient

from ace_skyspark_cli.config import Config
from ace_skyspark_cli.logging import configure_logging, get_logger, log_config

if TYPE_CHECKING:
    from ace_skyspark_cli.sync import PointSyncService

__version__ = "0.7.12"

logger: Any = None


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
@click.pass_obj
def sync(config: Config, site: str, dry_run: bool, limit: int | None, sync_all: bool) -> None:
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

    Recovery from failures:
        # If sync fails mid-run, re-running is safe (already-synced batches are skipped)
        ace-skyspark-cli sync --site "Building A"

        # To recover orphaned points from old failures (before v0.7.11):
        ace-skyspark-cli sync-refs-from-skyspark --site "Building A"
    """
    if not logger:
        click.echo("Logger not initialized", err=True)
        sys.exit(1)

    logger.info("sync_command_start", site=site, dry_run=dry_run, limit=limit, sync_all=sync_all)

    try:
        # Run async sync operation
        asyncio.run(_run_sync(config, site, dry_run, limit, sync_all))
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
) -> None:
    """Run the synchronization operation.

    Args:
        config: Application configuration
        site: Site name to synchronize
        dry_run: If True, don't make any changes
        limit: Maximum number of points to sync (sorted by name)
        sync_all: If True, sync all points including non-collected
    """
    # Import at runtime to avoid circular import issues
    from aceiot_models.api import APIClient
    from ace_skyspark_cli.sync import PointSyncService

    if not logger:
        raise RuntimeError("Logger not initialized")

    # Create API clients - use sync client for now since async isn't available
    ace_client = APIClient(
        base_url=config.flightdeck.api_url,
        api_key=config.flightdeck.jwt,
        timeout=config.flightdeck.timeout,
    )

    async with SkysparkClient(
        base_url=config.skyspark.url,
        project=config.skyspark.project,
        username=config.skyspark.user,
        password=config.skyspark.password,
        timeout=config.skyspark.timeout,
        max_retries=config.skyspark.max_retries,
        pool_size=config.skyspark.pool_size,
    ) as skyspark_client:
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
    from aceiot_models.api import APIClient
    from ace_skyspark_cli.sync import PointSyncService

    if not logger:
        raise RuntimeError("Logger not initialized")

    # Create API clients
    ace_client = APIClient(
        base_url=config.flightdeck.api_url,
        api_key=config.flightdeck.jwt,
        timeout=config.flightdeck.timeout,
    )

    async with SkysparkClient(
        base_url=config.skyspark.url,
        project=config.skyspark.project,
        username=config.skyspark.user,
        password=config.skyspark.password,
        timeout=config.skyspark.timeout,
        max_retries=config.skyspark.max_retries,
        pool_size=config.skyspark.pool_size,
    ) as skyspark_client:
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
