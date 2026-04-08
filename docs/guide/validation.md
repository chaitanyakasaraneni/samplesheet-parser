# Validation

## Basic usage

```python
from samplesheet_parser import SampleSheetFactory, SampleSheetValidator

sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
result = SampleSheetValidator().validate(sheet)

print(result.is_valid)     # True / False
print(result.summary())    # "PASS — 0 error(s), 0 warning(s)"

for err in result.errors:
    print(err)

for w in result.warnings:
    print(w)
```

## Validation checks

| Code | Level | Description |
|---|---|---|
| `EMPTY_SAMPLES` | error | No samples in Data section |
| `INVALID_INDEX_CHARS` | error | Index contains non-ACGTN characters |
| `INDEX_TOO_LONG` | error | Index longer than 24 bp |
| `DUPLICATE_INDEX` | error | Two samples share an index in the same lane |
| `DUPLICATE_SAMPLE_ID` | error | Same `Sample_ID` appears twice in one lane |
| `INDEX_TOO_SHORT` | warning | Index shorter than 6 bp |
| `INDEX_DISTANCE_TOO_LOW` | warning | Hamming distance between two indexes < threshold |
| `NO_ADAPTERS` | warning | No adapter sequences configured |
| `ADAPTER_MISMATCH` | warning | Adapter is non-standard |

## Hamming distance checking

Indexes that are too similar cause read bleed-through between samples during demultiplexing — a common cause of low-quality runs that is not caught by a simple duplicate check.

The validator computes the Hamming distance between every pair of indexes within each lane. For dual-index sheets, the I7 and I5 sequences are combined before comparison, so a pair that is close on I7 but well-separated on I5 is not incorrectly flagged.

```python
# Default threshold: 3
result = SampleSheetValidator().validate(sheet)

# Custom threshold — stricter for longer indexes
result = SampleSheetValidator().validate(sheet, min_hamming_distance=4)
```

## Structured results

```python
result.is_valid          # bool — False if any errors present
result.summary()         # str — one-line human-readable summary

for issue in result.errors:
    print(issue.code)      # e.g. "DUPLICATE_INDEX"
    print(issue.message)   # human-readable description
    print(issue.context)   # dict with relevant sample IDs, lane, etc.
```
