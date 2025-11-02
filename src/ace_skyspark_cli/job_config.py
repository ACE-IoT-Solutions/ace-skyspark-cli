"""Job configuration management for ACE SkySpark CLI.

This module provides a unified way to manage parameters through:
- Environment variables
- CLI arguments
- Job configuration files (YAML/JSON)

Precedence: CLI args > Job file > Environment variables > Defaults
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class SyncJobConfig(BaseModel):
    """Configuration for sync command."""

    site: str = Field(..., description="Site name to synchronize")
    dry_run: bool = Field(default=False, description="Perform dry run without making changes")
    limit: int | None = Field(
        default=None, description="Limit number of points to sync (sorted by name)"
    )
    sync_all: bool = Field(
        default=False,
        description="Sync all points including non-configured (default: only configured)",
    )
    batch_size: int | None = Field(
        default=None, description="Override batch size for SkySpark operations"
    )

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int | None) -> int | None:
        """Validate limit is positive."""
        if v is not None and v <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        return v

    @field_validator("batch_size")
    @classmethod
    def validate_batch_size(cls, v: int | None) -> int | None:
        """Validate batch_size is positive."""
        if v is not None and v <= 0:
            msg = "batch_size must be positive"
            raise ValueError(msg)
        return v


class SyncRefsJobConfig(BaseModel):
    """Configuration for sync-refs-from-skyspark command."""

    site: str | None = Field(
        default=None, description="Optional site filter (only sync refs for this site)"
    )
    dry_run: bool = Field(default=False, description="Perform dry run without making changes")


class WriteHistoryJobConfig(BaseModel):
    """Configuration for write-history command."""

    site: str = Field(..., description="Site name to write history for")
    start: str = Field(..., description="Start time (ISO format: 2025-11-01T00:00:00Z or 2025-11-01)")
    end: str = Field(..., description="End time (ISO format: 2025-11-01T23:59:59Z or 2025-11-01)")
    limit: int | None = Field(default=None, description="Limit number of points to process")
    chunk_size: int = Field(default=1000, description="Number of samples per write chunk")
    dry_run: bool = Field(default=False, description="Show what would be written without writing")

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int | None) -> int | None:
        """Validate limit is positive."""
        if v is not None and v <= 0:
            msg = "limit must be positive"
            raise ValueError(msg)
        return v

    @field_validator("chunk_size")
    @classmethod
    def validate_chunk_size(cls, v: int) -> int:
        """Validate chunk_size is positive."""
        if v <= 0:
            msg = "chunk_size must be positive"
            raise ValueError(msg)
        return v


class CheckTimezonesJobConfig(BaseModel):
    """Configuration for check-timezones command."""

    site: str | None = Field(default=None, description="Check specific site (default: check all)")
    fix: bool = Field(default=False, description="Fix timezone inconsistencies (not supported)")
    dry_run: bool = Field(default=False, description="Show what would be fixed without changes")


class JobFile(BaseModel):
    """Job file containing multiple job configurations."""

    sync: SyncJobConfig | None = Field(default=None, description="Sync job configuration")
    sync_refs: SyncRefsJobConfig | None = Field(
        default=None, description="Sync refs job configuration"
    )
    write_history: WriteHistoryJobConfig | None = Field(
        default=None, description="Write history job configuration"
    )
    check_timezones: CheckTimezonesJobConfig | None = Field(
        default=None, description="Check timezones job configuration"
    )

    @classmethod
    def from_file(cls, file_path: str | Path) -> "JobFile":
        """Load job configuration from YAML or JSON file.

        Args:
            file_path: Path to job configuration file

        Returns:
            JobFile instance

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        path = Path(file_path)
        if not path.exists():
            msg = f"Job file not found: {file_path}"
            raise FileNotFoundError(msg)

        with path.open() as f:
            if path.suffix in {".yaml", ".yml"}:
                data = yaml.safe_load(f)
            elif path.suffix == ".json":
                import json

                data = json.load(f)
            else:
                msg = f"Unsupported file format: {path.suffix}. Use .yaml, .yml, or .json"
                raise ValueError(msg)

        return cls.model_validate(data)

    def to_file(self, file_path: str | Path, format: str = "yaml") -> None:
        """Write job configuration to file.

        Args:
            file_path: Path to write configuration to
            format: File format ('yaml' or 'json')
        """
        path = Path(file_path)
        data = self.model_dump(exclude_none=True, mode="json")

        with path.open("w") as f:
            if format == "yaml":
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
            elif format == "json":
                import json

                json.dump(data, f, indent=2)
            else:
                msg = f"Unsupported format: {format}. Use 'yaml' or 'json'"
                raise ValueError(msg)


def generate_sync_template() -> dict[str, Any]:
    """Generate template for sync job configuration.

    Returns:
        Dictionary with sync job template
    """
    return {
        "sync": {
            "site": "my-site-name",
            "dry_run": False,
            "limit": None,
            "sync_all": False,
            "batch_size": None,
        }
    }


def generate_sync_refs_template() -> dict[str, Any]:
    """Generate template for sync-refs job configuration.

    Returns:
        Dictionary with sync-refs job template
    """
    return {"sync_refs": {"site": None, "dry_run": False}}


def generate_write_history_template() -> dict[str, Any]:
    """Generate template for write-history job configuration.

    Returns:
        Dictionary with write-history job template
    """
    return {
        "write_history": {
            "site": "my-site-name",
            "start": "2025-11-01T00:00:00Z",
            "end": "2025-11-01T23:59:59Z",
            "limit": None,
            "chunk_size": 1000,
            "dry_run": False,
        }
    }


def generate_check_timezones_template() -> dict[str, Any]:
    """Generate template for check-timezones job configuration.

    Returns:
        Dictionary with check-timezones job template
    """
    return {"check_timezones": {"site": None, "fix": False, "dry_run": False}}


def generate_full_template() -> dict[str, Any]:
    """Generate template with all job configurations.

    Returns:
        Dictionary with all job templates
    """
    return {
        **generate_sync_template(),
        **generate_sync_refs_template(),
        **generate_write_history_template(),
        **generate_check_timezones_template(),
    }
