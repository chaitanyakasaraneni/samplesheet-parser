# Merging

`SampleSheetMerger` combines multiple per-project sample sheets into one sheet for a flow cell run, detecting conflicts before writing.

## Basic usage

```python
from samplesheet_parser import SampleSheetMerger
from samplesheet_parser.enums import SampleSheetVersion

result = (
    SampleSheetMerger(target_version=SampleSheetVersion.V2)
    .add("ProjectA.csv")
    .add("ProjectB.csv")
    .add("ProjectC.csv")
    .merge("SampleSheet_combined.csv")
)

print(result.summary())
# Merged 3 sheet(s) → SampleSheet_combined.csv (12 samples) — 0 conflict(s), 0 warning(s)
```

## Conflict detection

The merger checks for:

| Code | Level | Description |
|---|---|---|
| `PARSE_ERROR` | conflict | An input sheet could not be parsed |
| `INDEX_COLLISION` | conflict | The same index appears in the same lane across two sheets |
| `READ_LENGTH_CONFLICT` | conflict | Sheets specify different read lengths or cycle counts |
| `MERGE_VALIDATION_ERROR` | conflict | Post-merge validation of the combined sheet failed |
| `MIXED_FORMAT` | warning | Input sheets are a mix of V1 and V2 formats |
| `INDEX_DISTANCE_TOO_LOW` | warning | Cross-sheet index pair has Hamming distance below threshold |
| `ADAPTER_CONFLICT` | warning | Adapter sequences differ between sheets |
| `INCOMPLETE_SAMPLE_RECORD` | warning | A sample row is missing `Sample_ID` or index |

## Handling conflicts

By default, `merge()` aborts (does not write output) if any conflicts are found:

```python
result = merger.merge("combined.csv")

if result.has_conflicts:
    for c in result.conflicts:
        print(c)
    # [CONFLICT] INDEX_COLLISION: Index 'ATTACTCG+TATAGCCT' in lane 1
    #   appears in both ProjectA.csv and ProjectB.csv
```

Pass `abort_on_conflicts=False` to write output even when conflicts exist:

```python
result = merger.merge("combined.csv", abort_on_conflicts=False)
```

## Mixed V1/V2 inputs

Mixed-format inputs are automatically converted to the target version:

```python
# ProjectA is V1, ProjectB is V2 — both converted to V2 for output
merger = SampleSheetMerger(target_version=SampleSheetVersion.V2)
merger.add("ProjectA_v1.csv").add("ProjectB_v2.csv")
result = merger.merge("combined_v2.csv")
```

A `MIXED_FORMAT` warning is emitted when this happens.

## Custom Hamming threshold

```python
merger = SampleSheetMerger(target_version=SampleSheetVersion.V2, min_hamming_distance=4)
```

## Inspecting MergeResult

```python
result.has_conflicts        # bool
result.sample_count         # int — samples in merged output
result.output_path          # Path | None — None if write was aborted
result.source_versions      # dict[str, str] — per-file detected version
result.conflicts            # list[MergeConflict]
result.warnings             # list[MergeConflict]
result.summary()            # str — one-line human-readable summary
```
