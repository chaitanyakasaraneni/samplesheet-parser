# Changelog

All notable changes to `samplesheet-parser` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added

- **`--format json` for `samplesheet convert`** — the convert command now accepts
  `--format json` and emits a structured JSON object with `input`, `output`,
  `source_version`, and `target_version` keys. All five CLI subcommands now
  support `--format json` uniformly.

- **Bioconda recipe (`recipes/meta.yaml`)** — a `noarch: python` conda recipe
  targeting Python ≥ 3.12 with `loguru` as the only runtime dependency.
  The CLI extra (`typer`) is intentionally omitted from the base recipe so the
  conda package stays lightweight; users who need the `samplesheet` CLI can
  `conda install typer` alongside.

### Tests

- Three new `TestCLIConvert` tests covering `--format json` exit code,
  JSON output structure (`source_version`, `target_version`, `input`, `output`
  keys), and the `--format xml` invalid-format guard.

---

## [1.1.0] - 2026-04-05

### Added

- **`--version` / `-V` CLI flag** — prints the installed package version
  and exits. Reads the version via `importlib.metadata` so the full package
  is not loaded just to print a version string.

- **`demo_converter.py`** — runnable example covering V1→V2 conversion,
  V2→V1 (lossy) conversion, and a full V1→V2→V1 roundtrip with sample
  identity verification.

- **`demo_diff.py`** — runnable example covering five diff scenarios:
  identical sheets, header change, sample added, index correction, and
  cross-format (V1 vs its V2 conversion) diff.

- **`demo_writer.py`** — runnable example covering the fluent
  `SampleSheetWriter` API: building V1 and V2 sheets from scratch,
  correcting a sample index on an existing sheet, and removing a sample
  before submission.

- **`demo_index_utils.py`** — runnable example covering
  `normalize_index_lengths` with trim and pad strategies, dual-index
  normalization, and a real-sheet walkthrough.

### Fixed

- `SampleSheetFactory.create_parser()` now returns a typed local variable
  instead of `self.parser`, resolving a mypy `return-value` error caused
  by the instance attribute being typed as `SampleSheetV1 | SampleSheetV2
  | None`.

- `cli.py` fallback type aliases (`_FormatOption`, `_OutputOption`,
  `_VersionOption`) reduced from `type: ignore[assignment,misc]` to
  `type: ignore[misc]` — the `assignment` suppression was unused under
  current mypy.

### Tests

- `TestCLIVersion` — four new tests covering `--version` exit code, `-V`
  short flag, package name in output, version string in output, and
  `PackageNotFoundError` fallback to `"unknown"`.

- Five Copilot PR #23 review comments resolved: long test signatures and
  `runner.invoke(...)` calls wrapped to the 100-char line limit.

---

## [1.0.0] - 2026-04-05

### Added

- **`py.typed` marker** — package now ships inline type information per
  PEP 561, enabling mypy and pyright to type-check downstream code without
  extra configuration.

- **`InstrumentPlatform` and `UMILocation` enums exported** — both were
  already defined in `enums.py` but not part of the public API. They are now
  importable directly from the top-level package and listed in `__all__`.

- **`.pre-commit-config.yaml`** — pre-commit hook configuration included in
  the repository (black, ruff with `--fix`, mypy, and standard file hygiene
  hooks) so contributors get the same checks locally that CI enforces.

### Fixed

- `SampleSheetFactory.create_parser()` now returns a typed local variable
  instead of `self.parser`, resolving a mypy `return-value` error caused by
  the instance attribute being typed as `SampleSheetV1 | SampleSheetV2 | None`.

- `SampleSheetMerger._parse_all()` guards against `factory.version` being
  `None` before accessing `.value`, fixing a potential `AttributeError` on
  unexpected parse paths.

- Removed redundant `type: ignore[assignment]` suppressions in
  `index_utils.py` that were no longer needed under strict mypy.

### Changed

- Development status classifier updated from `3 - Alpha` to
  `5 - Production/Stable`.

