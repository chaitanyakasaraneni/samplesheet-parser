# Quickstart

## Auto-detect format (recommended)

The simplest entry point. `SampleSheetFactory` detects V1 vs V2 automatically using a three-step strategy and returns the correct parser.

```python
from samplesheet_parser import SampleSheetFactory

factory = SampleSheetFactory()
sheet = factory.create_parser("SampleSheet.csv", parse=True)

print(factory.version)      # SampleSheetVersion.V1 or .V2
print(sheet.index_type())   # "dual", "single", or "none"

for sample in sheet.samples():
    print(sample["sample_id"], sample["index"])
```

## Validate a sheet

```python
from samplesheet_parser import SampleSheetFactory, SampleSheetValidator

sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
result = SampleSheetValidator().validate(sheet)

print(result.summary())
# PASS — 0 error(s), 2 warning(s)

for w in result.warnings:
    print(w)

for err in result.errors:
    print(err)
```

## Convert between formats

```python
from samplesheet_parser import SampleSheetConverter

# V1 → V2
SampleSheetConverter("SampleSheet_v1.csv").to_v2("SampleSheet_v2.csv")

# V2 → V1  (lossy — V2-only fields are dropped with a warning)
SampleSheetConverter("SampleSheet_v2.csv").to_v1("SampleSheet_v1.csv")
```

## CLI

```bash
# Install the CLI extra
pip install "samplesheet-parser[cli]"

# Validate
samplesheet validate SampleSheet.csv

# Convert
samplesheet convert SampleSheet_v1.csv --to v2 --output SampleSheet_v2.csv

# Diff
samplesheet diff old/SampleSheet.csv new/SampleSheet.csv

# Merge
samplesheet merge ProjectA.csv ProjectB.csv --output combined.csv
```

See the full [CLI Reference](../cli.md) for all options.
