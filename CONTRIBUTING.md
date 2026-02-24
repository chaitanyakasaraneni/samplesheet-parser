# Contributing to samplesheet-parser

Thanks for contributing! This guide explains how to set up a local development environment, run tests, and prepare your PR with the evidence reviewers need to merge confidently.

---

## Table of contents

- [Contributing to samplesheet-parser](#contributing-to-samplesheet-parser)
  - [Table of contents](#table-of-contents)
  - [Setup](#setup)
  - [Running the test suite](#running-the-test-suite)
  - [Running the demo script](#running-the-demo-script)
  - [What to attach to your PR](#what-to-attach-to-your-pr)
    - [For any PR](#for-any-pr)
    - [For PRs touching the converter](#for-prs-touching-the-converter)
    - [Example PR description](#example-pr-description)
  - [PR checklist](#pr-checklist)
  - [Code style](#code-style)
  - [Adding fixture files](#adding-fixture-files)

---

## Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/chaitanyakasaraneni/samplesheet-parser.git
cd samplesheet-parser

# 2. Create a virtual environment (Python 3.10+)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

---

## Running the test suite

```bash
# Run all tests with coverage
pytest

# Run only the converter tests
pytest tests/test_converter.py -v

# Run a single test class
pytest tests/test_converter.py::TestV1ToV2 -v

# Run with a coverage threshold (CI requires ≥ 85%)
pytest --cov-fail-under=85
```

Coverage and test results are printed to the terminal and written to `coverage.xml` (used by Codecov on CI).

---

## Running the demo script

For PRs that touch the converter, run the demo script to generate real input/output artifacts you can attach to the PR.

```bash
python scripts/demo_converter.py
```

This script:
1. Reads the fixture files from `tests/fixtures/`
2. Runs V1 → V2 and V2 → V1 conversions
3. Runs both round-trip directions (V1 → V2 → V1 and V2 → V1 → V2)
4. Validates that sample IDs survive each round-trip
5. Writes all output files to `tests/fixtures/outputs/`

A passing run looks like:

```
────────────────────────────────────────────────────────────
  1/4  V1 → V2  (SampleSheet_v1_dual_index.csv)
────────────────────────────────────────────────────────────
Input  : tests/fixtures/SampleSheet_v1_dual_index.csv
Output : tests/fixtures/outputs/SampleSheet_v1_converted_to_v2.csv

✓ FileFormatVersion : 2
✓ RunName           : NovaSeqRun_20240115
✓ Sample count      : 8
✓ Index type        : dual

...

✓ All conversions passed. Attach the files in tests/fixtures/outputs/ to your PR.
```

Exit code `0` means all conversions passed. Exit code `1` means something failed — the error is printed to stderr.

---

## What to attach to your PR

### For any PR

Paste the output of `pytest` into the PR description or a comment. The minimum required is the summary line:

```
===== 47 passed, 0 warnings in 3.21s =====
```

A screenshot works too. The CI checks will also run automatically on push.

### For PRs touching the converter

Run `python scripts/demo_converter.py` and attach **all four output files** from `tests/fixtures/outputs/` as file attachments to the PR description:

| File | What it shows |
|---|---|
| `SampleSheet_v1_converted_to_v2.csv` | V1 → V2 output |
| `SampleSheet_v2_converted_to_v1.csv` | V2 → V1 output (lossy — note dropped fields in logs) |
| `SampleSheet_v1_roundtrip.csv` | V1 → V2 → V1 — sample IDs must match the original |
| `SampleSheet_v2_roundtrip.csv` | V2 → V1 → V2 — sample IDs must match the original |

To attach files to a GitHub PR description or comment, drag-and-drop them into the text box, or use the paperclip icon. `.csv` files can be attached directly.

Also paste the full terminal output of the demo script so reviewers can see the round-trip validation results without running it themselves.

### Example PR description

```
## What this PR does
Adds `SampleSheetConverter` to support V1 ↔ V2 conversions.

## Test results

pytest output:
```
===== 47 passed in 3.2s =====
```

## Converter demo output

<paste full output of `python scripts/demo_converter.py` here>

## Attached files

- SampleSheet_v1_converted_to_v2.csv
- SampleSheet_v2_converted_to_v1.csv
- SampleSheet_v1_roundtrip.csv
- SampleSheet_v2_roundtrip.csv
```

---

## PR checklist

Before marking a PR ready for review, confirm:

- [ ] `pytest` passes locally with no failures
- [ ] Coverage has not decreased (run `pytest` and check the `TOTAL` line)
- [ ] New behaviour has tests — aim for one test per logical case, not per line
- [ ] For converter changes: demo script passes and output files are attached
- [ ] `ruff check .` passes (no lint errors)
- [ ] `black --check .` passes (code is formatted)
- [ ] Docstrings updated for any changed public methods
- [ ] `CHANGELOG.md` entry added under `[Unreleased]` if applicable

---

## Code style

The project uses [Black](https://black.readthedocs.io) for formatting and [Ruff](https://docs.astral.sh/ruff/) for linting.

```bash
# Format
black .

# Lint
ruff check .

# Fix auto-fixable lint issues
ruff check . --fix
```

Both are enforced by CI. The line length is **100 characters** (set in `pyproject.toml`).

Type annotations are required for all public functions. Run mypy with:

```bash
mypy samplesheet_parser/
```

---

## Adding fixture files

If your PR adds a new sheet format or edge case, add a corresponding fixture file to `tests/fixtures/` alongside the existing ones. Name it descriptively, e.g. `SampleSheet_v1_no_reads.csv`. The fixture directory is tracked in git so reviewers can inspect the inputs your tests use.
