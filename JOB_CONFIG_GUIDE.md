# Job Configuration Guide

## Overview

ACE SkySpark CLI supports job configuration files for running commands with predefined parameters. This allows you to:

- **Store complex configurations** in version control
- **Reuse common parameter sets** across multiple runs
- **Schedule automated jobs** using cron or other schedulers
- **Document operational procedures** with working configurations

## Supported Formats

- **YAML** (recommended, human-readable)
- **JSON** (machine-friendly)

## Parameter Precedence

When using job files, parameters are resolved in this order (highest to lowest priority):

1. **CLI arguments** - Explicitly provided command-line options
2. **Job file** - Parameters from the loaded job configuration
3. **Environment variables** - From .env file or system environment
4. **Defaults** - Built-in default values

## Generating Templates

### Generate All Commands Template

```bash
ace-skyspark-cli generate-job-template
# Creates: job-config.yaml
```

### Generate Single Command Template

```bash
# Sync template
ace-skyspark-cli generate-job-template --command sync --output sync-job.yaml

# Write history template
ace-skyspark-cli generate-job-template --command write-history --output history-job.yaml

# Check timezones template
ace-skyspark-cli generate-job-template --command check-timezones --output tz-check-job.yaml
```

### Generate JSON Format

```bash
ace-skyspark-cli generate-job-template --format json --output job-config.json
```

## Job File Structure

### Complete Example (YAML)

```yaml
sync:
  site: my-site-name
  dry_run: false
  limit: null
  sync_all: false
  batch_size: 500

sync_refs:
  site: null  # Optional: filter by site
  dry_run: false

write_history:
  site: my-site-name
  start: '2025-11-01T00:00:00Z'
  end: '2025-11-01T23:59:59Z'
  limit: null
  chunk_size: 1000
  dry_run: false

check_timezones:
  site: null  # Optional: check specific site
  fix: false
  dry_run: false
```

### Complete Example (JSON)

```json
{
  "sync": {
    "site": "my-site-name",
    "dry_run": false,
    "limit": null,
    "sync_all": false,
    "batch_size": 500
  },
  "write_history": {
    "site": "my-site-name",
    "start": "2025-11-01T00:00:00Z",
    "end": "2025-11-01T23:59:59Z",
    "limit": null,
    "chunk_size": 1000,
    "dry_run": false
  }
}
```

## Using Job Files

### Basic Usage

```bash
# Use job file for sync
ace-skyspark-cli sync --job-file sync-job.yaml

# Use job file for write-history
ace-skyspark-cli write-history --job-file history-job.yaml
```

### Override Job File Parameters

CLI arguments always take precedence over job file values:

```bash
# Job file has limit: 100, override to 50
ace-skyspark-cli sync --job-file sync-job.yaml --limit 50

# Job file has dry_run: false, override to true
ace-skyspark-cli sync --job-file sync-job.yaml --dry-run

# Multiple overrides
ace-skyspark-cli sync --job-file sync-job.yaml --limit 10 --batch-size 200
```

## Command-Specific Parameters

### Sync Command

```yaml
sync:
  site: "Building A"          # Required: Site name
  dry_run: false              # Optional: Dry run mode (default: false)
  limit: null                 # Optional: Limit points to sync
  sync_all: false             # Optional: Sync all points (default: false, only configured)
  batch_size: null            # Optional: Override default batch size (default: 500)
```

**Usage:**
```bash
ace-skyspark-cli sync --job-file sync-job.yaml
ace-skyspark-cli sync --job-file sync-job.yaml --dry-run  # Override to dry run
```

### Sync Refs Command

```yaml
sync_refs:
  site: null                  # Optional: Filter by site (default: all sites)
  dry_run: false              # Optional: Dry run mode (default: false)
```

**Usage:**
```bash
ace-skyspark-cli sync-refs-from-skyspark --job-file refs-job.yaml
```

### Write History Command

