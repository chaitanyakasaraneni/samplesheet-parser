"""
Tests for samplesheet_parser.splitter.SampleSheetSplitter.

Covers:
- Split by project: one file per Sample_Project
- Split by lane: one file per lane
- Header/reads/settings are preserved in each output file
- Samples with no project grouped under 'unassigned' with a warning
- Incomplete records (missing Sample_ID or Index) produce warnings and are skipped
- Empty input (no samples) returns a warning and no files
- Target version override (V2 input → V1 output)
- Custom prefix and suffix in output filenames
- SplitResult.summary() reflects outcome
- FileNotFoundError on missing input
- ValueError on invalid --by value
- Output directory is created if it does not exist
"""

from __future__ import annotations

from pathlib import Path

import pytest

from samplesheet_parser.splitter import SampleSheetSplitter

# ---------------------------------------------------------------------------
# Sheet content fixtures
# ---------------------------------------------------------------------------

_V2_MULTI_PROJECT = """\
[Header]
FileFormatVersion,2
RunName,CombinedRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,10
Index2Cycles,10

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,SampleA1,ATTACTCGAT,TATAGCCTGT,ProjectA
1,SampleA2,TCCGGAGAGA,ATAGAGGCGT,ProjectA
1,SampleB1,GCTTGTTTCC,CGTTAGAGTT,ProjectB
1,SampleB2,ATTCAGAAGT,CGATCTCGTT,ProjectB
1,SampleC1,GAATAATCCT,ACGGAGCGTT,ProjectC
"""

_V2_MULTI_LANE = """\
[Header]
FileFormatVersion,2
RunName,MultiLaneRun

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,10
Index2Cycles,10

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,Sample1,ATTACTCGAT,TATAGCCTGT,ProjectA
1,Sample2,TCCGGAGAGA,ATAGAGGCGT,ProjectA
2,Sample3,GCTTGTTTCC,CGTTAGAGTT,ProjectB
2,Sample4,ATTCAGAAGT,CGATCTCGTT,ProjectB
"""

_V2_NO_PROJECT = """\
[Header]
FileFormatVersion,2
RunName,NoProjectRun

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
1,Sample2,TCCGGAGAGA,ATAGAGGCGT
"""

_V1_MULTI_PROJECT = """\
[Header]
IEMFileVersion,5
Experiment Name,CombinedRun
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
1,SampleB1,SampleB1,D703,GCTTGTTT,D503,CGTTAGAG,ProjectB
1,SampleB2,SampleB2,D704,ATTCAGAA,D504,CGATCTCG,ProjectB
"""

_V2_INCOMPLETE = """\
[Header]
FileFormatVersion,2
RunName,IncompleteRun

[Reads]
Read1Cycles,151
Index1Cycles,10

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,SampleA1,ATTACTCGAT,ProjectA
1,,TCCGGAGAGA,ProjectA
1,SampleB1,GCTTGTTTCC,ProjectB
"""

_V2_EMPTY = """\
[Header]
FileFormatVersion,2
RunName,EmptyRun

[Reads]
Read1Cycles,151
Index1Cycles,10

[BCLConvert_Settings]

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests — split by project
# ---------------------------------------------------------------------------


def test_split_by_project_creates_one_file_per_project(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    assert set(result.output_files.keys()) == {"ProjectA", "ProjectB", "ProjectC"}
    assert result.sample_counts["ProjectA"] == 2
    assert result.sample_counts["ProjectB"] == 2
    assert result.sample_counts["ProjectC"] == 1
    assert not result.warnings


def test_split_by_project_output_files_exist(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    for path in result.output_files.values():
        assert path.exists()


def test_split_by_project_each_file_contains_correct_samples(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    project_a_content = result.output_files["ProjectA"].read_text(encoding="utf-8")
    assert "SampleA1" in project_a_content
    assert "SampleA2" in project_a_content
    assert "SampleB1" not in project_a_content

    project_b_content = result.output_files["ProjectB"].read_text(encoding="utf-8")
    assert "SampleB1" in project_b_content
    assert "SampleB2" in project_b_content
    assert "SampleA1" not in project_b_content


def test_split_by_project_header_preserved_in_each_file(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    for path in result.output_files.values():
        content = path.read_text(encoding="utf-8")
        assert "[Header]" in content
        assert "FileFormatVersion,2" in content
        assert "[Reads]" in content
        assert "Read1Cycles,151" in content
        assert "AdapterRead1" in content


def test_split_by_project_v1_input(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V1_MULTI_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    assert set(result.output_files.keys()) == {"ProjectA", "ProjectB"}
    assert result.sample_counts["ProjectA"] == 2
    assert result.sample_counts["ProjectB"] == 2


# ---------------------------------------------------------------------------
# Tests — split by lane
# ---------------------------------------------------------------------------


def test_split_by_lane_creates_one_file_per_lane(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI_LANE)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src, by="lane").split(out_dir)

    assert set(result.output_files.keys()) == {"1", "2"}
    assert result.sample_counts["1"] == 2
    assert result.sample_counts["2"] == 2


def test_split_by_lane_each_file_contains_correct_samples(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI_LANE)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src, by="lane").split(out_dir)

    lane1_content = result.output_files["1"].read_text(encoding="utf-8")
    assert "Sample1" in lane1_content
    assert "Sample3" not in lane1_content

    lane2_content = result.output_files["2"].read_text(encoding="utf-8")
    assert "Sample3" in lane2_content
    assert "Sample1" not in lane2_content


# ---------------------------------------------------------------------------
# Tests — unassigned samples
# ---------------------------------------------------------------------------


def test_split_no_project_grouped_under_unassigned(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_NO_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    assert "unassigned" in result.output_files
    assert result.sample_counts["unassigned"] == 2
    assert len(result.warnings) == 1
    assert "unassigned" in result.warnings[0]


def test_split_custom_unassigned_label(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_NO_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src, unassigned_label="misc").split(out_dir)

    assert "misc" in result.output_files


# ---------------------------------------------------------------------------
# Tests — incomplete records
# ---------------------------------------------------------------------------

_V2_MISSING_INDEX = """\
[Header]
FileFormatVersion,2
RunName,MissingIndexRun

