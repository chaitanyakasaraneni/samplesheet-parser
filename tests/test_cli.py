"""
Tests for samplesheet_parser.cli (the ``samplesheet`` CLI command).

Covers:
- info: exit 0 on valid sheet, shows format/samples/lanes/index type/reads/adapters
- info: --format json produces parseable output with expected keys
- info: exit 2 on missing file
- validate: exit 0 on valid sheet, exit 1 on errors, exit 2 on missing file
- validate: text output contains format version
- validate: --format json produces parseable output with expected keys
- validate: --min-hamming raises warning threshold
- convert: V1→V2 writes FileFormatVersion, V2→V1 writes IEMFileVersion
- convert: exit 2 on missing input, exit 2 on unknown --to version
- diff: exit 0 on identical sheets, exit 1 on differences, exit 2 on missing file
- diff: --format json produces parseable output with has_changes key
- merge: exit 0 on clean merge, exit 1 on conflicts/warnings
- merge: exit 2 on single file or missing file
- merge: --force flag writes output despite conflicts
- merge: --to v1 produces a V1 sheet
- merge: --format json produces parseable output
- error branches: exception paths in validate/convert/diff/merge → correct exit codes
- diff text branches: samples added, removed, changed in text output
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from samplesheet_parser.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Sheet content helpers
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

# Same index as SampleA1 → INDEX_COLLISION
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

# V1 sheet with a duplicate index → will fail SampleSheetValidator
_V1_INVALID = """\
[Header]
IEMFileVersion,5
Experiment Name,InvalidRun
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
1,SampleX,SampleX,D701,ATTACTCG,D501,TATAGCCT,ProjectX
1,SampleY,SampleY,D701,ATTACTCG,D501,TATAGCCT,ProjectX
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

# V1 sheet with same samples as _V1_A but SampleA1 has a different index —
# used to trigger sample_changes in diff text output (lines 301-305)
_V1_A_FIELD_CHANGED = """\
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
1,SampleA1,SampleA1,D701,TTTTTTTT,D501,TATAGCCT,ProjectA
1,SampleA2,SampleA2,D702,TCCGGAGA,D502,ATAGAGGC,ProjectA
"""

# V1 sheet with different samples/indexes from _V1_A — used to trigger
# samples_added / samples_removed / sample_changes in diff text output
_V1_A_MODIFIED = """\
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
1,SampleA3,SampleA3,D705,TAGGCATG,D505,CTCTCTAC,ProjectA
"""


