# ACE SkySpark CLI Test Suite

Comprehensive test suite for the ACE SkySpark CLI tool that synchronizes points between ACE FlightDeck and SkySpark.

## Test Structure

```
tests/
├── __init__.py                      # Test package init
├── conftest.py                      # Pytest fixtures and configuration
├── test_utils.py                    # Test utility functions
├── test_config.py                   # Configuration loading tests
├── test_unit_utils.py              # Unit tests for utility functions
├── test_unit_haystack_ref.py       # Unit tests for haystackRef tagging
├── test_unit_skyspark.py           # Unit tests for SkySpark operations
├── test_idempotency.py             # Idempotency verification tests
├── test_duplicate_prevention.py    # Duplicate prevention tests
├── test_tag_sync.py                # Tag synchronization tests
├── test_integration.py             # End-to-end integration tests
└── README.md                        # This file
```

## Test Categories

### Unit Tests (`@pytest.mark.unit`)
Fast tests that don't require external services. These use mocks and test individual components in isolation.

**Files:**
- `test_config.py` - Configuration loading and validation
- `test_unit_utils.py` - Utility function tests
- `test_unit_haystack_ref.py` - haystackRef tagging logic
- `test_unit_skyspark.py` - SkySpark entity operations

### Integration Tests (`@pytest.mark.integration`)
Tests that connect to real FlightDeck and SkySpark instances. Require valid credentials in `.env`.

**File:** `test_integration.py`

### Idempotency Tests (`@pytest.mark.idempotent`)
Tests verifying that operations can be repeated without side effects.

**Files:**
- `test_idempotency.py` - Unit-level idempotency tests
- `test_integration.py` - Integration-level idempotency tests

### Slow Tests (`@pytest.mark.slow`)
Tests that take longer to run, typically integration tests with multiple operations.

## Configuration

Tests use environment variables from `.env` file:

```bash
# FlightDeck Configuration
TEST_FLIGHTDECK_USER=your-email@example.com
TEST_FLIGHTDECK_JWT=your-jwt-token
TEST_FLIGHTDECK_SITE=your-site-name

# SkySpark Configuration
TEST_SKYSPARK_URL=http://your-skyspark-host:8080/
TEST_SKYSPARK_PROJECT=yourProject
TEST_SKYSPARK_USER=your-username
TEST_SKYSPARK_PASS=your-password
```

### Important: No Hardcoded Values
All test configuration comes from environment variables. This ensures:
- No credentials in version control
- Tests can run in different environments
- CI/CD pipelines can use their own credentials

## Running Tests

### Install Dependencies

```bash
# Install test dependencies
uv sync --dev
```

### Run All Tests

```bash
# Run all tests (unit + integration)
uv run pytest

# Run with coverage
uv run pytest --cov=ace_skyspark_cli --cov-report=html
```

### Run Specific Test Categories

```bash
# Unit tests only (fast, no external dependencies)
uv run pytest -m unit

# Integration tests only (requires .env configuration)
uv run pytest -m integration

# Idempotency tests
uv run pytest -m idempotent

# Skip slow tests
uv run pytest -m "not slow"
```

### Run Specific Test Files

```bash
# Configuration tests
uv run pytest tests/test_config.py

# Utility tests
uv run pytest tests/test_unit_utils.py

# Integration tests
uv run pytest tests/test_integration.py

# Idempotency tests
uv run pytest tests/test_idempotency.py
```

### Verbose Output

```bash
# Verbose output with detailed test names
uv run pytest -v

# Show print statements
uv run pytest -s

# Show locals on failure
uv run pytest -l
```

## Test Fixtures

### Configuration Fixtures
- `env_config` - Loads test configuration from environment variables
- `skip_if_no_integration_config` - Skips tests if integration config is missing

### Mock Fixtures
- `mock_flightdeck_client` - Mocked FlightDeck API client
- `mock_skyspark_client` - Mocked SkySpark client

### Sample Data Fixtures
- `sample_flightdeck_point` - Sample FlightDeck point without haystackRef
- `sample_flightdeck_point_with_haystack_ref` - Sample point with existing haystackRef
- `sample_skyspark_site` - Sample SkySpark site response
- `sample_skyspark_equipment` - Sample SkySpark equipment response
- `sample_skyspark_point` - Sample SkySpark point response
- `sample_site_model` - Sample Site Pydantic model
- `sample_equipment_model` - Sample Equipment Pydantic model
- `sample_point_model` - Sample Point Pydantic model

## Key Test Scenarios

### 1. Configuration Tests
- Load environment variables
- Validate required configuration present
- No hardcoded credentials
- Skip integration tests when config missing

### 2. haystackRef Tagging Tests
- Create haystackRef when syncing new point
- Use existing haystackRef to find entities
- Skip syncing points with valid haystackRef
- Detect orphaned haystackRef (SkySpark entity deleted)

