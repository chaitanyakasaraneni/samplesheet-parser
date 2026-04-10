"""
Tests for samplesheet_parser.filter.SampleSheetFilter.

Covers:
- Filter by project (exact match)
- Filter by lane (string and int)
- Filter by sample_id (exact and glob pattern)
- Multiple criteria ANDed together
- No matches → no file written, matched_count=0, exit via FilterResult
- Header/reads/settings preserved in filtered output
- V1 and V2 input sheets
- Target version override (V2 input → V1 output)
- FilterResult.summary() reflects outcome
- ValueError when no criteria provided
- FileNotFoundError on missing input
- Public import from samplesheet_parser
"""

from __future__ import annotations

from pathlib import Path

import pytest

from samplesheet_parser.filter import SampleSheetFilter

# ---------------------------------------------------------------------------
# Sheet content
# ---------------------------------------------------------------------------

_V2_MULTI = """\
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
2,SampleB1,GCTTGTTTCC,CGTTAGAGTT,ProjectB
2,SampleB2,ATTCAGAAGT,CGATCTCGTT,ProjectB
1,CTRL_A,GAATAATCCT,ACGGAGCGTT,Controls
2,CTRL_B,TAAGGCGAAT,GCGTAAGATT,Controls
"""

_V1_MULTI = """\
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
2,SampleB1,SampleB1,D703,GCTTGTTT,D503,CGTTAGAG,ProjectB
2,SampleB2,SampleB2,D704,ATTCAGAA,D504,CGATCTCG,ProjectB
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests — filter by project
# ---------------------------------------------------------------------------


def test_filter_by_project_keeps_matching_samples(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, project="ProjectA")

    assert result.matched_count == 2
    assert result.total_count == 6
    assert out.exists()


def test_filter_by_project_excludes_other_projects(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    SampleSheetFilter(src).filter(out, project="ProjectA")

    content = out.read_text(encoding="utf-8")
    assert "SampleA1" in content
    assert "SampleA2" in content
    assert "SampleB1" not in content
    assert "CTRL_A" not in content


def test_filter_by_project_v1_input(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V1_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, project="ProjectB")

    assert result.matched_count == 2
    content = out.read_text(encoding="utf-8")
    assert "SampleB1" in content
    assert "SampleA1" not in content


# ---------------------------------------------------------------------------
# Tests — filter by lane
# ---------------------------------------------------------------------------


def test_filter_by_lane_string(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, lane="1")

    assert result.matched_count == 3  # SampleA1, SampleA2, CTRL_A


def test_filter_by_lane_int(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, lane=2)

    assert result.matched_count == 3  # SampleB1, SampleB2, CTRL_B


def test_filter_by_lane_excludes_other_lanes(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    SampleSheetFilter(src).filter(out, lane="1")

    content = out.read_text(encoding="utf-8")
    assert "SampleA1" in content
    assert "SampleB1" not in content


# ---------------------------------------------------------------------------
# Tests — filter by sample_id
# ---------------------------------------------------------------------------


def test_filter_by_sample_id_exact(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, sample_id="SampleA1")

    assert result.matched_count == 1
    content = out.read_text(encoding="utf-8")
    assert "SampleA1" in content
    assert "SampleA2" not in content


def test_filter_by_sample_id_glob_prefix(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, sample_id="CTRL_*")

    assert result.matched_count == 2
    content = out.read_text(encoding="utf-8")
    assert "CTRL_A" in content
    assert "CTRL_B" in content
    assert "SampleA1" not in content


def test_filter_by_sample_id_glob_wildcard(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, sample_id="Sample*")

    assert result.matched_count == 4


# ---------------------------------------------------------------------------
# Tests — multiple criteria (ANDed)
# ---------------------------------------------------------------------------


def test_filter_project_and_lane(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, project="ProjectA", lane="1")

    assert result.matched_count == 2
    content = out.read_text(encoding="utf-8")
    assert "SampleA1" in content
    assert "SampleB1" not in content


def test_filter_project_and_sample_id_glob(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, project="ProjectA", sample_id="SampleA1")

    assert result.matched_count == 1


def test_filter_lane_and_sample_id(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, lane="1", sample_id="CTRL_*")

    assert result.matched_count == 1  # only CTRL_A is in lane 1


# ---------------------------------------------------------------------------
# Tests — no matches
# ---------------------------------------------------------------------------


def test_filter_no_match_returns_zero_count(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, project="NonExistentProject")

    assert result.matched_count == 0
    assert result.output_path is None
    assert not out.exists()


def test_filter_no_match_summary_has_no_output(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, project="Ghost")

    assert "no output" in result.summary().lower()


# ---------------------------------------------------------------------------
# Tests — header/settings preservation
# ---------------------------------------------------------------------------


def test_filter_preserves_header_and_settings(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    SampleSheetFilter(src).filter(out, project="ProjectA")

    content = out.read_text(encoding="utf-8")
    assert "[Header]" in content
    assert "FileFormatVersion,2" in content
    assert "[Reads]" in content
    assert "Read1Cycles,151" in content
    assert "AdapterRead1" in content


# ---------------------------------------------------------------------------
# Tests — target version override
# ---------------------------------------------------------------------------


def test_filter_target_version_v1_from_v2_input(tmp_path: Path) -> None:
    from samplesheet_parser.enums import SampleSheetVersion

    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    SampleSheetFilter(src, target_version=SampleSheetVersion.V1).filter(out, project="ProjectA")

    content = out.read_text(encoding="utf-8")
    assert "IEMFileVersion" in content
    assert "[Data]" in content


# ---------------------------------------------------------------------------
# Tests — FilterResult
# ---------------------------------------------------------------------------


def test_filter_result_total_count(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, project="ProjectA")

    assert result.total_count == 6


def test_filter_result_output_path_set_on_match(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, project="ProjectA")

    assert result.output_path is not None
    assert result.output_path.exists()


def test_filter_result_summary_contains_counts(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, project="ProjectA")

    summary = result.summary()
    assert "2" in summary
    assert "6" in summary


def test_filter_result_source_version(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, project="ProjectA")

    assert result.source_version == "V2"


# ---------------------------------------------------------------------------
# Tests — incomplete records that pass filter criteria
# ---------------------------------------------------------------------------

_V2_INCOMPLETE_MATCH = """\
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
"""


def test_filter_incomplete_record_matching_project_skipped(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_INCOMPLETE_MATCH)
    out = tmp_path / "filtered.csv"
    result = SampleSheetFilter(src).filter(out, project="ProjectA")

    assert result.matched_count == 1


# ---------------------------------------------------------------------------
# Tests — error conditions
# ---------------------------------------------------------------------------


def test_filter_no_criteria_raises_value_error(tmp_path: Path) -> None:
    src = _write(tmp_path, "combined.csv", _V2_MULTI)
    with pytest.raises(ValueError, match="At least one filter criterion"):
        SampleSheetFilter(src).filter(tmp_path / "out.csv")


def test_filter_missing_input_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        SampleSheetFilter(tmp_path / "nonexistent.csv").filter(
            tmp_path / "out.csv", project="ProjectA"
        )


# ---------------------------------------------------------------------------
# Tests — public import
# ---------------------------------------------------------------------------


def test_filter_importable_from_package() -> None:
    from samplesheet_parser import FilterResult, SampleSheetFilter  # noqa: F401
