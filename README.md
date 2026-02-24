# samplesheet-parser

**Format-agnostic parser for Illumina SampleSheet.csv files.**

Supports both the classic IEM V1 format (bcl2fastq era) and the modern BCLConvert V2 format (NovaSeq X series) — with automatic format detection, bidirectional conversion, index validation, and UMI parsing.

[![PyPI version](https://img.shields.io/pypi/v/samplesheet-parser.svg)](https://pypi.org/project/samplesheet-parser/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-yellow.svg)](https://opensource.org/licenses/Apache-2.0)
[![Tests](https://github.com/chaitanyakasaraneni/samplesheet-parser/actions/workflows/ci.yml/badge.svg)](https://github.com/chaitanyakasaraneni/samplesheet-parser/actions)
[![codecov](https://codecov.io/gh/chaitanyakasaraneni/samplesheet-parser/branch/main/graph/badge.svg?token=CODECOV_TOKEN)](https://codecov.io/gh/chaitanyakasaraneni/samplesheet-parser)

![samplesheet-parser overview](https://raw.githubusercontent.com/chaitanyakasaraneni/samplesheet-parser/main/images/samplesheet_parser_overview.png)

*`SampleSheetFactory` auto-detects the format and routes to the correct parser. Both formats share a common interface — and `SampleSheetConverter` handles bidirectional conversion between them.*

---

## The problem this solves

Labs running mixed instrument fleets — older NovaSeq 6000 alongside newer NovaSeq X series — produce two incompatible SampleSheet formats. BCLConvert V2 sheets use `[BCLConvert_Settings]` / `[BCLConvert_Data]` sections, `OverrideCycles` for UMI encoding, and `FileFormatVersion` in the header. IEM V1 sheets use `IEMFileVersion` and a flat `[Data]` section.

Existing tools either hard-code one format or require the caller to know which format they have. `samplesheet-parser` auto-detects the format, exposes a consistent interface for both, and can convert between them when needed.

---

## Installation

```bash
pip install samplesheet-parser
```

Requires Python 3.10+, no mandatory dependencies beyond `loguru`.

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
from samplesheet_parser import SampleSheetValidator, SampleSheetV1

sheet = SampleSheetV1("SampleSheet.csv")
sheet.parse()

sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
result = SampleSheetValidator().validate(sheet)

print(result.summary())
# PASS — 0 error(s), 1 warning(s)

for err in result.errors:
    print(err)
# [ERROR] DUPLICATE_INDEX: Index 'ATTACTCG+TATAGCCT' appears more than once in lane 1
```

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
| `DUPLICATE_SAMPLE_ID` | error | Same Sample_ID appears twice in one lane |
| `INDEX_TOO_SHORT` | warning | Index shorter than 6 bp |
| `NO_ADAPTERS` | warning | No adapter sequences configured |
| `ADAPTER_MISMATCH` | warning | Adapter is non-standard |

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
| Method | Returns | Description |
|---|---|---|
| `create_parser(path, *, clean, experiment_id, parse)` | `SampleSheetV1 \| SampleSheetV2` | Auto-detect and return appropriate parser |
| `get_umi_length()` | `int` | UMI length from current parser |
| `factory.version` | `SampleSheetVersion` | Detected format version |

### `SampleSheetV1` / `SampleSheetV2` (shared interface)
| Method | Returns | Description |
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
| `.source_version` | `SampleSheetVersion` | Auto-detected format of input file |

---

## Contributing

```bash
git clone https://github.com/chaitanyakasaraneni/samplesheet-parser
cd samplesheet-parser
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run example demo
python examples/parse_examples.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full local testing guide and PR checklist.

---

## Citation

```bibtex
@software{kasaraneni2026samplsheetparser,
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
