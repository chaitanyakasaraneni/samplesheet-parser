"""Tests for the shared parser helpers."""

from samplesheet_parser.parsers._common import strip_trailing_empty_fields


class TestStripTrailingEmptyFields:
    def test_strips_trailing_empties(self):
        assert strip_trailing_empty_fields("Read1Cycles,28,,,,") == "Read1Cycles,28"

    def test_strips_trailing_whitespace_only_fields(self):
        assert strip_trailing_empty_fields("Adapter,ACGT, , ,") == "Adapter,ACGT"

    def test_preserves_interior_empties(self):
        assert strip_trailing_empty_fields("a,b,,c,,") == "a,b,,c"

    def test_no_trailing_is_unchanged(self):
        assert strip_trailing_empty_fields("key,value") == "key,value"

    def test_single_field_is_unchanged(self):
        assert strip_trailing_empty_fields("solo") == "solo"

    def test_all_empty_collapses_to_empty_string(self):
        assert strip_trailing_empty_fields(",,,") == ""
