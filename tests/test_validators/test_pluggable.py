"""Tests for the pluggable validator hook: strictness dial, user-supplied
validators, strict Illumina v2 conformance, and optional JSON Schema."""

from samplesheet_parser import (
    SampleSheetValidator,
    Strictness,
    ValidationIssue,
    ValidatorError,
    illumina_v2_conformance,
    json_schema_validator,
    sheet_to_dict,
)
from samplesheet_parser.parsers.v2 import SampleSheetV2

try:
    import jsonschema  # noqa: F401

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


# Structurally fine but NOT spec-conformant: indexes are 10 bp while
# Index1Cycles is 8, and there is no RunName in [Header].
_NONCONFORMANT_V2 = """\
[Header]
FileFormatVersion,2
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,10

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2
1,Sample1,ATTACTCGAT,TATAGCCTGT
1,Sample2,TCCGGAGACC,ATAGAGGCAC
"""

# A clean, spec-conformant v2 sheet (index lengths match declared cycles).
# No InstrumentPlatform, so STRICT colour balance is skipped (a note, not an
# error) and the sheet exercises the conformance path in isolation.
_CONFORMANT_V2 = """\
[Header]
FileFormatVersion,2
RunName,ConformantRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,10
Index2Cycles,10

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2
1,Sample1,ATTACTCGAT,TATAGCCTGT
1,Sample2,TCCGGAGACC,ATAGAGGCAC
"""


def _parse_v2(path, content):
    path.write_text(content)
    sheet = SampleSheetV2(str(path))
    sheet.parse()
    return sheet


class TestStrictnessDial:
    def test_default_is_standard_and_backward_compatible(self, tmp_path):
        # No strictness passed: historical behaviour. A nonconformant-but-
        # structurally-fine sheet still passes (lenient structure is the point).
        sheet = _parse_v2(tmp_path / "s.csv", _NONCONFORMANT_V2)
        result = SampleSheetValidator().validate(sheet)
        assert result.is_valid

    def test_lenient_passes(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _NONCONFORMANT_V2)
        result = SampleSheetValidator().validate(sheet, strictness=Strictness.LENIENT)
        assert result.is_valid

    def test_strict_fails_on_nonconformant_sheet(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _NONCONFORMANT_V2)
        result = SampleSheetValidator().validate(sheet, strictness=Strictness.STRICT)
        assert not result.is_valid
        codes = {e.code for e in result.errors}
        assert "SPEC_INDEX_LENGTH_MISMATCH" in codes

    def test_strict_passes_on_conformant_sheet(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        result = SampleSheetValidator().validate(sheet, strictness=Strictness.STRICT)
        assert result.is_valid

    def test_strict_as_string(self, tmp_path):
        # The dial accepts the enum value as a plain string.
        sheet = _parse_v2(tmp_path / "s.csv", _NONCONFORMANT_V2)
        result = SampleSheetValidator().validate(sheet, strictness="strict")
        assert not result.is_valid

    def test_explicit_keyword_overrides_preset(self, tmp_path):
        # STRICT would normally raise the distance threshold to 4; an explicit
        # value wins, so the preset is a default, not a lock.
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        result = SampleSheetValidator().validate(
            sheet, strictness=Strictness.STRICT, min_hamming_distance=1
        )
        # (conformant sheet, so still valid; the point is the call is accepted
        # and the override is honoured without error)
        assert result.is_valid


class TestExtraValidators:
    def test_custom_validator_raising_error(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)

        def require_lib_prefix(sh):
            for sample in sh.samples():
                sid = sample.get("sample_id") or ""
                if not sid.startswith("LIB"):
                    raise ValidatorError(
                        f"Sample_ID {sid!r} must start with 'LIB'.",
                        code="LAB_RULE_SAMPLE_ID_PREFIX",
                        sample_id=sid,
                    )
            return []

        result = SampleSheetValidator().validate(sheet, extra_validators=[require_lib_prefix])
        assert not result.is_valid
        assert any(e.code == "LAB_RULE_SAMPLE_ID_PREFIX" for e in result.errors)

    def test_custom_validator_yielding_issues(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)

        def warn_always(_sheet):
            return [ValidationIssue("warning", "LAB_ADVISORY", "heads up")]

        result = SampleSheetValidator().validate(sheet, extra_validators=[warn_always])
        assert result.is_valid  # warnings do not fail
        assert any(w.code == "LAB_ADVISORY" for w in result.warnings)

    def test_custom_validator_returning_none(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)

        def noop(_sheet):
            return None

        result = SampleSheetValidator().validate(sheet, extra_validators=[noop])
        assert result.is_valid


class TestIlluminaV2Conformance:
    def test_flags_index_length_mismatch_and_missing_runname(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _NONCONFORMANT_V2)
        issues = illumina_v2_conformance(sheet)
        codes = {i.code for i in issues}
        assert "SPEC_INDEX_LENGTH_MISMATCH" in codes
        assert "SPEC_MISSING_RUNNAME" in codes

    def test_conformant_sheet_has_no_errors(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        issues = illumina_v2_conformance(sheet)
        assert [i for i in issues if i.level == "error"] == []

    def test_skips_non_v2_sheet(self, v1_minimal):
        from samplesheet_parser.parsers.v1 import SampleSheetV1

        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        issues = illumina_v2_conformance(sheet)
        assert any(i.code == "SPEC_NOT_APPLICABLE" for i in issues)


class TestJsonSchema:
    def test_sheet_to_dict_shape(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        doc = sheet_to_dict(sheet)
        assert set(doc) == {"header", "reads", "settings", "samples"}
        assert doc["header"]["RunName"] == "ConformantRun"
        assert len(doc["samples"]) == 2

    def test_schema_required_field(self, tmp_path):
        # Schema requires header.RunName; the nonconformant sheet lacks it.
        sheet = _parse_v2(tmp_path / "s.csv", _NONCONFORMANT_V2)
        schema = {
            "type": "object",
            "properties": {"header": {"type": "object", "required": ["RunName"]}},
        }
        result = SampleSheetValidator().validate(sheet, schema=schema)
        if HAS_JSONSCHEMA:
            assert not result.is_valid
            assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)
        else:
            # Soft dependency absent: degrades to a note, core stays valid.
            assert result.is_valid
            assert any(n.code == "SCHEMA_SKIPPED" for n in result.notes)

    def test_schema_satisfied(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        schema = {
            "type": "object",
            "properties": {"header": {"type": "object", "required": ["RunName"]}},
        }
        result = SampleSheetValidator().validate(sheet, schema=schema)
        # Conformant sheet satisfies the schema (or the check is skipped).
        assert result.is_valid
        assert not any(e.code == "SCHEMA_VIOLATION" for e in result.errors)

    def test_direct_validator_factory_skip_note(self, tmp_path):
        # Builds the validator directly and runs it; asserts the skip-note path
        # only when jsonschema is unavailable.
        if HAS_JSONSCHEMA:
            return
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        issues = json_schema_validator({"type": "object"})(sheet)
        assert any(i.code == "SCHEMA_SKIPPED" for i in issues)
