"""Tests for SampleSheetFactory — format detection and parser delegation."""

import pytest

from samplesheet_parser import SampleSheetFactory, SampleSheetVersion
from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2


class TestFormatDetection:

    def test_detects_v1_by_iem_version(self, v1_minimal):
        factory = SampleSheetFactory()
        sheet = factory.create_parser(v1_minimal)
        assert factory.version == SampleSheetVersion.V1
        assert isinstance(sheet, SampleSheetV1)

    def test_detects_v2_by_file_format_version(self, v2_minimal):
        factory = SampleSheetFactory()
        sheet = factory.create_parser(v2_minimal)
        assert factory.version == SampleSheetVersion.V2
        assert isinstance(sheet, SampleSheetV2)

    def test_detects_v2_by_section_names(self, v2_bclconvert_sections_only):
        """No [Header] but [BCLConvert_Settings] present → V2 detected."""
        factory = SampleSheetFactory()
        factory.create_parser(v2_bclconvert_sections_only)
        assert factory.version == SampleSheetVersion.V2

    def test_defaults_to_v1_when_no_indicators(self, tmp_path):
        """Sheet with no version markers → defaults to V1."""
        p = tmp_path / "ambiguous.csv"
        p.write_text(
            "[Header]\nExperiment Name,Test\n\n"
            "[Data]\nSample_ID,index\nS1,ATCACG\n"
        )
        factory = SampleSheetFactory()
        factory.create_parser(str(p))
        assert factory.version == SampleSheetVersion.V1

    def test_raises_file_not_found(self, tmp_path):
        factory = SampleSheetFactory()
        with pytest.raises(FileNotFoundError):
            factory.create_parser(str(tmp_path / "doesnotexist.csv"))


class TestFactoryParseDelegate:

    def test_parse_true_parses_immediately(self, v1_minimal):
        sheet = SampleSheetFactory().create_parser(v1_minimal, parse=True)
        # If parse ran, records should be populated
        assert sheet.records is not None
        assert len(sheet.records) >= 1

    def test_parse_false_defers(self, v1_minimal):
        sheet = SampleSheetFactory().create_parser(v1_minimal, parse=False)
        assert sheet.records is None  # not yet parsed

    def test_experiment_id_forwarded(self, v1_with_experiment_id):
        run_id = "240115_A01234_0042_AHJLG7DRXX"
        sheet = SampleSheetFactory().create_parser(
            v1_with_experiment_id, experiment_id=run_id, parse=True
        )
        assert sheet.experiment_name == run_id


class TestFactoryGetUmiLength:

    def test_umi_length_v2(self, v2_with_umi):
        factory = SampleSheetFactory()
        factory.create_parser(v2_with_umi, parse=True)
        assert factory.get_umi_length() == 9

    def test_umi_length_v1_no_umi(self, v1_minimal):
        factory = SampleSheetFactory()
        factory.create_parser(v1_minimal, parse=True)
        assert factory.get_umi_length() == 0

    def test_umi_length_v1_with_header_field(self, tmp_path):
        p = tmp_path / "umi_v1.csv"
        p.write_text(
            "[Header]\nIEMFileVersion,5\nExperiment Name,Test\nIndexUMILength,8\n\n"
            "[Data]\nSample_ID,index\nS1,ATCACGAT\n"
        )
        factory = SampleSheetFactory()
        factory.create_parser(str(p), parse=True)
        assert factory.get_umi_length() == 8

    def test_umi_raises_before_create_parser(self):
        with pytest.raises(RuntimeError, match="create_parser"):
            SampleSheetFactory().get_umi_length()


class TestFactoryRepr:

    def test_repr_before_use(self):
        r = repr(SampleSheetFactory())
        assert "version=None" in r
        assert "parser=None" in r

    def test_repr_after_use(self, v2_minimal):
        factory = SampleSheetFactory()
        factory.create_parser(v2_minimal)
        r = repr(factory)
        assert "SampleSheetV2" in r
        assert "V2" in r
