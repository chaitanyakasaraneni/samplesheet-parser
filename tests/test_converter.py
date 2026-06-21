"""Tests for SampleSheetConverter."""

# mypy: disable-error-code="misc"
# `@pytest.fixture` and `@pytest.mark.parametrize` are typed as `Any` when
# pytest's type stubs aren't installed in the pre-commit env, which makes
# every decorated function "untyped" under strict mypy. The functions
# themselves are fully annotated.

from __future__ import annotations

from pathlib import Path

import pytest

from samplesheet_parser.converter import SampleSheetConverter
from samplesheet_parser.instruments import Workflow, reverse_complement
from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def v1_sheet(tmp_path: Path) -> str:
    """Minimal IEM V1 sheet with dual index and adapters (workflow-A MiSeq)."""
    content = (
        "[Header]\n"
        "IEMFileVersion,5\n"
        "Experiment Name,MyRun_20240115\n"
        "Date,2024-01-15\n"
        "Workflow,GenerateFASTQ\n"
        "Instrument Type,MiSeq\n"
        "Chemistry,Amplicon\n"
        "\n"
        "[Reads]\n"
        "151\n"
        "151\n"
        "\n"
        "[Settings]\n"
        "AdapterRead1,CTGTCTCTTATACACATCT\n"
        "AdapterRead2,CTGTCTCTTATACACATCT\n"
        "\n"
        "[Data]\n"
        "Lane,Sample_ID,Sample_Name,Sample_Plate,Sample_Well,"
        "I7_Index_ID,index,I5_Index_ID,index2,Sample_Project,Description\n"
        "1,Sample1,Sample1,,A01,D701,ATTACTCG,D501,TATAGCCT,Project1,\n"
        "1,Sample2,Sample2,,B01,D702,TCCGGAGA,D502,ATAGAGGC,Project1,\n"
    )
    p = tmp_path / "SampleSheet_v1.csv"
    p.write_text(content)
    return str(p)


@pytest.fixture
def v1_no_reads(tmp_path: Path) -> str:
    """V1 sheet with no [Reads] section (workflow-A MiSeq)."""
    content = (
        "[Header]\n"
        "IEMFileVersion,5\n"
        "Experiment Name,NoReadsRun\n"
        "Instrument Type,MiSeq\n"
        "\n"
        "[Settings]\n"
        "Adapter,CTGTCTCTTATACACATCT\n"
        "\n"
        "[Data]\n"
        "Lane,Sample_ID,Sample_Name,index,index2,Sample_Project\n"
        "1,SampleA,SampleA,ATCGATCG,GCTAGCTA,ProjectA\n"
    )
    p = tmp_path / "SampleSheet_v1_no_reads.csv"
    p.write_text(content)
    return str(p)


@pytest.fixture
def v1_single_index(tmp_path: Path) -> str:
    """V1 sheet with single index only."""
    content = (
        "[Header]\n"
        "IEMFileVersion,5\n"
        "Experiment Name,SingleIndexRun\n"
        "\n"
        "[Reads]\n"
        "100\n"
        "\n"
        "[Data]\n"
        "Lane,Sample_ID,Sample_Name,I7_Index_ID,index,Sample_Project\n"
        "1,SampleX,SampleX,D701,ATTACTCG,ProjectX\n"
    )
    p = tmp_path / "SampleSheet_v1_single.csv"
    p.write_text(content)
    return str(p)


@pytest.fixture
def v2_sheet(tmp_path: Path) -> str:
    """Minimal BCLConvert V2 sheet with dual index."""
    content = (
        "[Header]\n"
        "FileFormatVersion,2\n"
        "RunName,TestRunV2\n"
        "InstrumentPlatform,NovaSeqXSeries\n"
        "\n"
        "[Reads]\n"
        "Read1Cycles,151\n"
        "Read2Cycles,151\n"
        "Index1Cycles,10\n"
        "Index2Cycles,10\n"
        "\n"
        "[BCLConvert_Settings]\n"
        "SoftwareVersion,3.9.3\n"
        "AdapterRead1,CTGTCTCTTATACACATCT\n"
        "AdapterRead2,CTGTCTCTTATACACATCT\n"
        "OverrideCycles,Y151;I10;I10;Y151\n"
        "\n"
        "[BCLConvert_Data]\n"
        "Lane,Sample_ID,Index,Index2,Sample_Project\n"
        "1,Sample1,ATTACTCG,TATAGCCT,Project1\n"
        "1,Sample2,TCCGGAGA,ATAGAGGC,Project1\n"
    )
    p = tmp_path / "SampleSheet_v2.csv"
    p.write_text(content)
    return str(p)