# V1 sheet with two single indexes that have Hamming distance exactly 3.
# Default --min-hamming 3 → no warning (3 is not < 3).
# --min-hamming 4 → INDEX_DISTANCE_TOO_LOW warning (3 < 4).
_V1_CLOSE_INDEXES = """\
[Header]
IEMFileVersion,5
Experiment Name,DistanceTest

[Reads]
151

[Settings]
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

[Data]
Lane,Sample_ID,index
1,S1,ATTACTCG
1,S2,GTTACCCC
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------


class TestCLIVersion:

    def test_version_exits_0(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0

    def test_version_short_flag_exits_0(self) -> None:
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0

    def test_version_output_contains_package_name(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert "samplesheet-parser" in result.output

    def test_version_output_contains_version_string(self) -> None:
        from samplesheet_parser import __version__

        result = runner.invoke(app, ["--version"])
        assert __version__ in result.output

    def test_version_fallback_when_package_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from importlib.metadata import PackageNotFoundError

        import samplesheet_parser.cli as cli_module

        monkeypatch.setattr(
            cli_module,
            "_metadata_version",
            lambda _: (_ for _ in ()).throw(PackageNotFoundError()),
        )
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "unknown" in result.output


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


class TestCLIInfo:

    def test_info_v1_exits_0(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["info", str(p)])
        assert result.exit_code == 0

    def test_info_v1_shows_format(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["info", str(p)])
        assert "V1" in result.output

    def test_info_v1_shows_sample_count(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["info", str(p), "--format", "json"])
        data = json.loads(result.output)
        assert data["sample_count"] == 2

    def test_info_v1_shows_read_lengths(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["info", str(p), "--format", "json"])
        data = json.loads(result.output)
        assert data["read_lengths"] == ["151", "151"]

    def test_info_v1_shows_index_type(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["info", str(p)])
        assert "dual" in result.output

    def test_info_v2_exits_0(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V2_C)
        result = runner.invoke(app, ["info", str(p)])
        assert result.exit_code == 0

    def test_info_v2_shows_format(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V2_C)
        result = runner.invoke(app, ["info", str(p)])
        assert "V2" in result.output

    def test_info_v2_shows_instrument(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V2_C)
        result = runner.invoke(app, ["info", str(p)])
        assert "NovaSeqXSeries" in result.output

    def test_info_json_exit_0(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["info", str(p), "--format", "json"])
        assert result.exit_code == 0

    def test_info_json_has_expected_keys(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["info", str(p), "--format", "json"])
        data = json.loads(result.output)
        for key in (
            "file",
            "format",
            "sample_count",
            "lanes",
            "index_type",
            "read_lengths",
            "adapters",
        ):
            assert key in data, f"missing key: {key}"

    def test_info_json_sample_count(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["info", str(p), "--format", "json"])
        data = json.loads(result.output)
        assert data["sample_count"] == 2

    def test_info_json_format_field(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V2_C)
        result = runner.invoke(app, ["info", str(p), "--format", "json"])
        data = json.loads(result.output)
        assert data["format"] == "V2"

    def test_info_missing_file_exits_2(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["info", str(tmp_path / "nope.csv")])
        assert result.exit_code == 2

    def test_info_parse_error_exits_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from samplesheet_parser import factory as factory_module

        def _explode(self: object, *a: object, **kw: object) -> None:
            raise ValueError("simulated parse failure")

        monkeypatch.setattr(factory_module.SampleSheetFactory, "create_parser", _explode)
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["info", str(p)])
        assert result.exit_code == 2

    def test_info_unknown_format_exits_2(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["info", str(p), "--format", "xml"])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


class TestCLIValidate:

    def test_valid_sheet_exits_0(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p)])
        assert result.exit_code == 0

    def test_invalid_sheet_exits_1(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_INVALID)
        result = runner.invoke(app, ["validate", str(p)])
        assert result.exit_code == 1

    def test_missing_file_exits_2(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["validate", str(tmp_path / "nope.csv")])
        assert result.exit_code == 2

    def test_text_output_contains_format_version(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p)])
        assert "V1" in result.output

    def test_text_output_contains_result_line(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p)])
        assert "Result" in result.output

    def test_json_output_is_valid_json(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p), "--format", "json"])
        data = json.loads(result.output)
        assert data is not None

    def test_json_output_is_valid_on_valid_sheet(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p), "--format", "json"])
        data = json.loads(result.output)
        assert data["is_valid"] is True

    def test_json_output_version_field(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p), "--format", "json"])
        data = json.loads(result.output)
        assert data["version"] == "V1"

    def test_json_output_contains_errors_and_warnings_lists(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p), "--format", "json"])
        data = json.loads(result.output)
        assert "errors" in data
        assert "warnings" in data
        assert isinstance(data["errors"], list)
        assert isinstance(data["warnings"], list)

    def test_json_output_invalid_sheet_has_errors(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_INVALID)
        result = runner.invoke(app, ["validate", str(p), "--format", "json"])
        data = json.loads(result.output)
        assert data["is_valid"] is False
        assert len(data["errors"]) > 0

    def test_v2_sheet_validate_exits_0(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V2_C)
        result = runner.invoke(app, ["validate", str(p)])
        assert result.exit_code == 0

    def test_v2_json_version_field(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V2_C)
        result = runner.invoke(app, ["validate", str(p), "--format", "json"])
        data = json.loads(result.output)
        assert data["version"] == "V2"

    def test_validate_does_not_create_backup_file(self, tmp_path: Path) -> None:
        """validate must be read-only — clean=False ensures no .backup is created."""
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p)])
        assert result.exit_code == 0
        assert not (tmp_path / "sheet.csv.backup").exists()

    def test_parse_error_exits_2(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 148-150: create_parser raises → exit 2 with error message."""
        from samplesheet_parser import factory as factory_module

        def _explode(self: object, *a: object, **kw: object) -> None:
            raise ValueError("simulated parse failure")

        monkeypatch.setattr(factory_module.SampleSheetFactory, "create_parser", _explode)

        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p)])
        assert result.exit_code == 2
        assert "Error" in result.output

    def test_min_hamming_default_no_warning(self, tmp_path: Path) -> None:
        """Indexes with Hamming distance 3 pass at default --min-hamming 3."""
        p = _write(tmp_path, "sheet.csv", _V1_CLOSE_INDEXES)
        result = runner.invoke(app, ["validate", str(p)])
        assert result.exit_code == 0
        assert "INDEX_DISTANCE_TOO_LOW" not in result.output

    def test_min_hamming_4_raises_warning(self, tmp_path: Path) -> None:
        """Indexes with Hamming distance 3 produce a warning at --min-hamming 4."""
        p = _write(tmp_path, "sheet.csv", _V1_CLOSE_INDEXES)
        result = runner.invoke(app, ["validate", str(p), "--min-hamming", "4"])
        assert "INDEX_DISTANCE_TOO_LOW" in result.output

    def test_min_hamming_json_includes_threshold(self, tmp_path: Path) -> None:
        """--format json output includes the min_hamming_distance value used."""
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p), "--format", "json", "--min-hamming", "4"])
        data = json.loads(result.output)
        assert data["min_hamming_distance"] == 4

    def test_min_hamming_zero_exits_2(self, tmp_path: Path) -> None:
        """--min-hamming 0 is invalid and should exit 2."""
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p), "--min-hamming", "0"])
        assert result.exit_code == 2

    def test_min_hamming_negative_exits_2(self, tmp_path: Path) -> None:
        """--min-hamming -1 is invalid and should exit 2."""
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p), "--min-hamming", "-1"])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# convert
# ---------------------------------------------------------------------------