### 3. Duplicate Prevention Tests
- Find existing entities by refName
- Prevent duplicate site creation
- Prevent duplicate equipment creation
- Prevent duplicate point creation
- Validate haystackRef before using

### 4. Idempotency Tests
- Create entity once, find it on subsequent runs
- Same tags applied multiple times produce same result
- Interrupted sync can resume without duplicates
- haystackRef updates are safe to repeat

### 5. Tag Synchronization Tests
- Sync marker tags from FlightDeck to SkySpark
- Sync key-value tags from FlightDeck to SkySpark
- Preserve existing SkySpark tags during sync
- Handle tag conflicts (FlightDeck takes precedence)
- Batch tag updates efficiently

### 6. Integration Tests
- Connect to real FlightDeck and SkySpark
- Create site → equipment → point hierarchy
- Verify entity relationships (siteRef, equipRef)
- Read and filter entities by tags
- End-to-end synchronization workflow

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync --dev

      - name: Run unit tests
        run: uv run pytest -m unit

      - name: Run integration tests
        if: env.TEST_SKYSPARK_URL != ''
        env:
          TEST_FLIGHTDECK_USER: ${{ secrets.TEST_FLIGHTDECK_USER }}
          TEST_FLIGHTDECK_JWT: ${{ secrets.TEST_FLIGHTDECK_JWT }}
          TEST_FLIGHTDECK_SITE: ${{ secrets.TEST_FLIGHTDECK_SITE }}
          TEST_SKYSPARK_URL: ${{ secrets.TEST_SKYSPARK_URL }}
          TEST_SKYSPARK_PROJECT: ${{ secrets.TEST_SKYSPARK_PROJECT }}
          TEST_SKYSPARK_USER: ${{ secrets.TEST_SKYSPARK_USER }}
          TEST_SKYSPARK_PASS: ${{ secrets.TEST_SKYSPARK_PASS }}
        run: uv run pytest -m integration
```

## Best Practices

### Writing Tests

1. **Use appropriate markers**
   ```python
   @pytest.mark.unit
   @pytest.mark.integration
   @pytest.mark.idempotent
   @pytest.mark.slow
   ```

2. **Clean up test data**
   Integration tests should clean up any entities they create:
   ```python
   # Create test entity
   created = await client.create_points([test_point])
   point_id = created[0]["id"]["val"]

   try:
       # Test operations
       ...
   finally:
       # Always clean up
       await client.delete_entity(point_id)
   ```

3. **Use descriptive test names**
   ```python
   def test_prevent_duplicate_point_creation_with_same_refname():
       """Test that points with same refName are not duplicated."""
   ```

4. **Test error cases**
   Don't just test the happy path - test failures too:
   ```python
   def test_invalid_haystack_ref_raises_error():
       with pytest.raises(ValueError):
           # Test error handling
   ```

### Running Tests Locally

1. Copy `.env.example` to `.env` and fill in credentials
2. Run unit tests first (fast, no external deps): `uv run pytest -m unit`
3. Run integration tests if you have valid credentials: `uv run pytest -m integration`
4. Check coverage: `uv run pytest --cov=ace_skyspark_cli`

## Troubleshooting

### Integration Tests Skipping
**Problem:** All integration tests are skipped.

**Solution:** Check that `.env` file exists and has all required variables:
```bash
cat .env | grep TEST_
```

### Authentication Errors
**Problem:** `AuthenticationError` in integration tests.

**Solution:**
1. Verify credentials are correct and not expired
2. Check SkySpark server is accessible: `curl http://your-server:8080/`
3. Verify FlightDeck JWT is valid

### Slow Test Performance
**Problem:** Tests take too long.

**Solution:**
1. Run unit tests only: `pytest -m unit`
2. Skip slow tests: `pytest -m "not slow"`
3. Run tests in parallel: `pytest -n auto` (requires pytest-xdist)

### Test Cleanup Issues
**Problem:** Test entities remain in SkySpark.

**Solution:**
1. Tests with `testPoint` marker can be cleaned up:
   ```bash
   # Query for test points
   read(testPoint)
   ```
2. Run cleanup script (if available)

## Coverage Goals

Target coverage: **80%+**

Check current coverage:
```bash
uv run pytest --cov=ace_skyspark_cli --cov-report=term-missing
```

Generate HTML coverage report:
```bash
uv run pytest --cov=ace_skyspark_cli --cov-report=html
open htmlcov/index.html
```

## Contributing

When adding new features:

1. **Write tests first** (TDD approach)
2. Add **unit tests** for business logic
3. Add **integration tests** for E2E workflows
4. Update **this README** with new test categories
5. Ensure **no hardcoded values** - use environment variables
6. Add appropriate **test markers**
7. Run **all tests** before submitting PR

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [ace-skyspark-lib documentation](https://github.com/aceiotsolutions/ace-skyspark-lib)
- [Project Haystack](https://project-haystack.org/)
