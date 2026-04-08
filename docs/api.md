# API Reference

All public classes are importable directly from the top-level package:

```python
from samplesheet_parser import (
    SampleSheetFactory,
    SampleSheetV1,
    SampleSheetV2,
    SampleSheetConverter,
    SampleSheetValidator,
    SampleSheetDiff,
    SampleSheetWriter,
    SampleSheetMerger,
    normalize_index_lengths,
)
```

---

## SampleSheetFactory

| Method / attribute | Returns | Description |
|---|---|---|
| `create_parser(path, *, clean, experiment_id, parse)` | `SampleSheetV1 \| SampleSheetV2` | Auto-detect format and return the appropriate parser |
| `get_umi_length()` | `int` | UMI length from the current parser |
| `.version` | `SampleSheetVersion \| None` | Detected format version |

---

## SampleSheetV1 / SampleSheetV2 (shared interface)

| Method / attribute | Returns | Description |
|---|---|---|
| `parse(do_clean=True)` | `None` | Parse all sections |
| `samples()` | `list[dict]` | One record per unique sample |
| `index_type()` | `str` | `"dual"`, `"single"`, or `"none"` |
| `.adapters` | `list[str]` | Adapter sequences |
| `.experiment_name` | `str \| None` | Run/experiment name |

### V2-only

| Method | Returns | Description |
|---|---|---|
| `get_umi_length()` | `int` | UMI length from `OverrideCycles` |
| `get_read_structure()` | `ReadStructure` | Parsed read structure dataclass |

---

## SampleSheetConverter

| Method | Returns | Description |
|---|---|---|
| `to_v2(output_path)` | `Path` | Convert IEM V1 → BCLConvert V2 |
| `to_v1(output_path)` | `Path` | Convert BCLConvert V2 → IEM V1 (lossy) |
| `.source_version` | `SampleSheetVersion \| None` | Auto-detected format of the input |

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

## Enums

```python
from samplesheet_parser.enums import SampleSheetVersion, InstrumentPlatform, UMILocation

SampleSheetVersion.V1   # IEM / bcl2fastq
SampleSheetVersion.V2   # BCLConvert
```
