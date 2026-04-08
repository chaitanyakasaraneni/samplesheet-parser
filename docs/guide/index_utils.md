# Index Utilities

## normalize_index_lengths

Normalizes index sequence lengths across a list of sample dicts before merging sheets with mixed-length indexes.

```python
from samplesheet_parser import normalize_index_lengths

samples = sheet.samples()

# Trim all indexes to the shortest length
normalized = normalize_index_lengths(samples, strategy="trim")

# Pad shorter indexes to the longest length using "N" wildcards
normalized = normalize_index_lengths(samples, strategy="pad")
```

### Strategies

| Strategy | Behaviour |
|---|---|
| `"trim"` | Trims all indexes to the shortest sequence present |
| `"pad"` | Pads shorter indexes to the longest length using `"N"` wildcard characters |

!!! note "BCLConvert compatibility"
    `"N"` padding is supported by BCLConvert ≥ 3.9 and bcl2fastq ≥ 2.20.

### Dual-index normalization

Both I7 (`Index` / `index`) and I5 (`Index2` / `index2`) are normalized independently:

```python
normalized = normalize_index_lengths(samples, strategy="pad")
```

### Field name auto-detection

The utility auto-detects V1-style (`index` / `index2`) and V2-style (`Index` / `Index2`) field names. Use explicit overrides if your samples use custom field names:

```python
normalized = normalize_index_lengths(
    samples,
    strategy="trim",
    index1_key="custom_index",
    index2_key="custom_index2",
)
```

### Typical workflow before merging

```python
from samplesheet_parser import SampleSheetMerger, normalize_index_lengths
from samplesheet_parser.enums import SampleSheetVersion

# Normalize each sheet's samples before merging
merger = SampleSheetMerger(target_version=SampleSheetVersion.V2)
merger.add("ProjectA.csv").add("ProjectB.csv")
result = merger.merge("combined.csv")
```
