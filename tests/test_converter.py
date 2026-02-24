"""Tests for SampleSheetConverter."""

import pytest
from samplesheet_parser.converter import SampleSheetConverter
from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def v1_sheet(tmp_path) -> str:
    """Minimal IEM V1 sheet with dual index and adapters."""
    content = (
        "[Header]\n"
        "IEMFileVersion,5\n"
        "Experiment Name,MyRun_20240115\n"
        "Date,2024-01-15\n"
        "Workflow,GenerateFASTQ\n"
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
def v1_no_reads(tmp_path) -> str:
    """V1 sheet with no [Reads] section."""
    content = (
        "[Header]\n"
        "IEMFileVersion,5\n"
        "Experiment Name,NoReadsRun\n"
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
def v1_single_index(tmp_path) -> str:
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
def v2_sheet(tmp_path) -> str:
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
def v2_with_cloud_data(tmp_path) -> str:
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

    def test_detects_v1(self, v1_sheet):
        from samplesheet_parser.enums import SampleSheetVersion
        conv = SampleSheetConverter(v1_sheet)
        assert conv.source_version == SampleSheetVersion.V1

    def test_detects_v2(self, v2_sheet):
        from samplesheet_parser.enums import SampleSheetVersion
        conv = SampleSheetConverter(v2_sheet)
        assert conv.source_version == SampleSheetVersion.V2

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            SampleSheetConverter(tmp_path / "nonexistent.csv")

    def test_repr(self, v1_sheet):
        conv = SampleSheetConverter(v1_sheet)
        r = repr(conv)
        assert "SampleSheetConverter" in r
        assert "V1" in r


# ---------------------------------------------------------------------------
# TestV1ToV2
# ---------------------------------------------------------------------------

class TestV1ToV2:

    def test_output_file_created(self, v1_sheet, tmp_path):
        out = tmp_path / "output_v2.csv"
        result = SampleSheetConverter(v1_sheet).to_v2(out)
        assert result.exists()

    def test_returns_path(self, v1_sheet, tmp_path):
        out = tmp_path / "output_v2.csv"
        result = SampleSheetConverter(v1_sheet).to_v2(out)
        assert str(out.resolve()) == str(result)

    def test_output_is_valid_v2(self, v1_sheet, tmp_path):
        """Converted output should be parseable by SampleSheetV2."""
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert sheet.header is not None
        assert sheet.header.get("FileFormatVersion") == "2"

    def test_run_name_preserved(self, v1_sheet, tmp_path):
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert sheet.experiment_name == "MyRun_20240115"

    def test_read_cycles_converted(self, v1_sheet, tmp_path):
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert sheet.reads.get("Read1Cycles") == 151
        assert sheet.reads.get("Read2Cycles") == 151

    def test_adapters_preserved(self, v1_sheet, tmp_path):
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert "CTGTCTCTTATACACATCT" in sheet.adapters

    def test_sample_ids_preserved(self, v1_sheet, tmp_path):
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        ids = [s["sample_id"] for s in sheet.samples()]
        assert "Sample1" in ids
        assert "Sample2" in ids

    def test_index_columns_remapped(self, v1_sheet, tmp_path):
        """V1 'index'/'index2' should become V2 'Index'/'Index2'."""
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert "Index" in sheet.columns
        assert "Index2" in sheet.columns
        # V1-only columns should be absent
        assert "I7_Index_ID" not in sheet.columns
        assert "I5_Index_ID" not in sheet.columns

    def test_index_values_preserved(self, v1_sheet, tmp_path):
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_sheet).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        sample = next(s for s in sheet.samples() if s["sample_id"] == "Sample1")
        assert sample["index"] == "ATTACTCG"
        assert sample["index2"] == "TATAGCCT"

    def test_no_reads_section(self, v1_no_reads, tmp_path):
        """V1 with no [Reads] should convert without error — empty [Reads] in V2."""
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_no_reads).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert sheet.records is not None

    def test_single_index_preserved(self, v1_single_index, tmp_path):
        out = tmp_path / "output_v2.csv"
        SampleSheetConverter(v1_single_index).to_v2(out)
        sheet = SampleSheetV2(str(out))
        sheet.parse()
        assert sheet.index_type() == "single"

    def test_already_v2_raises(self, v2_sheet, tmp_path):
        out = tmp_path / "output_v2.csv"
        with pytest.raises(ValueError, match="already V2"):
            SampleSheetConverter(v2_sheet).to_v2(out)


