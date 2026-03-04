"""Tests for SampleSheetV2."""

import pytest

from samplesheet_parser.parsers.v2 import ReadStructure, SampleSheetV2


class TestSampleSheetV2Parsing:

    def test_parse_header(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        assert sheet.header["FileFormatVersion"] == "2"
        assert sheet.header["RunName"] == "TestRunV2"
        assert sheet.instrument_platform == "NovaSeqXSeries"

    def test_parse_reads(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        assert sheet.reads["Read1Cycles"] == 151
        assert sheet.reads["Index1Cycles"] == 10

    def test_parse_reads_skips_invalid(self, tmp_path):
        p = tmp_path / "bad_reads.csv"
        p.write_text(
            "[Header]\nFileFormatVersion,2\nRunName,Test\n\n"
            "[Reads]\nRead1Cycles,ABC\nIndex1Cycles,10\n\n"
            "[BCLConvert_Data]\nSample_ID,Index\nS1,ATTACTCG\n"
        )
        sheet = SampleSheetV2(str(p))
        sheet.parse()
        assert "Read1Cycles" not in sheet.reads
        assert sheet.reads["Index1Cycles"] == 10

    def test_parse_settings(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        assert sheet.software_version == "3.9.3"
        assert "CTGTCTCTTATACACATCT" in sheet.adapters

    def test_parse_settings_custom_fields(self, tmp_path):
        p = tmp_path / "custom_settings.csv"
        p.write_text(
            "[Header]\nFileFormatVersion,2\nRunName,Test\n\n"
            "[BCLConvert_Settings]\nAdapterRead1,CTGTCTCTTATACACATCT\nCustom_Setting,CustomValue\n\n"
            "[BCLConvert_Data]\nSample_ID,Index\nS1,ATTACTCG\n"
        )
        sheet = SampleSheetV2(str(p))
        sheet.parse()
        assert "CTGTCTCTTATACACATCT" in sheet.adapters
        assert "Custom_Setting" in sheet.custom_fields["settings"]

    def test_parse_data_columns(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        assert "Sample_ID" in sheet.columns
        assert "Index" in sheet.columns
        assert "Index2" in sheet.columns

    def test_parse_data_record_count(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        assert len(sheet.records) == 2

    def test_parse_data_missing_required_columns(self, tmp_path):
        p = tmp_path / "missing_index.csv"
        p.write_text(
            "[Header]\nFileFormatVersion,2\nRunName,Test\n\n"
            "[BCLConvert_Data]\nSample_ID\nS1\n"
        )
        sheet = SampleSheetV2(str(p))
        with pytest.raises(ValueError, match="Missing required .*columns"):
            sheet.parse()

    def test_parse_data_custom_fields(self, tmp_path):
        p = tmp_path / "custom_data.csv"
        p.write_text(
            "[Header]\nFileFormatVersion,2\nRunName,Test\n\n"
            "[BCLConvert_Data]\nSample_ID,Index,Custom_Foo,ExtraCol\n"
            "S1,ATTACTCG,Alpha,Beta\n"
        )
        sheet = SampleSheetV2(str(p))
        sheet.parse()
        sample = sheet.samples()[0]
        assert sample["Custom_Foo"] == "Alpha"
        assert sample["ExtraCol"] == "Beta"
        assert "Custom_Foo" in sheet.custom_fields["data"]
        assert "ExtraCol" in sheet.custom_fields["data"]

    def test_missing_file_format_version_raises(self, tmp_path):
        bad_sheet = tmp_path / "bad.csv"
        bad_sheet.write_text(
            "[Header]\nRunName,Test\n\n[BCLConvert_Data]\nSample_ID,Index\nS1,ATCACG\n"
        )
        sheet = SampleSheetV2(str(bad_sheet))
        with pytest.raises(ValueError, match="FileFormatVersion"):
            sheet.parse()


class TestSampleSheetV2Samples:

    def test_samples_count(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        assert len(sheet.samples()) == 2

    def test_sample_fields(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        s = sheet.samples()[0]
        for key in ("sample_id", "index", "index2", "run_name", "instrument_platform"):
            assert key in s, f"Missing key: {key}"

    def test_sample_ids(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        ids = [s["sample_id"] for s in sheet.samples()]
        assert "Sample1" in ids
        assert "Sample2" in ids

    def test_clean_standardizes_sections_and_overrides_name(self, tmp_path):
        p = tmp_path / "dirty_v2.csv"
        p.write_text(
            "[Header]\nFileFormatVersion,2\nExperimentName,OldName\n\n"
            "[settings]\nAdapterRead1,CTGTCTCTTATACACATCT\n\n"
            "[data]\nSample_ID,Index\nS1, AT T AC T CG \n"
        )
        sheet = SampleSheetV2(str(p), experiment_id="NewName")
        sheet.clean()
        content = p.read_text()
        assert "ExperimentName,NewName" in content
        assert "[BCLConvert_Settings]" in content
        assert "[BCLConvert_Data]" in content
        assert "ATTACTCG" in content
        assert (tmp_path / "dirty_v2.csv.backup").exists()


class TestSampleSheetV2IndexType:

    def test_dual_index(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        assert sheet.index_type() == "dual"

    def test_single_index(self, v2_no_index2):
        sheet = SampleSheetV2(v2_no_index2)
        sheet.parse()
        assert sheet.index_type() == "single"

    def test_index_type_raises_before_parse(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal, clean=False)
        with pytest.raises(RuntimeError):
            sheet.index_type()


class TestOverrideCyclesDecoding:

    def test_no_umi(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        assert sheet.get_umi_length() == 0

    def test_index1_umi(self, v2_with_umi):
        sheet = SampleSheetV2(v2_with_umi)
        sheet.parse()
        assert sheet.get_umi_length() == 9

    def test_read_umi(self, v2_with_read_umi):
        sheet = SampleSheetV2(v2_with_read_umi)
        sheet.parse()
        assert sheet.get_umi_length() == 5

    def test_read_structure_index_umi(self, v2_with_umi):
        sheet = SampleSheetV2(v2_with_umi)
        sheet.parse()
        rs = sheet.get_read_structure()
        assert isinstance(rs, ReadStructure)
        assert rs.umi_length == 9
        assert rs.umi_location == "index2"   # Y151;I10U9;I10;Y151 → segment 2 = index2
        assert rs.read_structure["index2_umi"] == 9

    def test_read_structure_template_lengths(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        rs = sheet.get_read_structure()
        assert rs.read_structure.get("read1_template") == 151
        assert rs.read_structure.get("read4_template") == 151

    def test_get_umi_no_settings(self, tmp_path):
        sheet_path = tmp_path / "noset.csv"
        sheet_path.write_text(
            "[Header]\nFileFormatVersion,2\nInstrumentPlatform,NovaSeqXSeries\n\n"
            "[BCLConvert_Data]\nSample_ID,Index\nS1,ATCACGAT\n"
        )
        sheet = SampleSheetV2(str(sheet_path))
        sheet.parse()
        assert sheet.get_umi_length() == 0

    def test_parse_override_cycles_directly(self, v2_minimal):
        """Test _parse_override_cycles as a unit."""
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()

        # No UMI
        r = sheet._parse_override_cycles("Y151;I10;I10;Y151")
        assert r.umi_length == 0
        assert r.umi_location is None

        # Index UMI
        r = sheet._parse_override_cycles("Y151;I10U9;I10;Y151")
        assert r.umi_length == 9

        # Read UMI on both reads
        r = sheet._parse_override_cycles("U5Y146;I8;I8;U5Y146")
        assert r.umi_length == 5
        assert r.umi_location in ("read1", "read4")

        # Empty string
        r = sheet._parse_override_cycles("")
        assert r.umi_length == 0


class TestSampleSheetV2BCLConvertSectionsOnly:

    def test_no_header_falls_back(self, v2_bclconvert_sections_only):
        """Sheet with no [Header] at all should raise because FileFormatVersion is missing."""
        sheet = SampleSheetV2(v2_bclconvert_sections_only)
        with pytest.raises(ValueError, match="FileFormatVersion"):
            sheet.parse()


class TestSampleSheetV2CloudData:

    def test_parse_cloud_data_skips_malformed(self, tmp_path):
        p = tmp_path / "cloud.csv"
        p.write_text(
            "[Header]\nFileFormatVersion,2\nRunName,Test\n\n"
            "[BCLConvert_Data]\nSample_ID,Index\nS1,ATTACTCG\n\n"
            "[Cloud_Data]\nSample_ID,ProjectName\n"
            "S1,Project1\n"
            "S2\n"
        )
        sheet = SampleSheetV2(str(p))
        sheet.parse()
        assert len(sheet.cloud_data) == 1
        assert sheet.cloud_data[0]["Sample_ID"] == "S1"


class TestSampleSheetV2Equality:

    def test_equal_sheets(self, v2_minimal, tmp_path):
        import shutil
        copy = str(tmp_path / "copy.csv")
        shutil.copy(v2_minimal, copy)
        s1 = SampleSheetV2(v2_minimal)
        s2 = SampleSheetV2(copy)
        s1.parse()
        s2.parse()
        assert s1 == s2

    def test_repr(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        assert "SampleSheetV2" in repr(sheet)
        assert "records=2" in repr(sheet)

    def test_not_equal_different_type(self, v2_minimal):
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        assert sheet.__eq__("not a sheet") == NotImplemented


# ---------------------------------------------------------------------------
# Custom section tests
# ---------------------------------------------------------------------------

class TestSampleSheetV2ParseCustomSection:
    """Tests for parse_custom_section() on V2 sheets."""

    def test_cloud_settings_parsed(self, v2_with_cloud_settings):
        """[Cloud_Settings] section returns key-value dict."""
        sheet = SampleSheetV2(v2_with_cloud_settings)
        sheet.parse()
        result = sheet.parse_custom_section("Cloud_Settings")
        assert result["GeneratedVersion"] == "3.9.14"
        assert result["UploadToBaseSpace"] == "1"

    def test_custom_pipeline_section_parsed(self, v2_with_custom_section):
        """[Pipeline_Settings] is stored in _section_dict and accessible via
        parse_custom_section. clean() only normalises the exact canonical names
        [Settings] and [BCLConvert_Settings] → [BCLConvert_Settings], so custom
        sections like [Pipeline_Settings] pass through cleaning untouched."""
        sheet = SampleSheetV2(v2_with_custom_section)
        sheet.parse()
        result = sheet.parse_custom_section("Pipeline_Settings")
        assert result["PipelineVersion"] == "2.1.0"
        assert result["OutputFormat"] == "CRAM"
        assert result["ReferenceGenome"] == "hg38"

    def test_section_lookup_is_case_insensitive(self, v2_with_cloud_settings):
        """Section name is matched case-insensitively."""
        sheet = SampleSheetV2(v2_with_cloud_settings)
        sheet.parse()
        assert sheet.parse_custom_section("cloud_settings") == \
               sheet.parse_custom_section("CLOUD_SETTINGS")

    def test_missing_section_returns_empty_dict(self, v2_minimal):
        """Absent section with required=False (default) returns {}."""
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        assert sheet.parse_custom_section("NonExistent_Section") == {}

    def test_missing_section_required_raises(self, v2_minimal):
        """Absent section with required=True raises ValueError."""
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        with pytest.raises(ValueError, match="NonExistent_Section"):
            sheet.parse_custom_section("NonExistent_Section", required=True)

    def test_raises_before_parse_or_read(self, v2_minimal):
        """Calling parse_custom_section before parse()/read() raises RuntimeError."""
        sheet = SampleSheetV2(v2_minimal, clean=False)
        with pytest.raises(RuntimeError, match="parse()"):
            sheet.parse_custom_section("Cloud_Settings")

    def test_multiple_custom_sections_accessible(self, v2_with_multiple_custom_sections):
        """Multiple non-standard sections are all independently accessible.
        Both [Cloud_Settings] and [Pipeline_Settings] survive clean() because
        clean() now only normalises exact canonical BCLConvert section names."""
        sheet = SampleSheetV2(v2_with_multiple_custom_sections)
        sheet.parse()
        cloud = sheet.parse_custom_section("Cloud_Settings")
        pipeline = sheet.parse_custom_section("Pipeline_Settings")
        assert cloud["GeneratedVersion"] == "3.9.14"
        assert pipeline["OutputFormat"] == "FASTQ"

    def test_custom_section_does_not_break_standard_parsing(self, v2_with_custom_section):
        """Standard BCLConvert sections parse correctly alongside custom sections."""
        sheet = SampleSheetV2(v2_with_custom_section)
        sheet.parse()
        assert sheet.header["RunName"] == "CustomSectionRun"
        assert len(sheet.records) == 1
        assert sheet.records[0]["Sample_ID"] == "Sample1"
        assert sheet.software_version == "3.9.3"

    def test_bclconvert_settings_accessible_via_parse_custom_section(self, v2_minimal):
        """[BCLConvert_Settings] itself is accessible via parse_custom_section."""
        sheet = SampleSheetV2(v2_minimal)
        sheet.parse()
        result = sheet.parse_custom_section("BCLConvert_Settings")
        assert "AdapterRead1" in result or "SoftwareVersion" in result

    def test_empty_custom_section_returns_empty_dict(self, tmp_path):
        """A section present in the file but with no content lines returns {}."""
        p = tmp_path / "empty_section.csv"
        p.write_text(
            "[Header]\nFileFormatVersion,2\nRunName,Test\n\n"
            "[BCLConvert_Data]\nSample_ID,Index\nS1,ATTACTCG\n\n"
            "[Pipeline_Settings]\n\n"
        )
        sheet = SampleSheetV2(str(p))
        sheet.parse()
        assert sheet.parse_custom_section("Pipeline_Settings") == {}

    def test_malformed_lines_in_custom_section_are_skipped(self, tmp_path):
        """Lines with a missing key (empty first field) are skipped; valid lines returned.
        Uses Cloud_Settings — a V2 DEFAULT_SECTION — to ensure parse_custom_section
        reads it correctly today without needing non-default section support."""
        p = tmp_path / "malformed_custom.csv"
        p.write_text(
            "[Header]\nFileFormatVersion,2\nRunName,Test\n\n"
            "[BCLConvert_Data]\nSample_ID,Index\nS1,ATTACTCG\n\n"
            "[Cloud_Settings]\n"
            "ValidKey,ValidValue\n"
            ",MissingKey\n"
            "AnotherKey,AnotherValue\n"
        )
        sheet = SampleSheetV2(str(p))
        sheet.parse()
        result = sheet.parse_custom_section("Cloud_Settings")
        assert result["ValidKey"] == "ValidValue"
        assert result["AnotherKey"] == "AnotherValue"
        assert "" not in result


class TestSampleSheetV2RequiredSections:
    """Tests for parse(required_sections=[...]) on V2 sheets."""

    def test_required_section_present_does_not_raise(self, v2_with_cloud_settings):
        """parse() with a required section that exists completes normally."""
        sheet = SampleSheetV2(v2_with_cloud_settings, clean=False)
        sheet.parse(do_clean=False, required_sections=["Cloud_Settings"])
        assert sheet.records is not None

    def test_required_section_missing_raises(self, v2_minimal):
        """parse() raises ValueError when a required section is absent."""
        sheet = SampleSheetV2(v2_minimal, clean=False)
        with pytest.raises(ValueError, match="Pipeline_Settings"):
            sheet.parse(do_clean=False, required_sections=["Pipeline_Settings"])

    def test_multiple_required_sections_all_present(
        self, v2_with_multiple_custom_sections
    ):
        """All required sections present — no error raised."""
        sheet = SampleSheetV2(v2_with_multiple_custom_sections, clean=False)
        sheet.parse(
            do_clean=False,
            required_sections=["Cloud_Settings", "Pipeline_Settings"],
        )
        assert sheet.records is not None

    def test_multiple_required_sections_one_missing_raises(self, v2_with_cloud_settings):
        """One of several required sections missing — ValueError raised."""
        sheet = SampleSheetV2(v2_with_cloud_settings, clean=False)
        with pytest.raises(ValueError, match="Pipeline_Settings"):
            sheet.parse(
                do_clean=False,
                required_sections=["Cloud_Settings", "Pipeline_Settings"],
            )

    def test_required_sections_check_is_case_insensitive(self, v2_with_cloud_settings):
        """required_sections matching is case-insensitive."""
        sheet = SampleSheetV2(v2_with_cloud_settings, clean=False)
        sheet.parse(do_clean=False, required_sections=["cloud_settings"])
        assert sheet.records is not None

    def test_none_required_sections_is_no_op(self, v2_minimal):
        """required_sections=None (default) behaves identically to not passing it."""
        sheet = SampleSheetV2(v2_minimal, clean=False)
        sheet.parse(do_clean=False, required_sections=None)
        assert sheet.records is not None

    def test_required_standard_section_bcl_data_present(self, v2_minimal):
        """Standard BCLConvert_Data can itself be named in required_sections."""
        sheet = SampleSheetV2(v2_minimal, clean=False)
        sheet.parse(do_clean=False, required_sections=["BCLConvert_Data"])
        assert sheet.records is not None
