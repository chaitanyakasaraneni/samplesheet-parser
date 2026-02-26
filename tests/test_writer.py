"""
Tests for samplesheet_parser.writer.SampleSheetWriter.

Covers:
- Build V1 and V2 sheets from scratch
- from_sheet() round-trip for V1 and V2
- add_sample / remove_sample / update_sample
- set_header / set_reads / set_adapter / set_override_cycles
- write() with and without validate=True
- to_string() output is parseable
- V1 column presence logic (index2, plate, well, etc.)
- V2 optional column logic (Index2, Sample_Project)
- Extra columns passed through verbatim
- Error cases (empty sheet, missing sample_id, validation failure)
- Cross-format: from_sheet V1 → write V2 and vice versa
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.writer import SampleSheetWriter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_fixture(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content).lstrip())
    return p


def _parse(path: Path):
    from samplesheet_parser.factory import SampleSheetFactory
    return SampleSheetFactory().create_parser(path, parse=True, clean=False)


def _writer_v2() -> SampleSheetWriter:
    """Return a minimal valid V2 writer with two samples."""
    w = SampleSheetWriter(version=SampleSheetVersion.V2)
    w.set_header(run_name="TestRun", platform="NovaSeqXSeries")
    w.set_reads(read1=151, read2=151, index1=10, index2=10)
    w.set_adapter("CTGTCTCTTATACACATCT", "CTGTCTCTTATACACATCT")
    w.set_override_cycles("Y151;I10;I10;Y151")
    w.add_sample("S1", index="ATTACTCGAT", index2="TATAGCCTGT", project="Proj")
    w.add_sample("S2", index="TCCGGAGACC", index2="ATAGAGGCAC", project="Proj")
    return w


def _writer_v1() -> SampleSheetWriter:
    """Return a minimal valid V1 writer with two samples."""
    w = SampleSheetWriter(version=SampleSheetVersion.V1)
    w.set_header(
        run_name="TestRun",
        workflow="GenerateFASTQ",
        chemistry="Amplicon",
    )
    w.set_reads(read1=151, read2=151)
    w.set_adapter("CTGTCTCTTATACACATCT")
    w.add_sample("S1", index="ATTACTCG", index2="TATAGCCT", project="Proj")
    w.add_sample("S2", index="TCCGGAGA", index2="ATAGAGGC", project="Proj")
    return w


# ---------------------------------------------------------------------------
# V2 — from scratch
# ---------------------------------------------------------------------------

class TestWriteV2FromScratch:
    def test_write_creates_file(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v2().write(out)
        assert out.exists()

    def test_returns_absolute_path(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        result = _writer_v2().write(out)
        assert result.is_absolute()

    def test_output_parseable(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v2().write(out)
        sheet = _parse(out)
        assert sheet is not None

    def test_sample_count_preserved(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v2().write(out)
        sheet = _parse(out)
        assert len(sheet.records) == 2

    def test_sample_ids_preserved(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v2().write(out)
        sheet = _parse(out)
        ids = {r["Sample_ID"] for r in sheet.records}
        assert ids == {"S1", "S2"}

    def test_indexes_preserved(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v2().write(out)
        sheet = _parse(out)
        rec = next(r for r in sheet.records if r["Sample_ID"] == "S1")
        assert rec["Index"] == "ATTACTCGAT"
        assert rec["Index2"] == "TATAGCCTGT"

    def test_run_name_in_header(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v2().write(out)
        sheet = _parse(out)
        assert sheet.header.get("RunName") == "TestRun"

    def test_file_format_version_is_2(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v2().write(out)
        sheet = _parse(out)
        assert sheet.header.get("FileFormatVersion") == "2"

    def test_read_cycles_written(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v2().write(out)
        sheet = _parse(out)
        assert sheet.reads.get("Read1Cycles") == 151
        assert sheet.reads.get("Read2Cycles") == 151

    def test_adapter_written(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v2().write(out)
        sheet = _parse(out)
        assert sheet.settings.get("AdapterRead1") == "CTGTCTCTTATACACATCT"

    def test_override_cycles_written(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v2().write(out)
        sheet = _parse(out)
        assert sheet.settings.get("OverrideCycles") == "Y151;I10;I10;Y151"

    def test_no_index2_column_omitted_when_single_index(self, tmp_path):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        w.set_header(run_name="Run")
        w.set_reads(read1=76)
        w.set_adapter("CTGTCTCTTATACACATCT")
        w.add_sample("S1", index="ATTACTCG")
        content = w.to_string()
        # Index2 column should not appear
        data_line = [line for line in content.splitlines() if line.startswith("Lane,")][0]
        assert "Index2" not in data_line

    def test_project_column_omitted_when_no_project(self, tmp_path):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        w.set_header(run_name="Run")
        w.set_reads(read1=76)
        w.set_adapter("CTGTCTCTTATACACATCT")
        w.add_sample("S1", index="ATTACTCG")
        content = w.to_string()
        data_line = [line for line in content.splitlines() if line.startswith("Lane,")][0]
        assert "Sample_Project" not in data_line

    def test_software_version_written(self, tmp_path):
        w = _writer_v2()
        w.set_software_version("4.2.7")
        out = tmp_path / "SampleSheet.csv"
        w.write(out)
        sheet = _parse(out)
        assert sheet.settings.get("SoftwareVersion") == "4.2.7"

    def test_extra_setting_written(self, tmp_path):
        w = _writer_v2()
        w.set_setting("NoLaneSplitting", "1")
        out = tmp_path / "SampleSheet.csv"
        w.write(out)
        sheet = _parse(out)
        assert sheet.settings.get("NoLaneSplitting") == "1"

    def test_to_string_no_file_created(self, tmp_path):
        content = _writer_v2().to_string()
        assert "[Header]" in content
        assert "[BCLConvert_Data]" in content

    def test_sample_count_property(self):
        w = _writer_v2()
        assert w.sample_count == 2

    def test_sample_ids_property(self):
        w = _writer_v2()
        assert set(w.sample_ids) == {"S1", "S2"}


# ---------------------------------------------------------------------------
# V1 — from scratch
# ---------------------------------------------------------------------------

class TestWriteV1FromScratch:
    def test_write_creates_file(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v1().write(out)
        assert out.exists()

    def test_output_parseable(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v1().write(out)
        sheet = _parse(out)
        assert sheet is not None

    def test_sample_count_preserved(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v1().write(out)
        sheet = _parse(out)
        assert len(sheet.records) == 2

    def test_iem_version_in_header(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v1().write(out)
        sheet = _parse(out)
        assert sheet.iem_version == "5"

    def test_experiment_name_written(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v1().write(out)
        sheet = _parse(out)
        assert sheet.experiment_name == "TestRun"

    def test_read_lengths_written(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v1().write(out)
        sheet = _parse(out)
        assert sheet.read_lengths == [151, 151]

    def test_adapter_written_as_adapter_key(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v1().write(out)
        content = out.read_text()
        assert "Adapter,CTGTCTCTTATACACATCT" in content

    def test_indexes_preserved(self, tmp_path):
        out = tmp_path / "SampleSheet.csv"
        _writer_v1().write(out)
        sheet = _parse(out)
        rec = next(r for r in sheet.records if r["Sample_ID"] == "S1")
        assert rec["index"] == "ATTACTCG"
        assert rec["index2"] == "TATAGCCT"

    def test_index2_column_omitted_when_single_index(self, tmp_path):
        w = SampleSheetWriter(version=SampleSheetVersion.V1)
        w.set_header(run_name="Run", workflow="GenerateFASTQ")
        w.set_reads(read1=76)
        w.set_adapter("CTGTCTCTTATACACATCT")
        w.add_sample("S1", index="ATTACTCG")
        content = w.to_string()
        data_line = [line for line in content.splitlines() if line.startswith("Lane,")][0]
        assert "index2" not in data_line

    def test_plate_well_columns_included_when_set(self, tmp_path):
        w = SampleSheetWriter(version=SampleSheetVersion.V1)
        w.set_header(run_name="Run", workflow="GenerateFASTQ")
        w.set_reads(read1=76)
        w.set_adapter("CTGTCTCTTATACACATCT")
        w.add_sample("S1", index="ATTACTCG", sample_plate="Plate1", sample_well="A01")
        content = w.to_string()
        data_line = [line for line in content.splitlines() if line.startswith("Lane,")][0]
        assert "Sample_Plate" in data_line
        assert "Sample_Well" in data_line

    def test_plate_well_columns_omitted_when_not_set(self, tmp_path):
        content = _writer_v1().to_string()
        data_line = [line for line in content.splitlines() if line.startswith("Lane,")][0]
        assert "Sample_Plate" not in data_line
        assert "Sample_Well" not in data_line

    def test_default_workflow_written(self, tmp_path):
        w = SampleSheetWriter(version=SampleSheetVersion.V1)
        w.set_header(run_name="Run")   # no workflow set
        w.set_reads(read1=76)
        w.set_adapter("CTGTCTCTTATACACATCT")
        w.add_sample("S1", index="ATTACTCG")
        content = w.to_string()
        assert "Workflow,GenerateFASTQ" in content


# ---------------------------------------------------------------------------
# add_sample / remove_sample / update_sample
# ---------------------------------------------------------------------------

class TestSampleManagement:
    def test_add_sample_increments_count(self):
        w = _writer_v2()
        before = w.sample_count
        w.add_sample("S3", index="TAGGCATGCC", index2="CCTATCCTGT")
        assert w.sample_count == before + 1

    def test_add_sample_index_uppercased(self):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        w.set_header(run_name="R")
        w.set_reads(read1=76)
        w.add_sample("S1", index="attactcg")
        assert w._samples[0].index == "ATTACTCG"

    def test_add_sample_empty_id_raises(self):
        w = _writer_v2()
        with pytest.raises(ValueError, match="sample_id"):
            w.add_sample("", index="ATTACTCG")

    def test_add_sample_empty_index_raises(self):
        w = _writer_v2()
        with pytest.raises(ValueError, match="index"):
            w.add_sample("S99", index="")

    def test_remove_sample_by_id(self):
        w = _writer_v2()
        w.remove_sample("S1")
        assert "S1" not in w.sample_ids

    def test_remove_sample_count_decremented(self):
        w = _writer_v2()
        w.remove_sample("S1")
        assert w.sample_count == 1

    def test_remove_sample_not_found_raises(self):
        w = _writer_v2()
        with pytest.raises(KeyError):
            w.remove_sample("NONEXISTENT")

    def test_remove_sample_by_lane(self):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        w.set_header(run_name="R")
        w.set_reads(read1=76)
        w.add_sample("S1", index="ATTACTCG", lane="1")
        w.add_sample("S1", index="ATTACTCG", lane="2")
        w.remove_sample("S1", lane="1")
        assert w.sample_count == 1
        assert w._samples[0].lane == "2"

    def test_remove_sample_wrong_lane_raises(self):
        w = _writer_v2()
        with pytest.raises(KeyError):
            w.remove_sample("S1", lane="9")

    def test_update_sample_index(self):
        w = _writer_v2()
        w.update_sample("S1", index="GGGGGGGGGG")
        rec = next(s for s in w._samples if s.sample_id == "S1")
        assert rec.index == "GGGGGGGGGG"

    def test_update_sample_index_uppercased(self):
        w = _writer_v2()
        w.update_sample("S1", index="gggggggggg")
        rec = next(s for s in w._samples if s.sample_id == "S1")
        assert rec.index == "GGGGGGGGGG"

    def test_update_sample_project(self):
        w = _writer_v2()
        w.update_sample("S1", project="NewProject")
        rec = next(s for s in w._samples if s.sample_id == "S1")
        assert rec.project == "NewProject"

    def test_update_sample_not_found_raises(self):
        w = _writer_v2()
        with pytest.raises(KeyError):
            w.update_sample("NONEXISTENT", project="X")

    def test_update_sample_extra_field_stored(self):
        w = _writer_v2()
        w.update_sample("S1", CustomField="custom_val")
        rec = next(s for s in w._samples if s.sample_id == "S1")
        assert rec.extra.get("CustomField") == "custom_val"


# ---------------------------------------------------------------------------
# CSV safety — _validate_field
# ---------------------------------------------------------------------------

class TestCSVSafety:
    def test_comma_in_sample_id_raises(self):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        with pytest.raises(ValueError, match="sample_id"):
            w.add_sample("S1,bad", index="ATTACTCG")

    def test_newline_in_sample_id_raises(self):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        with pytest.raises(ValueError, match="sample_id"):
            w.add_sample("S1\nbad", index="ATTACTCG")

    def test_comma_in_index_raises(self):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        with pytest.raises(ValueError, match="index"):
            w.add_sample("S1", index="ATTACT,CG")

    def test_comma_in_project_raises(self):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        with pytest.raises(ValueError, match="project"):
            w.add_sample("S1", index="ATTACTCG", project="Proj,A")

    def test_quote_in_project_raises(self):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        with pytest.raises(ValueError, match="project"):
            w.add_sample("S1", index="ATTACTCG", project='Proj"A')

    def test_comma_in_extra_key_raises(self):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        with pytest.raises(ValueError):
            w.add_sample("S1", index="ATTACTCG", **{"Bad,Key": "val"})

    def test_comma_in_extra_value_raises(self):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        with pytest.raises(ValueError):
            w.add_sample("S1", index="ATTACTCG", CustomCol="val,bad")

    def test_safe_values_pass_through(self):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        # Should not raise
        w.add_sample(
            "SAMPLE-001",
            index="ATTACTCG",
            project="Project_A",
            description="Normal description",
        )
        assert w.sample_count == 1


# ---------------------------------------------------------------------------
# Extra columns
# ---------------------------------------------------------------------------

class TestExtraColumns:
    def test_extra_column_in_header(self, tmp_path):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        w.set_header(run_name="R")
        w.set_reads(read1=76)
        w.add_sample("S1", index="ATTACTCG", MyCustomCol="val1")
        content = w.to_string()
        data_line = [line for line in content.splitlines() if line.startswith("Lane,")][0]
        assert "MyCustomCol" in data_line

    def test_extra_column_values_written(self, tmp_path):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        w.set_header(run_name="R")
        w.set_reads(read1=76)
        w.add_sample("S1", index="ATTACTCG", MyCustomCol="val1")
        content = w.to_string()
        assert "val1" in content

    def test_missing_extra_value_written_as_empty(self, tmp_path):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        w.set_header(run_name="R")
        w.set_reads(read1=76)
        # S1 has the extra col, S2 does not
        w.add_sample("S1", index="ATTACTCG", MyCustomCol="val1")
        w.add_sample("S2", index="TCCGGAGA")
        content = w.to_string()
        # S2 row should have an empty trailing field
        lines = content.splitlines()
        data_lines = lines[lines.index("[BCLConvert_Data]") + 2:]
        s2_line = next(line for line in data_lines if line.startswith("1,S2,"))
        assert s2_line.endswith(",")


# ---------------------------------------------------------------------------
# write() validation
# ---------------------------------------------------------------------------

class TestValidationOnWrite:
    def test_empty_sheet_raises(self, tmp_path):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        with pytest.raises(ValueError, match="empty"):
            w.write(tmp_path / "out.csv")

    def test_duplicate_index_raises_on_write(self, tmp_path):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        w.set_header(run_name="R")
        w.set_reads(read1=76, index1=8)
        w.set_adapter("CTGTCTCTTATACACATCT")
        w.add_sample("S1", index="ATTACTCG", lane="1")
        w.add_sample("S2", index="ATTACTCG", lane="1")  # same index, same lane
        with pytest.raises(ValueError, match="validation"):
            w.write(tmp_path / "out.csv", validate=True)

    def test_duplicate_index_validate_false_writes_anyway(self, tmp_path):
        w = SampleSheetWriter(version=SampleSheetVersion.V2)
        w.set_header(run_name="R")
        w.set_reads(read1=76, index1=8)
        w.set_adapter("CTGTCTCTTATACACATCT")
        w.add_sample("S1", index="ATTACTCG", lane="1")
        w.add_sample("S2", index="ATTACTCG", lane="1")
        out = tmp_path / "out.csv"
        w.write(out, validate=False)
        assert out.exists()

    def test_valid_sheet_passes_validation(self, tmp_path):
        out = tmp_path / "out.csv"
        _writer_v2().write(out, validate=True)
        assert out.exists()


# ---------------------------------------------------------------------------
# from_sheet() — V2 round-trip
# ---------------------------------------------------------------------------

class TestFromSheetV2:
    def test_round_trip_sample_count(self, tmp_path):
        src = tmp_path / "src.csv"
        _writer_v2().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet)
        out = tmp_path / "out.csv"
        writer2.write(out, validate=False)
        assert _parse(out).records is not None
        assert len(_parse(out).records) == 2

    def test_round_trip_sample_ids(self, tmp_path):
        src = tmp_path / "src.csv"
        _writer_v2().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet)
        out = tmp_path / "out.csv"
        writer2.write(out, validate=False)
        ids = {r["Sample_ID"] for r in _parse(out).records}
        assert ids == {"S1", "S2"}

    def test_round_trip_indexes(self, tmp_path):
        src = tmp_path / "src.csv"
        _writer_v2().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet)
        out = tmp_path / "out.csv"
        writer2.write(out, validate=False)
        rec = next(r for r in _parse(out).records if r["Sample_ID"] == "S1")
        assert rec["Index"] == "ATTACTCGAT"

    def test_round_trip_run_name(self, tmp_path):
        src = tmp_path / "src.csv"
        _writer_v2().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet)
        out = tmp_path / "out.csv"
        writer2.write(out, validate=False)
        assert _parse(out).header.get("RunName") == "TestRun"

    def test_remove_after_from_sheet(self, tmp_path):
        src = tmp_path / "src.csv"
        _writer_v2().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet)
        writer2.remove_sample("S1")
        out = tmp_path / "out.csv"
        writer2.write(out, validate=False)
        ids = {r["Sample_ID"] for r in _parse(out).records}
        assert ids == {"S2"}

    def test_version_preserved_by_default(self, tmp_path):
        src = tmp_path / "src.csv"
        _writer_v2().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet)
        assert writer2.version == SampleSheetVersion.V2


# ---------------------------------------------------------------------------
# from_sheet() — V1 round-trip
# ---------------------------------------------------------------------------

class TestFromSheetV1:
    def test_round_trip_sample_count(self, tmp_path):
        src = tmp_path / "src.csv"
        _writer_v1().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet)
        out = tmp_path / "out.csv"
        writer2.write(out, validate=False)
        assert len(_parse(out).records) == 2

    def test_round_trip_indexes(self, tmp_path):
        src = tmp_path / "src.csv"
        _writer_v1().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet)
        out = tmp_path / "out.csv"
        writer2.write(out, validate=False)
        rec = next(r for r in _parse(out).records if r["Sample_ID"] == "S1")
        assert rec["index"] == "ATTACTCG"

    def test_version_preserved_by_default(self, tmp_path):
        src = tmp_path / "src.csv"
        _writer_v1().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet)
        assert writer2.version == SampleSheetVersion.V1


# ---------------------------------------------------------------------------
# Cross-format: from_sheet V1 → write V2
# ---------------------------------------------------------------------------

class TestCrossFormatWrite:
    def test_v1_to_v2_via_writer(self, tmp_path):
        src = tmp_path / "v1.csv"
        _writer_v1().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet, version=SampleSheetVersion.V2)
        out = tmp_path / "v2.csv"
        writer2.write(out, validate=False)
        parsed = _parse(out)
        from samplesheet_parser.parsers.v2 import SampleSheetV2
        assert isinstance(parsed, SampleSheetV2)

    def test_v1_to_v2_sample_ids_preserved(self, tmp_path):
        src = tmp_path / "v1.csv"
        _writer_v1().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet, version=SampleSheetVersion.V2)
        out = tmp_path / "v2.csv"
        writer2.write(out, validate=False)
        ids = {r["Sample_ID"] for r in _parse(out).records}
        assert ids == {"S1", "S2"}

    def test_v2_to_v1_via_writer(self, tmp_path):
        src = tmp_path / "v2.csv"
        _writer_v2().write(src, validate=False)
        sheet = _parse(src)
        writer2 = SampleSheetWriter.from_sheet(sheet, version=SampleSheetVersion.V1)
        out = tmp_path / "v1.csv"
        writer2.write(out, validate=False)
        parsed = _parse(out)
        from samplesheet_parser.parsers.v1 import SampleSheetV1
        assert isinstance(parsed, SampleSheetV1)
