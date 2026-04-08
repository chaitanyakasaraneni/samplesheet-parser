# Diffing

`SampleSheetDiff` compares two sheets — any combination of V1 and V2 — and returns a structured `DiffResult`.

## Basic usage

```python
from samplesheet_parser import SampleSheetDiff

result = SampleSheetDiff("old/SampleSheet.csv", "new/SampleSheet.csv").compare()

print(result.summary())
# Diff (V1 → V2):
#   2 header/settings change(s)
#   1 sample(s) added: SAMPLE_009
#   1 sample(s) with field changes

print(result.has_changes)   # True
```

## What is compared

| Dimension | What is compared |
|---|---|
| Header | Key/value changes in `[Header]` / `[BCLConvert_Settings]` |
| Reads | Read length or cycle count changes |
| Samples added / removed | Keyed on `Sample_ID` + `Lane` |
| Sample field changes | Per-sample field-level diffs (index, project, etc.) |

## Inspecting results

```python
# Header / settings changes
for change in result.header_changes:
    print(f"{change.field}: {change.old_value!r} → {change.new_value!r}")

# Added / removed samples
for s in result.samples_added:
    print(f"Added: {s.get('Sample_ID') or s.get('sample_id')}")

for s in result.samples_removed:
    print(f"Removed: {s.get('Sample_ID') or s.get('sample_id')}")

# Per-sample field changes
for sc in result.sample_changes:
    print(f"{sc.sample_id} (lane {sc.lane}):")
    for field, (old, new) in sc.changes.items():
        print(f"  {field}: {old!r} → {new!r}")
```

## Cross-format diff

V1-only metadata columns (`I7_Index_ID`, `I5_Index_ID`, `Sample_Name`, `Description`) are suppressed when comparing V1 against V2 so that format differences do not generate noise.

```python
# V1 vs its own V2 conversion — should show zero meaningful changes
result = SampleSheetDiff("SampleSheet_v1.csv", "SampleSheet_v2.csv").compare()
print(result.has_changes)   # False (or only adapter field name differences)
```
