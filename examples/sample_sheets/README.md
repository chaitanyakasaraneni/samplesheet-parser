# Example Sample Sheets

Reference sample sheets covering the full range of supported formats.
Each file is a valid, runnable example that can be parsed by `samplesheet-parser`.

---

## V1 — IEM / bcl2fastq format

Used with: NovaSeq 6000, HiSeq, NextSeq 500/550, MiSeq  
Identified by: `IEMFileVersion` in `[Header]`

| File | Instrument | Indexes | Key feature |
|---|---|---|---|
| `v1_dual_index.csv` | NovaSeq 6000 | Dual (10+10 bp) | Multi-lane, TruSeq UD adapters |
| `v1_single_index.csv` | NextSeq 500 | Single (6 bp) | Small RNA, TruSeq Small RNA adapters |
| `v1_multi_lane.csv` | NovaSeq 6000 | Dual (10+10 bp) | 4 lanes, 2 projects, mixed assays |
| `v1_with_manifests.csv` | NovaSeq 6000 | Dual (10+10 bp) | Custom `[Manifests]` section — HyperCapture WES |
| `v1_with_lab_qc_settings.csv` | NovaSeq 6000 | Dual (10+10 bp) | Custom `[Lab_QC_Settings]` section — QC thresholds |

### V1 `[Settings]` adapter keys

The official IEM spec uses two separate keys — not `AdapterRead1`:

```
[Settings]
ReverseComplement,0
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA        ← Read 1
AdapterRead2,AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT   ← Read 2
```

`ReverseComplement,1` is only for Nextera Mate Pair libraries.
`Chemistry,Amplicon` means dual-index. `Chemistry,Default` means no or single index.

---

## V2 — BCLConvert format

Used with: NovaSeq X, NovaSeq X Plus, NextSeq 1000/2000  
Identified by: `FileFormatVersion` in `[Header]`, or `[BCLConvert_Settings]` / `[BCLConvert_Data]` section names

| File | Instrument | Indexes | UMI | Key feature |
|---|---|---|---|---|
| `v2_novaseq_x_dual_index.csv` | NovaSeq X | Dual (10+10 bp) | No | Standard multi-lane |
| `v2_with_index_umi.csv` | NovaSeq X | Dual (10+10 bp) | Yes — Index1 UMI (9 bp) | cfDNA / liquid biopsy |
| `v2_with_read_umi.csv` | NovaSeq X | Dual (8+8 bp) | Yes — read-level UMI (5 bp) | Duplex sequencing |
| `v2_nextseq_single_index.csv` | NextSeq 1000/2000 | Single (8 bp) | No | Amplicon panel, no Lane column |
| `v2_with_cloud_settings.csv` | NovaSeq X | Dual (10+10 bp) | No | Custom `[Cloud_Settings]` — BaseSpace upload config |
| `v2_with_pipeline_settings.csv` | NextSeq 1000/2000 | Single (8 bp) | No | Custom `[Pipeline_Settings]` — downstream pipeline config |

### V2 `OverrideCycles` format

```
Y151;I10;I10;Y151         — 151bp PE, 10bp dual index, no UMI
Y151;I10U9;I10;Y151       — same, with 9bp UMI appended to Index1
U5Y146;I8;I8;U5Y146       — 5bp UMI on both reads (read-level UMI)
Y151;I8;Y151              — single index, no Index2 cycle
```

Segment order: Read1 ; Index1 ; Index2 ; Read2

---

## Custom sections

Both V1 and V2 sheets support non-standard sections. These are preserved verbatim
during parsing and accessible via `sheet.parse_custom_section(name)`.

### V1 — `[Manifests]`

Used by Illumina's HyperCapture and other enrichment workflows to specify the
target capture manifest files the demultiplexer or aligner should load.

```
[Manifests]
MFGmanifest,HyperCapture_ExomeV2_manifest.txt
PoolingManifest,pooling_batch3_v1.txt
```

### V1 — `[Lab_QC_Settings]`

A lab-defined section for embedding QC thresholds and pipeline metadata
directly in the sample sheet, so downstream tools can read them without a
separate config file.

```
[Lab_QC_Settings]
MinQ30,85
TargetCoverage,100x
MinMappingRate,90
LibraryKit,TruSeq_Stranded_mRNA
SequencingCore,GenomicsCoreFacility
```

### V2 — `[Cloud_Settings]`

Used by Illumina DRAGEN and BaseSpace to configure automated cloud upload
after demultiplexing. `UploadToBaseSpace,1` triggers the upload; `BaseSpaceProjectId`
routes the data to the correct project.

```
[Cloud_Settings]
GeneratedVersion,3.9.14
UploadToBaseSpace,1
BaseSpaceProjectId,bs-proj-240715-wgs
```

### V2 — `[Pipeline_Settings]`

A lab-defined section for downstream pipeline configuration — reference genome,
variant caller, output format — bundled with the sample sheet so the compute
environment has everything it needs in one file.

```
[Pipeline_Settings]
PipelineVersion,2.1.0
ReferenceGenome,hg38
OutputFormat,CRAM
VariantCaller,DeepVariant
MinBaseQuality,20
MinMappingQuality,30
```

### Accessing custom sections in code

```python
from samplesheet_parser import SampleSheetFactory

sheet_with_manifests = SampleSheetFactory().create_parser(
    "examples/sample_sheets/v1_with_manifests.csv", parse=True
)

# Returns {} if section is absent (default)
manifests = sheet_with_manifests.parse_custom_section("Manifests")
print(manifests)
# {'MFGmanifest': 'HyperCapture_ExomeV2_manifest.txt',
#  'PoolingManifest': 'pooling_batch3_v1.txt'}

# Raise if a section your pipeline depends on is missing
sheet_with_lab_qc_settings = SampleSheetFactory().create_parser(
    "examples/sample_sheets/v1_with_lab_qc_settings.csv", parse=True
)
qc = sheet_with_lab_qc_settings.parse_custom_section("Lab_QC_Settings", required=True)

# Works identically on V2 sheets
sheet_v2 = SampleSheetFactory().create_parser(
    "examples/sample_sheets/v2_with_cloud_settings.csv", parse=True
)
cloud = sheet_v2.parse_custom_section("Cloud_Settings")
print(cloud["UploadToBaseSpace"])  # '1'
```

### Asserting required sections before parsing

```python
# parse() raises ValueError immediately if a required section is absent
sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=False)
sheet.parse(required_sections=["Manifests", "Lab_QC_Settings"])
```

---

## Parsing examples

```python
from samplesheet_parser import SampleSheetFactory, SampleSheetValidator

# Works for any of the files above — format is auto-detected
factory = SampleSheetFactory()
sheet = factory.create_parser("examples/sample_sheets/v2_with_index_umi.csv", parse=True)

print(factory.version)          # SampleSheetVersion.V2
print(sheet.index_type())       # "dual"
print(factory.get_umi_length()) # 9

for sample in sheet.samples():
    print(sample["sample_id"], sample["index"])

result = SampleSheetValidator().validate(sheet)
print(result.summary())         # PASS — 0 error(s), 0 warning(s)
```

---

## Notes on column capitalisation (V1)

From the Illumina IEM reference: **capitalisation in the `[Data]` header row matters.**

Standard capitalisation:
- `Sample_ID`, `Sample_Name`, `Sample_Plate`, `Sample_Well` — Title_Case with underscore
- `I7_Index_ID`, `I5_Index_ID` — uppercase I, mixed
- `index`, `index2` — **all lowercase**
- `Sample_Project`, `Description` — Title_Case

`index` and `index2` being lowercase is deliberate and required by bcl2fastq.