- Ruff config adds `[tool.ruff.lint.per-file-ignores]` to suppress E402 for
  `samplesheet_parser/__init__.py`, where the version-detection block
  intentionally precedes the package re-exports.

- **Stability guarantee** — `1.0.0` marks the first stable release.
  The public API (all names in `__init__.__all__`) is now subject to
  semantic versioning: breaking changes will not be made without a major
  version bump.

---

## [0.3.4] - 2026-04-04

### Added

- **`samplesheet info` CLI command** — prints a concise summary of any V1 or
  V2 sample sheet (format, sample count, lanes, index type, read lengths,
  adapters, experiment name, instrument). Supports `--format json` for
  machine-readable output; exits 0 on success, 2 on unreadable files.

- **Configurable Hamming distance threshold** — `SampleSheetValidator.validate()`
  now accepts a `min_hamming_distance` keyword argument (default: 3) so labs
  using longer indexes can enforce stricter thresholds without changing the
  module-level constant.
  - `SampleSheetMerger` accepts the same parameter in `__init__()` and applies
    it to both the intra-sheet and cross-sheet Hamming checks as well as the
    post-merge validation step.
  - `samplesheet validate` exposes `--min-hamming N` (must be ≥ 1; exits 2 on
    invalid input). The JSON output includes `min_hamming_distance` for
    auditability.

- **`normalize_index_lengths()` utility** — normalizes index sequence lengths
  across a list of sample dicts (output of `sheet.samples()`) to a consistent
  length before merging sheets with mixed-length indexes.
  - `strategy="trim"` — trims all indexes to the shortest sequence length.
  - `strategy="pad"` — pads shorter indexes to the longest length using `"N"`
    wildcard characters (supported by BCLConvert ≥ 3.9 and bcl2fastq ≥ 2.20).
  - Auto-detects V1-style (`index`/`index2`) and V2-style (`Index`/`Index2`)
    field names; explicit `index1_key`/`index2_key` overrides supported.
  - Exported from the top-level package as `normalize_index_lengths`.

- **CI / pre-commit integration guide** in README — GitHub Actions workflow
  and pre-commit hook configuration for automatic sample sheet validation on
  every commit or pull request that touches a `SampleSheet.csv`.

### Fixed

- `_detect_key()` in `index_utils` now selects the key with at least one
  non-empty value before falling back to key presence, preventing silent
  normalization skip when a key exists but all its values are `None` or `""`.

### Changed

- `--min-hamming` CLI option default and help text are now derived from the
  `MIN_HAMMING_DISTANCE` constant in `validators.py` to prevent drift.

---

## [0.3.3] - 2026-03-13

### Documentation
- Add architecture diagram showing full library structure including CLI and SampleSheetMerger
- Update README with architecture overview, solid vs dashed line legend
- Add `[Custom_Sections*]` to V1 and V2 format descriptions

## [0.3.2] - 2026-03-12

### Added
- `.zenodo.json` metadata file for automatic Zenodo archival and DOI
  minting on GitHub releases
- `CITATION.cff` file enabling GitHub's "Cite this repository" button
  and standardized software citation for downstream users

## [0.3.1] - 2026-03-11

### Fixed

- **`SampleSheetMerger`** — `INDEX_DISTANCE_TOO_LOW` and `DUPLICATE_INDEX`
  were reported twice in `--force` merges (once by the pre-merge cross-sheet
  check, once by the post-merge validator). Duplicate codes are now suppressed
  in `_validate_merged` — the more descriptive pre-merge message is always
  preferred.

## [0.3.0] - 2026-03-10

### Added

