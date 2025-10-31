"""Configuration management for ACE SkySpark CLI.

This module handles environment-based configuration without hardcoded values.
"""

import os
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FlightDeckConfig(BaseSettings):
    """FlightDeck (ACE API) configuration."""

    model_config = SettingsConfigDict(
        env_prefix="FLIGHTDECK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_url: str = Field(
        default="https://flightdeck.aceiot.cloud/api",
        description="FlightDeck API base URL",
    )
    jwt: str = Field(..., description="FlightDeck JWT authentication token")
    user: str | None = Field(None, description="FlightDeck user email")
    site: str | None = Field(None, description="Default site name for filtering")
    timeout: int = Field(default=30, description="API request timeout in seconds")

    @field_validator("jwt")
    @classmethod
    def validate_jwt(cls, v: str) -> str:
        """Validate JWT token is not empty."""
        if not v or not v.strip():
            msg = "FlightDeck JWT token cannot be empty"
            raise ValueError(msg)
        return v.strip()


class SkySparkConfig(BaseSettings):
    """SkySpark configuration."""

    model_config = SettingsConfigDict(
        env_prefix="SKYSPARK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = Field(..., description="SkySpark server URL")
    project: str = Field(..., description="SkySpark project name")
    user: str = Field(..., description="SkySpark username")
    password: str = Field(..., description="SkySpark password")
    timeout: float = Field(default=30.0, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    pool_size: int = Field(default=10, description="Connection pool size")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate and normalize URL."""
        if not v or not v.strip():
            msg = "SkySpark URL cannot be empty"
            raise ValueError(msg)
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            msg = "SkySpark URL must start with http:// or https://"
            raise ValueError(msg)
        # Only add /api if not already present
        v = v.rstrip("/")
        if not v.endswith("/api"):
            v = v + "/api"
        return v

    @field_validator("project", "user")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Validate required fields are not empty."""
        if not v or not v.strip():
            msg = "Field cannot be empty"
            raise ValueError(msg)
        return v.strip()


class AppConfig(BaseSettings):
    """Application-level configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ACE_SKYSPARK_CLI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = Field(default="INFO", description="Logging level")
    log_json: bool = Field(default=False, description="Use JSON logging format")
    batch_size: int = Field(default=100, description="Batch size for entity creation")
    max_concurrent: int = Field(default=5, description="Maximum concurrent operations")
    dry_run: bool = Field(default=False, description="Dry run mode - no changes made")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v = v.upper()
        if v not in valid_levels:
            msg = f"Invalid log level: {v}. Must be one of {valid_levels}"
            raise ValueError(msg)
        return v


class Config:
    """Main configuration class combining all settings."""

    def __init__(self) -> None:
        """Initialize configuration from environment variables."""
        self.flightdeck = FlightDeckConfig()
        self.skyspark = SkySparkConfig()
        self.app = AppConfig()

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "Config":
        """Load configuration from environment.

        Args:
            env_file: Optional path to .env file

        Returns:
            Configured Config instance
        """
        if env_file:
            os.environ["ENV_FILE"] = env_file
        return cls()

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        Returns:
            Dictionary representation of config (with sensitive data masked)
        """
        return {
            "flightdeck": {
                **self.flightdeck.model_dump(),
                "jwt": "***MASKED***",
            },
            "skyspark": {
                **self.skyspark.model_dump(),
                "password": "***MASKED***",
            },
            "app": self.app.model_dump(),
        }
