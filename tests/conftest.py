"""
Shared pytest fixtures for samplesheet-parser tests.

All fixtures write temporary files to pytest's tmp_path so nothing
is left on disk after the test run.
"""

import pytest

# ---------------------------------------------------------------------------
# V1 IEM sample sheet content
# ---------------------------------------------------------------------------

V1_MINIMAL = """\
[Header]
IEMFileVersion,5
Experiment Name,TestRun
Date,2024-01-15
Workflow,GenerateFASTQ
Application,FASTQ Only
Instrument Type,MiSeq
Assay,TruSeq Stranded mRNA
Index Adapters,TruSeq RNA CD Indexes (96 Indexes)
Chemistry,Amplicon

[Reads]
151
151

[Settings]
ReverseComplement,0
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA
AdapterRead2,AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT

[Data]
Lane,Sample_ID,Sample_Name,Sample_Plate,Sample_Well,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project,Description
1,Sample1,Sample1,,A01,D701,ATTACTCG,D501,TATAGCCT,Project1,
1,Sample2,Sample2,,B01,D702,TCCGGAGA,D502,ATAGAGGC,Project1,
"""

V1_SINGLE_INDEX = """\
[Header]
IEMFileVersion,4
Experiment Name,SingleIndexRun
Date,2024-02-01
Workflow,GenerateFASTQ
Chemistry,Default

[Reads]
76
76

[Settings]
Adapter,AGATCGGAAGAGC

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,Sample_Project,Description
1,SampleA,SampleA,AD001,ATCACG,ProjectA,
1,SampleB,SampleB,AD002,CGATGT,ProjectA,
1,SampleC,SampleC,AD003,TTAGGC,ProjectA,
"""

V1_MULTI_LANE = """\
[Header]
IEMFileVersion,5
Experiment Name,MultiLaneRun
Date,2024-03-01
Workflow,GenerateFASTQ
Chemistry,Amplicon

[Reads]
151
151

[Settings]
Adapter,CTGTCTCTTATACACATCT

[Data]
Lane,Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,Sample1,Sample1,D701,ATTACTCG,D501,TATAGCCT,ProjectA
1,Sample2,Sample2,D702,TCCGGAGA,D502,ATAGAGGC,ProjectA
2,Sample3,Sample3,D703,TAGGCATG,D503,CCTATCCT,ProjectB
2,Sample4,Sample4,D704,CTCTCTAC,D504,GGCTCTGA,ProjectB
"""

V1_NO_READS = """\
[Header]
IEMFileVersion,5
Experiment Name,NoReads

[Data]
Lane,Sample_ID,I7_Index_ID,index,Sample_Project
1,S1,D701,ATTACTCG,Project1
"""

V1_WITH_EXPERIMENT_ID = """\
[Header]
IEMFileVersion,5
Experiment Name,OldName
Date,2024-01-15
Workflow,GenerateFASTQ

[Reads]
151
151

[Settings]
Adapter,CTGTCTCTTATACACATCT

[Data]
Lane,Sample_ID,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project
1,Sample1,D701,ATTACTCG,D501,TATAGCCT,Project1
"""

# V1 sheet with a [Manifests] custom section
V1_WITH_MANIFESTS = """\
[Header]
IEMFileVersion,5
Experiment Name,ManifestRun
Date,2024-01-15
Workflow,GenerateFASTQ

[Reads]
151
151

[Settings]
Adapter,CTGTCTCTTATACACATCT

[Manifests]
MFGmanifest,HyperCapture_manifest_v2.0.txt
PoolingManifest,pooling_v1.txt

[Data]
Lane,Sample_ID,index,index2,Sample_Project
1,Sample1,ATTACTCG,TATAGCCT,Project1
1,Sample2,TCCGGAGA,ATAGAGGC,Project1
"""

# V1 sheet with a fully custom lab-specific section
V1_WITH_CUSTOM_SECTION = """\
[Header]
IEMFileVersion,5
Experiment Name,CustomSectionRun
Date,2024-01-15
Workflow,GenerateFASTQ

[Reads]
151
151

[Settings]
Adapter,CTGTCTCTTATACACATCT

[Lab_QC_Settings]
MinQ30,85
TargetCoverage,100x
LibraryKit,TruSeq_Nano

[Data]
Lane,Sample_ID,index,index2,Sample_Project
1,Sample1,ATTACTCG,TATAGCCT,Project1
"""

