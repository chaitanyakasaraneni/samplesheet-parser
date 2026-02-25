"""
Tests for samplesheet_parser.diff.SampleSheetDiff.

All fixtures write temporary CSV files via pytest's tmp_path so nothing
is left on disk after the test run.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from samplesheet_parser.diff import DiffResult, HeaderChange, SampleChange, SampleSheetDiff

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content).lstrip())
    return p


# ---------------------------------------------------------------------------
# Shared content strings
# ---------------------------------------------------------------------------

V1_BASE = """\
[Header]
IEMFileVersion,5
Experiment Name,Run001
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,CTGTCTCTTATACACATCT

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleA,SampleA,D701,ATTACTCG,D501,TATAGCCT,ProjectX
1,SampleB,SampleB,D702,TCCGGAGA,D502,ATAGAGGC,ProjectX
"""

V1_INDEX_CHANGED = """\
[Header]
IEMFileVersion,5
Experiment Name,Run001
Date,2024-01-15
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,CTGTCTCTTATACACATCT

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,SampleA,SampleA,D701,ATTACTCG,D501,TATAGCCT,ProjectX
1,SampleB,SampleB,D702,GGGGGGGG,D502,ATAGAGGC,ProjectX
"""

V2_BASE = """\
[Header]
FileFormatVersion,2
RunName,Run001
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I8;I8;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,SampleA,ATTACTCG,TATAGCCT,ProjectX
1,SampleB,TCCGGAGA,ATAGAGGC,ProjectX
"""

V2_SAMPLE_ADDED = """\
[Header]
FileFormatVersion,2
RunName,Run001
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I8;I8;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,SampleA,ATTACTCG,TATAGCCT,ProjectX
1,SampleB,TCCGGAGA,ATAGAGGC,ProjectX
1,SampleC,CCCCCCCC,GGGGGGGG,ProjectX
"""

V2_SAMPLE_REMOVED = """\
[Header]
FileFormatVersion,2
RunName,Run001
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I8;I8;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,SampleA,ATTACTCG,TATAGCCT,ProjectX
"""

V2_READ_CYCLES_CHANGED = """\
[Header]
FileFormatVersion,2
RunName,Run001
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,76
Read2Cycles,76
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT
OverrideCycles,Y76;I8;I8;Y76

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,SampleA,ATTACTCG,TATAGCCT,ProjectX
1,SampleB,TCCGGAGA,ATAGAGGC,ProjectX
"""

V2_PROJECT_CHANGED = """\
[Header]
FileFormatVersion,2
RunName,Run001
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I8;I8;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,SampleA,ATTACTCG,TATAGCCT,ProjectY
1,SampleB,TCCGGAGA,ATAGAGGC,ProjectX
"""

V2_MULTILANE = """\
[Header]
FileFormatVersion,2
RunName,Run001
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I8;I8;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,SampleA,ATTACTCG,TATAGCCT,ProjectX
1,SampleB,TCCGGAGA,ATAGAGGC,ProjectX
2,SampleC,TAGGCATG,CCTATCCT,ProjectX
2,SampleD,CTCTCTAC,GGCTCTGA,ProjectX
"""

V2_MULTILANE_ONE_REMOVED = """\
[Header]
FileFormatVersion,2
RunName,Run001
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I8;I8;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,SampleA,ATTACTCG,TATAGCCT,ProjectX
1,SampleB,TCCGGAGA,ATAGAGGC,ProjectX
2,SampleC,TAGGCATG,CCTATCCT,ProjectX
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def v1_base(tmp_path):
    return _write(tmp_path, "v1_base.csv", V1_BASE)

@pytest.fixture
def v1_index_changed(tmp_path):
    return _write(tmp_path, "v1_idx.csv", V1_INDEX_CHANGED)

@pytest.fixture
def v2_base(tmp_path):
    return _write(tmp_path, "v2_base.csv", V2_BASE)

@pytest.fixture
def v2_sample_added(tmp_path):
    return _write(tmp_path, "v2_added.csv", V2_SAMPLE_ADDED)

