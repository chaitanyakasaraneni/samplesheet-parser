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

Both `SampleSheetV1` and `SampleSheetV2` satisfy the `SampleSheetParser` Protocol and expose:

| Method / attribute | Returns | Description |
|---|---|---|
| `parse(do_clean=True)` | `None` | Parse all sections |
| `clean()` | `str` | Return cleaned content as a string — source file is **never** modified |
| `samples()` | `list[dict]` | One record per unique `(sample_id, lane)` pair |
| `index_type()` | `str` | `"dual"`, `"single"`, or `"none"` |
| `parse_custom_section(name, *, required=False)` | `dict[str, str]` | Parse any non-standard section as key/value pairs |
| `.adapters` | `list[str]` | Adapter sequences |
| `.experiment_name` | `str \| None` | Run/experiment name |

### In-memory cleaning

`parse(do_clean=True)` (the default) cleans the file content in memory before parsing — stripping BOM, quotes, stray whitespace, and normalising V2 section names. **The source file on disk is never modified and no `.backup` files are created.**

```python
# Access the cleaned content directly
cleaned = sheet.clean()   # returns str, no file I/O side-effects

# Parse with cleaning (default)
sheet.parse()

# Parse without cleaning (raw file)
sheet.parse(do_clean=False)
```

### Multi-lane deduplication

`samples()` deduplicates by `(sample_id, lane)` pair, not by `sample_id` alone. A sample appearing across multiple lanes produces one record per lane.

```python
sheet.parse()
samples = sheet.samples()
# Multi-lane sheet with Sample1 in lanes 1 and 2 → two records:
# [{"sample_id": "Sample1", "lane": "1", ...},
#  {"sample_id": "Sample1", "lane": "2", ...}]
```
