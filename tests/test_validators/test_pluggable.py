"""Tests for the pluggable validator hook: strictness dial, user-supplied
validators, strict Illumina v2 conformance, and optional JSON Schema."""

from samplesheet_parser import (
    ILLUMINA_V2_URN,
    SAMSHEE_V2_URN,
    SampleSheetValidator,
    Strictness,
    ValidationIssue,
    ValidatorError,
    illumina_v2_conformance,
    illumina_v2_schema_validator,
    json_schema_validator,
    sheet_to_dict,
    sheet_to_sections,
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
        # Schema validates the sectioned view (Header section); the nonconformant
        # sheet has no RunName.
        sheet = _parse_v2(tmp_path / "s.csv", _NONCONFORMANT_V2)
        schema = {
            "type": "object",
            "properties": {"Header": {"type": "object", "required": ["RunName"]}},
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
            "properties": {"Header": {"type": "object", "required": ["RunName"]}},
        }
        result = SampleSheetValidator().validate(sheet, schema=schema)
        # Conformant sheet satisfies the schema (or the check is skipped).
        assert result.is_valid
        assert not any(e.code == "SCHEMA_VIOLATION" for e in result.errors)

    def test_schema_skipped_when_jsonschema_unavailable(self, tmp_path, monkeypatch):
        # Force the soft-dependency fallback even when jsonschema is installed
        # (as it is in CI), so the SCHEMA_SKIPPED path is always exercised.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "jsonschema":
                raise ImportError("forced absent for test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        issues = json_schema_validator({"type": "object"})(sheet)
        assert any(i.code == "SCHEMA_SKIPPED" for i in issues)


class _StubSheet:
    """Minimal stand-in exposing just what illumina_v2_conformance reads.

    Lets the conformance branches be exercised directly, without constructing a
    sheet the parser would reject (e.g. a bad FileFormatVersion or missing
    Read1Cycles).
    """

    def __init__(self, header, reads, samples):
        self.header = header
        self.reads = reads
        self._samples = samples

    def samples(self):
        return self._samples


class TestConformanceBranches:
    def test_bad_format_version(self):
        sheet = _StubSheet({"FileFormatVersion": "3", "RunName": "x"}, {"Read1Cycles": 151}, [])
        codes = {i.code for i in illumina_v2_conformance(sheet)}
        assert "SPEC_BAD_FORMAT_VERSION" in codes

    def test_missing_read1(self):
        sheet = _StubSheet({"FileFormatVersion": "2", "RunName": "x"}, {}, [])
        codes = {i.code for i in illumina_v2_conformance(sheet)}
        assert "SPEC_MISSING_READ1" in codes

    def test_index2_length_mismatch_and_single_index(self):
        # Sample A has no Index2 (exercises the "no index" path); Sample B has a
        # 2 bp Index2 against Index2Cycles=10 (exercises the Index2 mismatch).
        samples = [
            {"sample_id": "A", "index": "ACGTACGTAC"},
            {"sample_id": "B", "index": "ACGTACGTAC", "index2": "AC"},
        ]
        sheet = _StubSheet(
            {"FileFormatVersion": "2", "RunName": "x"},
            {"Read1Cycles": 151, "Index1Cycles": 10, "Index2Cycles": 10},
            samples,
        )
        issues = illumina_v2_conformance(sheet)
        index2_mismatches = [
            i
            for i in issues
            if i.code == "SPEC_INDEX_LENGTH_MISMATCH" and i.context.get("field") == "index2"
        ]
        assert len(index2_mismatches) == 1


class TestPluggableMerge:
    def test_note_level_issue_merges_into_notes(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)

        def note_validator(_sheet):
            return [ValidationIssue("note", "LAB_NOTE", "fyi")]

        result = SampleSheetValidator().validate(sheet, extra_validators=[note_validator])
        assert result.is_valid
        assert any(n.code == "LAB_NOTE" for n in result.notes)

    def test_strict_on_v1_sheet_notes_not_applicable(self, v1_minimal):
        # STRICT runs conformance; on a V1 sheet it returns SPEC_NOT_APPLICABLE,
        # which flows through the note branch of the merge helper.
        from samplesheet_parser.parsers.v1 import SampleSheetV1

        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        result = SampleSheetValidator().validate(sheet, strictness=Strictness.STRICT)
        assert any(n.code == "SPEC_NOT_APPLICABLE" for n in result.notes)


# Parses fine, but violates the v2 schema: FileFormatVersion is 3, and the
# schema's Header.FileFormatVersion enum requires "2". Index lengths match the
# declared cycles, so this isolates a schema-only structural failure.
_SCHEMA_INVALID_V2 = """\
[Header]
FileFormatVersion,3
RunName,SchemaInvalid
InstrumentPlatform,NovaSeqXSeries

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


class TestSheetToSections:
    def test_sections_shape(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        sec = sheet_to_sections(sheet)
        assert "Header" in sec and "Reads" in sec and "BCLConvert_Data" in sec
        assert sec["Header"]["RunName"] == "ConformantRun"
        # Reads values are integers in the sectioned view.
        assert sec["Reads"]["Read1Cycles"] == 151
        # Data rows keep their original column names.
        assert sec["BCLConvert_Data"][0]["Sample_ID"] == "Sample1"


class TestIlluminaV2SchemaValidator:
    def test_conformant_sheet_passes_schema(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        issues = illumina_v2_schema_validator()(sheet)
        assert not any(i.code == "SPEC_SCHEMA_VIOLATION" for i in issues)

    def test_bad_format_version_fails_schema(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _SCHEMA_INVALID_V2)
        issues = illumina_v2_schema_validator()(sheet)
        if HAS_JSONSCHEMA:
            assert any(i.code == "SPEC_SCHEMA_VIOLATION" for i in issues)
        else:
            assert any(i.code == "SCHEMA_SKIPPED" for i in issues)

    def test_skips_non_v2(self, v1_minimal):
        from samplesheet_parser.parsers.v1 import SampleSheetV1

        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        issues = illumina_v2_schema_validator()(sheet)
        assert any(i.code == "SPEC_NOT_APPLICABLE" for i in issues)

    def test_strict_runs_schema_check(self, tmp_path):
        # STRICT appends the schema validator; a missing Index column fails it.
        sheet = _parse_v2(tmp_path / "s.csv", _SCHEMA_INVALID_V2)
        result = SampleSheetValidator().validate(sheet, strictness=Strictness.STRICT)
        if HAS_JSONSCHEMA:
            assert not result.is_valid
            assert any(e.code == "SPEC_SCHEMA_VIOLATION" for e in result.errors)


class TestSchemaRegistry:
    def test_ref_to_project_urn_resolves(self, tmp_path):
        # A user schema that $refs the bundled URN must resolve offline and pass
        # a conformant sheet.
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        result = SampleSheetValidator().validate(sheet, schema={"$ref": ILLUMINA_V2_URN})
        assert result.is_valid
        assert not any(e.code == "SCHEMA_REF_UNRESOLVED" for e in result.errors)

    def test_ref_to_samshee_urn_alias_resolves(self, tmp_path):
        # The samshee compatibility alias resolves to the bundled schema, so a
        # samshee-authored $ref keeps working and flags a bad sheet.
        sheet = _parse_v2(tmp_path / "s.csv", _SCHEMA_INVALID_V2)
        result = SampleSheetValidator().validate(sheet, schema={"$ref": SAMSHEE_V2_URN})
        if HAS_JSONSCHEMA:
            assert not result.is_valid
            assert any(e.code == "SCHEMA_VIOLATION" for e in result.errors)
            assert not any(e.code == "SCHEMA_REF_UNRESOLVED" for e in result.errors)
        else:
            assert any(n.code == "SCHEMA_SKIPPED" for n in result.notes)

    def test_unresolvable_ref_is_reported_not_raised(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        result = SampleSheetValidator().validate(
            sheet, schema={"$ref": "urn:nope:does-not-exist/v1"}
        )
        if HAS_JSONSCHEMA:
            assert not result.is_valid
            assert any(e.code == "SCHEMA_REF_UNRESOLVED" for e in result.errors)
        else:
            assert any(n.code == "SCHEMA_SKIPPED" for n in result.notes)


class _SectionStub:
    """Stub exposing just the attributes sheet_to_sections reads, for branch
    coverage of its v2/non-v2 (Data) and Cloud_Data paths."""

    def __init__(self, *, header=None, records=None, cloud_data=None, samples=None):
        if header is not None:
            self.header = header
        if records is not None:
            self.records = records
        if cloud_data is not None:
            self.cloud_data = cloud_data
        self._samples = samples or []

    def samples(self):
        return self._samples


class TestSheetToSectionsBranches:
    def test_falls_back_to_data_without_records(self):
        # No `records` attribute: rows come from samples() under a generic Data key.
        stub = _SectionStub(samples=[{"sample_id": "A", "index": "ACGT"}])
        sec = sheet_to_sections(stub)
        assert sec["Data"] == [{"sample_id": "A", "index": "ACGT"}]

    def test_includes_cloud_data(self):
        stub = _SectionStub(
            header={"FileFormatVersion": "2"},
            records=[{"Sample_ID": "A", "Index": "ACGTACGTAC"}],
            cloud_data=[{"Sample_ID": "A", "ProjectName": "P"}],
        )
        sec = sheet_to_sections(stub)
        assert "BCLConvert_Data" in sec
        assert sec["Cloud_Data"] == [{"Sample_ID": "A", "ProjectName": "P"}]

    def test_v1_records_use_generic_data_key(self, v1_minimal):
        # V1 exposes `records` too, but it is not a v2 BCLConvert_Data section.
        from samplesheet_parser.parsers.v1 import SampleSheetV1

        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        sec = sheet_to_sections(sheet)
        assert "BCLConvert_Data" not in sec
        assert "Data" in sec

    def test_empty_v2_data_still_projected(self):
        # An empty [BCLConvert_Data] on a v2 sheet projects an empty array, not a
        # missing section, so a schema can distinguish empty from absent.
        stub = _SectionStub(header={"FileFormatVersion": "2"}, records=[])
        sec = sheet_to_sections(stub)
        assert sec["BCLConvert_Data"] == []


class TestRegistryAndSchemaEdgeCases:
    def test_build_registry_none_without_referencing(self, monkeypatch):
        # When `referencing` cannot be imported, build_registry degrades to None.
        import builtins

        from samplesheet_parser import build_registry

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "referencing":
                raise ImportError("forced absent for test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert build_registry() is None

    def test_validation_without_registry_uses_plain_validator(self, tmp_path, monkeypatch):
        # Force build_registry() -> None so the no-registry validator path runs.
        if not HAS_JSONSCHEMA:
            return
        import samplesheet_parser.validators as validators_mod

        monkeypatch.setattr(validators_mod, "build_registry", lambda: None)
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        schema = {
            "type": "object",
            "properties": {"Header": {"type": "object", "required": ["RunName"]}},
        }
        result = SampleSheetValidator().validate(sheet, schema=schema)
        # Conformant sheet; the point is the plain-validator branch ran cleanly.
        assert not any(e.code == "SCHEMA_REF_UNRESOLVED" for e in result.errors)
        assert not any(e.code == "SCHEMA_INVALID" for e in result.errors)

    def test_malformed_schema_reports_schema_invalid(self, tmp_path):
        # A genuinely malformed schema (`type` must be a string/array) is caught
        # by check_schema and reported as SCHEMA_INVALID, not SCHEMA_REF_UNRESOLVED.
        sheet = _parse_v2(tmp_path / "s.csv", _CONFORMANT_V2)
        result = SampleSheetValidator().validate(sheet, schema={"type": 123})
        if HAS_JSONSCHEMA:
            assert any(e.code == "SCHEMA_INVALID" for e in result.errors)
            assert not any(e.code == "SCHEMA_REF_UNRESOLVED" for e in result.errors)
        else:
            assert any(n.code == "SCHEMA_SKIPPED" for n in result.notes)


class TestEmptySheetRunsValidators:
    def test_pluggable_chain_runs_on_empty_sheet(self):
        # An empty sheet still reports EMPTY_SAMPLES, but the pluggable chain
        # (here a custom validator) must not be silently skipped.
        class _EmptySheet:
            def samples(self):
                return []

        def marker(_sheet):
            return [ValidationIssue("warning", "RAN_ANYWAY", "ran on empty sheet")]

        result = SampleSheetValidator().validate(_EmptySheet(), extra_validators=[marker])
        assert any(e.code == "EMPTY_SAMPLES" for e in result.errors)
        assert any(w.code == "RAN_ANYWAY" for w in result.warnings)
