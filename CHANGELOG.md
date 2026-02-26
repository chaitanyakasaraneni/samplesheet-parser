# Changelog

All notable changes to `samplesheet-parser` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