class TestCLIConvert:

    def test_v1_to_v2_exits_0(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "in.csv", _V1_A)
        out = tmp_path / "out.csv"
        result = runner.invoke(app, ["convert", str(p), "--to", "v2", "--output", str(out)])
        assert result.exit_code == 0

    def test_v1_to_v2_output_contains_file_format_version(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "in.csv", _V1_A)
        out = tmp_path / "out.csv"
        result = runner.invoke(app, ["convert", str(p), "--to", "v2", "--output", str(out)])
        assert result.exit_code == 0
        assert "FileFormatVersion" in out.read_text()

    def test_v2_to_v1_exits_0(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "in.csv", _V2_C)
        out = tmp_path / "out.csv"
        result = runner.invoke(app, ["convert", str(p), "--to", "v1", "--output", str(out)])
        assert result.exit_code == 0

    def test_v2_to_v1_output_contains_iem_file_version(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "in.csv", _V2_C)
        out = tmp_path / "out.csv"
        result = runner.invoke(app, ["convert", str(p), "--to", "v1", "--output", str(out)])
        assert result.exit_code == 0
        assert "IEMFileVersion" in out.read_text()

    def test_missing_input_exits_2(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["convert", str(tmp_path / "nope.csv"), "--to", "v2"])
        assert result.exit_code == 2

    def test_bad_version_string_exits_2(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "in.csv", _V1_A)
        result = runner.invoke(app, ["convert", str(p), "--to", "v99"])
        assert result.exit_code == 2

    def test_convert_output_file_is_written(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "in.csv", _V1_A)
        out = tmp_path / "out.csv"
        result = runner.invoke(app, ["convert", str(p), "--to", "v2", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_conversion_exception_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 222-224: to_v2 raises → exit 1 with error message."""
        from samplesheet_parser import converter as conv_module

        def _explode(self: object, *a: object, **kw: object) -> None:
            raise RuntimeError("simulated conversion failure")

        monkeypatch.setattr(conv_module.SampleSheetConverter, "to_v2", _explode)

        p = _write(tmp_path, "in.csv", _V1_A)
        result = runner.invoke(app, ["convert", str(p), "--to", "v2"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_convert_json_format_exits_0(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "in.csv", _V1_A)
        out = tmp_path / "out.csv"
        result = runner.invoke(
            app, ["convert", str(p), "--to", "v2", "--output", str(out), "--format", "json"]
        )
        assert result.exit_code == 0

    def test_convert_json_format_is_valid_json(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "in.csv", _V1_A)
        out = tmp_path / "out.csv"
        result = runner.invoke(
            app, ["convert", str(p), "--to", "v2", "--output", str(out), "--format", "json"]
        )
        data = json.loads(result.output)
        assert data["source_version"] == "V1"
        assert data["target_version"] == "V2"
        assert data["input"] == str(p)
        assert data["output"] == str(out)

    def test_convert_bad_format_exits_2(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "in.csv", _V1_A)
        out = tmp_path / "out.csv"
        result = runner.invoke(
            app, ["convert", str(p), "--to", "v2", "--output", str(out), "--format", "xml"]
        )
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


class TestCLIDiff:

    def test_identical_sheets_exit_0(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_A)
        result = runner.invoke(app, ["diff", str(a), str(b)])
        assert result.exit_code == 0

    def test_different_sheets_exit_1(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = runner.invoke(app, ["diff", str(a), str(b)])
        assert result.exit_code == 1

    def test_missing_old_file_exits_2(self, tmp_path: Path) -> None:
        b = _write(tmp_path, "b.csv", _V1_B)
        result = runner.invoke(app, ["diff", str(tmp_path / "nope.csv"), str(b)])
        assert result.exit_code == 2

    def test_missing_new_file_exits_2(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        result = runner.invoke(app, ["diff", str(a), str(tmp_path / "nope.csv")])
        assert result.exit_code == 2

    def test_json_output_is_valid_json(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = runner.invoke(app, ["diff", str(a), str(b), "--format", "json"])
        data = json.loads(result.output)
        assert data is not None

    def test_json_output_has_changes_true(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = runner.invoke(app, ["diff", str(a), str(b), "--format", "json"])
        data = json.loads(result.output)
        assert data["has_changes"] is True

    def test_json_output_has_changes_false_on_identical(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_A)
        result = runner.invoke(app, ["diff", str(a), str(b), "--format", "json"])
        data = json.loads(result.output)
        assert data["has_changes"] is False

    def test_json_output_contains_required_keys(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = runner.invoke(app, ["diff", str(a), str(b), "--format", "json"])
        data = json.loads(result.output)
        for key in (
            "has_changes",
            "source_version",
            "target_version",
            "header_changes",
            "samples_added",
            "samples_removed",
            "sample_changes",
        ):
            assert key in data

    def test_cross_format_v1_v2_exits_1_on_differences(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        c = _write(tmp_path, "c.csv", _V2_C)
        result = runner.invoke(app, ["diff", str(a), str(c)])
        assert result.exit_code == 1

    def test_text_output_shows_samples_removed(self, tmp_path: Path) -> None:
        """Lines 295-298: removed samples appear in text diff output."""
        # _V1_A has SampleA1, SampleA2; _V1_A_MODIFIED has SampleA1, SampleA3
        # Diffing _V1_A (old) vs _V1_A_MODIFIED (new) shows SampleA2 removed
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_A_MODIFIED)
        result = runner.invoke(app, ["diff", str(a), str(b)])
        assert "Samples removed" in result.output
        assert "SampleA2" in result.output

    def test_text_output_shows_sample_field_changes(self, tmp_path: Path) -> None:
        """Lines 301-305: sample field changes appear in text diff output."""
        # _V1_A has SampleA1 with index ATTACTCG;
        # _V1_A_FIELD_CHANGED has SampleA1 with index TTTTTTTT → sample_changes
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_A_FIELD_CHANGED)
        result = runner.invoke(app, ["diff", str(a), str(b)])
        assert "Sample field changes" in result.output
        assert "SampleA1" in result.output

    def test_diff_exception_exits_2(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 260-262: compare() raises → exit 2 with error message."""
        from samplesheet_parser import diff as diff_module

        def _explode(self: object) -> None:
            raise ValueError("simulated diff failure")

        monkeypatch.setattr(diff_module.SampleSheetDiff, "compare", _explode)

        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = runner.invoke(app, ["diff", str(a), str(b)])
        assert result.exit_code == 2
        assert "Error" in result.output

    def test_text_output_samples_added(self, tmp_path: Path) -> None:
        """Lines 307-309: samples_added branch in text output."""
        a = _write(tmp_path, "a.csv", _V1_A)  # has SampleA1, SampleA2
        b = _write(tmp_path, "b.csv", _V1_A_MODIFIED)  # has SampleA1, SampleA3
        result = runner.invoke(app, ["diff", str(a), str(b)])
        assert result.exit_code == 1
        assert "added" in result.output.lower() or "removed" in result.output.lower()

    def test_text_output_samples_removed(self, tmp_path: Path) -> None:
        """Lines 310-311: samples_removed branch in text output."""
        a = _write(tmp_path, "a.csv", _V1_A_MODIFIED)  # has SampleA1, SampleA3
        b = _write(tmp_path, "b.csv", _V1_A)  # has SampleA1, SampleA2
        result = runner.invoke(app, ["diff", str(a), str(b)])
        assert result.exit_code == 1
        assert "added" in result.output.lower() or "removed" in result.output.lower()


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------


class TestCLIMerge:

    def test_clean_merge_exits_0(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "combined.csv"
        result = runner.invoke(app, ["merge", str(a), str(b), "--output", str(out)])
        assert result.exit_code == 0

    def test_clean_merge_writes_output_file(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "combined.csv"
        result = runner.invoke(app, ["merge", str(a), str(b), "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_index_collision_exits_1(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_COLLISION)
        out = tmp_path / "combined.csv"
        result = runner.invoke(app, ["merge", str(a), str(b), "--output", str(out)])
        assert result.exit_code == 1

    def test_single_file_exits_2(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        result = runner.invoke(app, ["merge", str(a), "--output", str(tmp_path / "out.csv")])
        assert result.exit_code == 2

    def test_missing_file_exits_2(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        result = runner.invoke(
            app,
            [
                "merge",
                str(a),
                str(tmp_path / "nope.csv"),
                "--output",
                str(tmp_path / "out.csv"),
            ],
        )
        assert result.exit_code == 2

    def test_force_flag_writes_despite_collision(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B_COLLISION)
        out = tmp_path / "combined.csv"
        result = runner.invoke(app, ["merge", str(a), str(b), "--output", str(out), "--force"])
        assert result.exit_code == 1  # conflict present but --force allows write
        assert out.exists()

    def test_to_v1_produces_iem_sheet(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "combined.csv"
        result = runner.invoke(app, ["merge", str(a), str(b), "--output", str(out), "--to", "v1"])
        assert result.exit_code == 0
        assert "IEMFileVersion" in out.read_text()

    def test_to_v2_produces_bcl_sheet(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "combined.csv"
        result = runner.invoke(app, ["merge", str(a), str(b), "--output", str(out), "--to", "v2"])
        assert result.exit_code == 0
        assert "FileFormatVersion" in out.read_text()

    def test_json_output_is_valid_json(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "combined.csv"
        result = runner.invoke(
            app,
            [
                "merge",
                str(a),
                str(b),
                "--output",
                str(out),
                "--format",
                "json",
            ],
        )
        data = json.loads(result.output)
        assert data is not None

    def test_json_output_contains_required_keys(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "combined.csv"
        result = runner.invoke(
            app,
            [
                "merge",
                str(a),
                str(b),
                "--output",
                str(out),
                "--format",
                "json",
            ],
        )
        data = json.loads(result.output)
        for key in (
            "has_conflicts",
            "sample_count",
            "output_path",
            "source_versions",
            "conflicts",
            "warnings",
        ):
            assert key in data

    def test_json_sample_count_is_correct(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)  # 2 samples
        b = _write(tmp_path, "b.csv", _V1_B)  # 2 samples
        out = tmp_path / "combined.csv"
        result = runner.invoke(
            app,
            [
                "merge",
                str(a),
                str(b),
                "--output",
                str(out),
                "--format",
                "json",
            ],
        )
        data = json.loads(result.output)
        assert data["sample_count"] == 4

    def test_three_files_merged(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        c = _write(tmp_path, "c.csv", _V2_C)
        out = tmp_path / "combined.csv"
        result = runner.invoke(app, ["merge", str(a), str(b), str(c), "--output", str(out)])
        # Mixed format warning → exit 1 (has_issues=True), but file still written
        assert result.exit_code == 1
        assert out.exists()

    def test_merge_exception_exits_2(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 370-372: merger.merge() raises → exit 2 with error message."""
        from samplesheet_parser import merger as merger_module

        def _explode(self: object, *a: object, **kw: object) -> None:
            raise RuntimeError("simulated merge failure")

        monkeypatch.setattr(merger_module.SampleSheetMerger, "merge", _explode)

        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = runner.invoke(
            app,
            [
                "merge",
                str(a),
                str(b),
                "--output",
                str(tmp_path / "out.csv"),
            ],
        )
        assert result.exit_code == 2
        assert "Error" in result.output


# ---------------------------------------------------------------------------
# _validate_fmt — unknown format exits 2 on all commands that accept --format
# ---------------------------------------------------------------------------


class TestCLIUnknownFormat:

    def test_validate_unknown_format_exits_2(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "sheet.csv", _V1_A)
        result = runner.invoke(app, ["validate", str(p), "--format", "xml"])
        assert result.exit_code == 2

    def test_diff_unknown_format_exits_2(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        result = runner.invoke(app, ["diff", str(a), str(b), "--format", "xml"])
        assert result.exit_code == 2

    def test_merge_unknown_format_exits_2(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.csv", _V1_A)
        b = _write(tmp_path, "b.csv", _V1_B)
        out = tmp_path / "combined.csv"
        result = runner.invoke(
            app,
            [
                "merge",
                str(a),
                str(b),
                "--output",
                str(out),
                "--format",
                "xml",
            ],
        )
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# split fixtures
# ---------------------------------------------------------------------------

_V2_COMBINED = """\
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
"""

_V2_NO_PROJECT = """\
[Header]
FileFormatVersion,2
RunName,NoProjectRun

[Reads]
Read1Cycles,151
Index1Cycles,10

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index
1,Sample1,ATTACTCGAT
1,Sample2,TCCGGAGAGA
"""


# ---------------------------------------------------------------------------
# CLI — split
# ---------------------------------------------------------------------------


class TestCLISplit:

    def test_split_by_project_exits_0_no_warnings(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out_dir = tmp_path / "split"
        result = runner.invoke(app, ["split", str(src), "--output-dir", str(out_dir)])
        assert result.exit_code == 0

    def test_split_by_project_creates_files(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out_dir = tmp_path / "split"
        runner.invoke(app, ["split", str(src), "--output-dir", str(out_dir)])
        assert (out_dir / "ProjectA_SampleSheet.csv").exists()
        assert (out_dir / "ProjectB_SampleSheet.csv").exists()

    def test_split_by_lane(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out_dir = tmp_path / "split"
        result = runner.invoke(
            app, ["split", str(src), "--by", "lane", "--output-dir", str(out_dir)]
        )
        assert result.exit_code == 0

    def test_split_with_warnings_exits_1(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_NO_PROJECT)
        out_dir = tmp_path / "split"
        result = runner.invoke(app, ["split", str(src), "--output-dir", str(out_dir)])
        assert result.exit_code == 1

    def test_split_json_output(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out_dir = tmp_path / "split"
        result = runner.invoke(
            app, ["split", str(src), "--output-dir", str(out_dir), "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "files" in data
        assert "sample_counts" in data
        assert data["by"] == "project"

    def test_split_missing_file_exits_2(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["split", str(tmp_path / "missing.csv"), "--output-dir", str(tmp_path)]
        )
        assert result.exit_code == 2

    def test_split_invalid_by_exits_2(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        result = runner.invoke(
            app,
            ["split", str(src), "--by", "sample", "--output-dir", str(tmp_path)],
        )
        assert result.exit_code == 2

    def test_split_unknown_format_exits_2(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        result = runner.invoke(
            app,
            ["split", str(src), "--output-dir", str(tmp_path), "--format", "xml"],
        )
        assert result.exit_code == 2

    def test_split_with_prefix(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out_dir = tmp_path / "split"
        runner.invoke(app, ["split", str(src), "--output-dir", str(out_dir), "--prefix", "Run_"])
        assert (out_dir / "Run_ProjectA_SampleSheet.csv").exists()

    def test_split_text_output_lists_files(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out_dir = tmp_path / "split"
        result = runner.invoke(app, ["split", str(src), "--output-dir", str(out_dir)])
        assert "ProjectA" in result.output
        assert "ProjectB" in result.output

    def test_split_text_output_shows_warnings(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_NO_PROJECT)
        out_dir = tmp_path / "split"
        result = runner.invoke(app, ["split", str(src), "--output-dir", str(out_dir)])
        assert "Warnings" in result.output

    def test_split_exception_exits_2(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out_dir = tmp_path / "split"
        from samplesheet_parser import splitter as splitter_mod

        monkeypatch.setattr(
            splitter_mod.SampleSheetSplitter,
            "split",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = runner.invoke(app, ["split", str(src), "--output-dir", str(out_dir)])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# CLI — filter
# ---------------------------------------------------------------------------


class TestCLIFilter:

    def test_filter_by_project_exits_0(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out = tmp_path / "filtered.csv"
        result = runner.invoke(
            app, ["filter", str(src), "--project", "ProjectA", "--output", str(out)]
        )
        assert result.exit_code == 0

    def test_filter_by_project_writes_file(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out = tmp_path / "filtered.csv"
        runner.invoke(app, ["filter", str(src), "--project", "ProjectA", "--output", str(out)])
        assert out.exists()
        content = out.read_text()
        assert "SampleA1" in content
        assert "SampleB1" not in content

    def test_filter_by_lane(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out = tmp_path / "filtered.csv"
        result = runner.invoke(app, ["filter", str(src), "--lane", "1", "--output", str(out)])
        assert result.exit_code == 0

    def test_filter_by_sample_id_glob(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out = tmp_path / "filtered.csv"
        result = runner.invoke(
            app, ["filter", str(src), "--sample-id", "SampleA*", "--output", str(out)]
        )
        assert result.exit_code == 0

    def test_filter_no_match_exits_1(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out = tmp_path / "filtered.csv"
        result = runner.invoke(
            app,
            ["filter", str(src), "--project", "NonExistent", "--output", str(out)],
        )
        assert result.exit_code == 1

    def test_filter_no_criteria_exits_2(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out = tmp_path / "filtered.csv"
        result = runner.invoke(app, ["filter", str(src), "--output", str(out)])
        assert result.exit_code == 2

    def test_filter_missing_file_exits_2(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "filter",
                str(tmp_path / "missing.csv"),
                "--project",
                "X",
                "--output",
                str(tmp_path / "out.csv"),
            ],
        )
        assert result.exit_code == 2

    def test_filter_unknown_format_exits_2(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out = tmp_path / "filtered.csv"
        result = runner.invoke(
            app,
            ["filter", str(src), "--project", "ProjectA", "--output", str(out), "--format", "xml"],
        )
        assert result.exit_code == 2

    def test_filter_json_output(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out = tmp_path / "filtered.csv"
        result = runner.invoke(
            app,
            ["filter", str(src), "--project", "ProjectA", "--output", str(out), "--format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["matched_count"] == 2
        assert data["total_count"] == 4
        assert data["criteria"]["project"] == "ProjectA"

    def test_filter_text_output_shows_summary(self, tmp_path: Path) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out = tmp_path / "filtered.csv"
        result = runner.invoke(
            app, ["filter", str(src), "--project", "ProjectA", "--output", str(out)]
        )
        assert "2" in result.output
        assert str(out) in result.output

    def test_filter_exception_exits_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = _write(tmp_path, "combined.csv", _V2_COMBINED)
        out = tmp_path / "filtered.csv"
        from samplesheet_parser import filter as filter_mod

        monkeypatch.setattr(
            filter_mod.SampleSheetFilter,
            "filter",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = runner.invoke(
            app, ["filter", str(src), "--project", "ProjectA", "--output", str(out)]
        )
        assert result.exit_code == 2
