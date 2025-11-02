# ACE SkySpark CLI

[![CI](https://github.com/ACE-IoT-Solutions/ace-skyspark-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/ACE-IoT-Solutions/ace-skyspark-cli/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/ace-skyspark-cli.svg)](https://badge.fury.io/py/ace-skyspark-cli)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)

CLI tool for synchronizing points, equipment, and entities from ACE FlightDeck to SkySpark with idempotent operations and haystack tag management.

## Features

- **Idempotent Synchronization** - Safe to run multiple times, creates or updates entities as needed
- **Haystack Ref Tracking** - Uses `haystackRef` tags to maintain relationships between ACE and SkySpark
- **Resilient Operations** - Continues processing even if individual batches fail
- **Batch Processing** - Configurable batch sizes for optimal performance
- **Historical Data Sync** - Write historical timeseries data from ACE to SkySpark
- **Job Configuration Files** - YAML/JSON job files for reusable configurations
- **Flexible Credential Management** - CLI args, job files, or environment variables
- **Timezone Validation** - Check and report timezone inconsistencies

## Installation

```bash
pip install ace-skyspark-cli
```

## Quick Start

### Initialize Configuration

```bash
ace-skyspark-cli init
```

Edit the generated `.env` file with your credentials:

```bash
FLIGHTDECK_JWT=your-jwt-token
FLIGHTDECK_API_URL=https://flightdeck.aceiot.cloud/api
SKYSPARK_URL=http://localhost:8080/api
SKYSPARK_PROJECT=myProject
SKYSPARK_USER=admin
SKYSPARK_PASSWORD=secret
```

### Sync Points to SkySpark

```bash
# Sync configured points for a site
ace-skyspark-cli sync --site "Building A"

# Dry run to see what would be synced
ace-skyspark-cli sync --site "Building A" --dry-run

# Sync all points (including non-configured)
ace-skyspark-cli sync --site "Building A" --sync-all

# Limit sync to first 10 points
ace-skyspark-cli sync --site "Building A" --limit 10
```

### Write Historical Data

```bash
# Write historical data for a date range
ace-skyspark-cli write-history --site "Building A" \
  --start 2025-11-01 \
  --end 2025-11-02

# With custom chunk size
ace-skyspark-cli write-history --site "Building A" \
  --start 2025-11-01T00:00:00Z \
  --end 2025-11-01T23:59:59Z \
  --chunk-size 5000
```

### Sync Refs from SkySpark

```bash
# Sync haystack refs back to ACE FlightDeck
ace-skyspark-cli sync-refs-from-skyspark

# For specific site only
ace-skyspark-cli sync-refs-from-skyspark --site "Building A"
```

## Job Configuration Files

Generate and use job configuration files for complex workflows:

```bash
# Generate template for all commands
ace-skyspark-cli generate-job-template

# Generate template for specific command
ace-skyspark-cli generate-job-template --command sync --output sync-job.yaml

# Use job file
ace-skyspark-cli sync --job-file sync-job.yaml

# Override job file parameters
ace-skyspark-cli sync --job-file sync-job.yaml --limit 50 --dry-run
```

Example job file:

```yaml
credentials:
  flightdeck_jwt: your-jwt-token
  skyspark_url: http://localhost:8080/api
  skyspark_project: myProject
  skyspark_user: admin
  skyspark_password: secret

sync:
  site: Building A
  dry_run: false
  limit: null
  sync_all: false
  batch_size: 500
```

See [Job Configuration Guide](JOB_CONFIG_GUIDE.md) for complete documentation.

## Commands

### `sync`
Synchronize points from FlightDeck to SkySpark for a specific site.

**Options:**
- `--site TEXT` - Site name to synchronize (required)
- `--dry-run` - Perform dry run without making changes
- `--limit INT` - Limit number of points to sync
- `--sync-all` - Sync all points including non-configured
- `--batch-size INT` - Override batch size
- `--job-file PATH` - Load parameters from job file

### `write-history`
Write historical timeseries data from ACE to SkySpark.

**Options:**
- `--site TEXT` - Site name (required)
- `--start TEXT` - Start time in ISO format (required)
- `--end TEXT` - End time in ISO format (required)
- `--limit INT` - Limit number of points to process
- `--chunk-size INT` - Samples per write chunk (default: 1000)
- `--dry-run` - Show what would be written
- `--job-file PATH` - Load parameters from job file

### `sync-refs-from-skyspark`
Sync haystack refs from SkySpark back to ACE FlightDeck.

**Options:**
- `--site TEXT` - Optional site filter
- `--dry-run` - Perform dry run
- `--job-file PATH` - Load parameters from job file

### `check-timezones`
Check for timezone inconsistencies in SkySpark points.

**Options:**
- `--site TEXT` - Check specific site
- `--dry-run` - Dry run mode
- `--job-file PATH` - Load parameters from job file

### `generate-job-template`
Generate job configuration file templates.

**Options:**
- `--command TEXT` - Command to generate template for (sync, write-history, etc.)
- `--output PATH` - Output file path
- `--format TEXT` - Output format (yaml or json)
- `--force` - Overwrite existing file

### `init`
Initialize a new `.env` configuration file.

### `version`
Display version and configuration information.

## Credential Management

Credentials can be provided via three methods (in order of precedence):

1. **CLI Arguments** - Global flags like `--flightdeck-jwt`, `--skyspark-user`
2. **Job Files** - In the `credentials` section
3. **Environment Variables** - From `.env` file

Example using CLI arguments:

```bash
ace-skyspark-cli --flightdeck-jwt "new-token" \
                 --skyspark-project "production" \
                 sync --site "Building A"
```

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/ACE-IoT-Solutions/ace-skyspark-cli.git
cd ace-skyspark-cli

# Install with development dependencies
uv sync --all-extras --group dev
```

### Run Tests

```bash
# Run unit tests
uv run pytest -m unit

# Run integration tests (requires FlightDeck and SkySpark)
uv run pytest -m integration

# Run all tests with coverage
uv run pytest --cov=ace_skyspark_cli
```

### Linting and Type Checking

```bash
# Run linting
uv run ruff check .
uv run ruff format .

# Run type checking
uv run pyrefly check src tests
```

## Architecture

### Key Features

- **Idempotent Operations** - Uses `haystackRef` tags to track existing entities
- **Batch Processing** - Processes points in configurable batches for efficiency
- **Resilient Sync** - Stores refs after each successful batch, safe to re-run
- **Session Management** - Proper async lifecycle management for clients
- **Structured Logging** - JSON-formatted logs with structured data

### Data Flow

1. **Sync Command**
   - Fetch points from ACE FlightDeck API
   - Check for existing SkySpark entities using `haystackRef` tags
   - Create new entities or update existing ones
   - Store SkySpark refs back to ACE as KV tags

2. **Write History Command**
   - Read timeseries data from ACE FlightDeck
   - Map point names to SkySpark IDs using `haystack_entityRef` tags
   - Write data to SkySpark history in chunks

3. **Sync Refs Command**
   - Read points from SkySpark with `ace_topic` tags
   - Extract SkySpark refs (id, siteRef, equipRef)
   - Write refs back to ACE FlightDeck as KV tags

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please open an issue or pull request.

## Support

- **Issues**: [GitHub Issues](https://github.com/ACE-IoT-Solutions/ace-skyspark-cli/issues)
- **Documentation**: [Job Configuration Guide](JOB_CONFIG_GUIDE.md)
