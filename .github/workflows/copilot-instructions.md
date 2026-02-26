# Copilot Review Instructions

## Project context

`samplesheet-parser` is a Python library for parsing, validating, converting,
and writing Illumina SampleSheet.csv files. The codebase follows strict typing
(mypy strict mode), ruff linting, and pytest for tests.

---

## What to focus on

- Logic bugs in CSV rendering that would produce malformed output
- Correctness of V1 ↔ V2 format conversion
- Missing edge cases in tests (multi-lane, empty sections, malformed input)
- Violations of the shared V1/V2 interface contract
- Actual type errors or missing None checks

---

## What to skip

**Do not suggest `_validate_field` or defensive input validation on fields
with naturally constrained input domains**, including:

- `set_software_version(version)` — version strings like `"4.2.7"` do not
  contain commas by definition
- `set_reads(read1, read2, index1, index2)` — integer parameters
- `set_override_cycles(override)` — semicolon-delimited cycle strings where
  commas are not valid syntax anyway
- Any integer, enum, or boolean parameter

`_validate_field` is intentionally applied only to free-text string fields
where user input is genuinely unpredictable (sample IDs, project names,
index sequences, custom column values).

**Do not flag unused-looking constants or helpers without checking all call
sites**, including private methods prefixed with `_`.

**Do not suggest adding `__all__` exports for internal helpers** (functions
or classes prefixed with `_`).

**Do not suggest docstring changes** unless the docstring is factually wrong.

---

## Code style expectations

- Line length: 88 (ruff default)
- Type annotations: required on all public methods
- Test naming: `test_<what>_<condition>_<expected>` pattern
- No `assert` in production code — raise `ValueError` with a descriptive message
- Method chaining: all configuration methods return `self`