@pytest.fixture
def v2_sample_removed(tmp_path):
    return _write(tmp_path, "v2_removed.csv", V2_SAMPLE_REMOVED)

@pytest.fixture
def v2_read_cycles_changed(tmp_path):
    return _write(tmp_path, "v2_reads.csv", V2_READ_CYCLES_CHANGED)

@pytest.fixture
def v2_project_changed(tmp_path):
    return _write(tmp_path, "v2_project.csv", V2_PROJECT_CHANGED)

@pytest.fixture
def v2_multilane(tmp_path):
    return _write(tmp_path, "v2_multilane.csv", V2_MULTILANE)

@pytest.fixture
def v2_multilane_one_removed(tmp_path):
    return _write(tmp_path, "v2_multilane_removed.csv", V2_MULTILANE_ONE_REMOVED)


# ---------------------------------------------------------------------------
# DiffResult unit tests
# ---------------------------------------------------------------------------

class TestDiffResult:
    def test_no_changes_has_changes_false(self):
        r = DiffResult(source_version=None, target_version=None)  # type: ignore
        assert not r.has_changes

    def test_header_change_sets_has_changes(self):
        r = DiffResult(source_version=None, target_version=None)  # type: ignore
        r.header_changes.append(HeaderChange("RunName", "A", "B"))
        assert r.has_changes

    def test_sample_added_sets_has_changes(self):
        r = DiffResult(source_version=None, target_version=None)  # type: ignore
        r.samples_added.append({"Sample_ID": "S1"})
        assert r.has_changes

    def test_sample_removed_sets_has_changes(self):
        r = DiffResult(source_version=None, target_version=None)  # type: ignore
        r.samples_removed.append({"Sample_ID": "S1"})
        assert r.has_changes

    def test_sample_change_sets_has_changes(self):
        r = DiffResult(source_version=None, target_version=None)  # type: ignore
        r.sample_changes.append(
            SampleChange(lane="1", sample_id="S1", changes={"Index": ("A", "B")})
        )
        assert r.has_changes

    def test_summary_no_changes(self):
        from samplesheet_parser.enums import SampleSheetVersion
        r = DiffResult(source_version=SampleSheetVersion.V2, target_version=SampleSheetVersion.V2)
        assert "No differences" in r.summary()

    def test_summary_with_changes_mentions_counts(self):
        from samplesheet_parser.enums import SampleSheetVersion
        r = DiffResult(source_version=SampleSheetVersion.V1, target_version=SampleSheetVersion.V2)
        r.samples_added.append({"Sample_ID": "S1"})
        r.header_changes.append(HeaderChange("RunName", "A", "B"))
        summary = r.summary()
        assert "1 header" in summary
        assert "1 sample(s) added" in summary

    def test_str_includes_section_headers(self):
        from samplesheet_parser.enums import SampleSheetVersion
        r = DiffResult(source_version=SampleSheetVersion.V1, target_version=SampleSheetVersion.V2)
        r.samples_removed.append({"Sample_ID": "S2", "Lane": "1"})
        r.sample_changes.append(SampleChange("1", "S1", {"Index": ("AAA", "BBB")}))
        text = str(r)
        assert "Removed samples" in text
        assert "Changed samples" in text

    def test_header_change_str(self):
        c = HeaderChange(
            field="AdapterRead1", old_value="AAAA", new_value="CCCC", section="settings"
        )
        assert "settings" in str(c)
        assert "AdapterRead1" in str(c)
        assert "AAAA" in str(c)
        assert "CCCC" in str(c)

    def test_sample_change_str(self):
        c = SampleChange(lane="2", sample_id="MySample", changes={"Index": ("OLD", "NEW")})
        text = str(c)
        assert "MySample" in text
        assert "lane 2" in text
        assert "OLD" in text
        assert "NEW" in text


# ---------------------------------------------------------------------------
# SampleSheetDiff — identical sheets
# ---------------------------------------------------------------------------

