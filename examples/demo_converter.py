#!/usr/bin/env python3
"""
demo_converter.py — SampleSheetConverter usage examples.

Demonstrates bidirectional conversion between V1 (IEM / bcl2fastq) and
V2 (BCLConvert) formats.

    Scenario 1: V1 → V2  — classic dual-index sheet converted for NovaSeq X
    Scenario 2: V2 → V1  — BCLConvert sheet converted back for bcl2fastq
    Scenario 3: Roundtrip — V1 → V2 → V1 to inspect what is preserved / lost

Run from the repo root::

    python3 examples/demo_converter.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from samplesheet_parser import SampleSheetConverter, SampleSheetFactory

SHEETS = Path(__file__).parent / "sample_sheets"
OUT = Path(__file__).parent / "sample_sheets"


def _print_summary(label: str, path: Path) -> None:
    factory = SampleSheetFactory()
    sheet = factory.create_parser(path, parse=True)
    samples = sheet.samples()
    print(f"  [{label}]")
    print(f"    Format   : {factory.version.value if factory.version else 'unknown'}")
    print(f"    Samples  : {len(samples)}")
    print(f"    Index    : {sheet.index_type()}")
    first = samples[0] if samples else {}
    idx = first.get("index") or first.get("Index") or "—"
    print(f"    1st idx  : {idx}")
    print()


# ---------------------------------------------------------------------------
# Scenario 1: V1 → V2
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 1: V1 → V2")
print("=" * 60)

src_v1 = SHEETS / "v1_dual_index.csv"
out_v2 = OUT / "converted_v1_to_v2.csv"

converter = SampleSheetConverter(str(src_v1))
result_path = converter.to_v2(str(out_v2))

print(f"  Input  : {src_v1.name}  ({converter.source_version.value})")
print(f"  Output : {result_path.name}")
print()
_print_summary("before", src_v1)
_print_summary("after", result_path)

# ---------------------------------------------------------------------------
# Scenario 2: V2 → V1
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 2: V2 → V1")
print("=" * 60)

src_v2 = SHEETS / "v2_novaseq_x_dual_index.csv"
out_v1 = OUT / "converted_v2_to_v1.csv"

converter = SampleSheetConverter(str(src_v2))
result_path = converter.to_v1(str(out_v1))

print(f"  Input  : {src_v2.name}  ({converter.source_version.value})")
print(f"  Output : {result_path.name}")
print("  Note   : V2→V1 is lossy — OverrideCycles, UMI fields are dropped.")
print()
_print_summary("before", src_v2)
_print_summary("after", result_path)

# ---------------------------------------------------------------------------
# Scenario 3: Roundtrip V1 → V2 → V1
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 3: Roundtrip V1 → V2 → V1")
print("=" * 60)

tmp_v2 = OUT / "roundtrip_v2.csv"
tmp_v1 = OUT / "roundtrip_v1.csv"

SampleSheetConverter(str(src_v1)).to_v2(str(tmp_v2))
SampleSheetConverter(str(tmp_v2)).to_v1(str(tmp_v1))

factory_orig = SampleSheetFactory()
sheet_orig = factory_orig.create_parser(src_v1, parse=True)
factory_rt = SampleSheetFactory()
sheet_rt = factory_rt.create_parser(tmp_v1, parse=True)

orig_samples = {s["sample_id"] for s in sheet_orig.samples()}
rt_samples = {s["sample_id"] for s in sheet_rt.samples()}

print(f"  Original format  : {factory_orig.version.value if factory_orig.version else 'unknown'}")
print(f"  Roundtrip format : {factory_rt.version.value if factory_rt.version else 'unknown'}")
print(f"  Samples preserved: {orig_samples == rt_samples}")
print(f"  Original IDs : {sorted(s for s in orig_samples if s)}")
print(f"  Roundtrip IDs: {sorted(s for s in rt_samples if s)}")

# Clean up temp files
tmp_v2.unlink(missing_ok=True)
tmp_v1.unlink(missing_ok=True)
(OUT / "converted_v1_to_v2.csv").unlink(missing_ok=True)
(OUT / "converted_v2_to_v1.csv").unlink(missing_ok=True)
