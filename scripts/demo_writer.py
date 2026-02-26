#!/usr/bin/env python3
"""
demo_writer.py — local smoke test for SampleSheetWriter.

Run this script from the repo root after installing the package in dev mode:

    pip install -e ".[dev]"
    python scripts/demo_writer.py

Demonstrates three scenarios:

    1. Build a V2 sheet from scratch
    2. Build a V1 sheet from scratch
    3. Load an existing sheet, edit it (remove + update), write back

Exit code 0 = all scenarios completed and output files are parseable.
Exit code 1 = something went wrong (error printed to stderr).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES  = REPO_ROOT / "tests" / "fixtures"
OUTPUTS   = FIXTURES / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)

INPUT_V2 = FIXTURES / "SampleSheet_v2_dual_index.csv"

OUT_V2_SCRATCH    = OUTPUTS / "SampleSheet_writer_v2_scratch.csv"
OUT_V1_SCRATCH    = OUTPUTS / "SampleSheet_writer_v1_scratch.csv"
OUT_V2_EDITED     = OUTPUTS / "SampleSheet_writer_v2_edited.csv"


def _separator(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def run() -> int:
    try:
        from samplesheet_parser import SampleSheetFactory
        from samplesheet_parser.enums import SampleSheetVersion
        from samplesheet_parser.writer import SampleSheetWriter
    except ImportError as exc:
        print(
            f"ERROR: could not import samplesheet_parser — "
            f"did you run 'pip install -e .[dev]'?\n{exc}",
            file=sys.stderr,
        )
        return 1

    errors: list[str] = []

    # ------------------------------------------------------------------
    # Scenario 1 — Build V2 sheet from scratch
    # ------------------------------------------------------------------
    _separator("1/3  Build V2 sheet from scratch")

    writer = SampleSheetWriter(version=SampleSheetVersion.V2)
    writer.set_header(
        run_name="NovaSeqXRun_20240115",
        platform="NovaSeqXSeries",
        instrument="NovaSeqX",
        run_desc="Amplicon panel - batch 7",
    )
    writer.set_reads(read1=151, read2=151, index1=10, index2=10)
    writer.set_adapter("CTGTCTCTTATACACATCT", "CTGTCTCTTATACACATCT")
    writer.set_override_cycles("Y151;I10;I10;Y151")
    writer.set_software_version("4.2.7")

    for i, (idx, idx2) in enumerate([
        ("ATTACTCGAT", "TATAGCCTGT"),
        ("TCCGGAGACC", "ATAGAGGCAC"),
        ("TAGGCATGCC", "CCTATCCTGT"),
        ("CTCTCTACTT", "GGCTCTGACC"),
    ], start=1):
        writer.add_sample(
            f"SAMPLE_00{i}",
            index=idx,
            index2=idx2,
            lane="1",
            project="Project_Amplicon",
        )

    writer.write(OUT_V2_SCRATCH)
    print(OUT_V2_SCRATCH.read_text())

    sheet = SampleSheetFactory().create_parser(
        OUT_V2_SCRATCH, parse=True, clean=False
    )
    if len(sheet.records) != 4:
        msg = f"✗ Expected 4 samples, got {len(sheet.records)}"
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print(f"✓ {len(sheet.records)} samples written and parsed correctly")
    if sheet.header.get("FileFormatVersion") != "2":
        msg = "✗ FileFormatVersion is not 2"
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print(f"✓ FileFormatVersion = {sheet.header.get('FileFormatVersion')}")

    # ------------------------------------------------------------------
    # Scenario 2 — Build V1 sheet from scratch
    # ------------------------------------------------------------------
    _separator("2/3  Build V1 sheet from scratch")

    writer_v1 = SampleSheetWriter(version=SampleSheetVersion.V1)
    writer_v1.set_header(
        run_name="NovaSeqRun_20240115",
        workflow="GenerateFASTQ",
        chemistry="Amplicon",
    )
    writer_v1.set_reads(read1=151, read2=151)
    writer_v1.set_adapter("CTGTCTCTTATACACATCT")

    for i, (idx, idx2, i7, i5) in enumerate([
        ("ATTACTCG", "TATAGCCT", "D701", "D501"),
        ("TCCGGAGA", "ATAGAGGC", "D702", "D502"),
        ("TAGGCATG", "CCTATCCT", "D703", "D503"),
        ("CTCTCTAC", "GGCTCTGA", "D704", "D504"),
    ], start=1):
        writer_v1.add_sample(
            f"SAMPLE_00{i}",
            index=idx,
            index2=idx2,
            lane="1",
            i7_index_id=i7,
            i5_index_id=i5,
            project="Project_Amplicon",
        )

    writer_v1.write(OUT_V1_SCRATCH)
    print(OUT_V1_SCRATCH.read_text())

    sheet_v1 = SampleSheetFactory().create_parser(
        OUT_V1_SCRATCH, parse=True, clean=False
    )
    if len(sheet_v1.records) != 4:
        msg = f"✗ Expected 4 samples, got {len(sheet_v1.records)}"
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print(f"✓ {len(sheet_v1.records)} samples written and parsed correctly")
    if sheet_v1.iem_version != "5":
        msg = f"✗ Expected IEMFileVersion 5, got {sheet_v1.iem_version}"
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print(f"✓ IEMFileVersion = {sheet_v1.iem_version}")

    # ------------------------------------------------------------------
    # Scenario 3 — Load existing sheet, remove + update + write back
    # ------------------------------------------------------------------
    _separator("3/3  Load existing V2 sheet, edit, write back")
    print(f"Input: {INPUT_V2}\n")

    src_sheet = SampleSheetFactory().create_parser(
        INPUT_V2, parse=True, clean=False
    )
    original_count = len(src_sheet.records)

    editor = SampleSheetWriter.from_sheet(src_sheet)
    print(f"Loaded {editor.sample_count} samples: {editor.sample_ids}")

    # Remove SAMPLE_008
    editor.remove_sample("SAMPLE_008")
    print(f"After remove SAMPLE_008: {editor.sample_count} samples")

    # Update SAMPLE_002's index
    editor.update_sample("SAMPLE_002", index="GGGGGGGGGG")
    print("Updated SAMPLE_002 index to GGGGGGGGGG")

    editor.write(OUT_V2_EDITED, validate=False)
    print(f"\nWritten to: {OUT_V2_EDITED}")
    print(OUT_V2_EDITED.read_text())

    edited_sheet = SampleSheetFactory().create_parser(
        OUT_V2_EDITED, parse=True, clean=False
    )
    expected_count = original_count - 1

    if len(edited_sheet.records) != expected_count:
        msg = (
            f"✗ Expected {expected_count} samples after remove, "
            f"got {len(edited_sheet.records)}"
        )
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print(f"✓ Sample count correct after remove: {len(edited_sheet.records)}")

    s2 = next(
        (r for r in edited_sheet.records if r["Sample_ID"] == "SAMPLE_002"), None
    )
    if s2 is None:
        msg = "✗ SAMPLE_002 not found in edited sheet"
        print(msg, file=sys.stderr)
        errors.append(msg)
    elif s2.get("Index") != "GGGGGGGGGG":
        msg = (
            f"✗ SAMPLE_002 index not updated — "
            f"expected GGGGGGGGGG, got {s2.get('Index')}"
        )
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print(f"✓ SAMPLE_002 index correctly updated to {s2.get('Index')}")

    removed = next(
        (r for r in edited_sheet.records if r["Sample_ID"] == "SAMPLE_008"), None
    )
    if removed is not None:
        msg = "✗ SAMPLE_008 still present after remove"
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print("✓ SAMPLE_008 correctly removed")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    _separator("Summary")
    print(f"Output files written to: {OUTPUTS}/\n")
    for f in sorted(OUTPUTS.glob("SampleSheet_writer_*.csv")):
        print(f"  {f.name}")

    if errors:
        print(f"\n{'─'*60}")
        print(f"FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")
        return 1

    print("\n✓ All 3 writer scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