class TestIdenticalSheets:
    def test_v2_identical_no_changes(self, v2_base, tmp_path):
        copy = _write(tmp_path, "v2_copy.csv", V2_BASE)
        result = SampleSheetDiff(v2_base, copy).compare()
        assert not result.has_changes

    def test_v1_identical_no_changes(self, v1_base, tmp_path):
        copy = _write(tmp_path, "v1_copy.csv", V1_BASE)
        result = SampleSheetDiff(v1_base, copy).compare()
        assert not result.has_changes

    def test_summary_says_no_differences(self, v2_base, tmp_path):
        copy = _write(tmp_path, "v2_copy2.csv", V2_BASE)
        result = SampleSheetDiff(v2_base, copy).compare()
        assert "No differences" in result.summary()


# ---------------------------------------------------------------------------
# Sample added / removed
# ---------------------------------------------------------------------------

class TestSampleAddedRemoved:
    def test_sample_added_detected(self, v2_base, v2_sample_added):
        result = SampleSheetDiff(v2_base, v2_sample_added).compare()
        assert len(result.samples_added) == 1
        assert result.samples_added[0]["Sample_ID"] == "SampleC"

    def test_no_false_positive_removals_when_adding(self, v2_base, v2_sample_added):
        result = SampleSheetDiff(v2_base, v2_sample_added).compare()
        assert len(result.samples_removed) == 0

    def test_sample_removed_detected(self, v2_base, v2_sample_removed):
        result = SampleSheetDiff(v2_base, v2_sample_removed).compare()
        assert len(result.samples_removed) == 1
        assert result.samples_removed[0]["Sample_ID"] == "SampleB"

    def test_no_false_positive_additions_when_removing(self, v2_base, v2_sample_removed):
        result = SampleSheetDiff(v2_base, v2_sample_removed).compare()
        assert len(result.samples_added) == 0

    def test_has_changes_when_sample_added(self, v2_base, v2_sample_added):
        result = SampleSheetDiff(v2_base, v2_sample_added).compare()
        assert result.has_changes

    def test_has_changes_when_sample_removed(self, v2_base, v2_sample_removed):
        result = SampleSheetDiff(v2_base, v2_sample_removed).compare()
        assert result.has_changes


# ---------------------------------------------------------------------------
# Sample field changes
# ---------------------------------------------------------------------------

class TestSampleFieldChanges:
    def test_index_change_detected(self, v2_base, tmp_path):
        changed = _write(tmp_path, "idx_changed.csv", V2_BASE.replace(
            "1,SampleB,TCCGGAGA,ATAGAGGC,ProjectX",
            "1,SampleB,GGGGGGGG,ATAGAGGC,ProjectX",
        ))
        result = SampleSheetDiff(v2_base, changed).compare()
        assert len(result.sample_changes) == 1
        sc = result.sample_changes[0]
        assert sc.sample_id == "SampleB"
        assert "Index" in sc.changes
        assert sc.changes["Index"] == ("TCCGGAGA", "GGGGGGGG")

    def test_index2_change_detected(self, v2_base, tmp_path):
        changed = _write(tmp_path, "idx2_changed.csv", V2_BASE.replace(
            "1,SampleA,ATTACTCG,TATAGCCT,ProjectX",
            "1,SampleA,ATTACTCG,TTTTTTTT,ProjectX",
        ))
        result = SampleSheetDiff(v2_base, changed).compare()
        assert len(result.sample_changes) == 1
        sc = result.sample_changes[0]
        assert "Index2" in sc.changes
        assert sc.changes["Index2"][1] == "TTTTTTTT"

    def test_project_change_detected(self, v2_base, v2_project_changed):
        result = SampleSheetDiff(v2_base, v2_project_changed).compare()
        assert len(result.sample_changes) == 1
        sc = result.sample_changes[0]
        assert sc.sample_id == "SampleA"
        assert "Sample_Project" in sc.changes
        assert sc.changes["Sample_Project"] == ("ProjectX", "ProjectY")

    def test_unchanged_samples_not_reported(self, v2_base, v2_project_changed):
        result = SampleSheetDiff(v2_base, v2_project_changed).compare()
        changed_ids = {sc.sample_id for sc in result.sample_changes}
        assert "SampleB" not in changed_ids


