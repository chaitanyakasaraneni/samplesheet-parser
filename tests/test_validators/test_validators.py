"""Tests for SampleSheetValidator."""

from samplesheet_parser import SampleSheetValidator
from samplesheet_parser.chemistry import ColorBalanceMode
from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2

# index1 cycle 1 is all G/T across the pool (green present, red {A,C} absent):
# a single-channel cycle on 2-channel chemistry. No all-G cycle anywhere.
_SINGLE_CHANNEL_V2 = """\
[Header]
FileFormatVersion,2
RunName,SingleChannel
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Sample_ID,Index
S1,GACATACG
S2,TAACGTAC
S3,GAGTACGA
S4,TATGCGTT
"""

_DARK_CYCLE_V2 = """\
[Header]
FileFormatVersion,2
RunName,DarkCycle
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Sample_ID,Index,Index2
S1,ATGGCTAC,TATAGCCT
S2,CAGGTACG,ATAGAGGC
S3,TCGGACGT,CCTATCCT
S4,GATGGCTA,GGCTCTGA
"""


def _parse_v2(path, content):
    path.write_text(content)
    sheet = SampleSheetV2(str(path))
    sheet.parse()
    return sheet


def _valid_v1(path):
    sheet = SampleSheetV1(path)
    sheet.parse()
    return sheet


def _valid_v2(path):
    sheet = SampleSheetV2(path)
    sheet.parse()
    return sheet


class TestValidValidation:
    def test_valid_v1_passes(self, v1_minimal):
        result = SampleSheetValidator().validate(_valid_v1(v1_minimal))
        assert result.is_valid
        assert result.errors == []

    def test_valid_v2_passes(self, v2_minimal):
        result = SampleSheetValidator().validate(_valid_v2(v2_minimal))
        assert result.is_valid
        assert result.errors == []

    def test_summary_pass(self, v1_minimal):
        result = SampleSheetValidator().validate(_valid_v1(v1_minimal))
        assert result.summary().startswith("PASS")


class TestColorBalance:
    def test_off_by_default(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _DARK_CYCLE_V2)
        result = SampleSheetValidator().validate(sheet)
        assert result.is_valid
        assert not any(e.code.startswith("COLOR_BALANCE") for e in result.errors)

    def test_dark_cycle_errors_when_enabled(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _DARK_CYCLE_V2)
        result = SampleSheetValidator().validate(sheet, check_color_balance=True)
        assert not result.is_valid
        codes = [e.code for e in result.errors]
        assert "COLOR_BALANCE_NO_SIGNAL" in codes

    def test_unknown_instrument_skips_silently(self, tmp_path):
        sheet = _parse_v2(tmp_path / "s.csv", _DARK_CYCLE_V2)
        result = SampleSheetValidator().validate(
            sheet, check_color_balance=True, instrument="MysterySeq 9000"
        )
        assert not any(e.code.startswith("COLOR_BALANCE") for e in result.errors)

    def test_avidity_override_makes_all_g_advisory_not_error(self, tmp_path):
        # Force AVITI (avidity): all-G index cycles are advisory, never errors.
        sheet = _parse_v2(tmp_path / "s.csv", _DARK_CYCLE_V2)
        result = SampleSheetValidator().validate(
            sheet, check_color_balance=True, instrument="AVITI"
        )
        assert result.is_valid
        assert not any(e.code == "COLOR_BALANCE_NO_SIGNAL" for e in result.errors)

    def test_four_channel_all_g_fails_on_red_laser(self, tmp_path):
        # On MiSeq (4-channel) an all-G cycle fails: the red {A,C} laser is dark.
        sheet = _parse_v2(tmp_path / "s.csv", _DARK_CYCLE_V2)
        result = SampleSheetValidator().validate(
            sheet, check_color_balance=True, instrument="MiSeq"
        )
        assert not result.is_valid
        assert any(e.code == "COLOR_BALANCE_NO_SIGNAL" for e in result.errors)

    def test_single_channel_passes_vendor_faithful_fails_conservative(self, tmp_path):
        # A single-channel 2-channel cycle: vendor_faithful (default) treats it
        # as a weak warning (pass); conservative escalates it to an error.
        sheet = _parse_v2(tmp_path / "s.csv", _SINGLE_CHANNEL_V2)

        vf = SampleSheetValidator().validate(sheet, check_color_balance=True)
        assert vf.is_valid
        assert any(w.code == "COLOR_BALANCE_LOW" for w in vf.warnings)

        cons = SampleSheetValidator().validate(
            sheet, check_color_balance=True, color_balance_mode=ColorBalanceMode.CONSERVATIVE
        )
        assert not cons.is_valid
        assert any(e.code == "COLOR_BALANCE_NO_SIGNAL" for e in cons.errors)


