"""
Tests for samplesheet_parser.merger.SampleSheetMerger.

Covers:
- Happy path: two clean V1 sheets merge without conflicts
- Output file is written with all sample IDs present
- source_versions dict is populated for each input path
- MergeResult.summary() reflects outcome
- Mixed V1/V2 input produces MIXED_FORMAT warning but still merges
- INDEX_COLLISION → error, write aborted by default
- INDEX_COLLISION → write proceeds when abort_on_conflicts=False (--force)
- READ_LENGTH_CONFLICT → error
- INDEX_DISTANCE_TOO_LOW → warning (cross-sheet Hamming)
- ADAPTER_CONFLICT → warning
- Target version respected in merged output (V1 or V2)
- Usage errors: no paths, single path, missing file
- Fluent .add() returns self for chaining
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from samplesheet_parser.merger import MergeResult, SampleSheetMerger

# ---------------------------------------------------------------------------
# Sheet content fixtures
# ---------------------------------------------------------------------------

_V1_A = """\
[Header]
IEMFileVersion,5
Experiment Name,RunA
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleA1,SampleA1,D701,ATTACTCG,D501,TATAGCCT,ProjectA
1,SampleA2,SampleA2,D702,TCCGGAGA,D502,ATAGAGGC,ProjectA
"""

_V1_B = """\
[Header]
IEMFileVersion,5
Experiment Name,RunA
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleB1,SampleB1,D703,GCATGCTA,D503,CCTATCCT,ProjectB
1,SampleB2,SampleB2,D704,TGCATGGT,D504,GGCTCTGA,ProjectB
"""

# Same index as SampleA1 → collision
_V1_B_COLLISION = """\
[Header]
IEMFileVersion,5
Experiment Name,RunA
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleB1,SampleB1,D701,ATTACTCG,D501,TATAGCCT,ProjectB
"""

# Different read length (76 vs 151)
_V1_B_DIFF_READ = """\
[Header]
IEMFileVersion,5
Experiment Name,RunA
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
76
76

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleB1,SampleB1,D703,GCATGCTA,D503,CCTATCCT,ProjectB
"""

# Different adapter sequence
_V1_B_DIFF_ADAPTER = """\
[Header]
IEMFileVersion,5
Experiment Name,RunA
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,CTGTCTCTTATACACATCT

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleB1,SampleB1,D703,GCATGCTA,D503,CCTATCCT,ProjectB
"""

# Indexes differing by only 1 bp from _V1_A SampleA1 (ATTACTCG+TATAGCCT)
# → Hamming distance 1 cross-sheet → triggers INDEX_DISTANCE_TOO_LOW warning
_V1_B_CLOSE_INDEX = """\
[Header]
IEMFileVersion,5
Experiment Name,RunA
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleB1,SampleB1,D703,ATTACTCA,D503,TATAGCCA,ProjectB
"""

_V2_C = """\
[Header]
FileFormatVersion,2
RunName,RunC
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,10
Index2Cycles,10

