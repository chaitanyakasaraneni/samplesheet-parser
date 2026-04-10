# samplesheet-parser

**Format-agnostic parser for Illumina SampleSheet.csv files.**

Supports both the classic IEM V1 format (bcl2fastq era) and the modern BCLConvert V2 format (NovaSeq X series) — with automatic format detection, bidirectional conversion, index validation, Hamming distance checking, diff comparison, multi-sheet merging, splitting, filtering, programmatic sheet creation, and a full-featured CLI.

[![PyPI version](https://img.shields.io/pypi/v/samplesheet-parser.svg)](https://pypi.org/project/samplesheet-parser/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-yellow.svg)](https://opensource.org/licenses/Apache-2.0)
[![Tests](https://github.com/chaitanyakasaraneni/samplesheet-parser/actions/workflows/ci.yml/badge.svg)](https://github.com/chaitanyakasaraneni/samplesheet-parser/actions)
[![codecov](https://codecov.io/gh/chaitanyakasaraneni/samplesheet-parser/branch/main/graph/badge.svg?token=CODECOV_TOKEN)](https://codecov.io/gh/chaitanyakasaraneni/samplesheet-parser)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18989694.svg)](https://doi.org/10.5281/zenodo.18989694)

![samplesheet-parser overview](https://raw.githubusercontent.com/chaitanyakasaraneni/samplesheet-parser/main/images/samplesheet_parser_arch_v03.png)

---

## The problem this solves

Labs running mixed instrument fleets — older NovaSeq 6000 alongside newer NovaSeq X series — produce two incompatible SampleSheet formats. BCLConvert V2 sheets use `[BCLConvert_Settings]` / `[BCLConvert_Data]` sections, `OverrideCycles` for UMI encoding, and `FileFormatVersion` in the header. IEM V1 sheets use `IEMFileVersion` and a flat `[Data]` section.

Existing tools either hard-code one format or require the caller to know which format they have. `samplesheet-parser` auto-detects the format, exposes a consistent interface for both, converts between formats, validates index integrity (including Hamming distance), diffs sheets to catch accidental changes before a run starts, and writes new sheets programmatically — so you never have to hand-edit a CSV again.

---

## Key features

| Feature | Description |
|---|---|
| **Auto-detection** | Three-step format detection — no hints required |
| **V1 & V2 parsing** | Consistent `samples()` / `index_type()` interface for both formats |
| **Bidirectional conversion** | V1 → V2 and V2 → V1 (lossy, with warnings) |
| **Validation** | 9 checks covering index chars, length, duplicates, Hamming distance, adapters |
| **Diff** | Cross-format structural comparison with per-field change records |
| **Merge** | Combine multiple per-project sheets with collision detection |
| **Split** | Divide a combined sheet into per-project or per-lane files |
| **Filter** | Extract a sample subset by project, lane, or ID (glob patterns supported) |
| **Writer** | Fluent API for building or editing sheets programmatically |
| **CLI** | Full shell interface with `--format json` for pipeline integration |
| **UMI parsing** | Decode `OverrideCycles` to extract UMI length and location |

---

## Quickstart

```bash
pip install samplesheet-parser
```

```python
from samplesheet_parser import SampleSheetFactory, SampleSheetValidator

sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
result = SampleSheetValidator().validate(sheet)
print(result.summary())
# PASS — 0 error(s), 0 warning(s)
```

See [Installation](installation.md) for full setup options, jump to the [Quickstart guide](guide/quickstart.md), or browse the [Examples](examples.md) for end-to-end runnable scenarios.
