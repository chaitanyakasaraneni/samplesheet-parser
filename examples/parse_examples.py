#!/usr/bin/env python3
"""
parse_examples.py — Parse all example sample sheets and print a summary.

Run from the repo root:
    python examples/parse_examples.py

Demonstrates auto-detection, samples(), index_type(), UMI extraction,
and validation for every example sheet in examples/sample_sheets/.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).parent.parent))

from samplesheet_parser import SampleSheetFactory, SampleSheetValidator

SHEETS_DIR = Path(__file__).parent / "sample_sheets"

# Ordered for readability: V1 first, then V2
EXAMPLE_FILES = [
    "v1_dual_index.csv",
    "v1_single_index.csv",
    "v1_multi_lane.csv",
    "v2_novaseq_x_dual_index.csv",
    "v2_with_index_umi.csv",
    "v2_with_read_umi.csv",
    "v2_nextseq_single_index.csv",
]


def parse_sheet(path: Path) -> None:
    print(f"\n{'='*60}")
    print(f"  {path.name}")
    print(f"{'='*60}")

    factory = SampleSheetFactory()
    try:
        sheet = factory.create_parser(path, parse=True)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return

    # Format + basic metadata
    print(f"  Format          : {factory.version.value}")
    print(f"  Index type      : {sheet.index_type()}")
    print(f"  UMI length      : {factory.get_umi_length()} bp")

    if hasattr(sheet, "experiment_name") and sheet.experiment_name:
        print(f"  Experiment      : {sheet.experiment_name}")
    if hasattr(sheet, "instrument_type") and sheet.instrument_type:
        print(f"  Instrument type : {sheet.instrument_type}")
    if hasattr(sheet, "instrument_platform") and sheet.instrument_platform:
        print(f"  Platform        : {sheet.instrument_platform}")

    # Adapters
    if sheet.adapters:
        r1 = getattr(sheet, "adapter_read1", sheet.adapters[0])
        r2 = getattr(sheet, "adapter_read2", sheet.adapters[1] if len(sheet.adapters) > 1 else "")
        print(f"  AdapterRead1    : {r1 or '—'}")
        print(f"  AdapterRead2    : {r2 or '—'}")

    # Read structure (V2 only)
    if factory.version.value == "V2" and factory.get_umi_length() > 0:
        rs = sheet.get_read_structure()  # type: ignore[union-attr]
        print(f"  UMI location    : {rs.umi_location}")
        print(f"  Read structure  : {rs.read_structure}")

    # Samples table
    samples = sheet.samples()
    print(f"\n  Samples ({len(samples)} total):")
    print(f"  {'Sample_ID':<20} {'Lane':<6} {'index':<12} {'index2':<12} {'Project'}")
    print(f"  {'-'*20} {'-'*6} {'-'*12} {'-'*12} {'-'*20}")
    for s in samples:
        lane    = str(s.get("lane") or "—")
        idx     = (s.get("index") or s.get("Index") or "—")[:12]
        idx2    = (s.get("index2") or s.get("Index2") or "—")[:12]
        project = (s.get("sample_project") or "—")[:20]
        print(f"  {s['sample_id']:<20} {lane:<6} {idx:<12} {idx2:<12} {project}")

    # Validation
    result = SampleSheetValidator().validate(sheet)
    status = "✓ PASS" if result.is_valid else "✗ FAIL"
    errors, warnings = len(result.errors), len(result.warnings)
    print(f"\n  Validation      : {status} — {errors} error(s), {warnings} warning(s)")
    for err in result.errors:
        print(f"    [ERROR]   {err.code}: {err.message}")
    for warn in result.warnings:
        print(f"    [WARNING] {warn.code}: {warn.message}")


def main() -> None:
    print("samplesheet-parser — Example Sheet Demo")
    print(f"Parsing {len(EXAMPLE_FILES)} example sheets from {SHEETS_DIR}\n")

    missing = [f for f in EXAMPLE_FILES if not (SHEETS_DIR / f).exists()]
    if missing:
        print(f"Warning: missing files: {missing}")

    for filename in EXAMPLE_FILES:
        path = SHEETS_DIR / filename
        if path.exists():
            parse_sheet(path)

    print(f"\n{'='*60}")
    print("Done.")


if __name__ == "__main__":
    main()