# V1 sheet with multiple custom sections
V1_WITH_MULTIPLE_CUSTOM_SECTIONS = """\
[Header]
IEMFileVersion,5
Experiment Name,MultiCustomRun
Date,2024-04-01
Workflow,GenerateFASTQ

[Reads]
151
151

[Settings]
Adapter,CTGTCTCTTATACACATCT

[Manifests]
MFGmanifest,HyperCapture_manifest_v2.0.txt

[Cloud_Settings]
GeneratedVersion,3.9.14
UploadToBaseSpace,1

[Data]
Lane,Sample_ID,index,index2,Sample_Project
1,Sample1,ATTACTCG,TATAGCCT,Project1
"""

# V1 sheet with a custom section that has malformed lines
V1_WITH_MALFORMED_CUSTOM_SECTION = """\
[Header]
IEMFileVersion,5
Experiment Name,MalformedCustomRun
Date,2024-01-15
Workflow,GenerateFASTQ

[Reads]
151
151

[Settings]
Adapter,CTGTCTCTTATACACATCT

[Lab_QC_Settings]
MinQ30,85
,MissingKey
ValidKey,ValidValue

[Data]
Lane,Sample_ID,index,index2,Sample_Project
1,Sample1,ATTACTCG,TATAGCCT,Project1
"""

# ---------------------------------------------------------------------------
# V2 BCLConvert sample sheet content
# ---------------------------------------------------------------------------

V2_MINIMAL = """\
[Header]
FileFormatVersion,2
RunName,TestRunV2
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,10
Index2Cycles,10

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I10;I10;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,Sample1,ATTACTCGAT,TATAGCCTGT,Project1
1,Sample2,TCCGGAGACC,ATAGAGGCAC,Project1
"""

V2_WITH_UMI = """\
[Header]
FileFormatVersion,2
RunName,UMIRun
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,10
Index2Cycles,10

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
AdapterRead2,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I10U9;I10;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,Sample1,ATTACTCGAT,TATAGCCTGT,Project1
"""

V2_WITH_READ_UMI = """\
[Header]
FileFormatVersion,2
RunName,ReadUMIRun
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
OverrideCycles,U5Y146;I8;I8;U5Y146

[BCLConvert_Data]
Sample_ID,Index,Index2
Sample1,ATTACTCG,TATAGCCT
"""

V2_NO_INDEX2 = """\
[Header]
FileFormatVersion,2
RunName,SingleIndexV2
InstrumentPlatform,NextSeq1000/2000

[Reads]
Read1Cycles,76
Read2Cycles,76
Index1Cycles,8

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
OverrideCycles,Y76;I8;Y76

[BCLConvert_Data]
Sample_ID,Index,Sample_Project
Sample1,ATTACTCG,Project1
Sample2,TCCGGAGA,Project1
"""

V2_BCLCONVERT_SECTIONS_ONLY = """\
[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Sample_ID,Index,Index2
Sample1,ATTACTCG,TATAGCCT
"""

# V2 sheet with a [Cloud_Settings] custom section
V2_WITH_CLOUD_SETTINGS = """\
[Header]
FileFormatVersion,2
RunName,CloudRun
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,10
Index2Cycles,10

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I10;I10;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,Sample1,ATTACTCGAT,TATAGCCTGT,Project1

[Cloud_Settings]
GeneratedVersion,3.9.14
UploadToBaseSpace,1
"""

# V2 sheet with a fully arbitrary custom section
V2_WITH_CUSTOM_SECTION = """\
[Header]
FileFormatVersion,2
RunName,CustomSectionRun
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,10
Index2Cycles,10

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I10;I10;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,Sample1,ATTACTCGAT,TATAGCCTGT,Project1

[Pipeline_Settings]
PipelineVersion,2.1.0
OutputFormat,CRAM
ReferenceGenome,hg38
"""

# V2 sheet with multiple custom sections
V2_WITH_MULTIPLE_CUSTOM_SECTIONS = """\
[Header]
FileFormatVersion,2
RunName,MultiCustomRun
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,10
Index2Cycles,10

[BCLConvert_Settings]
SoftwareVersion,3.9.3
AdapterRead1,CTGTCTCTTATACACATCT
OverrideCycles,Y151;I10;I10;Y151

[BCLConvert_Data]
Lane,Sample_ID,Index,Index2,Sample_Project
1,Sample1,ATTACTCGAT,TATAGCCTGT,Project1

[Cloud_Settings]
GeneratedVersion,3.9.14
UploadToBaseSpace,1

[Pipeline_Settings]
PipelineVersion,2.1.0
OutputFormat,FASTQ
"""

