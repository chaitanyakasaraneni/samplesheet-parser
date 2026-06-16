# samplesheet-parser

**Multi-vendor, format-agnostic parser for sequencing sample sheets.**

Supports the classic Illumina IEM V1 format (bcl2fastq era), the modern BCLConvert V2 format (NovaSeq X series), and non-Illumina **Element AVITI** run manifests behind one interface — with automatic format detection, bidirectional conversion, index validation, Hamming distance checking, **per-cycle color-balance validation** against the instrument's optical chemistry, diff comparison, multi-sheet merging, splitting, filtering, programmatic sheet creation, and a full-featured CLI.

[![PyPI version](https://img.shields.io/pypi/v/samplesheet-parser.svg)](https://pypi.org/project/samplesheet-parser/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-yellow.svg)](https://opensource.org/licenses/Apache-2.0)
[![Tests](https://github.com/chaitanyakasaraneni/samplesheet-parser/actions/workflows/ci.yml/badge.svg)](https://github.com/chaitanyakasaraneni/samplesheet-parser/actions)
[![codecov](https://codecov.io/gh/chaitanyakasaraneni/samplesheet-parser/branch/main/graph/badge.svg?token=CODECOV_TOKEN)](https://codecov.io/gh/chaitanyakasaraneni/samplesheet-parser)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18989694.svg)](https://doi.org/10.5281/zenodo.18989694)

![samplesheet-parser overview](https://raw.githubusercontent.com/chaitanyakasaraneni/samplesheet-parser/main/images/samplesheet_parser_arch_v2.3.png)

---

## The problem this solves

Labs running mixed instrument fleets — older NovaSeq 6000 alongside newer NovaSeq X series, and increasingly non-Illumina platforms like the Element AVITI — produce several incompatible sample-sheet formats. BCLConvert V2 sheets use `[BCLConvert_Settings]` / `[BCLConvert_Data]` sections, `OverrideCycles` for UMI encoding, and `FileFormatVersion` in the header. IEM V1 sheets use `IEMFileVersion` and a flat `[Data]` section. Element AVITI ships a `RunManifest.csv` with an entirely different layout.

Existing tools either hard-code one vendor's format or require the caller to know which format they have. `samplesheet-parser` auto-detects the format across vendors, exposes a consistent interface for all of them, converts between the Illumina formats, validates index integrity (including Hamming distance and per-cycle color balance against each instrument's optical chemistry), diffs sheets to catch accidental changes before a run starts, and writes new sheets programmatically — so you never have to hand-edit a CSV again.

---

## Key features

| Feature | Description |
|---|---|
| **Auto-detection** | Format detection across vendors — no hints required |
| **V1, V2 & AVITI parsing** | Consistent `samples()` / `index_type()` interface for Illumina V1/V2 and Element AVITI run manifests |
| **Multi-vendor** | Element Biosciences AVITI `RunManifest.csv` parsed through the same `SampleSheetParser` protocol |
| **Bidirectional conversion** | V1 → V2 and V2 → V1 (lossy, with warnings) |
| **Validation** | Index chars, length, duplicates, Hamming distance, adapters |
| **Color balance** | Opt-in per-cycle optical-signal check against 4-/2-/1-channel instrument chemistry |
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
