# samplesheet-parser

**Format-agnostic Python parser for Illumina `SampleSheet.csv` files.**

Supports IEM V1 (bcl2fastq / NovaSeq 6000 era) and BCLConvert V2 (NovaSeq X series) with automatic format detection, index validation, and `OverrideCycles` / UMI decoding — no format hints required from the caller.

[![PyPI version](https://img.shields.io/pypi/v/samplesheet-parser.svg)](https://pypi.org/project/samplesheet-parser/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-yellow.svg)](https://opensource.org/licenses/Apache-2.0)
[![Tests](https://github.com/chaitanyakasaraneni/samplesheet-parser/actions/workflows/ci.yml/badge.svg)](https://github.com/chaitanyakasaraneni/samplesheet-parser/actions)
[![codecov](https://codecov.io/gh/chaitanyakasaraneni/samplesheet-parser/branch/main/graph/badge.svg)](https://codecov.io/gh/chaitanyakasaraneni/samplesheet-parser)

---

## The problem

Labs running mixed instrument fleets — NovaSeq 6000 alongside NovaSeq X series — produce two structurally incompatible `SampleSheet.csv` formats:

| | IEM V1 | BCLConvert V2 |
|---|---|---|
| Discriminator | `IEMFileVersion` in `[Header]` | `FileFormatVersion` in `[Header]` |
| Data section | `[Data]` | `[BCLConvert_Data]` |
| Settings section | `[Settings]` | `[BCLConvert_Settings]` |
| Index columns | `index`, `index2` (lowercase) | `Index`, `Index2` (uppercase) |
| Read cycles | Bare integers | Key-value (`Read1Cycles,151`) |
| UMI encoding | Not supported | `OverrideCycles` string |
| Used with | bcl2fastq | BCLConvert ≥ 3.x |

Without a single parser, every pipeline component that reads a SampleSheet needs an `if v1 else v2` branch — or worse, the format is hardcoded and the wrong sheet is silently processed.

---

## Installation

```bash
pip install samplesheet-parser
```

Requires Python 3.10+. The only mandatory dependency is [`loguru`](https://github.com/Delgan/loguru).

---

## Quickstart

### Auto-detect format (recommended)

```python
from samplesheet_parser import SampleSheetFactory

factory = SampleSheetFactory()
sheet = factory.create_parser("SampleSheet.csv", parse=True)

print(factory.version)           # SampleSheetVersion.V1 or .V2
print(sheet.index_type())        # "dual", "single", or "none"
print(factory.get_umi_length())  # 0 if no UMI

for sample in sheet.samples():
    print(sample["sample_id"], sample["index"])
```

### Validate before demultiplexing

```python
from samplesheet_parser import SampleSheetFactory, SampleSheetValidator

sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
result = SampleSheetValidator().validate(sheet)

print(result.summary())
# PASS — 0 error(s), 1 warning(s)

for err in result.errors:
    print(err)
# [ERROR] DUPLICATE_INDEX: Index 'ATTACTCG+TATAGCCT' appears more than once in lane 1.
```

### UMI extraction (V2 only)

```python
from samplesheet_parser import SampleSheetV2

sheet = SampleSheetV2("SampleSheet.csv", parse=True)

# OverrideCycles: Y151;I10U9;I10;Y151 → 9 bp UMI in Index1
print(sheet.get_umi_length())        # 9
rs = sheet.get_read_structure()
print(rs.umi_location)               # "index2"
print(rs.read_structure)             # {"read1_template": 151, "index2_length": 10, "index2_umi": 9, ...}
```

### Use parsers directly

```python
from samplesheet_parser import SampleSheetV1, SampleSheetV2

# V1
v1 = SampleSheetV1("SampleSheet_v1.csv", parse=True)
print(v1.experiment_name)    # "240115_A01234_0042_AHJLG7DRXX"
print(v1.instrument_type)    # "NovaSeq 6000"
print(v1.adapter_read1)      # "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA"
print(v1.adapter_read2)      # "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT"
print(v1.reverse_complement) # 0
print(v1.read_lengths)       # [151, 151]

# V2
v2 = SampleSheetV2("SampleSheet_v2.csv", parse=True)
print(v2.instrument_platform)  # "NovaSeqXSeries"
print(v2.software_version)     # "3.9.3"
```

---

## Format detection logic

The factory uses a three-step strategy — stopping as early as possible:

```
1. Scan [Header] for FileFormatVersion  → V2
                  or IEMFileVersion     → V1

2. If undetermined: scan full file for
   [BCLConvert_Settings] or
   [BCLConvert_Data]                    → V2

3. Default                              → V1
```

The file is read only once. No second `open()`, no `seek()`.

---

## OverrideCycles decoding

The V2 `OverrideCycles` string encodes the full read structure using single-letter type codes:

| Code | Meaning |
|---|---|
| `Y` | Template (sequenced) bases |
| `I` | Index bases |
| `U` | UMI bases |
| `N` | Masked / skipped bases |

Segment order: `Read1 ; Index1 ; Index2 ; Read2`

| OverrideCycles | UMI length | UMI location |
|---|---|---|
| `Y151;I10;I10;Y151` | 0 | — |
| `Y151;I10U9;I10;Y151` | 9 bp | Index1 |
| `U5Y146;I8;I8;U5Y146` | 5 bp | Read1 + Read2 |
| `Y76;I8;Y76` | 0 | — (single-index) |

---

## Validation checks

| Code | Level | Condition |
|---|---|---|
| `EMPTY_SAMPLES` | error | No samples found in data section |
| `INVALID_INDEX_CHARS` | error | Index contains non-ACGTN characters |
| `INDEX_TOO_LONG` | error | Index longer than 24 bp |
| `DUPLICATE_INDEX` | error | Two samples share an index in the same lane |
| `DUPLICATE_SAMPLE_ID` | error | Same `Sample_ID` appears twice in one lane |
| `INDEX_TOO_SHORT` | warning | Index shorter than 6 bp |
| `NO_ADAPTERS` | warning | No adapter sequences configured |
| `ADAPTER_MISMATCH` | warning | Adapter is not a standard Illumina sequence |

---

## API reference

### `SampleSheetFactory`

```python
factory = SampleSheetFactory()
sheet = factory.create_parser(path, *, clean=True, experiment_id=None, parse=None)
```

| Attribute / Method | Returns | Description |
|---|---|---|
| `.create_parser(path, ...)` | `SampleSheetV1 \| SampleSheetV2` | Auto-detect format and return parser |
| `.get_umi_length()` | `int` | UMI length from current parser |
| `.version` | `SampleSheetVersion` | Detected version after `create_parser()` |

### Shared interface — `SampleSheetV1` and `SampleSheetV2`

| Method / Attribute | Returns | Description |
|---|---|---|
| `.parse(do_clean=True)` | `None` | Parse all sections |
| `.samples()` | `list[dict]` | One record per unique sample |
| `.index_type()` | `str` | `"dual"`, `"single"`, or `"none"` |
| `.adapters` | `list[str]` | All configured adapter sequences |
| `.experiment_name` | `str \| None` | Run or experiment name |
| `.read_lengths` / `.reads` | `list[int]` / `dict` | Read cycle lengths |

### V1-specific

| Attribute | Type | Description |
|---|---|---|
| `.iem_version` | `str \| None` | e.g. `"5"` |
| `.instrument_type` | `str \| None` | e.g. `"NovaSeq 6000"`, `"MiSeq"` |
| `.application` | `str \| None` | e.g. `"FASTQ Only"` |
| `.assay` | `str \| None` | Library prep kit name |
| `.index_adapters` | `str \| None` | Illumina index set name |
| `.chemistry` | `str \| None` | `"Amplicon"` = dual index, `"Default"` = single/no index |
| `.adapter_read1` | `str` | Read 1 adapter (`Adapter` or `AdapterRead1` key) |
| `.adapter_read2` | `str` | Read 2 adapter (`AdapterRead2` key) |
| `.reverse_complement` | `int` | `0` = default, `1` = reverse-complement R2 (Nextera MP only) |
| `.flowcell_id` | `str \| None` | Parsed from experiment ID run folder name |

### V2-specific

| Method / Attribute | Returns | Description |
|---|---|---|
| `.get_umi_length()` | `int` | UMI length from `OverrideCycles` |
| `.get_read_structure()` | `ReadStructure` | Full decoded read structure |
| `.instrument_platform` | `str \| None` | e.g. `"NovaSeqXSeries"` |
| `.software_version` | `str \| None` | BCLConvert version string |
| `.custom_fields` | `dict[str, set[str]]` | Non-standard fields by section |

---

## Example sample sheets

The [`examples/sample_sheets/`](examples/sample_sheets/) directory contains ready-to-use reference sheets for every supported configuration:

| File | Format | Instrument | UMI | Use case |
|---|---|---|---|---|
| `v1_dual_index.csv` | V1 | NovaSeq 6000 | No | Standard WGS, multi-lane |
| `v1_single_index.csv` | V1 | NextSeq 500 | No | Small RNA |
| `v1_multi_lane.csv` | V1 | NovaSeq 6000 | No | 4 lanes, mixed projects |
| `v2_novaseq_x_dual_index.csv` | V2 | NovaSeq X | No | Standard PE150 |
| `v2_with_index_umi.csv` | V2 | NovaSeq X | Index1 UMI (9 bp) | cfDNA / liquid biopsy |
| `v2_with_read_umi.csv` | V2 | NovaSeq X | Read UMI (5 bp) | Duplex sequencing |
| `v2_nextseq_single_index.csv` | V2 | NextSeq 1000/2000 | No | Amplicon panel |

Run the demo to parse all of them:

```bash
python examples/parse_examples.py
```

---

## V1 adapter key reference

From the [Illumina IEM specification](https://knowledge.illumina.com/software/on-premises-software/software-on-premises-software-reference_material-list/000002204), the correct V1 `[Settings]` adapter keys are:

```csv
[Settings]
ReverseComplement,0
Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA
AdapterRead2,AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT
```

- `Adapter` = Read 1 adapter (primary key per IEM spec)
- `AdapterRead2` = Read 2 adapter (explicit separate key)
- `AdapterRead1` = BCLConvert V1-mode alias for `Adapter` (also accepted)
- `ReverseComplement,1` = only for Nextera Mate Pair libraries; `0` for everything else

---

## Project structure

```
samplesheet-parser/
├── samplesheet_parser/
│   ├── __init__.py          # Public API
│   ├── factory.py           # SampleSheetFactory — auto-detection
│   ├── enums.py             # SampleSheetVersion, IndexType, ...
│   ├── validators.py        # SampleSheetValidator, ValidationResult
│   └── parsers/
│       ├── v1.py            # IEM V1 parser (bcl2fastq)
│       └── v2.py            # BCLConvert V2 parser (NovaSeq X)
├── tests/
│   ├── conftest.py          # Shared fixtures
│   ├── test_factory.py
│   ├── test_parsers/
│   │   ├── test_v1.py
│   │   └── test_v2.py
│   └── test_validators/
│       └── test_validators.py
├── examples/
│   ├── parse_examples.py    # Demo script
│   └── sample_sheets/       # Reference SampleSheet.csv files
├── pyproject.toml
├── LICENSE
└── README.md
```

---

## Development

```bash
git clone https://github.com/chaitanyakasaraneni/samplesheet-parser
cd samplesheet-parser
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run example demo
python examples/parse_examples.py
```

---

## Citation

If you use this library in a published pipeline or analysis, please cite:

```bibtex
@software{kasaraneni2026samplsheetparser,
  author  = {Kasaraneni, Chaitanya},
  title   = {samplesheet-parser: Format-agnostic parser for Illumina SampleSheet.csv},
  year    = {2026},
  url     = {https://github.com/chaitanyakasaraneni/samplesheet-parser},
  version = {0.1.0}
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