# ---------------------------------------------------------------------------
# Fixtures — V1
# ---------------------------------------------------------------------------


@pytest.fixture
def v1_minimal(tmp_path):
    p = tmp_path / "SampleSheet_v1.csv"
    p.write_text(V1_MINIMAL)
    return str(p)


@pytest.fixture
def v1_single_index(tmp_path):
    p = tmp_path / "SampleSheet_v1_single.csv"
    p.write_text(V1_SINGLE_INDEX)
    return str(p)


@pytest.fixture
def v1_multi_lane(tmp_path):
    p = tmp_path / "SampleSheet_v1_multilane.csv"
    p.write_text(V1_MULTI_LANE)
    return str(p)


@pytest.fixture
def v1_no_reads(tmp_path):
    p = tmp_path / "SampleSheet_v1_noreads.csv"
    p.write_text(V1_NO_READS)
    return str(p)


@pytest.fixture
def v1_with_experiment_id(tmp_path):
    p = tmp_path / "SampleSheet_v1_expid.csv"
    p.write_text(V1_WITH_EXPERIMENT_ID)
    return str(p)


@pytest.fixture
def v1_with_manifests(tmp_path):
    p = tmp_path / "SampleSheet_v1_manifests.csv"
    p.write_text(V1_WITH_MANIFESTS)
    return str(p)


@pytest.fixture
def v1_with_custom_section(tmp_path):
    p = tmp_path / "SampleSheet_v1_custom.csv"
    p.write_text(V1_WITH_CUSTOM_SECTION)
    return str(p)


@pytest.fixture
def v1_with_multiple_custom_sections(tmp_path):
    p = tmp_path / "SampleSheet_v1_multicustom.csv"
    p.write_text(V1_WITH_MULTIPLE_CUSTOM_SECTIONS)
    return str(p)


@pytest.fixture
def v1_with_malformed_custom_section(tmp_path):
    p = tmp_path / "SampleSheet_v1_malformed_custom.csv"
    p.write_text(V1_WITH_MALFORMED_CUSTOM_SECTION)
    return str(p)


# ---------------------------------------------------------------------------
# Fixtures — V2
# ---------------------------------------------------------------------------


@pytest.fixture
def v2_minimal(tmp_path):
    p = tmp_path / "SampleSheet_v2.csv"
    p.write_text(V2_MINIMAL)
    return str(p)


@pytest.fixture
def v2_with_umi(tmp_path):
    p = tmp_path / "SampleSheet_v2_umi.csv"
    p.write_text(V2_WITH_UMI)
    return str(p)


@pytest.fixture
def v2_with_read_umi(tmp_path):
    p = tmp_path / "SampleSheet_v2_readumi.csv"
    p.write_text(V2_WITH_READ_UMI)
    return str(p)


@pytest.fixture
def v2_no_index2(tmp_path):
    p = tmp_path / "SampleSheet_v2_single.csv"
    p.write_text(V2_NO_INDEX2)
    return str(p)


@pytest.fixture
def v2_bclconvert_sections_only(tmp_path):
    p = tmp_path / "SampleSheet_v2_sections.csv"
    p.write_text(V2_BCLCONVERT_SECTIONS_ONLY)
    return str(p)


@pytest.fixture
def v2_with_cloud_settings(tmp_path):
    p = tmp_path / "SampleSheet_v2_cloud.csv"
    p.write_text(V2_WITH_CLOUD_SETTINGS)
    return str(p)


@pytest.fixture
def v2_with_custom_section(tmp_path):
    p = tmp_path / "SampleSheet_v2_custom.csv"
    p.write_text(V2_WITH_CUSTOM_SECTION)
    return str(p)


@pytest.fixture
def v2_with_multiple_custom_sections(tmp_path):
    p = tmp_path / "SampleSheet_v2_multicustom.csv"
    p.write_text(V2_WITH_MULTIPLE_CUSTOM_SECTIONS)
    return str(p)