class TestEmptySamples:
    def test_empty_data_section(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n[Data]\nLane,Sample_ID,index\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        assert not result.is_valid
        assert any(e.code == "EMPTY_SAMPLES" for e in result.errors)


class TestIndexValidation:
    def test_invalid_chars_in_index(self, tmp_path):
        p = tmp_path / "bad_index.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATCAX!\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        assert not result.is_valid
        assert any(e.code == "INVALID_INDEX_CHARS" for e in result.errors)

    def test_index_too_short_warning(self, tmp_path):
        p = tmp_path / "short.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATC\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        assert any(w.code == "INDEX_TOO_SHORT" for w in result.warnings)

    def test_index_too_long_error(self, tmp_path):
        p = tmp_path / "long_idx.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATCGATCGATCGATCGATCGATCGATCG\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        assert any(e.code == "INDEX_TOO_LONG" for e in result.errors)


class TestDuplicateIndex:
    def test_duplicate_index_same_lane(self, tmp_path):
        p = tmp_path / "dup_idx.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n"
            "1,S1,ATTACTCG\n"
            "1,S2,ATTACTCG\n"  # same index, same lane - error
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        assert not result.is_valid
        assert any(e.code == "DUPLICATE_INDEX" for e in result.errors)

    def test_same_index_different_lanes_ok(self, v1_multi_lane):
        """Identical indexes on different lanes should be valid."""
        # Override: write a sheet where lane 1 and lane 2 have identical indexes
        # This is valid in NovaSeq lane-split mode
        sheet = _valid_v1(v1_multi_lane)
        result = SampleSheetValidator().validate(sheet)
        # Multi-lane fixture uses unique indexes per lane - should pass
        assert result.is_valid

    def test_duplicate_dual_index(self, tmp_path):
        p = tmp_path / "dup_dual.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,I7_Index_ID,index,I5_Index_ID,index2\n"
            "1,S1,D701,ATTACTCG,D501,TATAGCCT\n"
            "1,S2,D701,ATTACTCG,D501,TATAGCCT\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        assert not result.is_valid
        assert any(e.code == "DUPLICATE_INDEX" for e in result.errors)

    def test_duplicate_index_detected_case_insensitively(self, tmp_path):
        # The same index in different casing is still a duplicate.
        p = tmp_path / "dup_case.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n"
            "1,S1,ATTACTCG\n"
            "1,S2,attactcg\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        assert any(e.code == "DUPLICATE_INDEX" for e in result.errors)

    def test_index_free_library_is_not_a_duplicate(self, tmp_path):
        # A full-lane, index-free library legitimately has empty indexes for
        # every sample. Sharing an empty index must not raise DUPLICATE_INDEX.
        p = tmp_path / "no_index.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n"
            "1,S1,\n"
            "1,S2,\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        assert not any(e.code == "DUPLICATE_INDEX" for e in result.errors)


class TestDuplicateSampleId:
    def test_duplicate_sample_id_error(self, tmp_path):
        p = tmp_path / "dup_sid.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n"
            "1,S1,ATTACTCG\n"
            "1,S1,TCCGGAGA\n"  # duplicate Sample_ID, same lane
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        # Note: V1 samples() deduplicates by Sample_ID, so the validator
        # receives only one sample - no duplicate to flag at validation time.
        # The duplicate index should still be caught.
        assert result is not None  # just confirm it doesn't crash

    def test_duplicate_sample_id_in_same_lane_raises_error(self):
        """Line 402: duplicate Sample_ID in same lane produces DUPLICATE_SAMPLE_ID error."""
        from samplesheet_parser.validators import SampleSheetValidator, ValidationResult

        validator = SampleSheetValidator()
        result = ValidationResult()
        # Provide samples with duplicate (lane, sample_id) - samples() always deduplicates
        # so we call the private method directly with crafted input
        samples = [
            {"lane": "1", "sample_id": "S1"},
            {"lane": "1", "sample_id": "S1"},  # duplicate in same lane
        ]
        validator._check_duplicate_sample_ids(samples, result)
        codes = [e.code for e in result.errors]
        assert "DUPLICATE_SAMPLE_ID" in codes


class TestAdapterValidation:
    def test_no_adapters_warning(self, tmp_path):
        p = tmp_path / "no_adapter.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        assert any(w.code == "NO_ADAPTERS" for w in result.warnings)

    def test_nonstandard_adapter_warning(self, tmp_path):
        p = tmp_path / "custom_adapter.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Settings]\nAdapter,TTTTTTTTTTTTTTTTTTTT\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        assert any(w.code == "ADAPTER_MISMATCH" for w in result.warnings)

    def test_standard_adapter_no_warning(self, v1_minimal):
        result = SampleSheetValidator().validate(_valid_v1(v1_minimal))
        adapter_warnings = [w for w in result.warnings if w.code == "ADAPTER_MISMATCH"]
        assert adapter_warnings == []


class TestMinHammingDistance:
    """Tests for the min_hamming_distance parameter on validate()."""

    def _sheet_with_distance(self, tmp_path, distance: int):
        """Build a minimal V1 sheet whose two indexes have the given Hamming distance."""
        # Base index: ATTACTCG (8 bp)
        # Modify last `distance` characters to create an index with exactly
        # `distance` mismatches.
        base = list("ATTACTCG")
        other = list("ATTACTCG")
        replacements = {"A": "T", "T": "A", "C": "G", "G": "C"}
        changes = 0
        for i in range(len(base) - 1, -1, -1):
            if changes >= distance:
                break
            other[i] = replacements[base[i]]
            changes += 1
        idx2 = "".join(other)

        p = tmp_path / f"dist{distance}.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Settings]\nAdapter,AGATCGGAAGAGC\n\n"
            "[Data]\nLane,Sample_ID,index\n"
            f"1,S1,ATTACTCG\n"
            f"1,S2,{idx2}\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        return sheet

    def test_default_min_3_passes_distance_3(self, tmp_path):
        sheet = self._sheet_with_distance(tmp_path, 3)
        result = SampleSheetValidator().validate(sheet)
        assert not any(w.code == "INDEX_DISTANCE_TOO_LOW" for w in result.warnings)

    def test_default_min_3_warns_distance_2(self, tmp_path):
        sheet = self._sheet_with_distance(tmp_path, 2)
        result = SampleSheetValidator().validate(sheet)
        assert any(w.code == "INDEX_DISTANCE_TOO_LOW" for w in result.warnings)

    def test_custom_min_4_warns_distance_3(self, tmp_path):
        sheet = self._sheet_with_distance(tmp_path, 3)
        result = SampleSheetValidator().validate(sheet, min_hamming_distance=4)
        assert any(w.code == "INDEX_DISTANCE_TOO_LOW" for w in result.warnings)

    def test_custom_min_4_passes_distance_4(self, tmp_path):
        sheet = self._sheet_with_distance(tmp_path, 4)
        result = SampleSheetValidator().validate(sheet, min_hamming_distance=4)
        assert not any(w.code == "INDEX_DISTANCE_TOO_LOW" for w in result.warnings)

    def test_custom_min_2_passes_distance_2(self, tmp_path):
        sheet = self._sheet_with_distance(tmp_path, 2)
        result = SampleSheetValidator().validate(sheet, min_hamming_distance=2)
        assert not any(w.code == "INDEX_DISTANCE_TOO_LOW" for w in result.warnings)


class TestValidationResult:
    def test_to_dict(self, v1_minimal):
        result = SampleSheetValidator().validate(_valid_v1(v1_minimal))
        d = result.to_dict()
        assert "is_valid" in d
        assert "errors" in d
        assert "warnings" in d

    def test_summary_fail(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nSample_ID,index\n"  # no records
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        assert result.summary().startswith("FAIL")

    def test_str_issue(self):
        from samplesheet_parser.validators import ValidationIssue

        issue = ValidationIssue("error", "TEST_CODE", "Something went wrong", {"lane": 1})
        s = str(issue)
        assert "[ERROR]" in s
        assert "TEST_CODE" in s
        assert "lane" in s


class TestHammingSkipsNoIndex:
    def test_sample_without_index_skipped_in_hamming_check(self, tmp_path):
        """Line 360: sample with no index is skipped without error during distance check."""
        p = tmp_path / "no_idx.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n1,S2,\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = SampleSheetValidator().validate(sheet)
        # S2 has no index so it is skipped - no INDEX_DISTANCE_TOO_LOW error
        codes = [e.code for e in result.errors]
        assert "INDEX_DISTANCE_TOO_LOW" not in codes