# ---------------------------------------------------------------------------
# TestV2ToV1
# ---------------------------------------------------------------------------

class TestV2ToV1:

    def test_output_file_created(self, v2_sheet, tmp_path):
        out = tmp_path / "output_v1.csv"
        result = SampleSheetConverter(v2_sheet).to_v1(out)
        assert result.exists()

    def test_returns_path(self, v2_sheet, tmp_path):
        out = tmp_path / "output_v1.csv"
        result = SampleSheetConverter(v2_sheet).to_v1(out)
        assert str(out.resolve()) == str(result)

    def test_output_is_valid_v1(self, v2_sheet, tmp_path):
        """Converted output should be parseable by SampleSheetV1."""
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        assert sheet.iem_version == "5"

    def test_run_name_preserved(self, v2_sheet, tmp_path):
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        assert sheet.experiment_name == "TestRunV2"

    def test_read_cycles_converted(self, v2_sheet, tmp_path):
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        assert 151 in sheet.read_lengths

    def test_adapters_preserved(self, v2_sheet, tmp_path):
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        assert "CTGTCTCTTATACACATCT" in sheet.adapters

    def test_sample_ids_preserved(self, v2_sheet, tmp_path):
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        ids = [s["sample_id"] for s in sheet.samples()]
        assert "Sample1" in ids
        assert "Sample2" in ids

    def test_index_columns_remapped(self, v2_sheet, tmp_path):
        """V2 'Index'/'Index2' should become V1 'index'/'index2'."""
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        assert "index" in sheet.columns
        assert "index2" in sheet.columns
        assert "Index" not in sheet.columns

    def test_index_values_preserved(self, v2_sheet, tmp_path):
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        sheet = SampleSheetV1(str(out))
        sheet.parse()
        sample = next(s for s in sheet.samples() if s["sample_id"] == "Sample1")
        assert sample["index"] == "ATTACTCG"
        assert sample["index2"] == "TATAGCCT"

    def test_v2_only_settings_dropped(self, v2_sheet, tmp_path):
        """OverrideCycles and other V2-only settings should not appear in V1 output."""
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_sheet).to_v1(out)
        content = out.read_text()
        assert "OverrideCycles" not in content
        assert "SoftwareVersion" not in content
        assert "InstrumentPlatform" not in content

    def test_cloud_data_dropped_with_warning(self, v2_with_cloud_data, tmp_path):
        """Cloud_Data section should be dropped and logged as a warning."""
        out = tmp_path / "output_v1.csv"
        SampleSheetConverter(v2_with_cloud_data).to_v1(out)
        content = out.read_text()
        assert "Cloud_Data" not in content
        assert "Cloud_Settings" not in content

    def test_already_v1_raises(self, v1_sheet, tmp_path):
        out = tmp_path / "output_v1.csv"
        with pytest.raises(ValueError, match="already V1"):
            SampleSheetConverter(v1_sheet).to_v1(out)


# ---------------------------------------------------------------------------
# TestRoundTrip
# ---------------------------------------------------------------------------

class TestRoundTrip:

    def test_v1_to_v2_to_v1_sample_ids(self, v1_sheet, tmp_path):
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

    def test_v1_to_v2_to_v1_index_values(self, v1_sheet, tmp_path):
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

    def test_v2_to_v1_to_v2_sample_ids(self, v2_sheet, tmp_path):
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
