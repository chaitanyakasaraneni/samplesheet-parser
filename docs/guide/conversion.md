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

## Index 2 (i5) orientation

`bcl2fastq` and `BCLConvert` disagree on the orientation of `Index2`
(i5) for some instruments. Conversion handles this automatically when
the source sheet declares an instrument; for ambiguous cases pass
`workflow=` (Python) or `--workflow` (CLI).

### Workflow split

| Workflow | i5 on the chip | Instruments |
|---|---|---|
| **A** (i5 forward) | as written | MiSeq, HiSeq 2000, HiSeq 2500, NovaSeq 6000 (v1.0 chemistry) |
| **B** (i5 RC'd on chip) | reverse-complemented | NovaSeq X / X Plus, NextSeq 500/550/1000/2000, iSeq 100, MiniSeq, HiSeq 3000/4000, NovaSeq 6000 (v1.5 chemistry) |

- **Workflow A** — both demultiplexers expect i5 in the forward
  orientation, so V1 ↔ V2 conversion leaves `Index2` unchanged.
- **Workflow B** — `bcl2fastq` (V1) records i5 reverse-complemented as
  it was read; `BCLConvert` (V2) always expects the forward orientation.
  The converter reverse-complements `Index2` in both directions so the
  output is correct for the target demultiplexer.

### Auto-detection

The workflow is auto-detected from:

- V1 `[Header]` → `Instrument Type` (e.g. `NovaSeq X Plus`)
- V2 `[Header]` → `InstrumentPlatform` (e.g. `NovaSeqXSeries`),
  falling back to `InstrumentType`

```python
# V1 sheet declares "Instrument Type,NovaSeq X Plus"
# → workflow B detected; Index2 is reverse-complemented in the V2 output
SampleSheetConverter("novaseq_xplus.v1.csv").to_v2("novaseq_xplus.v2.csv")
```

V2 → V1 conversion preserves the instrument as `Instrument Type` in the
V1 `[Header]`, so a V1 → V2 → V1 round-trip restores the original
`Index2` exactly.

### Explicit override

Pass `workflow="a"` or `workflow="b"` to skip auto-detection. This is
**required** for `NovaSeq 6000`, whose i5 orientation depends on
chemistry (v1.0 = workflow A, v1.5 = workflow B) and cannot be inferred
from the instrument name alone.

```python
# NovaSeq 6000 with v1.5 chemistry → workflow B
SampleSheetConverter("novaseq6000.csv", workflow="b").to_v2("out.csv")
```

CLI:

```bash
samplesheet convert novaseq6000.v1.csv --to v2 --workflow b --output out.csv
```

### Failure mode

If the sheet has a non-empty `Index2` column **and** the workflow
cannot be determined **and** no override is given, conversion fails
loudly:

```text
V1 → V2: cannot determine i5 orientation workflow for instrument <missing>.
The sheet has dual indexes, and workflow-A vs workflow-B instruments
record Index2 in opposite orientations. Pass workflow='a' or
workflow='b' explicitly (CLI: --workflow {a,b}).
```

This is intentional — silently passing i5 through would produce a V2
sheet that runs but quietly misassigns reads. Single-index sheets and
sheets whose `Index2` column is entirely empty are unaffected.
