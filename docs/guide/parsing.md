# Parsing

## Format auto-detection

`SampleSheetFactory` uses a three-step detection strategy — no format hints required from the caller:

1. **Header discriminator** — scan `[Header]` for `FileFormatVersion` (→ V2) or `IEMFileVersion` (→ V1)
2. **Section name scan** — if no header key found, look for `[BCLConvert_Settings]` / `[BCLConvert_Data]` in the full file (→ V2)
3. **Default** — fall back to V1 (broadest compatibility with legacy files)

The detector reads only as much of the file as needed — stopping after `[Header]` in the common case.

```python
from samplesheet_parser import SampleSheetFactory

factory = SampleSheetFactory()
sheet = factory.create_parser("SampleSheet.csv", parse=True)

print(factory.version)   # SampleSheetVersion.V1 or .V2
```

## V1 parser

```python
from samplesheet_parser import SampleSheetV1

sheet = SampleSheetV1("SampleSheet.csv")
sheet.parse()

print(sheet.experiment_name)   # "MyRun_20240115"
print(sheet.read_lengths)      # [151, 151]
print(sheet.adapters)          # ["CTGTCTCTTATACACATCT"]
print(sheet.index_type())      # "dual"

for sample in sheet.samples():
    print(sample["sample_id"], sample["index"], sample["index2"])
```

## V2 parser

```python
from samplesheet_parser import SampleSheetV2

sheet = SampleSheetV2("SampleSheet.csv")
sheet.parse()

print(sheet.reads)             # {"Read1Cycles": 151, "Read2Cycles": 151}
print(sheet.adapters)          # ["CTGTCTCTTATACACATCT"]
print(sheet.index_type())      # "dual"

for sample in sheet.samples():
    print(sample["Sample_ID"], sample["Index"], sample["Index2"])
```

## UMI / OverrideCycles parsing

The V2 `OverrideCycles` field encodes read structure including UMI positions:

| OverrideCycles | UMI length | UMI location |
|---|---|---|
| `Y151;I10;I10;Y151` | 0 | — |
| `Y151;I10U9;I10;Y151` | 9 | `index2` |
| `U5Y146;I8;I8;U5Y146` | 5 | `read1` |

```python
# OverrideCycles: Y151;I10U9;I10;Y151 → 9 bp UMI in Index1
print(sheet.get_umi_length())       # 9
rs = sheet.get_read_structure()
print(rs.umi_location)              # "index2"
print(rs.read_structure)
# {"read1_template": 151, "index2_length": 10, "index2_umi": 9, ...}
```

## Shared interface

Both `SampleSheetV1` and `SampleSheetV2` expose:

| Method / attribute | Returns | Description |
|---|---|---|
| `parse(do_clean=True)` | `None` | Parse all sections |
| `samples()` | `list[dict]` | One record per unique sample |
| `index_type()` | `str` | `"dual"`, `"single"`, or `"none"` |
| `.adapters` | `list[str]` | Adapter sequences |
| `.experiment_name` | `str \| None` | Run/experiment name |
