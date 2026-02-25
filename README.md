# samplesheet-parser

**Format-agnostic parser for Illumina SampleSheet.csv files.**

Supports both the classic IEM V1 format (bcl2fastq era) and the modern BCLConvert V2 format (NovaSeq X series) — with automatic format detection, bidirectional conversion, index validation, Hamming distance checking, and diff comparison between sheets.

[![PyPI version](https://img.shields.io/pypi/v/samplesheet-parser.svg)](https://pypi.org/project/samplesheet-parser/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-yellow.svg)](https://opensource.org/licenses/Apache-2.0)
[![Tests](https://github.com/chaitanyakasaraneni/samplesheet-parser/actions/workflows/ci.yml/badge.svg)](https://github.com/chaitanyakasaraneni/samplesheet-parser/actions)
[![codecov](https://codecov.io/gh/chaitanyakasaraneni/samplesheet-parser/branch/main/graph/badge.svg?token=CODECOV_TOKEN)](https://codecov.io/gh/chaitanyakasaraneni/samplesheet-parser)

![samplesheet-parser overview](https://raw.githubusercontent.com/chaitanyakasaraneni/samplesheet-parser/main/images/samplesheet_parser_overview.png)

*`SampleSheetFactory` auto-detects the format and routes to the correct parser. Both formats share a common interface — `SampleSheetConverter` handles bidirectional conversion, `SampleSheetValidator` catches index and adapter issues, and `SampleSheetDiff` compares two sheets across any combination of V1/V2 formats.*

---

## The problem this solves

Labs running mixed instrument fleets — older NovaSeq 6000 alongside newer NovaSeq X series — produce two incompatible SampleSheet formats. BCLConvert V2 sheets use `[BCLConvert_Settings]` / `[BCLConvert_Data]` sections, `OverrideCycles` for UMI encoding, and `FileFormatVersion` in the header. IEM V1 sheets use `IEMFileVersion` and a flat `[Data]` section.

Existing tools either hard-code one format or require the caller to know which format they have. `samplesheet-parser` auto-detects the format, exposes a consistent interface for both, converts between formats, validates index integrity (including Hamming distance), and diffs sheets to catch accidental changes before a run starts.

---

## Installation

```bash
pip install samplesheet-parser
```

Requires Python 3.10+. No mandatory dependencies beyond `loguru`.

---

## Quickstart

### Auto-detect format (recommended)

```python
from samplesheet_parser import SampleSheetFactory

factory = SampleSheetFactory()
sheet = factory.create_parser("SampleSheet.csv", parse=True)

print(factory.version)      # SampleSheetVersion.V1 or .V2
print(sheet.index_type())   # "dual", "single", or "none"

for sample in sheet.samples():
    print(sample["sample_id"], sample["index"])
```

### V1 parser directly

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

### V2 parser + UMI extraction

```python
from samplesheet_parser import SampleSheetV2

sheet = SampleSheetV2("SampleSheet.csv")
sheet.parse()

# OverrideCycles: Y151;I10U9;I10;Y151 → 9 bp UMI in Index1
print(sheet.get_umi_length())       # 9
rs = sheet.get_read_structure()
print(rs.umi_location)              # "index2"
print(rs.read_structure)            # {"read1_template": 151, "index2_length": 10, "index2_umi": 9, ...}
```

### Format conversion

```python
from samplesheet_parser import SampleSheetConverter

# V1 → V2
SampleSheetConverter("SampleSheet_v1.csv").to_v2("SampleSheet_v2.csv")

# V2 → V1  (lossy — V2-only fields are dropped with a warning)
SampleSheetConverter("SampleSheet_v2.csv").to_v1("SampleSheet_v1.csv")
```

### Validation

```python
from samplesheet_parser import SampleSheetFactory, SampleSheetValidator

sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
result = SampleSheetValidator().validate(sheet)

print(result.summary())
# PASS — 0 error(s), 2 warning(s)

for w in result.warnings:
    print(w)
# [WARNING] INDEX_DISTANCE_TOO_LOW: Indexes for 'S1' and 'S2' in lane '1'
#   have a Hamming distance of 1 (minimum recommended: 3).
#   This may cause demultiplexing bleed-through.

for err in result.errors:
    print(err)
# [ERROR] DUPLICATE_INDEX: Index 'ATTACTCG+TATAGCCT' appears more than once in lane 1
```

### Diff two sheets

```python
from samplesheet_parser import SampleSheetDiff

diff = SampleSheetDiff("old/SampleSheet.csv", "new/SampleSheet.csv")
result = diff.compare()

print(result.summary())
# Diff (V1 → V2):
#   2 header/settings change(s)
#   1 sample(s) added: SAMPLE_009
#   1 sample(s) with field changes

if result.has_changes:
    for change in result.sample_changes:
        print(change)
    # Sample 'SAMPLE_002' (lane 1):
    #   Index: 'TCCGGAGA' → 'GGGGGGGG'

    for s in result.samples_added:
        print(f"Added: {s['Sample_ID']}")
```

Works across any combination of V1 and V2 — field names are normalised before
comparison so V1-only columns (`I7_Index_ID`, `Sample_Name`, etc.) do not
generate spurious diffs.

---

## Format detection logic

The factory uses a three-step detection strategy — no format hints required from the caller:

1. **Header discriminator** — scan `[Header]` for `FileFormatVersion` (→ V2) or `IEMFileVersion` (→ V1)
2. **Section name scan** — if no header key found, look for `[BCLConvert_Settings]` / `[BCLConvert_Data]` in the full file (→ V2)
3. **Default** — fall back to V1 (broadest compatibility with legacy files)

The detector reads only as much of the file as needed — stopping after `[Header]` in the common case.

---

## Validation checks

| Code | Level | Description |
|---|---|---|
| `EMPTY_SAMPLES` | error | No samples in Data section |
| `INVALID_INDEX_CHARS` | error | Index contains non-ACGTN characters |
| `INDEX_TOO_LONG` | error | Index longer than 24 bp |
| `DUPLICATE_INDEX` | error | Two samples share an index in the same lane |
| `DUPLICATE_SAMPLE_ID` | error | Same `Sample_ID` appears twice in one lane |
| `INDEX_TOO_SHORT` | warning | Index shorter than 6 bp |
| `INDEX_DISTANCE_TOO_LOW` | warning | Two indexes in the same lane have Hamming distance < 3, risking demultiplexing bleed-through |
| `NO_ADAPTERS` | warning | No adapter sequences configured |
| `ADAPTER_MISMATCH` | warning | Adapter is non-standard |

### Hamming distance checking

Indexes that are too similar cause read bleed-through between samples during
demultiplexing — a common cause of low-quality runs that is not caught by a
simple duplicate check. The validator computes the Hamming distance between
every pair of indexes within each lane and warns when the distance falls below
the recommended minimum of 3.

For dual-index sheets, the I7 and I5 sequences are combined before comparison,
so a pair that is close on I7 but well-separated on I5 (as most dual-index
kits are designed) is not incorrectly flagged.

```python
# Custom threshold — stricter than the default of 3
from samplesheet_parser.validators import SampleSheetValidator, ValidationResult

samples = sheet.samples()
result = ValidationResult()
SampleSheetValidator()._check_index_distances(samples, result, min_distance=4)
```

---

## Diff

`SampleSheetDiff` compares two sheets — any combination of V1 and V2 — and
returns a structured `DiffResult` across four dimensions:

| Dimension | What is compared |
|---|---|
| Header | Key/value changes in `[Header]` / `[BCLConvert_Settings]` |
| Reads | Read length or cycle count changes |
| Samples added / removed | Keyed on `Sample_ID` + `Lane` |
| Sample field changes | Per-sample field-level diffs (index, project, etc.) |

```python
result = SampleSheetDiff("before.csv", "after.csv").compare()

result.has_changes          # bool
result.summary()            # one-paragraph human-readable summary
result.header_changes       # list[HeaderChange]
result.samples_added        # list[dict]
result.samples_removed      # list[dict]
result.sample_changes       # list[SampleChange]

# Inspect per-sample changes
for sc in result.sample_changes:
    print(sc.sample_id, sc.lane)
    for field, (old, new) in sc.changes.items():
        print(f"  {field}: {old!r} → {new!r}")
```

V1-only metadata columns (`I7_Index_ID`, `I5_Index_ID`, `Sample_Name`,
`Description`) are suppressed when comparing V1 against V2 so that format
differences do not generate noise.

---

## UMI / OverrideCycles parsing

The V2 `OverrideCycles` field encodes read structure including UMI positions:

| OverrideCycles | UMI length | UMI location |
|---|---|---|
| `Y151;I10;I10;Y151` | 0 | — |
| `Y151;I10U9;I10;Y151` | 9 | `index2` |
| `U5Y146;I8;I8;U5Y146` | 5 | `read1` |

```python
sheet.get_umi_length()       # → int
sheet.get_read_structure()   # → ReadStructure dataclass
```

---

## API reference

### `SampleSheetFactory`

| Method / attribute | Returns | Description |
|---|---|---|
| `create_parser(path, *, clean, experiment_id, parse)` | `SampleSheetV1 \| SampleSheetV2` | Auto-detect format and return appropriate parser |
| `get_umi_length()` | `int` | UMI length from the current parser |
| `.version` | `SampleSheetVersion` | Detected format version |

### `SampleSheetV1` / `SampleSheetV2` (shared interface)

| Method / attribute | Returns | Description |
|---|---|---|
| `parse(do_clean=True)` | `None` | Parse all sections |
| `samples()` | `list[dict]` | One record per unique sample |
| `index_type()` | `str` | `"dual"`, `"single"`, or `"none"` |
| `.adapters` | `list[str]` | Adapter sequences |
| `.experiment_name` | `str \| None` | Run/experiment name |

### V2-only
| Method | Returns |
|---|---|
| `get_umi_length()` | `int` |
| `get_read_structure()` | `ReadStructure` |

### `SampleSheetConverter`
| Method | Returns | Notes |
|---|---|---|
| `to_v2(output_path)` | `Path` | Converts IEM V1 → BCLConvert V2 |
| `to_v1(output_path)` | `Path` | Converts BCLConvert V2 → IEM V1 (lossy) |
| `.source_version` | `SampleSheetVersion` | Auto-detected format of input |


### `SampleSheetValidator`

| Method | Returns | Description |
|---|---|---|
| `validate(sheet)` | `ValidationResult` | Run all checks; returns structured result |
| `_check_index_distances(samples, result, min_distance=3)` | `None` | Hamming distance check (callable directly for custom thresholds) |

### `SampleSheetDiff`

| Method | Returns | Description |
|---|---|---|
| `compare()` | `DiffResult` | Full comparison across header, reads, settings, and samples |

### `DiffResult`

| Attribute / method | Type | Description |
|---|---|---|
| `has_changes` | `bool` | `True` if any difference was detected |
| `summary()` | `str` | Human-readable one-paragraph summary |
| `header_changes` | `list[HeaderChange]` | Header, reads, and settings diffs |
| `samples_added` | `list[dict]` | Records present in new sheet only |
| `samples_removed` | `list[dict]` | Records present in old sheet only |
| `sample_changes` | `list[SampleChange]` | Per-sample field-level diffs |
| `source_version` | `SampleSheetVersion` | Format of the old sheet |
| `target_version` | `SampleSheetVersion` | Format of the new sheet |

---

## Contributing

```bash
git clone https://github.com/chaitanyakasaraneni/samplesheet-parser
cd samplesheet-parser
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run demo scripts
python scripts/demo_converter.py
python scripts/demo_diff.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full local testing guide and PR checklist.

---

## Citation

```bibtex
@software{kasaraneni2026samplesheetparser,
  author  = {Kasaraneni, Chaitanya},
  title   = {samplesheet-parser: Format-agnostic parser for Illumina SampleSheet.csv},
  year    = {2026},
  url     = {https://github.com/chaitanyakasaraneni/samplesheet-parser},
  version = {0.1.5}
}
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

## Related resources

- [Illumina IEM V1 SampleSheet reference (Knowledge Article #2204)](https://knowledge.illumina.com/software/on-premises-software/software-on-premises-software-reference_material-list/000002204)
- [BCLConvert Software Guide](https://support.illumina.com/sequencing/sequencing_software/bcl-convert.html)
- [Upgrading from bcl2fastq to BCLConvert](https://knowledge.illumina.com/software/general/software-general-reference_material-list/000003710)
- [Illumina index design recommendations](https://support.illumina.com/bulletins/2020/06/index-misassignment-between-samples-on-the-novaseq-6000.html)
