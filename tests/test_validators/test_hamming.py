"""
Tests for the Hamming distance index check added to SampleSheetValidator.

Covers:
- _hamming_distance helper directly
- _check_index_distances via SampleSheetValidator.validate()
- V1 and V2 sheets
- Single-index and dual-index sheets
- Multi-lane isolation (problems in lane 1 don't bleed into lane 2)
- Custom min_distance threshold
- Interaction with existing duplicate-index check (distance=0 case)
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from samplesheet_parser.validators import (
    MIN_HAMMING_DISTANCE,
    SampleSheetValidator,
    ValidationResult,
    _hamming_distance,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content).lstrip())
    return p


def _validate(path: Path) -> ValidationResult:
    from samplesheet_parser.factory import SampleSheetFactory
    sheet = SampleSheetFactory().create_parser(path, parse=True, clean=False)
    return SampleSheetValidator().validate(sheet)


def _distance_warnings(result: ValidationResult) -> list:
    return [w for w in result.warnings if w.code == "INDEX_DISTANCE_TOO_LOW"]


# ---------------------------------------------------------------------------
# _hamming_distance unit tests
# ---------------------------------------------------------------------------

class TestHammingDistance:
    def test_identical_sequences(self):
        assert _hamming_distance("ATTACTCG", "ATTACTCG") == 0

    def test_one_mismatch(self):
        assert _hamming_distance("ATTACTCG", "ATTACTCA") == 1

    def test_two_mismatches(self):
        assert _hamming_distance("ATTACTCG", "ATTACTAA") == 2

    def test_all_mismatches(self):
        assert _hamming_distance("AAAA", "CCCC") == 4

    def test_completely_different_8bp(self):
        assert _hamming_distance("ATTACTCG", "GCTAGCTA") == 6

    def test_unequal_length_uses_shorter(self):
        # "ATTACTCG" vs "ATTACTCGAT" — first 8 chars match → distance 0
        assert _hamming_distance("ATTACTCG", "ATTACTCGAT") == 0

    def test_unequal_length_with_mismatch(self):
        # "ATTACTCG" vs "GTTACTCGAT" — first char differs → distance 1
        assert _hamming_distance("ATTACTCG", "GTTACTCGAT") == 1

    def test_empty_strings(self):
        assert _hamming_distance("", "") == 0

    def test_single_char_match(self):
        assert _hamming_distance("A", "A") == 0

    def test_single_char_mismatch(self):
        assert _hamming_distance("A", "C") == 1

    def test_symmetric(self):
        assert _hamming_distance("ATTACTCG", "ATTACTCA") == \
               _hamming_distance("ATTACTCA", "ATTACTCG")

    def test_min_hamming_distance_constant(self):
        assert MIN_HAMMING_DISTANCE == 3


# ---------------------------------------------------------------------------
# V2 single-index sheets
# ---------------------------------------------------------------------------

class TestV2SingleIndex:
    def test_well_separated_indexes_no_warning(self, tmp_path):
        sheet = _write(tmp_path, "ok.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,TCCGGAGA,Proj
1,S3,TAGGCATG,Proj
""")
        result = _validate(sheet)
        assert _distance_warnings(result) == []

    def test_distance_2_triggers_warning(self, tmp_path):
        # ATTACTCG vs ATTACTAA — 2 mismatches, below threshold of 3
        sheet = _write(tmp_path, "close.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,ATTACTAA,Proj
""")
        result = _validate(sheet)
        warnings = _distance_warnings(result)
        assert len(warnings) == 1
        assert warnings[0].context["distance"] == 2
        assert {"S1", "S2"} == {
            warnings[0].context["sample_a"],
            warnings[0].context["sample_b"],
        }

    def test_distance_1_triggers_warning(self, tmp_path):
        sheet = _write(tmp_path, "dist1.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,ATTACTCA,Proj
""")
        result = _validate(sheet)
        warnings = _distance_warnings(result)
        assert len(warnings) == 1
        assert warnings[0].context["distance"] == 1

    def test_distance_exactly_3_no_warning(self, tmp_path):
        # ATTACTCG vs GTTAAACG — exactly 3 mismatches (positions 0, 4, 5)
        sheet = _write(tmp_path, "dist3.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,GTTAAACG,Proj
""")
        assert _hamming_distance("ATTACTCG", "GTTAAACG") == 3
        result = _validate(sheet)
        assert _distance_warnings(result) == []

    def test_three_samples_one_close_pair(self, tmp_path):
        # S1/S2 are fine, S2/S3 are fine, S1/S3 are too close
        # ATTACTCG vs ATTACTAA = 2
        sheet = _write(tmp_path, "three.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,TCCGGAGA,Proj
1,S3,ATTACTAA,Proj
""")
        result = _validate(sheet)
        warnings = _distance_warnings(result)
        assert len(warnings) == 1
        flagged = {warnings[0].context["sample_a"], warnings[0].context["sample_b"]}
        assert flagged == {"S1", "S3"}

    def test_multiple_close_pairs_all_reported(self, tmp_path):
        # S1≈S2 (dist 1) and S3≈S4 (dist 1) — two separate warnings
        sheet = _write(tmp_path, "multi.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,ATTACTCA,Proj
1,S3,TCCGGAGA,Proj
1,S4,TCCGGAGC,Proj
""")
        result = _validate(sheet)
        warnings = _distance_warnings(result)
        assert len(warnings) == 2


# ---------------------------------------------------------------------------
# V2 dual-index sheets — combined index comparison
# ---------------------------------------------------------------------------

class TestV2DualIndex:
    def test_close_i7_rescued_by_i5(self, tmp_path):
        # I7: ATTACTCG vs ATTACTCA (dist 1 — too close alone)
        # I5: TATAGCCT vs GCTAGCTA (dist 6 — very different)
        # Combined: dist = 1 + 6 = 7 → should NOT warn
        sheet = _write(tmp_path, "dual_ok.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,S1,ATTACTCG,TATAGCCT,Proj
1,S2,ATTACTCA,GCTAGCTA,Proj
""")
        combined_dist = _hamming_distance(
            "ATTACTCG" + "TATAGCCT",
            "ATTACTCA" + "GCTAGCTA",
        )
        assert combined_dist >= MIN_HAMMING_DISTANCE
        result = _validate(sheet)
        assert _distance_warnings(result) == []

    def test_close_combined_index_warns(self, tmp_path):
        # Both I7 and I5 are very similar → combined distance still low
        sheet = _write(tmp_path, "dual_bad.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,S1,ATTACTCG,TATAGCCT,Proj
1,S2,ATTACTCA,TATAGCCA,Proj
""")
        combined_dist = _hamming_distance(
            "ATTACTCG" + "TATAGCCT",
            "ATTACTCA" + "TATAGCCA",
        )
        assert combined_dist < MIN_HAMMING_DISTANCE
        result = _validate(sheet)
        assert len(_distance_warnings(result)) == 1

    def test_context_contains_combined_index(self, tmp_path):
        sheet = _write(tmp_path, "dual_ctx.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,S1,ATTACTCG,TATAGCCT,Proj
1,S2,ATTACTCA,TATAGCCA,Proj
""")
        result = _validate(sheet)
        w = _distance_warnings(result)[0]
        # index_a and index_b in context should be the combined strings
        assert len(w.context["index_a"]) == 16  # 8 + 8
        assert len(w.context["index_b"]) == 16


