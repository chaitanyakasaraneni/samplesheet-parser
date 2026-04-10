# Examples

Runnable demo scripts for every feature live in the `examples/` directory of
the repository.  Run any of them from the repo root:

```bash
python3 examples/demo_splitter.py
python3 examples/demo_filter.py
# etc.
```

The snippets below show the key scenarios from each script.

---

## Parsing

```python
from samplesheet_parser import SampleSheetFactory

factory = SampleSheetFactory()
sheet = factory.create_parser("SampleSheet.csv", parse=True)

print(factory.version)       # SampleSheetVersion.V1 or .V2
print(sheet.index_type())    # "dual", "single", or "none"
print(sheet.experiment_name)

for sample in sheet.samples():
    print(sample["sample_id"], sample["index"])
```

---

## Validation

```python
from samplesheet_parser import SampleSheetFactory, SampleSheetValidator

sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
result = SampleSheetValidator().validate(sheet)

print(result.summary())
# PASS — 0 error(s), 2 warning(s)

for w in result.warnings:
    print(f"[{w.code}] {w.message}")

for err in result.errors:
    print(f"[{err.code}] {err.message}")

# Custom Hamming distance threshold
result = SampleSheetValidator().validate(sheet, min_hamming_distance=4)
```

---

## Conversion

```python
from samplesheet_parser import SampleSheetConverter

# V1 → V2
converter = SampleSheetConverter("SampleSheet_v1.csv")
out = converter.to_v2("SampleSheet_v2.csv")
print(f"Converted {converter.source_version.value} → {out.name}")

# V2 → V1  (lossy — V2-only fields are dropped with a warning)
converter = SampleSheetConverter("SampleSheet_v2.csv")
converter.to_v1("SampleSheet_v1.csv")

# Roundtrip — V1 → V2 → V1
from samplesheet_parser import SampleSheetFactory

SampleSheetConverter("original_v1.csv").to_v2("tmp_v2.csv")
SampleSheetConverter("tmp_v2.csv").to_v1("roundtrip_v1.csv")

orig = {s["sample_id"] for s in SampleSheetFactory().create_parser("original_v1.csv", parse=True).samples()}
rt   = {s["sample_id"] for s in SampleSheetFactory().create_parser("roundtrip_v1.csv", parse=True).samples()}
print(f"Samples preserved: {orig == rt}")
```

!!! warning "V2 → V1 is lossy"
    `OverrideCycles`, `InstrumentPlatform`, and other V2-only fields are
    dropped with a warning.

---

## Diffing

```python
from samplesheet_parser import SampleSheetDiff

result = SampleSheetDiff("old/SampleSheet.csv", "new/SampleSheet.csv").compare()

print(result.has_changes)   # True if any difference found
print(result.summary())

# Header / settings changes
for c in result.header_changes:
    print(f"{c.field}: {c.old_value!r} → {c.new_value!r}")

# Samples added or removed
print("Added  :", result.samples_added)
print("Removed:", result.samples_removed)

# Per-sample field changes
for sc in result.sample_changes:
    for field, (old_val, new_val) in sc.changes.items():
        print(f"{sc.sample_id} — {field}: {old_val!r} → {new_val!r}")
```

Cross-format diff (V1 vs its V2 conversion) works the same way — V1-only
metadata columns are suppressed to avoid format-noise:

```python
result = SampleSheetDiff("SampleSheet_v1.csv", "SampleSheet_v2.csv").compare()
```

---

## Writing & editing

### Build a V2 sheet from scratch

```python
from samplesheet_parser import SampleSheetWriter
from samplesheet_parser.enums import SampleSheetVersion

writer = SampleSheetWriter(version=SampleSheetVersion.V2)
writer.set_header(run_name="240115_LH00336_0025_A227HGJLT3",
                  instrument_platform="NovaSeqXSeries")
writer.set_reads(read1=151, read2=151, index1=10, index2=10)
writer.set_override_cycles("Y151;I10;I10;Y151")
writer.set_adapter("CTGTCTCTTATACACATCT")
writer.add_sample("SampleA", index="ATTACTCGAT", index2="TATAGCCTGT",
                  lane="1", project="ProjectAlpha")
writer.add_sample("SampleB", index="TCCGGAGACC", index2="ATAGAGGCAC",
                  lane="1", project="ProjectAlpha")
writer.write("SampleSheet.csv")
print(f"Written {writer.sample_count} samples")
```

### Build a V1 sheet from scratch

```python
writer = SampleSheetWriter(version=SampleSheetVersion.V1)
writer.set_header(run_name="Run_001", workflow="GenerateFASTQ")
writer.set_reads(read1=151, read2=151)
writer.set_adapter("AGATCGGAAGAGCACACGTCTGAACTCCAGTCA")
writer.add_sample("SampleA", index="CAAGACAGAT", index2="ACTATAGCCT",
                  lane="1", project="ProjectX")
writer.write("SampleSheet_v1.csv")
```

### Edit an existing sheet

```python
from samplesheet_parser import SampleSheetFactory, SampleSheetWriter

sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
writer = SampleSheetWriter.from_sheet(sheet)

# Fix a mistyped index
writer.update_sample("Sample2", index="AACCGTGATC")

# Remove a sample that failed QC
writer.remove_sample("Sample7")

print(f"{writer.sample_count} samples remaining: {writer.sample_ids}")
writer.write("SampleSheet_updated.csv")
```

### Copy header/settings, replace all samples

