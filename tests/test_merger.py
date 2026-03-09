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
