# Filtering

`SampleSheetFilter` extracts a subset of samples from a sheet by project, lane,
or sample ID.  Header, reads, and settings from the input sheet are preserved
in the output.

## Filter by project

```python
from samplesheet_parser import SampleSheetFilter

result = SampleSheetFilter("SampleSheet_combined.csv").filter(
    "ProjectA.csv",
    project="ProjectA",
)

print(result.summary())
# Kept 4 of 12 sample(s) → ProjectA.csv
```

## Filter by lane

```python
result = SampleSheetFilter("SampleSheet_combined.csv").filter(
    "lane1.csv",
    lane=1,       # int or str — both accepted
)
```

## Filter by sample ID

Exact match or glob pattern (case-sensitive on all platforms):

```python
# Exact match
result = SampleSheetFilter("combined.csv").filter("ctrl.csv", sample_id="CTRL_001")

# Glob pattern — keeps all samples whose ID starts with "CTRL_"
result = SampleSheetFilter("combined.csv").filter("ctrls.csv", sample_id="CTRL_*")

# Character range pattern
result = SampleSheetFilter("combined.csv").filter("out.csv", sample_id="SAMPLE_00[1-3]")
```

## Multiple criteria (ANDed)

All provided criteria must match — a sample is kept only if it satisfies
**every** criterion:

```python
# ProjectA samples on lane 1 only
result = SampleSheetFilter("combined.csv").filter(
    "out.csv",
    project="ProjectA",
    lane=1,
)

# Controls on lane 2
result = SampleSheetFilter("combined.csv").filter(
    "out.csv",
    lane=2,
    sample_id="CTRL_*",
)
```

## No matches

When no samples match, no file is written and `output_path` is `None`:

```python
result = SampleSheetFilter("combined.csv").filter("out.csv", project="NonExistent")

if result.matched_count == 0:
    print("No samples matched — output not written.")

print(result.output_path)   # None
```

## Target version override

Filter a V2 sheet and write V1 output:

```python
from samplesheet_parser import SampleSheetFilter
from samplesheet_parser.enums import SampleSheetVersion

result = SampleSheetFilter(
    "combined_v2.csv",
    target_version=SampleSheetVersion.V1,
).filter("projectA_v1.csv", project="ProjectA")
```

## Inspecting FilterResult

```python
result.matched_count    # int       — samples that passed all criteria
result.total_count      # int       — total samples in the input sheet
result.output_path      # Path | None — None when no samples matched
result.source_version   # str       — "V1" or "V2"
result.summary()        # str       — one-line human-readable summary
```
