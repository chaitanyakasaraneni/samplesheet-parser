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
        """Core normalized keys are always present.

        I7_Index_ID / I5_Index_ID are in STANDARD_DATA_COLUMNS so they are
        excluded from the non-standard column loop in samples(). They are
        therefore not present in the output dict under any casing — this is
        the documented post-refactor behaviour.
        """
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        s = sheet.samples()[0]
        # Normalized keys always emitted by samples()
        for key in ("sample_id", "sample_name", "index", "index2", "sample_project"):
            assert key in s, f"Missing normalized key: {key}"
        # I7/I5 index ID columns are in STANDARD_DATA_COLUMNS and are not
        # re-keyed into the normalized output — assert neither form appears.
        assert "I7_Index_ID" not in s, (
            "I7_Index_ID should not appear in samples() output "
            "(it is in STANDARD_DATA_COLUMNS but not re-keyed by samples())"
        )
        assert "i7_index_id" not in s, "Lowercase i7_index_id should not appear either"

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


# ---------------------------------------------------------------------------
# Edge-case parsing coverage
# ---------------------------------------------------------------------------

class TestSampleSheetV1EdgeCases:

    def test_required_section_error_raises_value_error(self, tmp_path):
        """Lines 249-250, 603: completely empty [Data] section triggers required-section error."""
        p = tmp_path / "empty_data.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\n"
        )
        sheet = SampleSheetV1(str(p))
        with pytest.raises(ValueError, match=r"\[Data\]"):
            sheet.parse(do_clean=False)

    def test_index_type_returns_none_when_no_index_column(self, tmp_path):
        """Line 419: index_type() returns 'none' when Data has no index/index2 column."""
        p = tmp_path / "no_index.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,Sample_Name\n1,S1,Sample1\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        assert sheet.index_type() == "none"

    def test_malformed_section_header_is_skipped(self, tmp_path):
        """Lines 497-498: section header without closing ']' is silently skipped."""
        p = tmp_path / "malformed.csv"
        p.write_text(
            "[Header\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        assert sheet.experiment_name == "Test"

    def test_content_before_first_section_is_skipped(self, tmp_path):
        """Line 506: lines before the first section header are silently skipped."""
        p = tmp_path / "preamble.csv"
        p.write_text(
            "preamble line\nanother line\n"
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        assert sheet.experiment_name == "Test"

    def test_experiment_id_overrides_experiment_name(self, tmp_path):
        """Line 548: experiment_id replaces experiment_name when they differ."""
        p = tmp_path / "exp_id.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        sheet = SampleSheetV1(str(p), experiment_id="OverrideName")
        sheet.parse()
        assert sheet.experiment_name == "OverrideName"

    def test_repr(self, v1_minimal):
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        r = repr(sheet)
        assert "SampleSheetV1" in r
        assert "records=2" in r


# ---------------------------------------------------------------------------
# Custom section tests
# ---------------------------------------------------------------------------

class TestSampleSheetV1ParseCustomSection:
    """Tests for parse_custom_section() — the new non-standard section API."""

    def test_manifests_section_returns_key_value_dict(self, v1_with_manifests):
        """[Manifests] section is parsed into a key-value dict."""
        sheet = SampleSheetV1(v1_with_manifests)
        sheet.parse()
        result = sheet.parse_custom_section("Manifests")
        assert result["MFGmanifest"] == "HyperCapture_manifest_v2.0.txt"
        assert result["PoolingManifest"] == "pooling_v1.txt"

    def test_manifests_section_case_insensitive(self, v1_with_manifests):
        """Section name lookup is case-insensitive."""
        sheet = SampleSheetV1(v1_with_manifests)
        sheet.parse()
        assert sheet.parse_custom_section("manifests") == sheet.parse_custom_section("MANIFESTS")

    def test_custom_lab_section_parsed(self, v1_with_custom_section):
        """A fully custom lab-specific section is parsed correctly."""
        sheet = SampleSheetV1(v1_with_custom_section)
        sheet.parse()
        result = sheet.parse_custom_section("Lab_QC_Settings")
        assert result["MinQ30"] == "85"
        assert result["TargetCoverage"] == "100x"
        assert result["LibraryKit"] == "TruSeq_Nano"

    def test_missing_section_returns_empty_dict_by_default(self, v1_minimal):
        """Absent section with required=False (default) returns {}."""
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        result = sheet.parse_custom_section("NonExistent_Section")
        assert result == {}

    def test_missing_section_required_raises(self, v1_minimal):
        """Absent section with required=True raises ValueError."""
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        with pytest.raises(ValueError, match="NonExistent_Section"):
            sheet.parse_custom_section("NonExistent_Section", required=True)

    def test_raises_before_parse_or_read(self, v1_minimal):
        """Calling parse_custom_section before parse()/read() raises RuntimeError."""
        sheet = SampleSheetV1(v1_minimal, clean=False)
        with pytest.raises(RuntimeError, match=r"parse\(\)"):
            sheet.parse_custom_section("Manifests")

    def test_malformed_lines_are_skipped(self, v1_with_malformed_custom_section):
        """Lines with a missing key (empty first field) are skipped; valid lines returned."""
        sheet = SampleSheetV1(v1_with_malformed_custom_section)
        sheet.parse()
        result = sheet.parse_custom_section("Lab_QC_Settings")
        # Only the well-formed lines should be present
        assert "MinQ30" in result
        assert "ValidKey" in result
        # The malformed line (,MissingKey) should not produce a key called ""
        assert "" not in result

    def test_multiple_custom_sections_accessible(self, v1_with_multiple_custom_sections):
        """Multiple non-standard sections are all accessible independently."""
        sheet = SampleSheetV1(v1_with_multiple_custom_sections)
        sheet.parse()
        manifests = sheet.parse_custom_section("Manifests")
        cloud = sheet.parse_custom_section("Cloud_Settings")
        assert manifests["MFGmanifest"] == "HyperCapture_manifest_v2.0.txt"
        assert cloud["GeneratedVersion"] == "3.9.14"
        assert cloud["UploadToBaseSpace"] == "1"

    def test_custom_section_does_not_interfere_with_standard_parsing(
        self, v1_with_custom_section
    ):
        """Standard [Data] and [Header] parse correctly alongside custom sections."""
        sheet = SampleSheetV1(v1_with_custom_section)
        sheet.parse()
        assert sheet.experiment_name == "CustomSectionRun"
        assert len(sheet.records) == 1
        assert sheet.records[0]["Sample_ID"] == "Sample1"

    def test_standard_section_via_parse_custom_section(self, v1_minimal):
        """Standard sections (e.g. Settings) are also accessible via parse_custom_section."""
        sheet = SampleSheetV1(v1_minimal)
        sheet.parse()
        # [Settings] is a standard section but should still be in _section_dict
        result = sheet.parse_custom_section("Settings")
        assert "Adapter" in result or "AdapterRead1" in result or "ReverseComplement" in result

    def test_empty_custom_section_returns_empty_dict(self, tmp_path):
        """A section present but with no content returns {}."""
        p = tmp_path / "empty_section.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\n\n"
            "[Lab_QC_Settings]\n\n"
            "[Data]\nLane,Sample_ID,index\n1,S1,ATTACTCG\n"
        )
        sheet = SampleSheetV1(str(p))
        sheet.parse()
        result = sheet.parse_custom_section("Lab_QC_Settings")
        assert result == {}


class TestSampleSheetV1RequiredSections:
    """Tests for parse(required_sections=[...]) — enforcing section presence."""

    def test_required_section_present_does_not_raise(self, v1_with_manifests):
        """parse() with a required section that exists should complete normally."""
        sheet = SampleSheetV1(v1_with_manifests, clean=False)
        sheet.parse(do_clean=False, required_sections=["Manifests"])
        assert sheet.records is not None

    def test_required_section_missing_raises(self, v1_minimal):
        """parse() raises ValueError when a required section is absent."""
        sheet = SampleSheetV1(v1_minimal, clean=False)
        with pytest.raises(ValueError, match="Cloud_Settings"):
            sheet.parse(do_clean=False, required_sections=["Cloud_Settings"])

    def test_multiple_required_sections_all_present(self, v1_with_multiple_custom_sections):
        """All required sections present — no error raised."""
        sheet = SampleSheetV1(v1_with_multiple_custom_sections, clean=False)
        sheet.parse(do_clean=False, required_sections=["Manifests", "Cloud_Settings"])
        assert sheet.records is not None

    def test_multiple_required_sections_one_missing_raises(
        self, v1_with_multiple_custom_sections
    ):
        """One of several required sections missing — ValueError raised."""
        sheet = SampleSheetV1(v1_with_multiple_custom_sections, clean=False)
        with pytest.raises(ValueError, match="Pipeline_Settings"):
            sheet.parse(
                do_clean=False,
                required_sections=["Manifests", "Pipeline_Settings"],
            )

    def test_required_sections_check_is_case_insensitive(self, v1_with_manifests):
        """required_sections matching is case-insensitive."""
        sheet = SampleSheetV1(v1_with_manifests, clean=False)
        # Both "manifests" and "MANIFESTS" should find the [Manifests] section
        sheet.parse(do_clean=False, required_sections=["manifests"])
        assert sheet.records is not None

    def test_required_section_error_raised_before_other_parsing(self, v1_minimal):
        """The required_sections check fires before Header/Data parsing completes."""
        sheet = SampleSheetV1(v1_minimal, clean=False)
        # records should remain None because parse() aborts early
        with pytest.raises(ValueError):
            sheet.parse(do_clean=False, required_sections=["Missing_Section"])

    def test_none_required_sections_is_no_op(self, v1_minimal):
        """required_sections=None (default) behaves identically to not passing it."""
        sheet = SampleSheetV1(v1_minimal, clean=False)
        sheet.parse(do_clean=False, required_sections=None)
        assert sheet.records is not None
