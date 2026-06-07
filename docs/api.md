# API Reference

All public classes are importable directly from the top-level package:

```python
from samplesheet_parser import (
    SampleSheetFactory,
    SampleSheetParser,
    SampleSheetV1,
    SampleSheetV2,
    SampleSheetConverter,
    SampleSheetValidator,
    SampleSheetDiff,
    SampleSheetWriter,
    SampleSheetMerger,
    SampleSheetSplitter,
    SampleSheetFilter,
    normalize_index_lengths,
    hamming_distance,
)
```

---

## SampleSheetFactory

| Method / attribute | Returns | Description |
|---|---|---|
| `create_parser(path, *, clean, experiment_id, parse)` | `SampleSheetParser` | Auto-detect format and return the appropriate parser |
| `get_umi_length()` | `int` | UMI length from the current parser |
| `register(detector, parser_class, version)` | `None` | Register a custom format detector; tried before built-in detection in LIFO order |
| `clear_registry()` | `None` | Remove all custom registrations (useful in tests) |
| `.version` | `SampleSheetVersion \| None` | Detected format version |

---

## SampleSheetParser Protocol

`SampleSheetParser` is a `runtime_checkable` structural protocol satisfied by both `SampleSheetV1` and `SampleSheetV2`. Use it as a type hint wherever either parser is accepted, or implement it in a third-party parser and register it with the factory.

```python
from samplesheet_parser import SampleSheetParser

isinstance(sheet, SampleSheetParser)   # True for V1 and V2 instances
```

---

## SampleSheetV1 / SampleSheetV2 (shared interface)

Both parsers satisfy `SampleSheetParser` and expose:

| Method / attribute | Returns | Description |
|---|---|---|
| `parse(do_clean=True)` | `None` | Parse all sections |
| `clean()` | `str` | Return cleaned content as a string — source file is **never** modified |
| `samples()` | `list[dict]` | One record per unique `(sample_id, lane)` pair |
| `index_type()` | `str` | `"dual"`, `"single"`, or `"none"` |
| `parse_custom_section(name, *, required=False)` | `dict[str, str]` | Parse any non-standard section as key/value pairs |
| `.adapters` | `list[str]` | Adapter sequences |
| `.experiment_name` | `str \| None` | Run/experiment name |

### V2-only

| Method | Returns | Description |
|---|---|---|
| `get_umi_length()` | `int` | UMI length from `OverrideCycles` |
| `get_read_structure()` | `ReadStructure` | Parsed read structure dataclass |

---

## SampleSheetConverter

```python
SampleSheetConverter(path, *, workflow: Workflow | str | None = None)
```

| Method / attribute | Returns | Description |
|---|---|---|
| `to_v2(output_path)` | `Path` | Convert IEM V1 → BCLConvert V2 |
| `to_v1(output_path)` | `Path` | Convert BCLConvert V2 → IEM V1 (lossy) |
| `.source_version` | `SampleSheetVersion \| None` | Auto-detected format of the input |
| `.workflow_override` | `Workflow \| None` | Resolved workflow override, if any |

