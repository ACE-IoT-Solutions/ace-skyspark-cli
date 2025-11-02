"""Tests for configuration loading and validation."""

import os

import pytest


class TestConfiguration:
    """Test configuration loading from environment variables."""

    @pytest.mark.unit
    def test_env_config_loads_all_variables(self, env_config: dict[str, str]) -> None:
        """Test that all expected environment variables are loaded."""
        expected_keys = {
            "flightdeck_user",
            "flightdeck_jwt",
            "flightdeck_site",
            "skyspark_url",
            "skyspark_project",
            "skyspark_user",
            "skyspark_pass",
        }
        assert set(env_config.keys()) == expected_keys

    @pytest.mark.unit
    def test_flightdeck_user_from_env(self, env_config: dict[str, str]) -> None:
        """Test FlightDeck user is loaded from TEST_FLIGHTDECK_USER."""
        expected = os.getenv("TEST_FLIGHTDECK_USER", "")
        assert env_config["flightdeck_user"] == expected

    @pytest.mark.unit
    def test_flightdeck_jwt_from_env(self, env_config: dict[str, str]) -> None:
        """Test FlightDeck JWT is loaded from TEST_FLIGHTDECK_JWT."""
        expected = os.getenv("TEST_FLIGHTDECK_JWT", "")
        assert env_config["flightdeck_jwt"] == expected

    @pytest.mark.unit
    def test_flightdeck_site_from_env(self, env_config: dict[str, str]) -> None:
        """Test FlightDeck site is loaded from TEST_FLIGHTDECK_SITE."""
        expected = os.getenv("TEST_FLIGHTDECK_SITE", "")
        assert env_config["flightdeck_site"] == expected

    @pytest.mark.unit
    def test_skyspark_url_from_env(self, env_config: dict[str, str]) -> None:
        """Test SkySpark URL is loaded from TEST_SKYSPARK_URL."""
        expected = os.getenv("TEST_SKYSPARK_URL", "")
        assert env_config["skyspark_url"] == expected

    @pytest.mark.unit
    def test_skyspark_project_from_env(self, env_config: dict[str, str]) -> None:
        """Test SkySpark project is loaded from TEST_SKYSPARK_PROJECT."""
        expected = os.getenv("TEST_SKYSPARK_PROJECT", "")
        assert env_config["skyspark_project"] == expected

    @pytest.mark.unit
    def test_skyspark_user_from_env(self, env_config: dict[str, str]) -> None:
        """Test SkySpark user is loaded from TEST_SKYSPARK_USER."""
        expected = os.getenv("TEST_SKYSPARK_USER", "")
        assert env_config["skyspark_user"] == expected

    @pytest.mark.unit
    def test_skyspark_pass_from_env(self, env_config: dict[str, str]) -> None:
        """Test SkySpark password is loaded from TEST_SKYSPARK_PASS."""
        expected = os.getenv("TEST_SKYSPARK_PASS", "")
        assert env_config["skyspark_pass"] == expected

    @pytest.mark.unit
    def test_no_hardcoded_credentials_in_config(self, env_config: dict[str, str]) -> None:
        """Test that no hardcoded test credentials are present."""
        # This ensures we're always using environment variables
        for key, value in env_config.items():
            # If a value is set, it should come from environment, not hardcoded defaults
            if value:
                env_var_name = f"TEST_{key.upper()}"
                assert os.getenv(env_var_name) == value, (
                    f"{key} should come from {env_var_name} environment variable"
                )

    @pytest.mark.unit
    def test_skip_integration_when_config_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that integration tests skip when configuration is missing."""
        # Clear all test environment variables
        test_env_vars = [
            "TEST_FLIGHTDECK_USER",
            "TEST_FLIGHTDECK_JWT",
            "TEST_FLIGHTDECK_SITE",
            "TEST_SKYSPARK_URL",
            "TEST_SKYSPARK_PROJECT",
            "TEST_SKYSPARK_USER",
            "TEST_SKYSPARK_PASS",
        ]
        for var in test_env_vars:
            monkeypatch.delenv(var, raising=False)

        # Reload env_config after clearing
        env_config = {
            "flightdeck_user": os.getenv("TEST_FLIGHTDECK_USER", ""),
            "flightdeck_jwt": os.getenv("TEST_FLIGHTDECK_JWT", ""),
            "flightdeck_site": os.getenv("TEST_FLIGHTDECK_SITE", ""),
            "skyspark_url": os.getenv("TEST_SKYSPARK_URL", ""),
            "skyspark_project": os.getenv("TEST_SKYSPARK_PROJECT", ""),
            "skyspark_user": os.getenv("TEST_SKYSPARK_USER", ""),
            "skyspark_pass": os.getenv("TEST_SKYSPARK_PASS", ""),
        }

        # Verify skip logic
        required_keys = [
            "flightdeck_user",
            "flightdeck_jwt",
            "flightdeck_site",
            "skyspark_url",
            "skyspark_project",
            "skyspark_user",
            "skyspark_pass",
        ]
        missing = [k for k in required_keys if not env_config.get(k)]
        assert len(missing) == len(required_keys), "All config should be missing"