@pytest.fixture
def v2_with_cloud_data(tmp_path: Path) -> str:
    """V2 sheet with Cloud_Data section."""
    content = (
        "[Header]\n"
        "FileFormatVersion,2\n"
        "RunName,CloudRun\n"
        "InstrumentPlatform,NovaSeqXSeries\n"
        "\n"
        "[BCLConvert_Settings]\n"
        "SoftwareVersion,4.2.7\n"
        "AdapterRead1,CTGTCTCTTATACACATCT\n"
        "\n"
        "[BCLConvert_Data]\n"
        "Lane,Sample_ID,Index,Index2\n"
        "1,Sample1,ATTACTCG,TATAGCCT\n"
        "\n"
        "[Cloud_Settings]\n"
        "GeneratedVersion,4.2.7\n"
        "\n"
        "[Cloud_Data]\n"
        "Sample_ID,ProjectName,LibraryName\n"
        "Sample1,CloudProject,Lib1\n"
    )
    p = tmp_path / "SampleSheet_cloud.csv"
    p.write_text(content)
    return str(p)


# ---------------------------------------------------------------------------
# TestConverterInit
# ---------------------------------------------------------------------------


class TestConverterInit:
    def test_detects_v1(self, v1_sheet: str) -> None:
        from samplesheet_parser.enums import SampleSheetVersion

        conv = SampleSheetConverter(v1_sheet)
        assert conv.source_version == SampleSheetVersion.V1

    def test_detects_v2(self, v2_sheet: str) -> None:
        from samplesheet_parser.enums import SampleSheetVersion

        conv = SampleSheetConverter(v2_sheet)
        assert conv.source_version == SampleSheetVersion.V2

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            SampleSheetConverter(tmp_path / "nonexistent.csv")

    def test_repr(self, v1_sheet: str) -> None:
        conv = SampleSheetConverter(v1_sheet)
        r = repr(conv)
        assert "SampleSheetConverter" in r
        assert "V1" in r


# ---------------------------------------------------------------------------
# TestV1ToV2
# ---------------------------------------------------------------------------