[Reads]
Read1Cycles,151
Index1Cycles,10

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,SampleA1,ATTACTCGAT,ProjectA
1,SampleA2,,ProjectA
"""

_V2_ALL_INCOMPLETE = """\
[Header]
FileFormatVersion,2
RunName,AllIncompleteRun

[Reads]
Read1Cycles,151
Index1Cycles,10

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Sample_Project
1,,ATTACTCGAT,ProjectA
1,,TCCGGAGAGA,ProjectA
"""


def test_split_incomplete_records_skipped_with_warning(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_INCOMPLETE)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    assert result.sample_counts["ProjectA"] == 1
    assert result.sample_counts["ProjectB"] == 1
    assert any("incomplete" in w.lower() or "missing" in w.lower() for w in result.warnings)


def test_split_record_missing_index_warns(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MISSING_INDEX)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    assert result.sample_counts["ProjectA"] == 1
    assert any("Index" in w for w in result.warnings)


def test_split_group_all_incomplete_skipped(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_ALL_INCOMPLETE)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    assert "ProjectA" not in result.output_files
    assert any("no valid samples" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Tests — empty input
# ---------------------------------------------------------------------------


def test_split_empty_sheet_returns_warning_no_files(tmp_path: Path) -> None:
    src = _write(tmp_path, "empty.csv", _V2_EMPTY)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    assert not result.output_files
    assert result.warnings


# ---------------------------------------------------------------------------
# Tests — target version override
# ---------------------------------------------------------------------------


def test_split_target_version_v1_from_v2_input(tmp_path: Path) -> None:
    from samplesheet_parser.enums import SampleSheetVersion

    src = _write(tmp_path, "combined.csv", _V2_MULTI_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src, target_version=SampleSheetVersion.V1).split(out_dir)

    for path in result.output_files.values():
        content = path.read_text(encoding="utf-8")
        assert "IEMFileVersion" in content
        assert "[Data]" in content


# ---------------------------------------------------------------------------
# Tests — filename customisation
# ---------------------------------------------------------------------------


def test_split_custom_prefix(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir, prefix="Run001_")

    for fname in [p.name for p in result.output_files.values()]:
        assert fname.startswith("Run001_")


def test_split_custom_suffix(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir, suffix=".csv")

    for fname in [p.name for p in result.output_files.values()]:
        assert fname.endswith(".csv")
        assert "_SampleSheet" not in fname


# ---------------------------------------------------------------------------
# Tests — output directory creation
# ---------------------------------------------------------------------------


def test_split_creates_output_directory(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI_PROJECT)
    out_dir = tmp_path / "nested" / "output"
    assert not out_dir.exists()
    SampleSheetSplitter(src).split(out_dir)
    assert out_dir.exists()


# ---------------------------------------------------------------------------
# Tests — SplitResult
# ---------------------------------------------------------------------------


def test_split_result_summary_reflects_outcome(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    summary = result.summary()
    assert "3" in summary  # 3 files
    assert "5" in summary  # 5 samples total


def test_split_result_source_version(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI_PROJECT)
    out_dir = tmp_path / "split"
    result = SampleSheetSplitter(src).split(out_dir)

    assert result.source_version == "V2"


# ---------------------------------------------------------------------------
# Tests — error conditions
# ---------------------------------------------------------------------------


def test_split_missing_input_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        SampleSheetSplitter(tmp_path / "nonexistent.csv").split(tmp_path)


def test_split_invalid_by_raises_value_error() -> None:
    with pytest.raises(ValueError, match="by must be"):
        SampleSheetSplitter("any.csv", by="sample")


# ---------------------------------------------------------------------------
# Tests — public import
# ---------------------------------------------------------------------------


def test_splitter_importable_from_package() -> None:
    from samplesheet_parser import SampleSheetSplitter, SplitResult  # noqa: F401
