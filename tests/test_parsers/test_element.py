"""Tests for the Element Biosciences AVITI RunManifest parser."""

from __future__ import annotations

import pytest

from samplesheet_parser import SampleSheetFactory, SampleSheetParser
from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.parsers.element import ElementRunManifest

MANIFEST = """\
[RUNVALUES]
KeyName,Value
run_name,AVITI_Run
instrument,AVITI

[SETTINGS]
SettingName,Value
R1Adapter,CTGTCTCTTATACACATCT

[SAMPLES]
SampleName,Index1,Index2,Lane,Project
S1,ACGTACGTAC,TGCATGCATG,1,ProjA
S2,GGTTCCAAGG,CCAAGGTTCC,1,ProjA
"""

MANIFEST_NO_RUNVALUES = """\
[SAMPLES]
SampleName,Index1,Index2,Lane
S1,ACGTACGTAC,TGCATGCATG,1
"""

SINGLE_INDEX_MANIFEST = """\
[RUNVALUES]
KeyName,Value
run_name,AVITI_Single

[SAMPLES]
SampleName,Index1,Lane
S1,ACGTACGTAC,1
"""


def _write(tmp_path, content, name="RunManifest.csv"):
    p = tmp_path / name
    p.write_text(content)
    return p


class TestParsing:
    def test_satisfies_protocol(self, tmp_path):
        sheet = ElementRunManifest(str(_write(tmp_path, MANIFEST)), parse=True)
        assert isinstance(sheet, SampleSheetParser)

    def test_samples_mapped_to_shared_schema(self, tmp_path):
        sheet = ElementRunManifest(str(_write(tmp_path, MANIFEST)), parse=True)
        samples = sheet.samples()
        assert len(samples) == 2
        assert samples[0]["sample_id"] == "S1"
        assert samples[0]["index"] == "ACGTACGTAC"
        assert samples[0]["index2"] == "TGCATGCATG"
        assert samples[0]["lane"] == "1"
        assert samples[0]["sample_project"] == "ProjA"

    def test_header_and_settings(self, tmp_path):
        sheet = ElementRunManifest(str(_write(tmp_path, MANIFEST)), parse=True)
        assert sheet.header["run_name"] == "AVITI_Run"
        assert sheet.instrument == "AVITI"
        assert sheet.adapters == ["CTGTCTCTTATACACATCT"]

    def test_index_type_dual(self, tmp_path):
        sheet = ElementRunManifest(str(_write(tmp_path, MANIFEST)), parse=True)
        assert sheet.index_type() == "dual"

    def test_index_type_single(self, tmp_path):
        sheet = ElementRunManifest(str(_write(tmp_path, SINGLE_INDEX_MANIFEST)), parse=True)
        assert sheet.index_type() == "single"

    def test_default_instrument_when_absent(self, tmp_path):
        sheet = ElementRunManifest(str(_write(tmp_path, MANIFEST_NO_RUNVALUES)), parse=True)
        assert sheet.instrument == "AVITI"

    def test_missing_samples_section_raises(self, tmp_path):
        p = _write(tmp_path, "[RUNVALUES]\nKeyName,Value\nrun_name,X\n")
        with pytest.raises(ValueError, match="samples"):
            ElementRunManifest(str(p), parse=True)

    def test_parse_custom_section(self, tmp_path):
        sheet = ElementRunManifest(str(_write(tmp_path, MANIFEST)), parse=True)
        settings = sheet.parse_custom_section("SETTINGS")
        assert settings["R1Adapter"] == "CTGTCTCTTATACACATCT"


class TestDetection:
    def test_is_manifest_true(self, tmp_path):
        assert ElementRunManifest.is_manifest(_write(tmp_path, MANIFEST))

    def test_is_manifest_true_without_runvalues(self, tmp_path):
        assert ElementRunManifest.is_manifest(_write(tmp_path, MANIFEST_NO_RUNVALUES))

    def test_is_manifest_false_on_illumina(self, tmp_path):
        illumina = "[Header]\nFileFormatVersion,2\n\n[BCLConvert_Data]\nSample_ID,Index\nS1,ACGT\n"
        assert not ElementRunManifest.is_manifest(_write(tmp_path, illumina))

    def test_factory_autodetects(self, tmp_path):
        factory = SampleSheetFactory()
        sheet = factory.create_parser(str(_write(tmp_path, MANIFEST)), parse=True)
        assert factory.version is SampleSheetVersion.ELEMENT_AVITI
        assert isinstance(sheet, ElementRunManifest)

    def test_factory_detection_survives_clear_registry(self, tmp_path):
        SampleSheetFactory.clear_registry()
        factory = SampleSheetFactory()
        sheet = factory.create_parser(str(_write(tmp_path, MANIFEST)), parse=True)
        assert isinstance(sheet, ElementRunManifest)
