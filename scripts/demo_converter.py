#!/usr/bin/env python3
"""
demo_converter.py — local smoke test for SampleSheetConverter.

Run this script from the repo root after installing the package in dev mode:

    pip install -e ".[dev]"
    python scripts/demo_converter.py

It reads the fixture files from tests/fixtures/, runs both conversion
directions, and writes the outputs to tests/fixtures/outputs/.  The
output files are what you attach to a PR as evidence that the converter
works correctly.

Exit code 0 = all conversions completed and round-trip sample IDs match.
Exit code 1 = something went wrong (error printed to stderr).
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve paths relative to repo root regardless of cwd
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES  = REPO_ROOT / "tests" / "fixtures"
OUTPUTS   = FIXTURES / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)

INPUT_V1 = FIXTURES / "SampleSheet_v1_dual_index.csv"
INPUT_V2 = FIXTURES / "SampleSheet_v2_dual_index.csv"

OUT_V1_TO_V2      = OUTPUTS / "SampleSheet_v1_converted_to_v2.csv"
OUT_V2_TO_V1      = OUTPUTS / "SampleSheet_v2_converted_to_v1.csv"
OUT_ROUNDTRIP_V1  = OUTPUTS / "SampleSheet_v1_roundtrip.csv"
OUT_ROUNDTRIP_V2  = OUTPUTS / "SampleSheet_v2_roundtrip.csv"

# ---------------------------------------------------------------------------

def _separator(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _show_file(path: Path) -> None:
    print(path.read_text())


def run() -> int:
    try:
        from samplesheet_parser import SampleSheetConverter
        from samplesheet_parser.parsers.v1 import SampleSheetV1
        from samplesheet_parser.parsers.v2 import SampleSheetV2
    except ImportError as exc:
        print(
            f"ERROR: could not import samplesheet_parser — "
            f"did you run 'pip install -e .[dev]'?\n{exc}",
            file=sys.stderr,
        )
        return 1

    errors: list[str] = []

    # ------------------------------------------------------------------
    # 1. V1 → V2
    # ------------------------------------------------------------------
    _separator("1/4  V1 → V2  (SampleSheet_v1_dual_index.csv)")
    print(f"Input  : {INPUT_V1}")
    print(f"Output : {OUT_V1_TO_V2}\n")

    SampleSheetConverter(INPUT_V1).to_v2(OUT_V1_TO_V2)

    sheet_v2 = SampleSheetV2(str(OUT_V1_TO_V2))
    sheet_v2.parse()
    print("Converted V2 sheet:")
    _show_file(OUT_V1_TO_V2)
    print(f"✓ FileFormatVersion : {sheet_v2.header.get('FileFormatVersion')}")
    print(f"✓ RunName            : {sheet_v2.experiment_name}")
    print(f"✓ Sample count       : {len(sheet_v2.records)}")
    print(f"✓ Index type         : {sheet_v2.index_type()}")

    # ------------------------------------------------------------------
    # 2. V2 → V1
    # ------------------------------------------------------------------
    _separator("2/4  V2 → V1  (SampleSheet_v2_dual_index.csv)")
    print(f"Input  : {INPUT_V2}")
    print(f"Output : {OUT_V2_TO_V1}\n")

    SampleSheetConverter(INPUT_V2).to_v1(OUT_V2_TO_V1)

    sheet_v1 = SampleSheetV1(str(OUT_V2_TO_V1))
    sheet_v1.parse()
    print("Converted V1 sheet:")
    _show_file(OUT_V2_TO_V1)
    print(f"✓ IEMFileVersion : {sheet_v1.iem_version}")
    print(f"✓ Experiment Name: {sheet_v1.experiment_name}")
    print(f"✓ Sample count   : {len(sheet_v1.records)}")
    print(f"✓ Index type     : {sheet_v1.index_type()}")

    # ------------------------------------------------------------------
    # 3. Round-trip: V1 → V2 → V1
    # ------------------------------------------------------------------
    _separator("3/4  Round-trip V1 → V2 → V1")

    SampleSheetConverter(OUT_V1_TO_V2).to_v1(OUT_ROUNDTRIP_V1)
    rt_v1 = SampleSheetV1(str(OUT_ROUNDTRIP_V1))
    rt_v1.parse()

    orig_v1 = SampleSheetV1(str(INPUT_V1))
    orig_v1.parse()

    orig_ids = {s["sample_id"] for s in orig_v1.samples()}
    rt_ids   = {s["sample_id"] for s in rt_v1.samples()}

    if orig_ids == rt_ids:
        print(f"✓ Sample IDs match after V1→V2→V1 round-trip: {sorted(orig_ids)}")
    else:
        msg = (
            f"✗ Sample ID mismatch after V1→V2→V1 round-trip\n"
            f"  original  : {sorted(orig_ids)}\n"
            f"  round-trip: {sorted(rt_ids)}"
        )
        print(msg, file=sys.stderr)
        errors.append(msg)

    # ------------------------------------------------------------------
    # 4. Round-trip: V2 → V1 → V2
    # ------------------------------------------------------------------
    _separator("4/4  Round-trip V2 → V1 → V2")

    SampleSheetConverter(OUT_V2_TO_V1).to_v2(OUT_ROUNDTRIP_V2)
    rt_v2 = SampleSheetV2(str(OUT_ROUNDTRIP_V2))
    rt_v2.parse()

    orig_v2 = SampleSheetV2(str(INPUT_V2))
    orig_v2.parse()

    orig_ids_v2 = {s["sample_id"] for s in orig_v2.samples()}
    rt_ids_v2   = {s["sample_id"] for s in rt_v2.samples()}

    if orig_ids_v2 == rt_ids_v2:
        print(f"✓ Sample IDs match after V2→V1→V2 round-trip: {sorted(orig_ids_v2)}")
    else:
        msg = (
            f"✗ Sample ID mismatch after V2→V1→V2 round-trip\n"
            f"  original  : {sorted(orig_ids_v2)}\n"
            f"  round-trip: {sorted(rt_ids_v2)}"
        )
        print(msg, file=sys.stderr)
        errors.append(msg)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    _separator("Summary")
    print(f"Output files written to: {OUTPUTS}/\n")
    for f in sorted(OUTPUTS.iterdir()):
        print(f"  {f.name}")

    if errors:
        print(f"\n{'─'*60}")
        print(f"FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")
        return 1

    print("\n✓ All conversions passed. Attach the files in tests/fixtures/outputs/ to your PR.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