# ---------------------------------------------------------------------------
# Header / reads / settings changes
# ---------------------------------------------------------------------------

class TestHeaderAndSettingsChanges:
    def test_read_cycles_change_detected(self, v2_base, v2_read_cycles_changed):
        result = SampleSheetDiff(v2_base, v2_read_cycles_changed).compare()
        read_changes = [c for c in result.header_changes if c.section == "reads"]
        assert len(read_changes) >= 2
        fields_changed = {c.field for c in read_changes}
        assert "Read1Cycles" in fields_changed
        assert "Read2Cycles" in fields_changed

    def test_read_cycle_old_value_correct(self, v2_base, v2_read_cycles_changed):
        result = SampleSheetDiff(v2_base, v2_read_cycles_changed).compare()
        r1 = next(c for c in result.header_changes if c.field == "Read1Cycles")
        assert r1.old_value == "151"
        assert r1.new_value == "76"

    def test_adapter_change_in_settings(self, v2_base, tmp_path):
        changed = _write(tmp_path, "adapter.csv", V2_BASE.replace(
            "AdapterRead1,CTGTCTCTTATACACATCT",
            "AdapterRead1,AGATCGGAAGAGC",
        ))
        result = SampleSheetDiff(v2_base, changed).compare()
        settings_changes = [c for c in result.header_changes if c.section == "settings"]
        fields = {c.field for c in settings_changes}
        assert "AdapterRead1" in fields

    def test_new_settings_key_detected(self, v2_base, tmp_path):
        changed = _write(tmp_path, "new_key.csv", V2_BASE.replace(
            "OverrideCycles,Y151;I8;I8;Y151",
            "OverrideCycles,Y151;I8;I8;Y151\nNoLaneSplitting,1",
        ))
        result = SampleSheetDiff(v2_base, changed).compare()
        settings_changes = [c for c in result.header_changes if c.section == "settings"]
        fields = {c.field for c in settings_changes}
        assert "NoLaneSplitting" in fields

    def test_removed_settings_key_detected(self, v2_base, tmp_path):
        changed = _write(tmp_path, "rm_key.csv", V2_BASE.replace(
            "OverrideCycles,Y151;I8;I8;Y151\n", "",
        ))
        result = SampleSheetDiff(v2_base, changed).compare()
        settings_changes = [c for c in result.header_changes if c.section == "settings"]
        fields = {c.field for c in settings_changes}
        assert "OverrideCycles" in fields


# ---------------------------------------------------------------------------
# Multi-lane sheets
# ---------------------------------------------------------------------------

class TestMultiLane:
    def test_lane_aware_removal(self, v2_multilane, v2_multilane_one_removed):
        result = SampleSheetDiff(v2_multilane, v2_multilane_one_removed).compare()
        assert len(result.samples_removed) == 1
        assert result.samples_removed[0]["Sample_ID"] == "SampleD"

    def test_same_sample_id_different_lane_not_confused(self, tmp_path):
        # SampleA appears in lane 1 and lane 2 — they are different samples
        sheet_a = _write(tmp_path, "lanes_a.csv", V2_BASE.replace(
            "[BCLConvert_Data]\nLane,Sample_ID,Index,Index2,Sample_Project\n"
            "1,SampleA,ATTACTCG,TATAGCCT,ProjectX\n"
            "1,SampleB,TCCGGAGA,ATAGAGGC,ProjectX",
            "[BCLConvert_Data]\nLane,Sample_ID,Index,Index2,Sample_Project\n"
            "1,SampleA,ATTACTCG,TATAGCCT,ProjectX\n"
            "2,SampleA,TCCGGAGA,ATAGAGGC,ProjectX",
        ))
        sheet_b = _write(tmp_path, "lanes_b.csv", V2_BASE.replace(
            "[BCLConvert_Data]\nLane,Sample_ID,Index,Index2,Sample_Project\n"
            "1,SampleA,ATTACTCG,TATAGCCT,ProjectX\n"
            "1,SampleB,TCCGGAGA,ATAGAGGC,ProjectX",
            "[BCLConvert_Data]\nLane,Sample_ID,Index,Index2,Sample_Project\n"
            "1,SampleA,ATTACTCG,TATAGCCT,ProjectX\n"
            "2,SampleA,GGGGGGGG,ATAGAGGC,ProjectX",
        ))
        result = SampleSheetDiff(sheet_a, sheet_b).compare()
        # Lane 1 SampleA unchanged, lane 2 SampleA index changed
        assert len(result.sample_changes) == 1
        sc = result.sample_changes[0]
        assert sc.lane == "2"
        assert sc.sample_id == "SampleA"


