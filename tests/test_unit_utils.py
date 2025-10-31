"""Unit tests for utility functions."""

from typing import Any

import pytest

from tests.test_utils import (
    build_ref_string,
    create_haystack_ref_tag,
    extract_ref_id,
    find_by_ref_name,
    get_kv_tag,
    has_marker_tag,
    is_duplicate,
    normalize_tags_from_flightdeck,
)


class TestRefStringUtils:
    """Test reference string utility functions."""

    @pytest.mark.unit
    def test_extract_ref_id_from_string(self) -> None:
        """Test extracting ID from reference string."""
        ref = "p:aceTest:r:abc123"
        assert extract_ref_id(ref) == "abc123"

    @pytest.mark.unit
    def test_extract_ref_id_from_dict(self) -> None:
        """Test extracting ID from reference dict."""
        ref = {"_kind": "ref", "val": "p:aceTest:r:xyz789"}
        assert extract_ref_id(ref) == "xyz789"

    @pytest.mark.unit
    def test_extract_ref_id_invalid_format(self) -> None:
        """Test extracting ID from invalid format returns original."""
        ref = "invalid-format"
        assert extract_ref_id(ref) == ref

    @pytest.mark.unit
    def test_extract_ref_id_empty_string(self) -> None:
        """Test extracting ID from empty string."""
        assert extract_ref_id("") == ""

    @pytest.mark.unit
    def test_build_ref_string(self) -> None:
        """Test building reference string."""
        ref = build_ref_string("aceTest", "abc123")
        assert ref == "p:aceTest:r:abc123"


class TestMarkerTags:
    """Test marker tag utility functions."""

    @pytest.mark.unit
    def test_has_marker_tag_true(self) -> None:
        """Test detecting marker tag presence."""
        entity = {"site": {"_kind": "marker"}, "dis": "Test Site"}
        assert has_marker_tag(entity, "site") is True

    @pytest.mark.unit
    def test_has_marker_tag_false(self) -> None:
        """Test detecting marker tag absence."""
        entity = {"dis": "Test Site"}
        assert has_marker_tag(entity, "site") is False

    @pytest.mark.unit
    def test_has_marker_tag_kv_tag(self) -> None:
        """Test that KV tags are not detected as markers."""
        entity = {"area": {"_kind": "number", "val": 5000}}
        assert has_marker_tag(entity, "area") is False


class TestKVTags:
    """Test key-value tag utility functions."""

    @pytest.mark.unit
    def test_get_kv_tag_number(self) -> None:
        """Test getting numeric KV tag."""
        entity = {"area": {"_kind": "number", "val": 5000}}
        assert get_kv_tag(entity, "area") == 5000

    @pytest.mark.unit
    def test_get_kv_tag_string(self) -> None:
        """Test getting string KV tag."""
        entity = {"tz": {"_kind": "str", "val": "America/New_York"}}
        assert get_kv_tag(entity, "tz") == "America/New_York"

    @pytest.mark.unit
    def test_get_kv_tag_ref(self) -> None:
        """Test getting reference KV tag."""
        entity = {"siteRef": {"_kind": "ref", "val": "p:aceTest:r:site123"}}
        assert get_kv_tag(entity, "siteRef") == "p:aceTest:r:site123"

    @pytest.mark.unit
    def test_get_kv_tag_missing(self) -> None:
        """Test getting non-existent tag returns None."""
        entity = {"dis": "Test"}
        assert get_kv_tag(entity, "missing") is None


class TestFlightDeckTagNormalization:
    """Test FlightDeck tag normalization."""

    @pytest.mark.unit
    def test_normalize_marker_tags(self) -> None:
        """Test normalizing marker tags (None values)."""
        tags = {"sensor": None, "temp": None, "hvac": None}
        marker_tags, kv_tags = normalize_tags_from_flightdeck(tags)
        assert set(marker_tags) == {"sensor", "temp", "hvac"}
        assert kv_tags == {}

    @pytest.mark.unit
    def test_normalize_kv_tags(self) -> None:
        """Test normalizing key-value tags."""
        tags = {"zone": "hvac", "priority": "high", "floor": "2"}
        marker_tags, kv_tags = normalize_tags_from_flightdeck(tags)
        assert marker_tags == []
        assert kv_tags == {"zone": "hvac", "priority": "high", "floor": "2"}

    @pytest.mark.unit
    def test_normalize_mixed_tags(self) -> None:
        """Test normalizing mixed marker and KV tags."""
        tags = {"sensor": None, "temp": None, "zone": "hvac", "unit": "degF"}
        marker_tags, kv_tags = normalize_tags_from_flightdeck(tags)
        assert set(marker_tags) == {"sensor", "temp"}
        assert kv_tags == {"zone": "hvac", "unit": "degF"}

    @pytest.mark.unit
    def test_normalize_skips_haystack_ref(self) -> None:
        """Test that haystackRef is excluded from normalization."""
        tags = {"sensor": None, "haystackRef": "p:aceTest:r:point123"}
        marker_tags, kv_tags = normalize_tags_from_flightdeck(tags)
        assert marker_tags == ["sensor"]
        assert kv_tags == {}


class TestHaystackRefOperations:
    """Test haystackRef tag operations."""

    @pytest.mark.unit
    def test_create_haystack_ref_tag(self) -> None:
        """Test creating haystackRef tag."""
        ref = create_haystack_ref_tag("p:aceTest:r:point123")
        assert ref == "p:aceTest:r:point123"

    @pytest.mark.unit
    def test_extract_haystack_ref_present(
        self, sample_flightdeck_point_with_haystack_ref: Any
    ) -> None:
        """Test extracting haystackRef when present."""
        from tests.test_utils import extract_haystack_ref

        ref = extract_haystack_ref(sample_flightdeck_point_with_haystack_ref)
        assert ref == "p:aceTest:r:skyspark-id-456"

    @pytest.mark.unit
    def test_extract_haystack_ref_absent(self, sample_flightdeck_point: Any) -> None:
        """Test extracting haystackRef when absent."""
        from tests.test_utils import extract_haystack_ref

        ref = extract_haystack_ref(sample_flightdeck_point)
        assert ref is None


class TestEntityFinding:
    """Test entity finding utility functions."""

    @pytest.mark.unit
    def test_find_by_ref_name_found(self) -> None:
        """Test finding entity by refName."""
        entities = [
            {"id": {"val": "p:aceTest:r:1"}, "refName": "site-abc", "dis": "Site A"},
            {"id": {"val": "p:aceTest:r:2"}, "refName": "site-xyz", "dis": "Site X"},
        ]
        found = find_by_ref_name(entities, "site-xyz")
        assert found is not None
        assert found["dis"] == "Site X"

    @pytest.mark.unit
    def test_find_by_ref_name_not_found(self) -> None:
        """Test finding non-existent entity by refName."""
        entities = [
            {"id": {"val": "p:aceTest:r:1"}, "refName": "site-abc", "dis": "Site A"},
        ]
        found = find_by_ref_name(entities, "nonexistent")
        assert found is None

    @pytest.mark.unit
    def test_is_duplicate_true(self) -> None:
        """Test duplicate detection."""
        entity = {"refName": "duplicate-name"}
        assert is_duplicate(entity, "duplicate-name") is True

    @pytest.mark.unit
    def test_is_duplicate_false(self) -> None:
        """Test non-duplicate detection."""
        entity = {"refName": "unique-name"}
        assert is_duplicate(entity, "different-name") is False