- **`SampleSheetMerger`** — combines multiple per-project sample sheets into a
  single sheet for a flow cell run.
  - `add(path)` — register an input sheet (V1 or V2); mixed formats are
    auto-converted to the target version before merging.
  - `merge(output_path, validate=True, abort_on_conflicts=True)` — merges all
    registered sheets, writes the combined output, and returns a `MergeResult`.
  - **Index collision detection** — raises a conflict when two samples share
    the same lane and index sequence across project boundaries.
  - **Hamming distance check** — warns when the combined I7+I5 distance between
    any two samples across sheets falls below 3.
  - **Read-length conflict detection** — raises a conflict when registered
    sheets specify incompatible `Read1Cycles`/`Read2Cycles` (V2) or `[Reads]`
    lengths (V1).
  - **Adapter conflict detection** — warns when adapter sequences differ across
    sheets.
  - **Mixed-format warning** — emits a warning when V1 and V2 sheets are
    combined, with the auto-conversion strategy logged.
  - `MergeResult` dataclass — exposes `conflicts`, `warnings`, `sample_count`,
    `source_versions`, `output_path`, `has_conflicts`, and `summary()`;
    consistent with `ValidationResult` and `DiffResult`.
  - `abort_on_conflicts=True` (default) — skips writing the output file when
    any conflict is present; set `False` (via `--force` in the CLI) to write
    despite conflicts.
  - `SampleSheetMerger` and `MergeResult` are exported from the top-level
    package.

- **`samplesheet` CLI** — command-line interface exposing the four core
  operations, available as an optional extra (`pip install
  "samplesheet-parser[cli]"`; adds `typer` as a dependency).
  - `samplesheet validate <file>` — exits 0 if clean, 1 if errors, 2 on
    usage/parse errors. Supports `--format json` for machine-readable output.
  - `samplesheet convert <file> --to <v1|v2> --output <path>` — converts
    between formats; exits 0 on success, 1 on conversion error, 2 on bad
    arguments.
  - `samplesheet diff <old> <new>` — exits 0 if identical, 1 if differences
    detected (useful in CI pre-run checks). Supports `--format json`.
  - `samplesheet merge <files...> --output <path>` — merges two or more sheets;
    exits 0 on clean merge, 1 on conflicts or warnings, 2 on bad arguments.
    Supports `--force`, `--to <v1|v2>`, and `--format json`.
  - All commands print errors to stderr and structured data to stdout.
  - Entry point configured in `pyproject.toml`:
    `samplesheet = "samplesheet_parser.cli:main"`.
  - Module imports cleanly without `typer` installed — missing-extra error is
    surfaced only at invocation time.

### Changed

- README updated to document `SampleSheetMerger`, the `samplesheet` CLI, all
  new API reference tables, and installation instructions for the `[cli]` extra.
- `CONTRIBUTING.md` updated with CLI testing instructions and the new
  `[dev,cli]` install target.

---

## [0.2.0] - 2026-02-25

### Added

- **`SampleSheetWriter`** — programmatic creation and editing of IEM V1 and
  BCLConvert V2 sample sheets.
  - Build sheets from scratch with a fluent API: `set_header()`, `set_reads()`,
    `set_adapter()`, `set_override_cycles()`, `set_software_version()`,
    `set_setting()`, `add_sample()`.
  - `from_sheet(sheet, version=)` class method — load any parsed V1/V2 sheet,
    edit in place, and write back; pass a different `version` to convert format
    while editing.
  - `remove_sample(sample_id, lane=)` and `update_sample(sample_id, **fields)`
    for surgical edits to existing sheets.
  - `write(path, validate=True)` — runs `SampleSheetValidator` before writing
    by default; raises `ValueError` with the full error list if validation fails.
  - `to_string()` — serialise to a string without writing to disk (useful for
    testing and inspection).
  - CSV safety: `_validate_field` rejects commas, newlines, and quotes in all
    free-text inputs (`sample_id`, `index`, `project`, `run_name`, adapter
    sequences, custom column keys/values, etc.) at input time with a clear
    error message.
  - `SampleSheetWriter` is now exported from the top-level package.

- **`SampleSheetDiff`** — structured comparison of two sample sheets across
  any combination of V1 and V2 formats.
  - Compares header, reads, settings, and samples in a single `compare()` call.
  - Returns a `DiffResult` dataclass with `header_changes`, `samples_added`,
    `samples_removed`, and `sample_changes`.
  - V1-only metadata columns (`I7_Index_ID`, `I5_Index_ID`, `Sample_Name`,
    `Description`) are suppressed during cross-format comparison to avoid
    format-noise diffs.
  - `DiffResult.summary()` and `DiffResult.has_changes` for quick inspection.