# ---------------------------------------------------------------------------
# Cross-format V1 ↔ V2
# ---------------------------------------------------------------------------

class TestCrossFormat:
    def test_v1_v2_identical_samples_no_sample_changes(self, v1_base, v2_base):
        # Both sheets have SampleA and SampleB with matching indexes;
        # field-name normalisation should suppress spurious diffs.
        result = SampleSheetDiff(v1_base, v2_base).compare()
        assert len(result.sample_changes) == 0

    def test_v1_v2_no_spurious_additions_or_removals(self, v1_base, v2_base):
        result = SampleSheetDiff(v1_base, v2_base).compare()
        assert len(result.samples_added) == 0
        assert len(result.samples_removed) == 0

    def test_v1_v2_reports_correct_versions(self, v1_base, v2_base):
        from samplesheet_parser.enums import SampleSheetVersion
        result = SampleSheetDiff(v1_base, v2_base).compare()
        assert result.source_version == SampleSheetVersion.V1
        assert result.target_version == SampleSheetVersion.V2

    def test_v1_index_change_detected_across_format(self, v1_index_changed, v2_base):
        # V1 SampleB has GGGGGGGG, V2 has TCCGGAGA → should be a sample change
        result = SampleSheetDiff(v1_index_changed, v2_base).compare()
        changed_ids = {sc.sample_id for sc in result.sample_changes}
        assert "SampleB" in changed_ids

    def test_v2_v1_direction_also_works(self, v2_base, v1_base):
        from samplesheet_parser.enums import SampleSheetVersion
        result = SampleSheetDiff(v2_base, v1_base).compare()
        assert result.source_version == SampleSheetVersion.V2
        assert result.target_version == SampleSheetVersion.V1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_data_section_old(self, tmp_path):
        old = _write(tmp_path, "old_empty.csv", """\
[Header]
FileFormatVersion,2
RunName,Empty

[Reads]
Read1Cycles,151
Read2Cycles,151

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
""")
        new = _write(tmp_path, "new_one.csv", V2_BASE)
        result = SampleSheetDiff(old, new).compare()
        assert len(result.samples_added) == 2
        assert len(result.samples_removed) == 0

    def test_empty_data_section_new(self, tmp_path):
        old = _write(tmp_path, "old_full.csv", V2_BASE)
        new = _write(tmp_path, "new_empty.csv", """\
[Header]
FileFormatVersion,2
RunName,Run001
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I8;I8;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
""")
        result = SampleSheetDiff(old, new).compare()
        assert len(result.samples_removed) == 2
        assert len(result.samples_added) == 0

    def test_single_sample_no_changes(self, tmp_path):
        content = """\
[Header]
FileFormatVersion,2
RunName,OneRun
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I8;I8;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,Solo,ATCGATCG,GCTAGCTA,ProjectZ
"""
        p1 = _write(tmp_path, "solo1.csv", content)
        p2 = _write(tmp_path, "solo2.csv", content)
        result = SampleSheetDiff(p1, p2).compare()
        assert not result.has_changes

    def test_missing_file_raises(self, tmp_path):
        real = _write(tmp_path, "real.csv", V2_BASE)
        with pytest.raises(FileNotFoundError):
            SampleSheetDiff(real, tmp_path / "nonexistent.csv").compare()