```yaml
write_history:
  site: "Building A"          # Required: Site name
  start: "2025-11-01"         # Required: Start time (ISO format)
  end: "2025-11-02"           # Required: End time (ISO format)
  limit: null                 # Optional: Limit points to process
  chunk_size: 1000            # Optional: Samples per chunk (default: 1000)
  dry_run: false              # Optional: Dry run mode (default: false)
```

**Usage:**
```bash
ace-skyspark-cli write-history --job-file history-job.yaml
```

### Check Timezones Command

```yaml
check_timezones:
  site: null                  # Optional: Check specific site (default: all)
  fix: false                  # Optional: Attempt to fix (not supported, default: false)
  dry_run: false              # Optional: Dry run mode (default: false)
```

**Usage:**
```bash
ace-skyspark-cli check-timezones --job-file tz-check-job.yaml
```

## Practical Examples

### Daily Sync Job

```yaml
# daily-sync.yaml
sync:
  site: production-building
  dry_run: false
  sync_all: false
  batch_size: 1000
```

```bash
# In crontab:
0 2 * * * cd /path/to/project && ace-skyspark-cli sync --job-file daily-sync.yaml
```

### Historical Data Backfill

```yaml
# backfill-november.yaml
write_history:
  site: production-building
  start: "2025-11-01T00:00:00Z"
  end: "2025-11-30T23:59:59Z"
  chunk_size: 5000
  dry_run: false
```

```bash
ace-skyspark-cli write-history --job-file backfill-november.yaml
```

### Development Testing

```yaml
# test-sync.yaml
sync:
  site: test-building
  dry_run: true
  limit: 10
  sync_all: true
  batch_size: 50
```

```bash
# Quick test with limited points
ace-skyspark-cli sync --job-file test-sync.yaml

# Override limit for full test
ace-skyspark-cli sync --job-file test-sync.yaml --limit 100
```

## Validation

Job files are validated when loaded:

- **Required fields** must be present
- **Types** must match (string, integer, boolean)
- **Values** must be valid (e.g., positive integers for limits)

Example validation errors:

```bash
$ ace-skyspark-cli sync --job-file bad-job.yaml
Error loading job file: 1 validation error for JobFile
sync.limit
  Input should be a valid integer [type=int_type, input_value='not-a-number', input_type=str]
```

## Best Practices

1. **Version Control**: Store job files in git for auditability
2. **Descriptive Names**: Use clear filenames (e.g., `daily-sync-building-a.yaml`)
3. **Comments**: Add YAML comments to document purpose
4. **Testing**: Always test with `--dry-run` first
5. **Overrides**: Use CLI args for one-off changes rather than editing files
6. **Secrets**: Never store credentials in job files (use environment variables)

## Environment Variables

Job files work seamlessly with environment variables:

```bash
# .env file
FLIGHTDECK_JWT=your-jwt-token
FLIGHTDECK_API_URL=https://flightdeck.aceiot.cloud/api
SKYSPARK_URL=http://localhost:8080/api
SKYSPARK_PROJECT=myProject
SKYSPARK_USER=admin
SKYSPARK_PASSWORD=secret

# Job file references site name only
# sync-job.yaml
sync:
  site: building-a
  dry_run: false

# Credentials loaded from .env automatically
ace-skyspark-cli sync --job-file sync-job.yaml
```

## Troubleshooting

### Job file not found

```bash
Error loading job file: Job file not found: /path/to/job.yaml
```

**Solution**: Check file path and permissions

### Invalid format

```bash
Error loading job file: Unsupported file format: .txt. Use .yaml, .yml, or .json
```

**Solution**: Use `.yaml`, `.yml`, or `.json` extension

### Missing required field

```bash
Error: Job file does not contain 'sync' configuration
```

**Solution**: Ensure job file has the correct command section (e.g., `sync:`, `write_history:`)

### Validation error

```bash
Error loading job file: 1 validation error for JobFile
sync.batch_size
  Input should be greater than 0 [type=greater_than, input_value=-10]
```

**Solution**: Fix the invalid value in the job file