The `workflow` parameter accepts `"a"`, `"b"`, or a `Workflow` enum value
and overrides auto-detection of the i5 orientation workflow from the
instrument header. See
[Conversion → Index 2 orientation](guide/conversion.md#index-2-i5-orientation).

---

## samplesheet_parser.instruments

i5 orientation workflow classification helpers.

```python
from samplesheet_parser.instruments import (
    Workflow,
    detect_workflow,
    parse_workflow,
    reverse_complement,
    WORKFLOW_A_INSTRUMENTS,
    WORKFLOW_B_INSTRUMENTS,
    AMBIGUOUS_INSTRUMENTS,
)
```

| Name | Kind | Description |
|---|---|---|
| `Workflow` | `str, Enum` | `Workflow.A` (i5 forward) / `Workflow.B` (i5 RC'd on chip) |
| `detect_workflow(name)` | `Workflow \| None` | Classify an instrument name; `None` for unknown or ambiguous (e.g. `NovaSeq 6000`) |
| `parse_workflow(value)` | `Workflow \| None` | Coerce a CLI string (`"a"` / `"b"`) to `Workflow` |
| `reverse_complement(seq)` | `str` | Reverse-complement a DNA sequence (preserves `N`, case-preserving) |
| `WORKFLOW_A_INSTRUMENTS` | `frozenset[str]` | Normalised names of workflow-A instruments |
| `WORKFLOW_B_INSTRUMENTS` | `frozenset[str]` | Normalised names of workflow-B instruments |
| `AMBIGUOUS_INSTRUMENTS` | `frozenset[str]` | Instruments whose workflow depends on chemistry and require an explicit override |

---

## SampleSheetValidator

| Method | Returns | Description |
|---|---|---|
| `validate(sheet, *, min_hamming_distance=3)` | `ValidationResult` | Run all checks; returns structured result |

### ValidationResult

| Attribute / method | Type | Description |
|---|---|---|
| `is_valid` | `bool` | `False` if any errors present |
| `errors` | `list[ValidationIssue]` | Structured error records |
| `warnings` | `list[ValidationIssue]` | Structured warning records |
| `summary()` | `str` | One-line human-readable summary |

### ValidationIssue

| Attribute | Type | Description |
|---|---|---|
| `code` | `str` | e.g. `"DUPLICATE_INDEX"` |
| `message` | `str` | Human-readable description |
| `context` | `dict` | Relevant sample IDs, lane, etc. |

---

## SampleSheetDiff

| Method | Returns | Description |
|---|---|---|
| `compare()` | `DiffResult` | Full comparison across header, reads, settings, and samples |

### DiffResult

| Attribute / method | Type | Description |
|---|---|---|
| `has_changes` | `bool` | `True` if any difference detected |
| `summary()` | `str` | Human-readable one-paragraph summary |
| `header_changes` | `list[HeaderChange]` | Header, reads, and settings diffs |
| `samples_added` | `list[dict]` | Records present in new sheet only |
| `samples_removed` | `list[dict]` | Records present in old sheet only |
| `sample_changes` | `list[SampleChange]` | Per-sample field-level diffs |
| `source_version` | `SampleSheetVersion` | Format of the old sheet |
| `target_version` | `SampleSheetVersion` | Format of the new sheet |

---

## SampleSheetWriter

| Method / attribute | Returns | Description |
|---|---|---|
| `SampleSheetWriter(version=)` | — | Instantiate for `SampleSheetVersion.V1` or `.V2` |
| `from_sheet(sheet, version=)` | `SampleSheetWriter` | Load a parsed sheet for editing; optionally change format |
| `set_header(*, run_name, platform, ...)` | `self` | Set header fields (fluent) |
| `set_reads(*, read1, read2, index1, index2)` | `self` | Set read cycle counts (fluent) |
| `set_adapter(adapter_read1, adapter_read2)` | `self` | Set adapter sequences (fluent) |
| `set_override_cycles(override)` | `self` | Set `OverrideCycles` — V2 only (fluent) |
| `set_software_version(version)` | `self` | Set `SoftwareVersion` — V2 only (fluent) |
| `set_setting(key, value)` | `self` | Set an arbitrary settings key/value (fluent) |
| `add_sample(sample_id, *, index, ...)` | `self` | Append a sample row (fluent) |
| `remove_sample(sample_id, *, lane=)` | `self` | Remove sample(s) by ID, optionally scoped to a lane (fluent) |
| `update_sample(sample_id, *, lane=, **fields)` | `self` | Update fields on an existing sample in-place (fluent) |
| `clear_samples()` | `self` | Remove all samples while preserving header/reads/settings (fluent) |
| `write(path, *, validate=True)` | `Path` | Serialise to disk; validates first by default |
| `to_string()` | `str` | Serialise to string without writing to disk |
| `.sample_count` | `int` | Number of samples currently in the writer |
| `.sample_ids` | `list[str]` | Sample IDs currently in the writer |

---

## SampleSheetMerger

| Method / attribute | Returns | Description |
|---|---|---|
| `SampleSheetMerger(target_version=, min_hamming_distance=3)` | — | Instantiate with target format and optional Hamming threshold |
| `add(path)` | `self` | Register an input sheet path (fluent) |
| `merge(output_path, *, validate=True, abort_on_conflicts=True)` | `MergeResult` | Run the merge and write output |

### MergeResult

| Attribute / method | Type | Description |
|---|---|---|
| `has_conflicts` | `bool` | `True` if any conflict recorded |
| `sample_count` | `int` | Samples in the merged output |
| `output_path` | `Path \| None` | Path written; `None` if write was aborted |
| `source_versions` | `dict[str, str]` | Per-input-file detected version |
| `conflicts` | `list[MergeConflict]` | Structured conflict records |
| `warnings` | `list[MergeConflict]` | Structured warning records |
| `summary()` | `str` | One-line human-readable summary |

---

## SampleSheetSplitter

| Method / attribute | Returns | Description |
|---|---|---|
| `SampleSheetSplitter(path, *, by="project", target_version=None, unassigned_label="unassigned")` | — | Instantiate with input path and grouping strategy |
| `split(output_dir, *, prefix="", suffix="_SampleSheet.csv", validate=True)` | `SplitResult` | Parse input and write one file per group |

### SplitResult

| Attribute / method | Type | Description |
|---|---|---|
| `output_files` | `dict[str, Path]` | Group key → path of the written file |
| `sample_counts` | `dict[str, int]` | Group key → number of samples written |
| `warnings` | `list[str]` | Non-fatal issues (incomplete records, unassigned samples) |
| `source_version` | `str` | `"V1"` or `"V2"` |
| `summary()` | `str` | One-line human-readable summary |

---

## SampleSheetFilter

| Method / attribute | Returns | Description |
|---|---|---|
| `SampleSheetFilter(path, *, target_version=None)` | — | Instantiate with input path |
| `filter(output_path, *, project=None, lane=None, sample_id=None, validate=True)` | `FilterResult` | Write filtered copy to `output_path`; at least one criterion required |

`sample_id` supports glob patterns (e.g. `"CTRL_*"`) via `fnmatch.fnmatchcase` — matching is always case-sensitive.

### FilterResult

| Attribute / method | Type | Description |
|---|---|---|
| `matched_count` | `int` | Samples that passed all filter criteria |
| `total_count` | `int` | Total samples in the input sheet |
| `output_path` | `Path \| None` | Path written; `None` when no samples matched |
| `source_version` | `str` | `"V1"` or `"V2"` |
| `summary()` | `str` | One-line human-readable summary |

---

## normalize_index_lengths

```python
normalize_index_lengths(
    samples: list[dict],
    strategy: str,                  # "trim" or "pad"
    index1_key: str | None = None,  # auto-detected if None
    index2_key: str | None = None,  # auto-detected if None
) -> list[dict]
```

Normalizes index sequence lengths across a list of sample dicts. See [Index Utilities](guide/index_utils.md) for details.

---

## hamming_distance

```python
from samplesheet_parser import hamming_distance
```

Computes the Hamming distance between two equal-length index sequences, counting `N` wildcards as matches:

```python
hamming_distance("ATTACTCG", "ATTACTCG")   # 0
hamming_distance("ATTACTCG", "ATTACTCC")   # 1
hamming_distance("ATTNCNCG", "ATTACTCG")   # 0  — N matches anything
```

Used internally by `SampleSheetValidator` when checking index collision thresholds. Accepts sequences of different lengths (returns `None`) but in practice all samples in a valid sheet have uniform index lengths after normalization.

---

## Enums

```python
from samplesheet_parser.enums import SampleSheetVersion, InstrumentPlatform, UMILocation

SampleSheetVersion.V1   # IEM / bcl2fastq
SampleSheetVersion.V2   # BCLConvert
```