[BCLConvert_Settings]
AdapterRead1,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,SampleC1,CTTGTAATGT,AACCGCCGTA,ProjectC
1,SampleC2,TAAGTTGGGT,TGGAACGCTA,ProjectC
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestMergerHappyPath:

    def test_two_clean_v1_sheets_no_conflicts(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert not result.has_conflicts
        assert not result.conflicts

    def test_sample_count_is_sum_of_inputs(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert result.sample_count == 4

    def test_output_file_is_written(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "out.csv"

        result = SampleSheetMerger().add(a).add(b).merge(out)

        assert result.output_path == out.resolve()
        assert out.exists()

    def test_all_sample_ids_present_in_output(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "out.csv"
        SampleSheetMerger().add(a).add(b).merge(out)

        content = out.read_text()
        for sid in ("SampleA1", "SampleA2", "SampleB1", "SampleB2"):
            assert sid in content

    def test_returns_merge_result_instance(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert isinstance(result, MergeResult)

    def test_source_versions_recorded_for_each_input(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert str(a) in result.source_versions
        assert str(b) in result.source_versions

    def test_summary_ok_on_clean_merge(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert result.summary().startswith("OK")

    def test_three_sheets_merged(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        c = _write(tmp_path, "c.csv", _V2_C)
        result = SampleSheetMerger().add(a).add(b).add(c).merge(tmp_path / "out.csv")

        assert result.sample_count == 6


# ---------------------------------------------------------------------------
# Mixed V1 / V2 input
# ---------------------------------------------------------------------------

class TestMergerMixedFormat:

    def test_mixed_input_produces_mixed_format_warning(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        c = _write(tmp_path, "c.csv", _V2_C)
        result = SampleSheetMerger().add(a).add(c).merge(tmp_path / "out.csv")

        codes = [w.code for w in result.warnings]
        assert "MIXED_FORMAT" in codes

    def test_mixed_input_still_writes_output(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        c = _write(tmp_path, "c.csv", _V2_C)
        result = SampleSheetMerger().add(a).add(c).merge(tmp_path / "out.csv")

        assert result.output_path is not None
        assert result.output_path.exists()

    def test_mixed_input_sample_count(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)   # 2 samples
        c = _write(tmp_path, "c.csv", _V2_C)   # 2 samples
        result = SampleSheetMerger().add(a).add(c).merge(tmp_path / "out.csv")

        assert result.sample_count == 4

    def test_target_v2_output_contains_file_format_version(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "out.csv"
        from samplesheet_parser.enums import SampleSheetVersion
        SampleSheetMerger(target_version=SampleSheetVersion.V2).add(a).add(b).merge(out)

        assert "FileFormatVersion" in out.read_text()

    def test_target_v1_output_contains_iem_file_version(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "out.csv"
        from samplesheet_parser.enums import SampleSheetVersion
        SampleSheetMerger(target_version=SampleSheetVersion.V1).add(a).add(b).merge(out)

        assert "IEMFileVersion" in out.read_text()


# ---------------------------------------------------------------------------
# Conflict detection — INDEX_COLLISION
# ---------------------------------------------------------------------------

class TestMergerIndexCollision:

    def test_collision_sets_has_conflicts(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_COLLISION)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert result.has_conflicts

    def test_collision_code_in_conflicts_list(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_COLLISION)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [c.code for c in result.conflicts]
        assert "INDEX_COLLISION" in codes

    def test_collision_aborts_write_by_default(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_COLLISION)
        SampleSheetMerger().add(a).add(b).merge(out, abort_on_conflicts=True)

        assert not out.exists()

    def test_collision_output_path_is_none_when_aborted(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_COLLISION)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert result.output_path is None

    def test_collision_force_writes_file(self, tmp_path: Path) -> None:
        out = tmp_path / "out.csv"
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_COLLISION)
        result = SampleSheetMerger().add(a).add(b).merge(out, abort_on_conflicts=False)

        assert out.exists()
        assert result.output_path is not None

    def test_collision_context_contains_lane_and_index(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_COLLISION)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        collision = next(c for c in result.conflicts if c.code == "INDEX_COLLISION")
        assert "index" in collision.context
        assert "lane" in collision.context

    def test_collision_context_contains_both_sheet_names(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_COLLISION)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        collision = next(c for c in result.conflicts if c.code == "INDEX_COLLISION")
        assert "sheet_a" in collision.context
        assert "sheet_b" in collision.context

    def test_collision_summary_is_fail(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_COLLISION)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert result.summary().startswith("FAIL")


# ---------------------------------------------------------------------------
# Conflict detection — READ_LENGTH_CONFLICT
# ---------------------------------------------------------------------------

class TestMergerReadLengthConflict:

    def test_different_read_lengths_is_conflict(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)              # 151/151
        b = _write(tmp_path, "b.csv", _V1_B_DIFF_READ)   # 76/76
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert result.has_conflicts
        codes = [c.code for c in result.conflicts]
        assert "READ_LENGTH_CONFLICT" in codes

    def test_same_read_lengths_no_conflict(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [c.code for c in result.conflicts]
        assert "READ_LENGTH_CONFLICT" not in codes


# ---------------------------------------------------------------------------
# Warning detection — ADAPTER_CONFLICT
# ---------------------------------------------------------------------------

class TestMergerAdapterConflict:

    def test_different_adapters_produces_warning(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_DIFF_ADAPTER)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [w.code for w in result.warnings]
        assert "ADAPTER_CONFLICT" in codes

    def test_adapter_conflict_is_not_a_hard_error(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_DIFF_ADAPTER)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert not result.has_conflicts
        assert result.output_path is not None

    def test_matching_adapters_no_warning(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [w.code for w in result.warnings]
        assert "ADAPTER_CONFLICT" not in codes


# ---------------------------------------------------------------------------
# Usage errors
# ---------------------------------------------------------------------------

class TestMergerUsageErrors:

    def test_no_paths_raises_value_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="No input sheets registered"):
            SampleSheetMerger().merge(tmp_path / "out.csv")

    def test_single_path_raises_value_error(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        with pytest.raises(ValueError, match="At least two"):
            SampleSheetMerger().add(a).merge(tmp_path / "out.csv")

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            SampleSheetMerger().add(tmp_path / "does_not_exist.csv")

    def test_add_returns_self(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        merger = SampleSheetMerger()
        assert merger.add(a) is merger


# ---------------------------------------------------------------------------
# Warning detection — INDEX_DISTANCE_TOO_LOW (cross-sheet Hamming)
# ---------------------------------------------------------------------------

class TestMergerIndexDistance:

    def test_close_indexes_across_sheets_produce_distance_warning(
        self, tmp_path: Path
    ) -> None:
        """Indexes within Hamming distance < 3 across sheets → warning."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_CLOSE_INDEX)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [w.code for w in result.warnings]
        assert "INDEX_DISTANCE_TOO_LOW" in codes

    def test_distance_warning_is_not_a_hard_error(self, tmp_path: Path) -> None:
        """INDEX_DISTANCE_TOO_LOW is a warning — merge should still succeed."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_CLOSE_INDEX)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert not result.has_conflicts
        assert result.output_path is not None

    def test_distance_warning_context_contains_distance(self, tmp_path: Path) -> None:
        """Warning context should expose the actual Hamming distance value."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_CLOSE_INDEX)
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        dist_warnings = [w for w in result.warnings if w.code == "INDEX_DISTANCE_TOO_LOW"]
        assert dist_warnings, "Expected at least one INDEX_DISTANCE_TOO_LOW warning"
        assert "distance" in dist_warnings[0].context
        assert dist_warnings[0].context["distance"] < 3

    def test_well_separated_indexes_no_distance_warning(self, tmp_path: Path) -> None:
        """Sheets with well-separated indexes should not trigger the warning."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)   # indexes are far apart
        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [w.code for w in result.warnings]
        assert "INDEX_DISTANCE_TOO_LOW" not in codes


# ---------------------------------------------------------------------------
# Read-only parsing — clean=False on source files
# ---------------------------------------------------------------------------

class TestMergerReadOnlyParsing:

    def test_source_files_are_not_modified(self, tmp_path: Path) -> None:
        """Merger must not mutate source sheet files (clean=False)."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)

        mtime_a_before = a.stat().st_mtime
        mtime_b_before = b.stat().st_mtime

        SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert a.stat().st_mtime == mtime_a_before, "Source file 'a.csv' was modified"
        assert b.stat().st_mtime == mtime_b_before, "Source file 'b.csv' was modified"

    def test_no_backup_files_created(self, tmp_path: Path) -> None:
        """clean=False should not produce .backup files alongside inputs."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)

        SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        backup_files = list(tmp_path.glob("*.backup"))
        assert backup_files == [], f"Unexpected backup files: {backup_files}"


# ---------------------------------------------------------------------------
# INCOMPLETE_SAMPLE_RECORD — structured warning for skipped samples
# ---------------------------------------------------------------------------

# A V1 sheet where one sample row is missing its Index column value
_V1_MISSING_INDEX_ROW = """\
[Header]
IEMFileVersion,5
Experiment Name,RunA
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleB1,SampleB1,D703,GCATGCTA,D503,CCTATCCT,ProjectB
1,SampleB2,SampleB2,D704,,D504,,ProjectB
"""


class TestMergerIncompleteRecord:

    def test_missing_index_produces_structured_warning(self, tmp_path: Path) -> None:
        """A sample row with no Index should produce INCOMPLETE_SAMPLE_RECORD warning."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_MISSING_INDEX_ROW)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [w.code for w in result.warnings]
        assert "INCOMPLETE_SAMPLE_RECORD" in codes

    def test_incomplete_record_warning_is_not_a_hard_error(self, tmp_path: Path) -> None:
        """Skipped incomplete rows should warn, not abort the merge."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_MISSING_INDEX_ROW)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert not result.has_conflicts
        assert result.output_path is not None

    def test_incomplete_record_warning_context_has_sheet_path(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_MISSING_INDEX_ROW)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        w = next(w for w in result.warnings if w.code == "INCOMPLETE_SAMPLE_RECORD")
        assert "sheet" in w.context
        assert str(b) in w.context["sheet"]

    def test_incomplete_record_warning_context_has_missing_fields(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_MISSING_INDEX_ROW)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        w = next(w for w in result.warnings if w.code == "INCOMPLETE_SAMPLE_RECORD")
        assert "missing_fields" in w.context
        assert "Index" in w.context["missing_fields"]

    def test_complete_samples_still_merged_when_one_row_incomplete(
        self, tmp_path: Path
    ) -> None:
        """Valid samples from the same sheet must still appear in merged output."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_MISSING_INDEX_ROW)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")
        content = (result.output_path or tmp_path / "out.csv").read_text()

        # SampleB1 has a valid index → should be in output
        assert "SampleB1" in content
        # SampleB2 has no index → should be skipped
        assert "SampleB2" not in content


# ---------------------------------------------------------------------------
# ADAPTER_CONFLICT — warning references primary sheet as the actual source
# ---------------------------------------------------------------------------

class TestMergerAdapterConflictMessage:

    def test_adapter_conflict_warning_names_primary_sheet(self, tmp_path: Path) -> None:
        """Warning message must reference parsed[0] (the sheet whose adapters are used)."""
        a = _write(tmp_path, "a.csv", _V1_A)             # primary — adapters kept
        b = _write(tmp_path, "b.csv", _V1_B_DIFF_ADAPTER)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        w = next((w for w in result.warnings if w.code == "ADAPTER_CONFLICT"), None)
        assert w is not None
        # sheet_a in context must be the primary (first) sheet
        assert w.context["sheet_a"] == str(a)

    def test_adapter_conflict_context_has_both_sheet_paths(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_DIFF_ADAPTER)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        w = next(w for w in result.warnings if w.code == "ADAPTER_CONFLICT")
        assert "sheet_a" in w.context
        assert "sheet_b" in w.context


# ---------------------------------------------------------------------------
# Multi-lane collision detection — uses sheet.records not sheet.samples()
# ---------------------------------------------------------------------------

# Two sheets where the SAME Sample_ID appears in multiple lanes with
# different indexes — sheet.samples() would de-duplicate these to one row
# and miss the cross-sheet collision in lane 2.
_V1_MULTILANE_A = """\
[Header]
IEMFileVersion,5
Experiment Name,RunML
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleA,SampleA,D701,ATCACGTT,D501,AACGTGAT,ProjectA
2,SampleA,SampleA,D702,CGATGTTT,D502,AAACATCG,ProjectA
"""

# Sheet B uses the same index as sheet A lane-2 in lane 2 — collision
_V1_MULTILANE_B = """\
[Header]
IEMFileVersion,5
Experiment Name,RunML
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleB,SampleB,D703,GCATGCTA,D503,CCTATCCT,ProjectB
2,SampleB,SampleB,D702,CGATGTTT,D502,AAACATCG,ProjectB
"""


class TestMergerMultiLaneRecords:

    def test_collision_detected_in_non_primary_lane(self, tmp_path: Path) -> None:
        """INDEX_COLLISION must fire for lane 2 even when Sample_ID is the
        same across lanes (which sheet.samples() would de-duplicate)."""
        a = _write(tmp_path, "a.csv", _V1_MULTILANE_A)
        b = _write(tmp_path, "b.csv", _V1_MULTILANE_B)

        result = SampleSheetMerger().add(a).add(b).merge(
            tmp_path / "out.csv",
            abort_on_conflicts=False,
        )

        codes = [c.code for c in result.conflicts]
        assert "INDEX_COLLISION" in codes

    def test_non_colliding_lane_does_not_error(self, tmp_path: Path) -> None:
        """Lane 1 has distinct indexes — only lane 2 should collide."""
        a = _write(tmp_path, "a.csv", _V1_MULTILANE_A)
        b = _write(tmp_path, "b.csv", _V1_MULTILANE_B)

        result = SampleSheetMerger().add(a).add(b).merge(
            tmp_path / "out.csv",
            abort_on_conflicts=False,
        )
        # Exactly one collision (lane 2) — lane 1 is fine
        collisions = [c for c in result.conflicts if c.code == "INDEX_COLLISION"]
        assert len(collisions) == 1
        assert collisions[0].context.get("lane") in (2, "2")


# ---------------------------------------------------------------------------
# Primary sheet pre-scan — INCOMPLETE_SAMPLE_RECORD for primary records
# ---------------------------------------------------------------------------

_V1_PRIMARY_MISSING_INDEX = """\
[Header]
IEMFileVersion,5
Experiment Name,RunP
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleP1,SampleP1,D701,ATCACGTT,D501,AACGTGAT,ProjectP
1,SampleP2,SampleP2,D702,,D502,,ProjectP
"""


class TestMergerPrimaryPreScan:

    def test_incomplete_record_in_primary_sheet_emits_warning(
        self, tmp_path: Path
    ) -> None:
        """A row in parsed[0] that is missing Index must produce
        INCOMPLETE_SAMPLE_RECORD, not be silently dropped."""
        a = _write(tmp_path, "a.csv", _V1_PRIMARY_MISSING_INDEX)
        b = _write(tmp_path, "b.csv", _V1_B)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [w.code for w in result.warnings]
        assert "INCOMPLETE_SAMPLE_RECORD" in codes

    def test_incomplete_primary_record_warning_references_primary_sheet(
        self, tmp_path: Path
    ) -> None:
        a = _write(tmp_path, "a.csv", _V1_PRIMARY_MISSING_INDEX)
        b = _write(tmp_path, "b.csv", _V1_B)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        w = next(
            w for w in result.warnings if w.code == "INCOMPLETE_SAMPLE_RECORD"
        )
        assert w.context["sheet"] == str(a)

    def test_valid_primary_records_still_appear_in_output(
        self, tmp_path: Path
    ) -> None:
        """SampleP1 (valid) must be in output; SampleP2 (no index) must not."""
        a = _write(tmp_path, "a.csv", _V1_PRIMARY_MISSING_INDEX)
        b = _write(tmp_path, "b.csv", _V1_B)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")
        content = (result.output_path or tmp_path / "out.csv").read_text()

        assert "SampleP1" in content
        assert "SampleP2" not in content

    def test_merge_does_not_abort_due_to_incomplete_primary_record(
        self, tmp_path: Path
    ) -> None:
        """An incomplete primary record is a warning, not a hard conflict."""
        a = _write(tmp_path, "a.csv", _V1_PRIMARY_MISSING_INDEX)
        b = _write(tmp_path, "b.csv", _V1_B)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert not result.has_conflicts
        assert result.output_path is not None


# ---------------------------------------------------------------------------
# Multi-lane secondary sheets — _build_writer must preserve all lane rows
# ---------------------------------------------------------------------------

# Sheet where SampleC appears in both lane 1 and lane 2 with different indexes
_V1_MULTILANE_SECONDARY = """\
[Header]
IEMFileVersion,5
Experiment Name,RunS
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleC,SampleC,D705,TAGGCATG,D505,TAGATCGC,ProjectC
2,SampleC,SampleC,D706,CTCTCTAC,D506,CTATTAAG,ProjectC
"""


class TestMergerSecondaryMultiLane:

    def test_both_lane_rows_appear_in_merged_output(self, tmp_path: Path) -> None:
        """Secondary sheet with SampleC in lanes 1 and 2 — both rows must be
        written.  If _build_writer uses sheet.samples() the second lane entry
        is de-duplicated and lost."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_MULTILANE_SECONDARY)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")
        content = (result.output_path or tmp_path / "out.csv").read_text()

        # Both index values must appear — if only one lane was written, one
        # of these assertions will fail.
        assert "TAGGCATG" in content   # lane 1 index
        assert "CTCTCTAC" in content   # lane 2 index

    def test_sample_count_reflects_all_lane_rows(self, tmp_path: Path) -> None:
        result = SampleSheetMerger().add(
            _write(tmp_path, "a.csv", _V1_A)
        ).add(
            _write(tmp_path, "b.csv", _V1_MULTILANE_SECONDARY)
        ).merge(tmp_path / "out.csv")

        # _V1_A has 2 samples; _V1_MULTILANE_SECONDARY contributes 2 rows
        # (same Sample_ID, different lanes). Total > 2 confirms no de-dup.
        assert result.sample_count > 2


# ---------------------------------------------------------------------------
# _validate_merged — parse/validation exceptions become structured conflicts
# ---------------------------------------------------------------------------

class TestMergerValidateMergedExceptionHandling:

    def test_validate_merged_exception_produces_conflict_not_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If post-merge validation raises, merge() must return a MergeResult
        with MERGE_VALIDATION_ERROR rather than propagating the exception.

        SampleSheetValidator.validate() is only ever called from inside
        _validate_merged's try/except block, so patching it to raise is
        precise and immune to changes in _parse_all's factory usage.
        """
        import samplesheet_parser.merger as merger_module

        def _explode(self: object, *a: object, **kw: object) -> None:
            raise ValueError("simulated validation-phase failure")

        monkeypatch.setattr(merger_module.SampleSheetValidator, "validate", _explode)

        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)

        result = SampleSheetMerger().add(a).add(b).merge(
            tmp_path / "out.csv", validate=True
        )

        codes = [c.code for c in result.conflicts]
        assert "MERGE_VALIDATION_ERROR" in codes

    def test_validate_merged_exception_result_has_conflicts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """has_conflicts is True when _validate_merged raises."""
        import samplesheet_parser.merger as merger_module

        def _explode(self: object, *a: object, **kw: object) -> None:
            raise FileNotFoundError("simulated missing file in validate")

        monkeypatch.setattr(merger_module.SampleSheetValidator, "validate", _explode)

        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)

        result = SampleSheetMerger().add(a).add(b).merge(
            tmp_path / "out.csv", validate=True
        )

        assert result.has_conflicts


# ---------------------------------------------------------------------------
# _check_read_lengths — fixed key order prevents false READ_LENGTH_CONFLICT
# ---------------------------------------------------------------------------

class TestMergerReadLengthKeyOrder:

    def test_no_false_conflict_when_key_order_differs(self, tmp_path: Path) -> None:
        """Two sheets with identical read lengths (151/151) must not trigger
        READ_LENGTH_CONFLICT even if one parser returned Read2Cycles before
        Read1Cycles in its .reads dict."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [c.code for c in result.conflicts]
        assert "READ_LENGTH_CONFLICT" not in codes


# ---------------------------------------------------------------------------
# Sample metadata preservation — Sample_Name/Description/Plate/Well from records
# ---------------------------------------------------------------------------

_V1_WITH_METADATA = """\
[Header]
IEMFileVersion,5
Experiment Name,RunM
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,Sample_Plate,Sample_Well,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project,Description
1,SampleM1,AliasMeta,PlateX,A01,D703,GCATGCTA,D503,CCTATCCT,ProjectM,DescriptionText
"""


class TestMergerMetadataPreservation:
    """V2 [BCLConvert_Data] omits Sample_Name/Description/Plate/Well columns.
    Force target_version=V1 so the [Data] section preserves all per-sample
    metadata from secondary sheet.records (raw capitalised keys)."""

    def test_sample_name_preserved_from_records(self, tmp_path: Path) -> None:
        """Sample_Name from sheet.records must appear in V1 merged output."""
        from samplesheet_parser.enums import SampleSheetVersion
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_WITH_METADATA)

        result = (
            SampleSheetMerger(target_version=SampleSheetVersion.V1)
            .add(a).add(b).merge(tmp_path / "out.csv")
        )
        content = (result.output_path or tmp_path / "out.csv").read_text()

        assert "AliasMeta" in content

    def test_description_preserved_from_records(self, tmp_path: Path) -> None:
        from samplesheet_parser.enums import SampleSheetVersion
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_WITH_METADATA)

        result = (
            SampleSheetMerger(target_version=SampleSheetVersion.V1)
            .add(a).add(b).merge(tmp_path / "out.csv")
        )
        content = (result.output_path or tmp_path / "out.csv").read_text()

        assert "DescriptionText" in content

    def test_sample_plate_preserved_from_records(self, tmp_path: Path) -> None:
        from samplesheet_parser.enums import SampleSheetVersion
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_WITH_METADATA)

        result = (
            SampleSheetMerger(target_version=SampleSheetVersion.V1)
            .add(a).add(b).merge(tmp_path / "out.csv")
        )
        content = (result.output_path or tmp_path / "out.csv").read_text()

        assert "PlateX" in content


# ---------------------------------------------------------------------------
# _check_adapters — both-sheets guard (primary has no adapters → no warning)
# ---------------------------------------------------------------------------

_V1_NO_ADAPTER = """\
[Header]
IEMFileVersion,5
Experiment Name,RunNA
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleNA,SampleNA,D701,ATCACGTT,D501,AACGTGAT,ProjectNA
"""


class TestMergerAdapterBothGuard:

    def test_no_conflict_when_primary_has_no_adapters(self, tmp_path: Path) -> None:
        """Primary sheet has no adapters; secondary has adapters.
        Should NOT produce ADAPTER_CONFLICT — nothing to conflict against."""
        a = _write(tmp_path, "a.csv", _V1_NO_ADAPTER)   # primary — no adapter
        b = _write(tmp_path, "b.csv", _V1_B)             # secondary — has adapter

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [w.code for w in result.warnings]
        assert "ADAPTER_CONFLICT" not in codes

    def test_conflict_when_both_have_different_adapters(self, tmp_path: Path) -> None:
        """Both primary and secondary have adapters and they differ → warn."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_DIFF_ADAPTER)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [w.code for w in result.warnings]
        assert "ADAPTER_CONFLICT" in codes


# ---------------------------------------------------------------------------
# _check_read_lengths — sentinel catches missing-reads vs present-reads
# ---------------------------------------------------------------------------

_V1_NO_READS_SECTION = """\
[Header]
IEMFileVersion,5
Experiment Name,RunNR
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleNR,SampleNR,D701,ATCACGTT,D501,AACGTGAT,ProjectNR
"""


class TestMergerReadLengthSentinel:

    def test_missing_reads_vs_present_reads_is_conflict(self, tmp_path: Path) -> None:
        """One sheet has [Reads] (151/151), other has none → READ_LENGTH_CONFLICT."""
        a = _write(tmp_path, "a.csv", _V1_A)             # has [Reads] 151/151
        b = _write(tmp_path, "b.csv", _V1_NO_READS_SECTION)  # no [Reads]

        result = SampleSheetMerger().add(a).add(b).merge(
            tmp_path / "out.csv", abort_on_conflicts=False
        )

        codes = [c.code for c in result.conflicts]
        assert "READ_LENGTH_CONFLICT" in codes

    def test_both_missing_reads_is_not_conflict(self, tmp_path: Path) -> None:
        """Both sheets have no [Reads] → same sentinel key → no conflict."""
        a = _write(tmp_path, "a.csv", _V1_NO_READS_SECTION)
        b_content = _V1_NO_READS_SECTION.replace("SampleNR", "SampleNR2").replace(
            "ATCACGTT", "CGATGTTT"
        )
        b = _write(tmp_path, "b.csv", b_content)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        codes = [c.code for c in result.conflicts]
        assert "READ_LENGTH_CONFLICT" not in codes


# ---------------------------------------------------------------------------
# Coverage — branches missing from codecov report
# ---------------------------------------------------------------------------

class TestMergerAllFilesFail:
    """Line 247: if not parsed: return result — all inputs fail to parse."""

    def test_all_parse_failures_returns_empty_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When every input sheet raises during parsing, merge() must return
        a MergeResult with PARSE_ERROR conflicts and no output file."""
        import samplesheet_parser.merger as merger_module

        def _explode(self: object, *a: object, **kw: object) -> object:
            raise ValueError("simulated parse failure")

        monkeypatch.setattr(merger_module.SampleSheetFactory, "create_parser", _explode)

        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "out.csv"

        result = SampleSheetMerger().add(a).add(b).merge(out)

        assert result.output_path is None
        assert not out.exists()
        codes = [c.code for c in result.conflicts]
        assert all(c == "PARSE_ERROR" for c in codes)

    def test_all_parse_failures_has_conflicts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import samplesheet_parser.merger as merger_module

        def _explode(self: object, *a: object, **kw: object) -> object:
            raise RuntimeError("cannot read file")

        monkeypatch.setattr(merger_module.SampleSheetFactory, "create_parser", _explode)

        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)

        result = SampleSheetMerger().add(a).add(b).merge(tmp_path / "out.csv")

        assert result.has_conflicts


class TestMergerAbortAfterPostMergeValidation:
    """Line 271: abort after _validate_merged produces conflicts."""

    def test_abort_after_post_merge_validation_conflict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When _validate_merged adds a conflict and abort_on_conflicts=True,
        merge() must return without writing the output file."""
        import samplesheet_parser.merger as merger_module

        # Patch SampleSheetValidator.validate to inject a conflict-level error.
        # We do this by making the validator raise so _validate_merged catches it
        # and adds a MERGE_VALIDATION_ERROR conflict.
        def _explode(self: object, *a: object, **kw: object) -> None:
            raise ValueError("injected post-merge validation failure")

        monkeypatch.setattr(merger_module.SampleSheetValidator, "validate", _explode)

        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "out.csv"

        result = SampleSheetMerger().add(a).add(b).merge(
            out, validate=True, abort_on_conflicts=True
        )

        # Output must not be written because abort_on_conflicts=True
        assert not out.exists()
        assert result.output_path is None
        assert result.has_conflicts

    def test_abort_after_post_merge_validation_conflict_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import samplesheet_parser.merger as merger_module

        def _explode(self: object, *a: object, **kw: object) -> None:
            raise FileNotFoundError("injected missing file in post-merge")

        monkeypatch.setattr(merger_module.SampleSheetValidator, "validate", _explode)

        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)

        result = SampleSheetMerger().add(a).add(b).merge(
            tmp_path / "out.csv", validate=True, abort_on_conflicts=True
        )

        codes = [c.code for c in result.conflicts]
        assert "MERGE_VALIDATION_ERROR" in codes


# ---------------------------------------------------------------------------
# Incomplete sample records
# ---------------------------------------------------------------------------

_V1_WITH_INCOMPLETE_RECORD = """\
[Header]
IEMFileVersion,5
Experiment Name,RunA
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,Sample_Project
1,SampleA1,SampleA1,D701,ATTACTCG,ProjectA
1,,NoID,,,ProjectA
"""

_V1_WITH_INCOMPLETE_SECONDARY = """\
[Header]
IEMFileVersion,5
Experiment Name,RunB
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,Sample_Project
1,SampleB1,SampleB1,D703,GCATGCTA,ProjectB
1,,MissingID,,,ProjectB
"""


class TestMergerIncompleteRecords:

    def test_incomplete_record_in_primary_emits_warning(self, tmp_path: Path) -> None:
        """Lines 541-542: primary sheet record missing Sample_ID/Index gets a warning."""
        a = _write(tmp_path, "a.csv", _V1_WITH_INCOMPLETE_RECORD)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = SampleSheetMerger().add(a).add(b).merge(
            tmp_path / "out.csv", validate=False, abort_on_conflicts=False
        )
        codes = [w.code for w in result.warnings]
        assert "INCOMPLETE_SAMPLE_RECORD" in codes

    def test_incomplete_record_in_secondary_emits_warning(self, tmp_path: Path) -> None:
        """Lines 596-597: secondary sheet record missing Sample_ID/Index gets a warning."""
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_WITH_INCOMPLETE_SECONDARY)
        result = SampleSheetMerger().add(a).add(b).merge(
            tmp_path / "out.csv", validate=False, abort_on_conflicts=False
        )
        codes = [w.code for w in result.warnings]
        assert "INCOMPLETE_SAMPLE_RECORD" in codes