# ---------------------------------------------------------------------------
# Multi-lane isolation
# ---------------------------------------------------------------------------

class TestMultiLane:
    def test_close_indexes_in_different_lanes_no_warning(self, tmp_path):
        # S1 in lane 1 and S2 in lane 2 have identical indexes — valid
        # because they demultiplex independently per lane
        sheet = _write(tmp_path, "lanes_ok.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
2,S2,ATTACTCG,Proj
""")
        result = _validate(sheet)
        assert _distance_warnings(result) == []

    def test_close_indexes_within_lane_warns(self, tmp_path):
        # S1 and S2 are in the same lane with close indexes → warn
        # S3 and S4 are in lane 2 with well-separated indexes → no warn
        sheet = _write(tmp_path, "lanes_mixed.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,ATTACTCA,Proj
2,S3,TCCGGAGA,Proj
2,S4,GCTAGCTA,Proj
""")
        result = _validate(sheet)
        warnings = _distance_warnings(result)
        assert len(warnings) == 1
        assert warnings[0].context["lane"] == "1"

    def test_warning_context_contains_lane(self, tmp_path):
        sheet = _write(tmp_path, "lane_ctx.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
3,S1,ATTACTCG,Proj
3,S2,ATTACTCA,Proj
""")
        result = _validate(sheet)
        w = _distance_warnings(result)[0]
        assert w.context["lane"] == "3"


# ---------------------------------------------------------------------------
# V1 sheets
# ---------------------------------------------------------------------------

class TestV1Sheets:
    def test_v1_close_indexes_warns(self, tmp_path):
        sheet = _write(tmp_path, "v1_close.csv", """\
[Header]
IEMFileVersion,5
Experiment Name,TestRun
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,CTGTCTCTTATACACATCT

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,Sample_Project
1,S1,S1,D701,ATTACTCG,Proj
1,S2,S2,D702,ATTACTCA,Proj
""")
        result = _validate(sheet)
        warnings = _distance_warnings(result)
        assert len(warnings) == 1
        assert warnings[0].context["distance"] == 1

    def test_v1_well_separated_no_warning(self, tmp_path):
        sheet = _write(tmp_path, "v1_ok.csv", """\
[Header]
IEMFileVersion,5
Experiment Name,TestRun
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,CTGTCTCTTATACACATCT

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,Sample_Project
1,S1,S1,D701,ATTACTCG,Proj
1,S2,S2,D702,TCCGGAGA,Proj
1,S3,S3,D703,TAGGCATG,Proj
""")
        result = _validate(sheet)
        assert _distance_warnings(result) == []


# ---------------------------------------------------------------------------
# Custom threshold
# ---------------------------------------------------------------------------

class TestCustomThreshold:
    def test_custom_min_distance_stricter(self, tmp_path):
        # Distance of 3 is fine at default threshold but should warn at 4
        sheet = _write(tmp_path, "strict.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,GTTAAACG,Proj
""")
        assert _hamming_distance("ATTACTCG", "GTTAAACG") == 3
        from samplesheet_parser.factory import SampleSheetFactory
        from samplesheet_parser.validators import ValidationResult
        parsed = SampleSheetFactory().create_parser(sheet, parse=True, clean=False)
        samples = parsed.samples()

        # Default threshold (3) — no warning
        result_default = ValidationResult()
        SampleSheetValidator()._check_index_distances(
            samples, result_default, min_distance=3
        )
        assert _distance_warnings(result_default) == []

        # Stricter threshold (4) — should warn
        result_strict = ValidationResult()
        SampleSheetValidator()._check_index_distances(
            samples, result_strict, min_distance=4
        )
        assert len(_distance_warnings(result_strict)) == 1

    def test_custom_min_distance_in_context(self, tmp_path):
        sheet = _write(tmp_path, "ctx_thresh.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,ATTACTCA,Proj
""")
        from samplesheet_parser.factory import SampleSheetFactory
        parsed = SampleSheetFactory().create_parser(sheet, parse=True, clean=False)
        samples = parsed.samples()

        result = ValidationResult()
        SampleSheetValidator()._check_index_distances(
            samples, result, min_distance=5
        )
        w = _distance_warnings(result)[0]
        assert w.context["min_distance"] == 5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_sample_no_warning(self, tmp_path):
        sheet = _write(tmp_path, "single.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
""")
        result = _validate(sheet)
        assert _distance_warnings(result) == []

    def test_duplicate_index_is_error_not_distance_warning(self, tmp_path):
        # Identical indexes are caught by DUPLICATE_INDEX (error),
        # not by INDEX_DISTANCE_TOO_LOW (warning)
        sheet = _write(tmp_path, "dup.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,ATTACTCG,Proj
""")
        result = _validate(sheet)
        error_codes = {e.code for e in result.errors}
        assert "DUPLICATE_INDEX" in error_codes
        # Distance warning may or may not be present; what matters is
        # the error is raised and result is invalid
        assert not result.is_valid

    def test_warning_does_not_invalidate_result(self, tmp_path):
        # INDEX_DISTANCE_TOO_LOW is a warning — is_valid should stay True
        sheet = _write(tmp_path, "warn_valid.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,ATTACTCA,Proj
""")
        result = _validate(sheet)
        assert len(_distance_warnings(result)) == 1
        assert result.is_valid  # warning, not error

    def test_warning_message_mentions_bleedthrough(self, tmp_path):
        sheet = _write(tmp_path, "msg.csv", """\
[Header]
FileFormatVersion,2
RunName,TestRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,0

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,S1,ATTACTCG,Proj
1,S2,ATTACTCA,Proj
""")
        result = _validate(sheet)
        w = _distance_warnings(result)[0]
        assert "bleed" in w.message.lower() or "distance" in w.message.lower()
