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

### V2 `OverrideCycles` format

```
Y151;I10;I10;Y151         — 151bp PE, 10bp dual index, no UMI
Y151;I10U9;I10;Y151       — same, with 9bp UMI appended to Index1
U5Y146;I8;I8;U5Y146       — 5bp UMI on both reads (read-level UMI)
Y151;I8;Y151              — single index, no Index2 cycle
```

Segment order: Read1 ; Index1 ; Index2 ; Read2

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