```python
writer = SampleSheetWriter.from_sheet(sheet)
writer.clear_samples()          # keep header/reads/settings, drop sample rows
writer.add_sample("NewSample", index="GCTTGTTTCC", index2="CGTTAGAGTT",
                  lane="1", project="ProjectA")
writer.write("SampleSheet_repopulated.csv")
```

---

## Merging

```python
from samplesheet_parser import SampleSheetMerger
from samplesheet_parser.enums import SampleSheetVersion

# Clean merge — two V1 sheets → combined V2
result = (
    SampleSheetMerger(target_version=SampleSheetVersion.V2)
    .add("ProjectA.csv")
    .add("ProjectB.csv")
    .merge("combined.csv")
)
print(result.summary())
# Merged 2 sheet(s) → combined.csv (8 samples) — 0 conflict(s), 0 warning(s)
```

### Handling index collisions

```python
result = merger.merge("combined.csv")   # aborts by default on conflict

if result.has_conflicts:
    for c in result.conflicts:
        print(f"[{c.code}] {c.message}")

# Force write despite conflicts (equivalent to --force on the CLI)
result = merger.merge("combined.csv", abort_on_conflicts=False)
```

### Mixed V1/V2 inputs

```python
# All inputs auto-converted to V2; a MIXED_FORMAT warning is emitted
merger = SampleSheetMerger(target_version=SampleSheetVersion.V2)
merger.add("ProjectA_v1.csv").add("ProjectB_v2.csv")
result = merger.merge("combined_v2.csv")

for w in result.warnings:
    print(f"[{w.code}] {w.message}")
```

---

## Splitting

`SampleSheetSplitter` is the inverse of `SampleSheetMerger` — it divides a
combined sheet back into per-project or per-lane files.

### Split by project

```python
from samplesheet_parser import SampleSheetSplitter

result = SampleSheetSplitter("combined.csv").split("./per_project/")

print(result.summary())
# Split into 3 file(s), 12 sample(s) total, 0 warning(s)

for project, path in result.output_files.items():
    print(f"{project}: {path.name} ({result.sample_counts[project]} samples)")
# ProjectA: ProjectA_SampleSheet.csv (4 samples)
# ProjectB: ProjectB_SampleSheet.csv (6 samples)
# ProjectC: ProjectC_SampleSheet.csv (2 samples)
```

### Split by lane

```python
result = SampleSheetSplitter("combined.csv", by="lane").split("./per_lane/")
```

### Split to V1 output

```python
from samplesheet_parser.enums import SampleSheetVersion

result = SampleSheetSplitter(
    "combined_v2.csv",
    by="project",
    target_version=SampleSheetVersion.V1,
).split("./v1_output/", prefix="Run001_")
# → Run001_ProjectA_SampleSheet.csv, Run001_ProjectB_SampleSheet.csv, …
```

### Unassigned samples

```python
result = SampleSheetSplitter("combined.csv").split("./out/")

for w in result.warnings:
    print(w)
# 2 sample(s) have no project and will be written to 'unassigned_SampleSheet.csv'.
```

---

## Filtering

`SampleSheetFilter` extracts a subset of samples while preserving the header,
reads, and settings from the input sheet.

### Filter by project

```python
from samplesheet_parser import SampleSheetFilter

result = SampleSheetFilter("combined.csv").filter("ProjectA.csv", project="ProjectA")
print(result.summary())
# Kept 4 of 12 sample(s) → ProjectA.csv
```

### Filter by lane

```python
result = SampleSheetFilter("combined.csv").filter("lane1.csv", lane=1)
```

### Filter by sample ID — glob patterns

```python
# Exact match
result = SampleSheetFilter("combined.csv").filter("ctrl.csv", sample_id="CTRL_001")

# Glob: all IDs starting with "CTRL_"
result = SampleSheetFilter("combined.csv").filter("ctrls.csv", sample_id="CTRL_*")

# Glob: character range
result = SampleSheetFilter("combined.csv").filter("out.csv", sample_id="SAMPLE_00[1-3]")
```

### Multiple criteria (ANDed)

```python
# ProjectA samples on lane 1 only
result = SampleSheetFilter("combined.csv").filter(
    "out.csv",
    project="ProjectA",
    lane=1,
)
print(f"Matched {result.matched_count} of {result.total_count}")
```

### No-match behaviour

```python
result = SampleSheetFilter("combined.csv").filter("out.csv", project="Ghost")
print(result.matched_count)   # 0
print(result.output_path)     # None — file not written
```

---

## Index utilities

```python
from samplesheet_parser import normalize_index_lengths

samples = [
    {"sample_id": "SampleA", "index": "CAAGACAGAT"},   # 10 bp
    {"sample_id": "SampleB", "index": "TGAACCTG"},     #  8 bp
    {"sample_id": "SampleC", "index": "GCACAACG"},     #  8 bp
]

# Trim all to the shortest length (8 bp)
trimmed = normalize_index_lengths(samples, strategy="trim")

# Pad all to the longest length (10 bp) using 'N' wildcards
padded = normalize_index_lengths(samples, strategy="pad")
```

Dual-index sheets — both I7 and I5 lengths are normalized independently:

```python
dual = [
    {"sample_id": "SampleA", "index": "CAAGACAGAT", "index2": "ACTATAGCCT"},
    {"sample_id": "SampleB", "index": "TGAACCTG",   "index2": "TGATACG"},
]
normalized = normalize_index_lengths(dual, strategy="trim")
# I7 → 8 bp, I5 → 7 bp
```
