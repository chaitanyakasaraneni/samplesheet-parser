# Splitting

`SampleSheetSplitter` splits a combined sheet into one file per project or per
lane — the inverse of [`SampleSheetMerger`](merging.md).  Header, reads, and
settings are copied into every output file; only the sample rows are divided.

## Basic usage — split by project

```python
from samplesheet_parser import SampleSheetSplitter

result = SampleSheetSplitter("SampleSheet_combined.csv").split("./per_project/")

print(result.summary())
# Split into 3 file(s), 12 sample(s) total, 0 warning(s)

for project, path in result.output_files.items():
    count = result.sample_counts[project]
    print(f"{project}: {path} ({count} sample(s))")
# ProjectA: per_project/ProjectA_SampleSheet.csv (4 sample(s))
# ProjectB: per_project/ProjectB_SampleSheet.csv (6 sample(s))
# ProjectC: per_project/ProjectC_SampleSheet.csv (2 sample(s))
```

## Split by lane

```python
result = SampleSheetSplitter("SampleSheet_combined.csv", by="lane").split("./per_lane/")
```

## Output filename format

By default filenames are `{group}_SampleSheet.csv`.  Use `prefix` and `suffix`
to customise:

```python
result = splitter.split(
    "./out/",
    prefix="Run001_",           # → Run001_ProjectA_SampleSheet.csv
    suffix=".csv",              # → Run001_ProjectA.csv
)
```

## Target version override

Split a V2 combined sheet into V1 per-project files (e.g. for bcl2fastq):

```python
from samplesheet_parser import SampleSheetSplitter
from samplesheet_parser.enums import SampleSheetVersion

splitter = SampleSheetSplitter(
    "combined_v2.csv",
    by="project",
    target_version=SampleSheetVersion.V1,
)
result = splitter.split("./v1_output/")
```

## Unassigned samples

Samples that have no `Sample_Project` (when splitting by project) or no lane
(when splitting by lane) are grouped under a configurable label and trigger a
warning:

```python
splitter = SampleSheetSplitter("combined.csv", unassigned_label="misc")
result = splitter.split("./out/")

if result.warnings:
    for w in result.warnings:
        print(w)
# 2 sample(s) have no project and will be written to 'misc_SampleSheet.csv'.
```

!!! note
    The `unassigned_label` check tracks records that are **genuinely missing**
    a project/lane field.  Samples whose project happens to share the same
    string as `unassigned_label` are not affected.

## Incomplete records

Rows missing `Sample_ID` or `Index` are skipped with a warning and never
written to any output file:

```python
result = SampleSheetSplitter("combined.csv").split("./out/")

for w in result.warnings:
    print(w)
# Skipping incomplete record in group 'ProjectA': missing ['Sample_ID'].
```

## Inspecting SplitResult

```python
result.output_files     # dict[str, Path] — group key → output file path
result.sample_counts    # dict[str, int]  — group key → sample count
result.warnings         # list[str]       — non-fatal issues
result.source_version   # str             — "V1" or "V2"
result.summary()        # str             — one-line human-readable summary
```
