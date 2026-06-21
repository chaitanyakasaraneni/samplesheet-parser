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
| `COLOR_BALANCE_NO_SIGNAL` | error | An index cycle has no optical signal (2-/1-channel dark, or a 4-channel laser absent), or a conservative-mode escalation (opt-in) |
| `COLOR_BALANCE_LOW` | warning | An index cycle has weak or single-channel signal (opt-in) |
| `COLOR_BALANCE_ADVISORY` | warning | AVITI low-diversity advisory in `vendor_faithful` mode (opt-in) |

The last two checks are **opt-in** — see [Color-balance checking](#color-balance-checking) below.

## Index distance checking

Indexes that are too similar cause read bleed-through between samples during demultiplexing, a common cause of low-quality runs that a simple duplicate check does not catch.

For every pair of samples within a lane, the validator computes a combined distance: the I7 (index) mismatch count plus the I5 (index2) mismatch count. This sum equals the minimum number of sequencing errors needed to read one sample's barcodes as another's across both index reads, which is the quantity that governs misassignment risk. Summing the per-index distances (rather than concatenating the two indexes into one string) keeps the I7 and I5 positions aligned even when samples use different index lengths. A pair is flagged when the combined distance is below the threshold.

Each per-index distance treats an `N` cycle as a wildcard that matches any base, matching how demultiplexers handle `N`. Two indexes that differ only where one carries an `N` are therefore reported as colliding. Sequences of different lengths are compared up to the length of the shorter sequence.

```python
# Default threshold: 3
result = SampleSheetValidator().validate(sheet)

# Custom threshold: stricter for longer indexes
result = SampleSheetValidator().validate(sheet, min_hamming_distance=4)
```

The standalone helpers are also available: `hamming_distance(a, b)` for the literal Hamming distance and `index_collision_distance(a, b)` for the wildcard-aware per-index distance the validator uses.

## Color-balance checking

Optical sequencers read each index base by its fluorescent signal, and the detection differs by instrument: Illumina four-channel/two-laser (MiSeq, HiSeq), two-channel (NextSeq, NovaSeq 6000, NovaSeq X), one-channel (iSeq), and Element AVITI avidity (per-base dye). On two-channel chemistry the base `G` is "dark" — no dye — so an index cycle where the **entire pool** reads `G` emits no signal and the cycle fails to register, miscalling every barcode at that position. A Hamming-distance check cannot catch this because the indexes may still be perfectly distinct.

`samplesheet-parser` models each instrument's chemistry and scores the pool cycle-by-cycle. The check is **opt-in** because it can turn a passing sheet into a failing one, and it needs to know the instrument:

```python
result = SampleSheetValidator().validate(
    sheet,
    check_color_balance=True,
    instrument="NovaSeq X",   # optional; inferred from the sheet header when present
    color_balance_mode="vendor_faithful",   # or "conservative"
)
```

### Modes

- **`vendor_faithful`** (default) encodes each platform's published rule exactly.
- **`conservative`** is stricter than the published minimum (the behavior before modes existed — pass `color_balance_mode="conservative"` to keep it).

### Rules by chemistry

- **Two-/one-channel**: an all-`G` (no-signal) cycle is a `COLOR_BALANCE_NO_SIGNAL` error in both modes. A single-channel cycle (one channel present, the other dark) meets Illumina's "at least one channel" minimum, so it is a `COLOR_BALANCE_LOW` warning in `vendor_faithful` but an error in `conservative`. A both-present-but-faint channel (below `min_signal_fraction`, default 0.10) is a `COLOR_BALANCE_LOW` warning.
- **Four-channel** (Illumina MiSeq/HiSeq): the green laser reads `{G,T}` and the red laser reads `{A,C}`; a cycle missing either laser group (e.g. all-`G`, or `G/T`-only) is a `COLOR_BALANCE_NO_SIGNAL` error in **both** modes.
- **Avidity** (Element AVITI): each base has its own dye and there is no laser-pair constraint, so low diversity never fails. In `vendor_faithful` it is a `COLOR_BALANCE_ADVISORY` warning (first cycles only); in `conservative` it is escalated to an error.
- If the instrument is unknown, the check is skipped silently.

The CLI exposes the same check:

```bash
samplesheet validate SampleSheet.csv --color-balance --instrument "NovaSeq X"
```

The underlying API — `Chemistry`, `ColorBalanceMode`, `chemistry_for_instrument()`, and `analyze_color_balance(..., mode=...)` returning a `ColorBalanceReport` — is public and usable on its own.

## Structured results

```python
result.is_valid          # bool — False if any errors present
result.summary()         # str — one-line human-readable summary

for issue in result.errors:
    print(issue.code)      # e.g. "DUPLICATE_INDEX"
    print(issue.message)   # human-readable description
    print(issue.context)   # dict with relevant sample IDs, lane, etc.
```