- **`INDEX_DISTANCE_TOO_LOW` validation check** — `SampleSheetValidator` now
  computes the Hamming distance between every pair of index sequences within
  each lane and warns when the distance falls below the recommended minimum
  of 3. For dual-index sheets the combined I7+I5 sequence is used so that
  pairs well-separated on I5 are not incorrectly flagged.

- **`_hamming_distance` helper** — module-level pure function, independently
  testable, handles sequences of unequal length by comparing up to the shorter
  sequence length.

- **`scripts/demo_writer.py`** — smoke-test script demonstrating V1/V2
  from-scratch creation and round-trip editing.

- **`scripts/demo_diff.py`** — smoke-test script demonstrating identical,
  modified, and cross-format diff scenarios.

- **`.github/copilot-instructions.md`** — Copilot review instructions scoping
  suggestions to logic bugs, test coverage gaps, and type errors.

### Changed

- README updated to document `SampleSheetDiff`, `SampleSheetWriter`,
  Hamming distance validation, and the full API reference tables.

---

## [0.1.5] - 2026-02-23

### Added

- **`SampleSheetConverter`** — bidirectional V1 ↔ V2 format conversion.
  - `to_v2(output_path)` — converts IEM V1 to BCLConvert V2.
  - `to_v1(output_path)` — converts BCLConvert V2 to IEM V1 (lossy; V2-only
    fields dropped with a warning).
  - Auto-detects source format via `SampleSheetFactory`.

- **`scripts/demo_converter.py`** — smoke-test script for converter scenarios
  including V1→V2→V1 and V2→V1→V2 round-trips.

- **`CONTRIBUTING.md`** — local development setup, test instructions, and
  PR checklist.

---

## [0.1.1] – [0.1.4] - 2026-02-22 / 2026-02-23

### Fixed

- CI workflow not triggering on tag push — added `tags` trigger to
  `ci.yml` (was gated on tags but never configured to *run* on them).
- PyPI README image not rendering — switched from `badge.fury.io` to
  `shields.io` dynamic badge; bumped versions to force PyPI to re-render
  the README on each new release.
- Minor ruff and mypy fixes surfaced during initial CI runs.

> These were infrastructure-only patch releases with no API or behaviour
> changes.

---

## [0.1.0] - 2026-02-22

### Added

- **`SampleSheetV1`** — parser for IEM V1 (bcl2fastq-era) sample sheets.
  Parses `[Header]`, `[Reads]`, `[Settings]`, `[Manifests]`, and `[Data]`
  sections. Exposes `samples()`, `index_type()`, `adapters`, `read_lengths`,
  and all standard header fields.

- **`SampleSheetV2`** — parser for BCLConvert V2 (NovaSeq X series) sample
  sheets. Parses `[Header]`, `[Reads]`, `[BCLConvert_Settings]`,
  `[BCLConvert_Data]`, and optional `[Cloud_Data]` sections. Adds
  `get_umi_length()` and `get_read_structure()` for `OverrideCycles` decoding.

- **`SampleSheetFactory`** — auto-detects V1 vs V2 format using a three-step
  strategy (header key scan → section name scan → V1 fallback) and returns
  the appropriate parser.

- **`SampleSheetValidator`** — validates parsed sheets for `EMPTY_SAMPLES`,
  `INVALID_INDEX_CHARS`, `INDEX_TOO_SHORT`, `INDEX_TOO_LONG`,
  `DUPLICATE_INDEX`, `MISSING_INDEX2`, `DUPLICATE_SAMPLE_ID`, `NO_ADAPTERS`,
  and `ADAPTER_MISMATCH`. Returns a structured `ValidationResult`.

- Initial PyPI release. Requires Python 3.10+, depends only on `loguru`.
