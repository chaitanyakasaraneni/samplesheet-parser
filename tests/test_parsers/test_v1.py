"""Tests for SampleSheetV1."""

import pytest

from samplesheet_parser.parsers.v1 import SampleSheetV1


class TestSampleSheetV1Parsing:

    def test_parse_header(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        assert sheet.iem_version == "5"
        assert sheet.experiment_name == "TestRun"
        assert sheet.date == "2024-01-15"
        assert sheet.chemistry == "Amplicon"

    def test_parse_header_application_and_instrument(self, v1_minimal):
        """Application, Instrument Type, Index Adapters extracted as named attributes."""
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        assert sheet.application == "FASTQ Only"
        assert sheet.instrument_type == "MiSeq"
        assert sheet.assay == "TruSeq Stranded mRNA"
        assert sheet.index_adapters == "TruSeq RNA CD Indexes (96 Indexes)"

    def test_parse_reads(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        assert sheet.read_lengths == [151, 151]

    def test_parse_reads_skips_invalid(self, tmp_path):
        p = tmp_path / "bad_reads.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Reads]\n151\nABC\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        assert sheet.read_lengths == [151]

    def test_parse_adapters_iem_two_key(self, v1_minimal):
        """IEM spec format: Adapter (Read1) + AdapterRead2 parsed as separate keys."""
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        assert sheet.adapter_read1 == "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA"
        assert sheet.adapter_read2 == "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT"
        assert len(sheet.adapters) == 2

    def test_parse_reverse_complement(self, v1_minimal):
        """ReverseComplement setting parsed as integer."""
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        assert sheet.reverse_complement == 0

    def test_parse_reverse_complement_invalid_defaults(self, tmp_path):
        p = tmp_path / "bad_rc.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Settings]\nReverseComplement,not-a-number\nAdapter,CTGTCTCTTATACACATCT\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        assert sheet.reverse_complement == 0

    def test_parse_adapters_iem_spec_format(self, tmp_path):
        """Official IEM spec uses Adapter (Read1) + AdapterRead2 as two separate keys."""
        p = tmp_path / "iem_spec.csv"
        content_str = (
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Settings]\nReverseComplement,0\nAdapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA\nAdapterRead2,AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        p.write_text(content_str)
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        assert sheet.adapter_read1 == "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA"
        assert sheet.adapter_read2 == "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT"
        assert sheet.adapters == [
            "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA",
            "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT",
        ]
        assert sheet.reverse_complement == 0

    def test_parse_adapters_read1_only_no_default_for_read2(self, tmp_path):
        """Adapter key alone must NOT default adapter_read2 — Read1-only trimming."""
        p = tmp_path / "read1_trim_only.csv"
        content_str = (
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Settings]\nAdapter,CTGTCTCTTATACACATCT\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        p.write_text(content_str)
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        assert sheet.adapter_read1 == "CTGTCTCTTATACACATCT"
        assert sheet.adapter_read2 == ""   # must NOT default to Adapter value
        assert sheet.adapters == ["CTGTCTCTTATACACATCT"]

    def test_parse_adapters_per_read_bclconvert_alias(self, tmp_path):
        """AdapterRead1 (BCLConvert alias) is recognised as Read1."""
        p = tmp_path / "per_read.csv"
        content_str = (
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Settings]\nAdapterRead1,CTGTCTCTTATACACATCT\nAdapterRead2,AGATCGGAAGAGC\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        p.write_text(content_str)
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        assert sheet.adapter_read1 == "CTGTCTCTTATACACATCT"
        assert sheet.adapter_read2 == "AGATCGGAAGAGC"
        assert sheet.adapters == ["CTGTCTCTTATACACATCT", "AGATCGGAAGAGC"]

    def test_parse_adapters_read1_only(self, tmp_path):
        """AdapterRead1 only — adapter_read2 should be empty string."""
        p = tmp_path / "read1_only.csv"
        content_str = (
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Settings]\nAdapterRead1,CTGTCTCTTATACACATCT\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        p.write_text(content_str)
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        assert sheet.adapter_read1 == "CTGTCTCTTATACACATCT"
        assert sheet.adapter_read2 == ""
        assert sheet.adapters == ["CTGTCTCTTATACACATCT"]

    def test_parse_data_columns(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        assert "Sample_ID" in sheet.columns
        assert "index" in sheet.columns
        assert "index2" in sheet.columns

    def test_parse_data_record_count(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        assert len(sheet.records) == 2

    def test_parse_data_skips_malformed_lines(self, tmp_path):
        p = tmp_path / "bad_data.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n"
            "1,S1,ATTACTCG\n"
            "1,S2\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        assert len(sheet.records) == 1

    def test_parse_no_reads_section(self, v1_no_reads):
        # Should not raise — [Reads] is optional
        sheet = SampleSheetV1(v1_no_reads)
        sheet.parse()
        assert sheet.read_lengths == []

    def test_experiment_id_override(self, v1_with_experiment_id):
        sheet = SampleSheetV1(
            v1_with_experiment_id,
            experiment_id="240115_A01234_0042_AHJLG7DRXX",
        )
        sheet.parse()
        assert sheet.experiment_name == "240115_A01234_0042_AHJLG7DRXX"

    def test_experiment_id_parsed(self, v1_with_experiment_id):
        sheet = SampleSheetV1(
            v1_with_experiment_id,
            experiment_id="240115_A01234_0042_AHJLG7DRXX",
        )
        sheet.parse()
        assert sheet.flowcell_id == "HJLG7DRXX"
        assert sheet.flowcell_side == "A"
        assert sheet.seq_date == "240115"
        assert sheet.instrument_id == "A01234"

    def test_invalid_experiment_id_warns_not_raises(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal, experiment_id="not-a-valid-run-id")
        sheet.parse()  # Should not raise, just warn
        assert sheet.flowcell_id is None

    def test_clean_overrides_experiment_name_and_strips_ws(self, tmp_path):
        p = tmp_path / "dirty.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,OldName\n\n"
            "[Data]\nLane,Sample_ID,index\n"
            "1, Sample 1 , AT T AC T CG \n"
        )
        sheet = SampleSheetV1(str(p), experiment_id="NewName")
        sheet.clean()
        content = p.read_text()
        assert "Experiment Name,NewName" in content
        assert "ATTACTCG" in content
        assert (tmp_path / "dirty.csv.backup").exists()


class TestSampleSheetV1Samples:

    def test_samples_count(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        samples = sheet.samples()
        assert len(samples) == 2

    def test_sample_fields_present(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        s = sheet.samples()[0]
        for key in ("sample_id", "sample_name", "index", "index2",
                    "i7_index_id", "i5_index_id", "sample_project"):
            assert key in s, f"Missing key: {key}"

    def test_custom_columns_preserved(self, tmp_path):
        p = tmp_path / "custom_cols.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index,Custom_Field\n"
            "1,S1,ATTACTCG,CustomValue\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        sample = sheet.samples()[0]
        assert sample["Custom_Field"] == "CustomValue"

    def test_sample_ids(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        ids = [s["sample_id"] for s in sheet.samples()]
        assert ids == ["Sample1", "Sample2"]

    def test_no_duplicate_samples(self, v1_multi_lane):
        sheet = SampleSheetV1(v1_multi_lane)
        sheet.parse()
        # Multi-lane: all 4 samples should appear (each is unique)
        samples = sheet.samples()
        assert len(samples) == 4

    def test_samples_raises_before_parse(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal, clean=False)
        with pytest.raises(RuntimeError, match="Call parse()"):
            sheet.samples()


class TestSampleSheetV1IndexType:

    def test_dual_index(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        assert sheet.index_type() == "dual"

    def test_single_index(self, v1_single_index):
        sheet = SampleSheetV1(v1_single_index)
        sheet.parse()
        assert sheet.index_type() == "single"

    def test_index_type_raises_before_parse(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal, clean=False)
        with pytest.raises(RuntimeError):
            sheet.index_type()


class TestSampleSheetV1Equality:

    def test_equal_sheets(self, v1_minimal, tmp_path):
        import shutil
        copy_path = str(tmp_path / "copy.csv")
        shutil.copy(v1_minimal, copy_path)

        s1 = SampleSheetV1(v1_minimal)
        s2 = SampleSheetV1(copy_path)
        s1.parse()
        s2.parse()
        assert s1 == s2

    def test_not_equal_different_sheets(self, v1_minimal, v1_single_index):
        s1 = SampleSheetV1(v1_minimal)
        s2 = SampleSheetV1(v1_single_index)
        s1.parse()
        s2.parse()
        assert s1 != s2

    def test_not_equal_different_type(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        assert sheet.__eq__("not a sheet") == NotImplemented

    def test_repr(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        r = repr(sheet)
        assert "SampleSheetV1" in r
        assert "records=2" in r