class TestV1ToV2:
    def test_output_file_created(self, v1_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v2.csv"
        result = SampleSheetConverter(v1_sheet).to_v2(out)
        assert result.exists()

    def test_returns_path(self, v1_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v2.csv"
        result = SampleSheetConverter(v1_sheet).to_v2(out)
        assert str(out.resolve()) == str(result)

    def test_output_is_valid_v2(self, v1_sheet: str, tmp_path: Path) -> None:
        """Converted output should be parseable by SampleSheetV2."""
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert sheet.header is not None
        assert sheet.header.get("FileFormatVersion") == "2"

    def test_run_name_preserved(self, v1_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert sheet.experiment_name == "MyRun_20240115"

    def test_read_cycles_converted(self, v1_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert sheet.reads.get("Read1Cycles") == 151
        assert sheet.reads.get("Read2Cycles") == 151

    def test_adapters_preserved(self, v1_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert "CTGTCTCTTATACACATCT" in sheet.adapters

    def test_sample_ids_preserved(self, v1_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        ids = [s["sample_id"] for s in sheet.samples()]
        assert "Sample1" in ids
        assert "Sample2" in ids

    def test_index_columns_remapped(self, v1_sheet: str, tmp_path: Path) -> None:
        """V1 'index'/'index2' should become V2 'Index'/'Index2'."""
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert sheet.columns is not None
        assert "Index" in sheet.columns
        assert "Index2" in sheet.columns
        # V1-only columns should be absent
        assert "I7_Index_ID" not in sheet.columns
        assert "I5_Index_ID" not in sheet.columns

    def test_index_values_preserved(self, v1_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        sample = next(s for s in sheet.samples() if s["sample_id"] == "Sample1")
        assert sample["index"] == "ATTACTCG"
        assert sample["index2"] == "TATAGCCT"

    def test_no_reads_section(self, v1_no_reads: str, tmp_path: Path) -> None:
        """V1 with no [Reads] should convert without error - empty [Reads] in V2."""
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_no_reads).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert sheet.records is not None

    def test_single_index_preserved(self, v1_single_index: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_single_index).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert sheet.index_type() == "single"

    def test_already_v2_raises(self, v2_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v2.csv"
        with pytest.raises(ValueError, match="already V2"):
            SampleSheetConverter(v2_sheet).to_v2(out)


# ---------------------------------------------------------------------------
# TestV2ToV1
# ---------------------------------------------------------------------------


class TestV2ToV1:
    def test_output_file_created(self, v2_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v1.csv"
        result = SampleSheetConverter(v2_sheet).to_v1(out)
        assert result.exists()

    def test_returns_path(self, v2_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v1.csv"
        result = SampleSheetConverter(v2_sheet).to_v1(out)
        assert str(out.resolve()) == str(result)

    def test_output_is_valid_v1(self, v2_sheet: str, tmp_path: Path) -> None:
        """Converted output should be parseable by SampleSheetV1."""
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        assert sheet.iem_version == "5"

    def test_run_name_preserved(self, v2_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        assert sheet.experiment_name == "TestRunV2"

    def test_read_cycles_converted(self, v2_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        assert 151 in sheet.read_lengths

    def test_adapters_preserved(self, v2_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        assert "CTGTCTCTTATACACATCT" in sheet.adapters

    def test_sample_ids_preserved(self, v2_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        ids = [s["sample_id"] for s in sheet.samples()]
        assert "Sample1" in ids
        assert "Sample2" in ids

    def test_index_columns_remapped(self, v2_sheet: str, tmp_path: Path) -> None:
        """V2 'Index'/'Index2' should become V1 'index'/'index2'."""
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        assert sheet.columns is not None
        assert "index" in sheet.columns
        assert "index2" in sheet.columns
        assert "Index" not in sheet.columns

    def test_index_values_preserved(self, v2_sheet: str, tmp_path: Path) -> None:
        """V2 (NovaSeqXSeries, workflow B) → V1 must reverse-complement Index2.

        BCLConvert records Index2 in the forward orientation; bcl2fastq
        expects the on-chip (RC'd) orientation for workflow-B instruments.
        """
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        sample = next(s for s in sheet.samples() if s["sample_id"] == "Sample1")
        assert sample["index"] == "ATTACTCG"  # i7 passes through
        assert sample["index2"] == "AGGCTATA"  # RC of TATAGCCT

    def test_v2_only_settings_dropped(self, v2_sheet: str, tmp_path: Path) -> None:
        """OverrideCycles and other V2-only settings should not appear in V1 output."""
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        content = out.read_text()
        assert "OverrideCycles" not in content
        assert "SoftwareVersion" not in content
        assert "InstrumentPlatform" not in content

    def test_cloud_data_dropped_with_warning(self, v2_with_cloud_data: str, tmp_path: Path) -> None:
        """Cloud_Data section should be dropped and logged as a warning."""
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_with_cloud_data).to_v1(out)
        content = out.read_text()
        assert "Cloud_Data" not in content
        assert "Cloud_Settings" not in content

    def test_already_v1_raises(self, v1_sheet: str, tmp_path: Path) -> None:
        out = tmp_path / "output_v1.csv"
        with pytest.raises(ValueError, match="already V1"):
            SampleSheetConverter(v1_sheet).to_v1(out)


# ---------------------------------------------------------------------------
# TestRoundTrip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_v1_to_v2_to_v1_sample_ids(self, v1_sheet: str, tmp_path: Path) -> None:
        """Sample IDs should survive a full V1 → V2 → V1 round trip."""
        v2_out = tmp_path / "round_v2.csv"
        v1_out = tmp_path / "round_v1.csv"

        SampleSheetConverter(v1_sheet).to_v2(v2_out)
        SampleSheetConverter(str(v2_out)).to_v1(v1_out)

        sheet = SampleSheetV1(str(v1_out))
        sheet.parse()
        ids = [s["sample_id"] for s in sheet.samples()]
        assert "Sample1" in ids
        assert "Sample2" in ids

    def test_v1_to_v2_to_v1_index_values(self, v1_sheet: str, tmp_path: Path) -> None:
        """Index sequences should survive a full V1 → V2 → V1 round trip."""
        v2_out = tmp_path / "round_v2.csv"
        v1_out = tmp_path / "round_v1.csv"

        SampleSheetConverter(v1_sheet).to_v2(v2_out)
        SampleSheetConverter(str(v2_out)).to_v1(v1_out)

        sheet = SampleSheetV1(str(v1_out))
        sheet.parse()
        sample = next(s for s in sheet.samples() if s["sample_id"] == "Sample1")
        assert sample["index"] == "ATTACTCG"
        assert sample["index2"] == "TATAGCCT"

    def test_v2_to_v1_to_v2_sample_ids(self, v2_sheet: str, tmp_path: Path) -> None:
        """Sample IDs should survive a full V2 → V1 → V2 round trip."""
        v1_out = tmp_path / "round_v1.csv"
        v2_out = tmp_path / "round_v2.csv"

        SampleSheetConverter(v2_sheet).to_v1(v1_out)
        SampleSheetConverter(str(v1_out)).to_v2(v2_out)

        sheet = SampleSheetV2(str(v2_out))
        sheet.parse()
        ids = [s["sample_id"] for s in sheet.samples()]
        assert "Sample1" in ids
        assert "Sample2" in ids

    def test_header_only_v1_emits_column_header(self, tmp_path: Path) -> None:
        """V1 with columns but zero records should still emit [BCLConvert_Data] column header."""
        p = tmp_path / "header_only_v1.csv"
        p.write_text(
            "[Header]\n"
            "IEMFileVersion,5\n"
            "Experiment Name,EmptyRun\n"
            "\n"
            "[Data]\n"
            "Lane,Sample_ID,index,index2,Sample_Project\n"
        )
        out = tmp_path / "out_v2.csv"
        SampleSheetConverter(str(p)).to_v2(out)
        content = out.read_text()
        assert "[BCLConvert_Data]" in content
        assert "Sample_ID" in content

    def test_header_only_v2_emits_column_header(self, tmp_path: Path) -> None:
        """V2 with columns but zero records should still emit [Data] column header."""
        p = tmp_path / "header_only_v2.csv"
        p.write_text(
            "[Header]\n"
            "FileFormatVersion,2\n"
            "RunName,EmptyRun\n"
            "InstrumentPlatform,NovaSeqXSeries\n"
            "\n"
            "[BCLConvert_Data]\n"
            "Lane,Sample_ID,Index,Index2,Sample_Project\n"
        )
        out = tmp_path / "out_v1.csv"
        SampleSheetConverter(str(p)).to_v1(out)
        content = out.read_text()
        assert "[Data]" in content
        assert "Sample_ID" in content

    def test_rundescription_maps_to_description_not_date(self, tmp_path: Path) -> None:
        """V2 RunDescription should map to V1 Description, not Date."""
        p = tmp_path / "desc.csv"
        p.write_text(
            "[Header]\n"
            "FileFormatVersion,2\n"
            "RunName,MyRun\n"
            "RunDescription,Free text description\n"
            "InstrumentPlatform,NovaSeqXSeries\n"
            "\n"
            "[BCLConvert_Data]\n"
            "Lane,Sample_ID,Index\n"
            "1,S1,ATTACTCG\n"
        )
        out = tmp_path / "out_v1.csv"
        SampleSheetConverter(str(p)).to_v1(out)
        content = out.read_text()
        assert "Description,Free text description" in content
        assert "Date,Free text description" not in content

    def test_override_cycles_is_valid_csv_field(self, tmp_path: Path) -> None:
        """OverrideCycles placeholder in V2 output should be a real CSV field, not a comment."""
        p = tmp_path / "v1.csv"
        p.write_text(
            "[Header]\n"
            "IEMFileVersion,5\n"
            "Experiment Name,MyRun\n"
            "Instrument Type,MiSeq\n"
            "\n"
            "[Data]\n"
            "Lane,Sample_ID,index,index2\n"
            "1,S1,ATTACTCG,TATAGCCT\n"
        )
        out = tmp_path / "out_v2.csv"
        SampleSheetConverter(str(p)).to_v2(out)
        content = out.read_text()
        assert "OverrideCycles," in content
        assert "# OverrideCycles" not in content


class TestConverterEdgeCases:
    def test_to_v2_raises_type_error_for_wrong_sheet_type(self, tmp_path: Path) -> None:
        """Line 135: TypeError when internal _sheet is not SampleSheetV1."""
        p = tmp_path / "v1.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        converter = SampleSheetConverter(str(p))
        # Swap internal sheet to a V2 object so the isinstance check fails
        v2_p = tmp_path / "v2.csv"
        v2_p.write_text(
            "[Header]\nFileFormatVersion,2\nRunName,T\n\n"
            "[BCLConvert_Data]\nSample_ID,Index\nS1,ATTACTCG\n"
        )
        converter._sheet = SampleSheetV2(str(v2_p))
        with pytest.raises(TypeError, match="Expected SampleSheetV1"):
            converter.to_v2(str(tmp_path / "out.csv"))

    def test_v1_to_v2_includes_run_description(self, tmp_path: Path) -> None:
        """Line 151: RunDescription written when sheet.description is set."""
        p = tmp_path / "v1.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        converter = SampleSheetConverter(str(p))
        # `description` is a runtime attribute set on SampleSheetV1 only; use
        # setattr so mypy doesn't need to narrow the parser-union type.
        setattr(converter._sheet, "description", "My run description")  # noqa: B010
        out = tmp_path / "out.csv"
        converter.to_v2(str(out))
        assert "RunDescription,My run description" in out.read_text()

    def test_v2_to_v1_drops_override_cycles_data_column(self, tmp_path: Path) -> None:
        """Lines 283, 367, 385: OverrideCycles as a BCLConvert_Data column is dropped."""
        p = tmp_path / "v2.csv"
        p.write_text(
            "[Header]\nFileFormatVersion,2\nRunName,Test\nInstrumentPlatform,NovaSeqXSeries\n\n"
            "[BCLConvert_Data]\n"
            "Lane,Sample_ID,Index,Index2,OverrideCycles\n"
            "1,S1,ATTACTCG,TATAGCCT,Y151;I8;I8;Y151\n"
        )
        out = tmp_path / "out.csv"
        SampleSheetConverter(str(p)).to_v1(str(out))
        assert "OverrideCycles" not in out.read_text()

    def test_v2_record_with_unknown_key_is_skipped(self, tmp_path: Path) -> None:
        """Defensive guard: a record carrying a key not in v1_columns is dropped.

        Hard to trigger via the parser, but verifies the inner branch directly.
        """
        p = tmp_path / "v2.csv"
        p.write_text(
            "[Header]\nFileFormatVersion,2\nRunName,T\nInstrumentPlatform,MiSeq\n\n"
            "[BCLConvert_Data]\nSample_ID,Index\nS1,ATTACTCG\n"
        )
        converter = SampleSheetConverter(str(p))
        row = converter._v2_record_to_v1(
            record={"Sample_ID": "S1", "Index": "ATTACTCG", "PhantomColumn": "X"},
            v1_columns=["Sample_ID", "index"],
        )
        assert row == ["S1", "ATTACTCG"]


# ---------------------------------------------------------------------------
# TestI5Orientation - issue #30
# ---------------------------------------------------------------------------


def _write_v1(
    tmp_path: Path,
    name: str,
    instrument: str | None,
    index2: str = "TATAGCCT",
) -> Path:
    """Write a minimal dual-index V1 sheet declaring *instrument*."""
    instr_line = f"Instrument Type,{instrument}\n" if instrument else ""
    content = (
        "[Header]\n"
        "IEMFileVersion,5\n"
        "Experiment Name,Run\n"
        f"{instr_line}"
        "\n"
        "[Reads]\n"
        "151\n"
        "151\n"
        "\n"
        "[Data]\n"
        "Lane,Sample_ID,index,index2,Sample_Project\n"
        f"1,S1,ATTACTCG,{index2},P1\n"
    )
    p = tmp_path / name
    p.write_text(content)
    return p


def _write_v2(
    tmp_path: Path,
    name: str,
    instrument_platform: str | None,
    index2: str = "TATAGCCT",
) -> Path:
    """Write a minimal dual-index V2 sheet declaring *instrument_platform*."""
    instr_line = f"InstrumentPlatform,{instrument_platform}\n" if instrument_platform else ""
    content = (
        "[Header]\n"
        "FileFormatVersion,2\n"
        "RunName,Run\n"
        f"{instr_line}"
        "\n"
        "[Reads]\n"
        "Read1Cycles,151\n"
        "Read2Cycles,151\n"
        "\n"
        "[BCLConvert_Data]\n"
        "Lane,Sample_ID,Index,Index2,Sample_Project\n"
        f"1,S1,ATTACTCG,{index2},P1\n"
    )
    p = tmp_path / name
    p.write_text(content)
    return p


class TestI5OrientationWorkflowA:
    """Workflow A (MiSeq, HiSeq 2000/2500): Index2 must pass through unchanged."""

    def test_v1_to_v2_miseq_does_not_rc(self, tmp_path: Path) -> None:
        p = _write_v1(tmp_path, "miseq.csv", "MiSeq", index2="TATAGCCT")
        out = tmp_path / "v2.csv"
        SampleSheetConverter(p).to_v2(out)
        v2 = SampleSheetV2(str(out))
        v2.parse()
        sample = v2.samples()[0]
        assert sample["index2"] == "TATAGCCT"

    def test_v2_to_v1_miseq_does_not_rc(self, tmp_path: Path) -> None:
        p = _write_v2(tmp_path, "miseq.csv", "MiSeq", index2="TATAGCCT")
        out = tmp_path / "v1.csv"
        SampleSheetConverter(p).to_v1(out)
        v1 = SampleSheetV1(str(out))
        v1.parse()
        sample = v1.samples()[0]
        assert sample["index2"] == "TATAGCCT"

    def test_v1_to_v2_to_v1_miseq_round_trip(self, tmp_path: Path) -> None:
        """Round-trip on workflow A produces an identical Index2."""
        p = _write_v1(tmp_path, "miseq.csv", "MiSeq", index2="TATAGCCT")
        v2_out = tmp_path / "v2.csv"
        v1_out = tmp_path / "v1.csv"

        SampleSheetConverter(p).to_v2(v2_out)
        SampleSheetConverter(str(v2_out)).to_v1(v1_out)

        v1 = SampleSheetV1(str(v1_out))
        v1.parse()
        assert v1.samples()[0]["index2"] == "TATAGCCT"


class TestI5OrientationWorkflowB:
    """Workflow B (NovaSeq X, NextSeq, iSeq, MiniSeq, HiSeq 3/4000): Index2 must RC."""

    def test_v1_to_v2_novaseq_xplus_rcs_index2(self, tmp_path: Path) -> None:
        p = _write_v1(tmp_path, "novax.csv", "NovaSeq X Plus", index2="TATAGCCT")
        out = tmp_path / "v2.csv"
        SampleSheetConverter(p).to_v2(out)
        v2 = SampleSheetV2(str(out))
        v2.parse()
        assert v2.samples()[0]["index2"] == reverse_complement("TATAGCCT")  # AGGCTATA

    def test_v2_to_v1_novaseq_xseries_rcs_index2(self, tmp_path: Path) -> None:
        p = _write_v2(tmp_path, "novax.csv", "NovaSeqXSeries", index2="TATAGCCT")
        out = tmp_path / "v1.csv"
        SampleSheetConverter(p).to_v1(out)
        v1 = SampleSheetV1(str(out))
        v1.parse()
        assert v1.samples()[0]["index2"] == "AGGCTATA"

    @pytest.mark.parametrize(
        "instrument",
        [
            "NovaSeq X Plus",
            "NovaSeqXPlus",
            "NovaSeqXSeries",
            "NextSeq 500",
            "NextSeq550",
            "NextSeq 1000",
            "NextSeq2000",
            "iSeq 100",
            "iSeq",
            "MiniSeq",
            "HiSeq 3000",
            "HiSeq4000",
        ],
    )
    def test_v1_to_v2_all_workflow_b_instruments_rc_index2(
        self, tmp_path: Path, instrument: str
    ) -> None:
        """Acceptance criteria: every documented workflow-B instrument must RC i5."""
        p = _write_v1(tmp_path, "in.csv", instrument, index2="TATAGCCT")
        out = tmp_path / "out.csv"
        SampleSheetConverter(p).to_v2(out)
        v2 = SampleSheetV2(str(out))
        v2.parse()
        assert v2.samples()[0]["index2"] == "AGGCTATA"

    def test_v1_to_v2_to_v1_novaseq_xplus_round_trip(self, tmp_path: Path) -> None:
        """Workflow-B round-trip restores the original V1 Index2 (RC + RC = identity)."""
        p = _write_v1(tmp_path, "novax.csv", "NovaSeq X Plus", index2="TATAGCCT")
        v2_out = tmp_path / "v2.csv"
        v1_out = tmp_path / "v1.csv"

        SampleSheetConverter(p).to_v2(v2_out)
        SampleSheetConverter(str(v2_out)).to_v1(v1_out)

        v1 = SampleSheetV1(str(v1_out))
        v1.parse()
        assert v1.samples()[0]["index2"] == "TATAGCCT"


class TestI5OrientationWorkflowOverride:
    """`--workflow` override takes precedence over header auto-detection."""

    def test_workflow_b_override_forces_rc_on_unknown_instrument(self, tmp_path: Path) -> None:
        p = _write_v1(tmp_path, "in.csv", instrument=None, index2="TATAGCCT")
        out = tmp_path / "out.csv"
        SampleSheetConverter(p, workflow="b").to_v2(out)
        v2 = SampleSheetV2(str(out))
        v2.parse()
        assert v2.samples()[0]["index2"] == "AGGCTATA"

    def test_workflow_a_override_blocks_rc_on_workflow_b_instrument(self, tmp_path: Path) -> None:
        """Explicit override wins over auto-detection - useful for chemistry overrides."""
        p = _write_v1(tmp_path, "in.csv", "NovaSeq X Plus", index2="TATAGCCT")
        out = tmp_path / "out.csv"
        SampleSheetConverter(p, workflow="a").to_v2(out)
        v2 = SampleSheetV2(str(out))
        v2.parse()
        assert v2.samples()[0]["index2"] == "TATAGCCT"

    def test_workflow_override_accepts_enum(self, tmp_path: Path) -> None:
        p = _write_v1(tmp_path, "in.csv", instrument=None, index2="TATAGCCT")
        out = tmp_path / "out.csv"
        SampleSheetConverter(p, workflow=Workflow.B).to_v2(out)
        v2 = SampleSheetV2(str(out))
        v2.parse()
        assert v2.samples()[0]["index2"] == "AGGCTATA"

    def test_bad_workflow_string_raises_at_init(self, tmp_path: Path) -> None:
        p = _write_v1(tmp_path, "in.csv", "MiSeq")
        with pytest.raises(ValueError, match="Unknown workflow"):
            SampleSheetConverter(p, workflow="x")


class TestI5OrientationFailureModes:
    """Acceptance criteria: fail loudly when workflow can't be determined."""

    def test_unknown_instrument_with_index2_raises(self, tmp_path: Path) -> None:
        """A dual-index sheet with no detectable instrument must NOT silently
        pass i5 through - that is the exact silent-misassignment bug."""
        p = _write_v1(tmp_path, "in.csv", instrument=None, index2="TATAGCCT")
        out = tmp_path / "out.csv"
        with pytest.raises(ValueError, match="cannot determine i5 orientation"):
            SampleSheetConverter(p).to_v2(out)

    def test_novaseq_6000_ambiguous_raises_without_override(self, tmp_path: Path) -> None:
        """NovaSeq 6000 is chemistry-dependent (v1.0 vs v1.5) and must require
        an explicit --workflow override."""
        p = _write_v1(tmp_path, "in.csv", "NovaSeq 6000", index2="TATAGCCT")
        out = tmp_path / "out.csv"
        with pytest.raises(ValueError, match="cannot determine i5 orientation"):
            SampleSheetConverter(p).to_v2(out)

    def test_unknown_instrument_single_index_does_not_raise(self, tmp_path: Path) -> None:
        """No Index2 → no decision needed → no failure."""
        content = (
            "[Header]\n"
            "IEMFileVersion,5\n"
            "Experiment Name,Run\n"
            "\n"
            "[Data]\n"
            "Lane,Sample_ID,index\n"
            "1,S1,ATTACTCG\n"
        )
        p = tmp_path / "in.csv"
        p.write_text(content)
        out = tmp_path / "out.csv"
        SampleSheetConverter(p).to_v2(out)
        assert out.exists()

    def test_unknown_instrument_empty_index2_column_does_not_raise(self, tmp_path: Path) -> None:
        """Index2 column exists but every value is empty → safe to pass through."""
        content = (
            "[Header]\n"
            "IEMFileVersion,5\n"
            "Experiment Name,Run\n"
            "\n"
            "[Data]\n"
            "Lane,Sample_ID,index,index2\n"
            "1,S1,ATTACTCG,\n"
        )
        p = tmp_path / "in.csv"
        p.write_text(content)
        out = tmp_path / "out.csv"
        SampleSheetConverter(p).to_v2(out)
        assert out.exists()


class TestInstrumentTypePreservedAcrossConversion:
    """The workflow signal must survive a V2→V1 conversion, otherwise the
    return trip can't auto-detect."""

    def test_v2_to_v1_preserves_instrument_platform_as_instrument_type(
        self, tmp_path: Path
    ) -> None:
        p = _write_v2(tmp_path, "in.csv", "NovaSeqXSeries", index2="TATAGCCT")
        out = tmp_path / "out.csv"
        SampleSheetConverter(p).to_v1(out)
        text = out.read_text()
        assert "Instrument Type,NovaSeqXSeries" in text

    def test_v1_to_v2_preserves_instrument_type(self, tmp_path: Path) -> None:
        p = _write_v1(tmp_path, "in.csv", "MiSeq")
        out = tmp_path / "out.csv"
        SampleSheetConverter(p).to_v2(out)
        text = out.read_text()
        assert "InstrumentType,MiSeq" in text


class TestI5OrientationCLI:
    """CLI surface: --workflow flag wiring and failure exit codes."""

    def test_cli_convert_with_workflow_b_succeeds(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from samplesheet_parser.cli import app

        p = _write_v1(tmp_path, "in.csv", instrument=None, index2="TATAGCCT")
        out = tmp_path / "out.csv"
        result = CliRunner().invoke(
            app,
            ["convert", str(p), "--to", "v2", "--output", str(out), "--workflow", "b"],
        )
        assert result.exit_code == 0
        v2 = SampleSheetV2(str(out))
        v2.parse()
        assert v2.samples()[0]["index2"] == "AGGCTATA"

    def test_cli_convert_without_workflow_on_unknown_instrument_exits_nonzero(
        self, tmp_path: Path
    ) -> None:
        from typer.testing import CliRunner

        from samplesheet_parser.cli import app

        p = _write_v1(tmp_path, "in.csv", instrument=None, index2="TATAGCCT")
        out = tmp_path / "out.csv"
        result = CliRunner().invoke(app, ["convert", str(p), "--to", "v2", "--output", str(out)])
        assert result.exit_code != 0
        assert "i5 orientation" in result.output or "workflow" in result.output.lower()

    def test_cli_convert_bad_workflow_value_exits_2(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from samplesheet_parser.cli import app

        p = _write_v1(tmp_path, "in.csv", "MiSeq")
        out = tmp_path / "out.csv"
        result = CliRunner().invoke(
            app, ["convert", str(p), "--to", "v2", "--output", str(out), "--workflow", "x"]
        )
        assert result.exit_code == 2
