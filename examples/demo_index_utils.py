#!/usr/bin/env python3
"""
demo_index_utils.py — normalize_index_lengths usage examples.

Demonstrates normalizing mixed-length index sequences across a list of sample
records before merging sheets from different library prep kits.

    Scenario 1: Trim to shortest  — 10 bp + 8 bp kit → all trimmed to 8 bp
    Scenario 2: Pad to longest    — 8 bp + 10 bp kit → shorter padded with 'N'
    Scenario 3: Dual-index mixed  — both I7 and I5 lengths normalized together
    Scenario 4: Real sheet usage  — load a sheet, normalize, inspect the result

Run from the repo root::

    python3 examples/demo_index_utils.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from samplesheet_parser import SampleSheetFactory, normalize_index_lengths

SHEETS = Path(__file__).parent / "sample_sheets"


def _print_samples(samples: list[dict]) -> None:  # type: ignore[type-arg]
    for s in samples:
        idx = s.get("index") or s.get("Index") or "—"
        idx2 = s.get("index2") or s.get("Index2") or ""
        idx2_str = f"  index2={idx2}" if idx2 else ""
        print(f"    {s.get('sample_id') or s.get('Sample_ID'):<12} index={idx}{idx2_str}")
    print()


# ---------------------------------------------------------------------------
# Scenario 1: Trim to shortest (10-mer + 8-mer → 8-mer)
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 1: Trim to shortest — mixed 10 bp / 8 bp I7")
print("=" * 60)

samples_mixed = [
    {"sample_id": "SampleA", "index": "CAAGACAGAT"},  # 10 bp
    {"sample_id": "SampleB", "index": "TGAACCTG"},  #  8 bp
    {"sample_id": "SampleC", "index": "GCACAACG"},  #  8 bp
    {"sample_id": "SampleD", "index": "ATCGCCTGTT"},  # 10 bp
]

print("  Before:")
_print_samples(samples_mixed)

normalized = normalize_index_lengths(samples_mixed, strategy="trim")
print("  After (strategy='trim' → 8 bp):")
_print_samples(normalized)

# ---------------------------------------------------------------------------
# Scenario 2: Pad to longest (8-mer → 10-mer with 'NN' suffix)
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 2: Pad to longest — 8 bp padded to 10 bp")
print("=" * 60)

print("  Before:")
_print_samples(samples_mixed)

normalized = normalize_index_lengths(samples_mixed, strategy="pad")
print("  After (strategy='pad' → 10 bp, short indexes get 'N' suffix):")
_print_samples(normalized)

# ---------------------------------------------------------------------------
# Scenario 3: Dual-index — normalize both I7 and I5 together
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 3: Dual-index — normalize I7 and I5 independently")
print("=" * 60)

dual_mixed = [
    {"sample_id": "SampleA", "index": "CAAGACAGAT", "index2": "ACTATAGCCT"},  # 10+10
    {"sample_id": "SampleB", "index": "TGAACCTG", "index2": "TGATACG"},  #  8+ 7
    {"sample_id": "SampleC", "index": "GCACAACGTT", "index2": "CATCTCAC"},  # 10+ 8
]

print("  Before:")
_print_samples(dual_mixed)

normalized = normalize_index_lengths(dual_mixed, strategy="trim")
print("  After (strategy='trim' — I7→8bp, I5→7bp):")
_print_samples(normalized)

# ---------------------------------------------------------------------------
# Scenario 4: Real sheet — load, normalize, inspect
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 4: Real sheet — load V1, normalize, inspect")
print("=" * 60)

factory = SampleSheetFactory()
sheet = factory.create_parser(SHEETS / "v1_dual_index.csv", parse=True)
samples = sheet.samples()

print(f"  Loaded  : v1_dual_index.csv ({len(samples)} samples)")
print("  Before normalization:")
_print_samples(samples)

# Simulate a scenario where one index is shorter (trim to 8 bp)
for s in samples:
    if s.get("sample_id") == "Sample3":
        s["index"] = s["index"][:8]  # type: ignore[index]

print("  After trimming Sample3 index to 8 bp (simulated mixed kit):")
_print_samples(samples)

normalized = normalize_index_lengths(samples, strategy="trim")
print("  After normalize_index_lengths(strategy='trim'):")
_print_samples(normalized)
