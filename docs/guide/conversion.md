# Conversion

## V1 → V2

```python
from samplesheet_parser import SampleSheetConverter

converter = SampleSheetConverter("SampleSheet_v1.csv")
out = converter.to_v2("SampleSheet_v2.csv")

print(out)                          # Path("SampleSheet_v2.csv")
print(converter.source_version)     # SampleSheetVersion.V1
```

The converter maps IEM V1 fields to BCLConvert V2 equivalents:

| V1 field | V2 field |
|---|---|
| `IEMFileVersion` | `FileFormatVersion: 2` |
| `[Data]` section | `[BCLConvert_Data]` section |
| `Sample_ID` | `Sample_ID` |
| `index` | `Index` |
| `index2` | `Index2` |
| `[Reads]` lengths | `Read1Cycles` / `Read2Cycles` in `[Reads]` |
| `Adapter` in `[Settings]` | `AdapterRead1` in `[BCLConvert_Settings]` |

## V2 → V1 (lossy)

```python
converter = SampleSheetConverter("SampleSheet_v2.csv")
out = converter.to_v1("SampleSheet_v1.csv")
```

!!! warning "Lossy conversion"
    V2-only fields are dropped during V2 → V1 conversion:

    - `OverrideCycles`
    - `InstrumentPlatform`
    - `FileFormatVersion`
    - `[BCLConvert_Settings]` keys with no V1 equivalent

    A warning is logged for each dropped field.

## Round-trip

```python
converter = SampleSheetConverter("SampleSheet_v1.csv")
converter.to_v2("temp_v2.csv")

converter2 = SampleSheetConverter("temp_v2.csv")
converter2.to_v1("roundtrip_v1.csv")
```

Sample IDs survive a V1 → V2 → V1 round-trip. V2-only fields do not survive a V2 → V1 → V2 round-trip.
