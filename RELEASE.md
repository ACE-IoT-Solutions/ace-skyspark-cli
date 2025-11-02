# Release Process

This document describes the release process for ace-skyspark-cli.

## Workflows

### 1. CI Workflow (`ci.yml`)
**Triggers:** Push or PR to `main` branch

Runs on every commit:
- Linting (ruff)
- Type checking (pyrefly)
- Unit tests with coverage
- Codecov upload

### 2. Test Multi-Python (`test-multi-python.yml`)
**Triggers:** Push/PR to `main` or `develop`, or manual dispatch

Comprehensive testing:
- Multiple OS (Ubuntu, macOS, Windows)
- Python 3.13 (expandable to 3.10-3.13)
- Package build and installation verification

### 3. Publish Workflow (`publish.yml`)
**Triggers:**
- Push tag `v*` → Publishes to **TestPyPI**
- GitHub Release (published) → Publishes to **PyPI**
- Manual workflow dispatch → Choose TestPyPI or PyPI

**Jobs:**
1. Run tests
2. Build package
3. Upload to TestPyPI (for tags) OR PyPI (for releases)

## Release Steps

### Step 1: Prepare Release

1. Update version in:
   - `pyproject.toml`
   - `src/ace_skyspark_cli/__init__.py`

2. Update documentation if needed:
   - `README.md`
   - `JOB_CONFIG_GUIDE.md`

3. Commit changes:
   ```bash
   git add .
   git commit -m "chore: Release v0.11.1"
   git push origin main
   ```

### Step 2: Create and Push Tag

Push a tag to trigger TestPyPI publish:

```bash
git tag v0.11.1
git push origin v0.11.1
```

This will:
- ✅ Run all tests
- ✅ Build package
- ✅ Publish to **TestPyPI** (test.pypi.org)

### Step 3: Test from TestPyPI

Test the package from TestPyPI:

```bash
# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  ace-skyspark-cli==0.11.1

# Test it
ace-skyspark-cli --version
ace-skyspark-cli --help
```

### Step 4: Create GitHub Release

Once TestPyPI publish succeeds and testing is complete:

1. Go to GitHub repository → Releases
2. Click "Draft a new release"
3. Select tag: `v0.11.1`
4. Release title: `v0.11.1`
5. Generate release notes or write changelog
6. Click **"Publish release"**

This triggers:
- ✅ Run all tests again
- ✅ Build package
- ✅ Publish to **PyPI** (pypi.org)

### Step 5: Verify PyPI Publication

Check that the package is available:

```bash
# Install from PyPI
pip install ace-skyspark-cli==0.11.1

# Verify
ace-skyspark-cli --version
```

## Manual Publishing (Emergency)

If you need to manually trigger publish:

1. Go to Actions → Publish to PyPI
2. Click "Run workflow"
3. Select branch: `main`
4. Choose target: `testpypi` or `pypi`
5. Click "Run workflow"

## PyPI Configuration

### Trusted Publishing (Recommended)

Both TestPyPI and PyPI use **trusted publishing** (no API tokens needed):

1. **TestPyPI** environment:
   - URL: https://test.pypi.org/p/ace-skyspark-cli
   - Uses `id-token: write` permission
   - Configured in GitHub repository settings

2. **PyPI** environment:
   - URL: https://pypi.org/p/ace-skyspark-cli
   - Uses `id-token: write` permission
   - Configured in GitHub repository settings

### Setting up Trusted Publishing

On PyPI/TestPyPI:
1. Go to project settings
2. Add trusted publisher:
   - Owner: ACE-IoT-Solutions
   - Repository: ace-skyspark-cli
   - Workflow: publish.yml
   - Environment: `pypi` or `testpypi`

## Rollback

If a release has issues:

1. Delete the GitHub release (does not unpublish from PyPI)
2. Use `pip install ace-skyspark-cli==<previous-version>` to use old version
3. Fix issues, bump version, and release again

**Note:** You cannot replace an existing PyPI version - you must bump the version number.

## Version Numbering

Follow semantic versioning:
- `v0.11.0` - Major/minor/patch
- `v0.11.1` - Patch release
- `v0.12.0` - Minor release with new features
- `v1.0.0` - Stable release

Test versions:
- `v0.11.1-test1` - Publishes to TestPyPI only (useful for pre-releases)
