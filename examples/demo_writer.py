#!/usr/bin/env python3
"""
demo_writer.py — SampleSheetWriter usage examples.

Demonstrates building and editing sample sheets programmatically using the
fluent SampleSheetWriter API.

    Scenario 1: Build V1 from scratch   — minimal sheet for bcl2fastq
    Scenario 2: Build V2 from scratch   — NovaSeq X sheet with OverrideCycles
    Scenario 3: Edit an existing sheet  — load, modify a sample index, write
    Scenario 4: Remove a sample         — filter out a sample before submission

Run from the repo root::

    python3 examples/demo_writer.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from samplesheet_parser import SampleSheetFactory, SampleSheetWriter
from samplesheet_parser.enums import SampleSheetVersion

SHEETS = Path(__file__).parent / "sample_sheets"
OUT = Path("/tmp")


def _print_csv(path: Path) -> None:
    print(f"  --- {path.name} ---")
    for line in path.read_text(encoding="utf-8").splitlines():
        print(f"  {line}")
    print()


# ---------------------------------------------------------------------------
# Scenario 1: Build a V1 sheet from scratch
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 1: Build V1 sheet from scratch")
print("=" * 60)

writer = SampleSheetWriter(version=SampleSheetVersion.V1)
writer.set_header(
    experiment_name="Run_001",
    date="2024-01-15",
    workflow="GenerateFASTQ",
    instrument_type="NovaSeq 6000",
)
writer.set_reads(read1=151, read2=151)
writer.set_adapter(
    adapter_read1="AGATCGGAAGAGCACACGTCTGAACTCCAGTCA",
    adapter_read2="AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT",
)
writer.add_sample(
    sample_id="SampleA",
    index="CAAGACAGAT",
    index2="ACTATAGCCT",
    lane="1",
    project="ProjectX",
)
writer.add_sample(
    sample_id="SampleB",
    index="TGAACCTGAT",
    index2="TGATACGTCC",
    lane="1",
    project="ProjectX",
)
writer.add_sample(
    sample_id="SampleC",
    index="GCACAACGTT",
    index2="CATCTCACAG",
    lane="1",
    project="ProjectX",
)

out_v1 = writer.write(OUT / "writer_v1_scratch.csv")
print(f"  Written {writer.sample_count} samples → {out_v1.name}")
print()
_print_csv(out_v1)

# ---------------------------------------------------------------------------
# Scenario 2: Build a V2 sheet from scratch
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 2: Build V2 sheet from scratch")
print("=" * 60)

writer = SampleSheetWriter(version=SampleSheetVersion.V2)
writer.set_header(
    run_name="240115_LH00336_0025_A227HGJLT3",
    instrument_platform="NovaSeqXSeries",
)
writer.set_reads(read1=151, read2=151, index1=10, index2=10)
writer.set_override_cycles("Y151;I10;I10;Y151")
writer.set_adapter(
    adapter_read1="CTGTCTCTTATACACATCT",
    adapter_read2="CTGTCTCTTATACACATCT",
)
writer.set_software_version("3.9.3")
writer.add_sample(
    sample_id="SampleA", index="ATTACTCGAT", index2="TATAGCCTGT", lane="1", project="ProjectAlpha"
)
writer.add_sample(
    sample_id="SampleB", index="TCCGGAGACC", index2="ATAGAGGCAC", lane="1", project="ProjectAlpha"
)
writer.add_sample(
    sample_id="SampleC", index="TAGGCATGCA", index2="CCTATCCTAG", lane="2", project="ProjectBeta"
)

out_v2 = writer.write(OUT / "writer_v2_scratch.csv")
print(f"  Written {writer.sample_count} samples → {out_v2.name}")
print()
_print_csv(out_v2)

# ---------------------------------------------------------------------------
# Scenario 3: Load an existing sheet and correct a sample index
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 3: Edit existing sheet — fix a sample index")
print("=" * 60)

src = SHEETS / "v1_dual_index.csv"
src_sheet = SampleSheetFactory().create_parser(src, parse=True)
writer = SampleSheetWriter.from_sheet(src_sheet)

print(f"  Loaded  : {src.name} ({writer.sample_count} samples)")
print(f"  IDs     : {writer.sample_ids}")

# Correct the index on Sample2 (simulate a sequencing core typo fix)
writer.update_sample("Sample2", index="AACCGTGATC")

out_edit = writer.write(OUT / "writer_v1_edited.csv")
print(f"  Updated index for Sample2 → {out_edit.name}")
print()

factory = SampleSheetFactory()
sheet = factory.create_parser(out_edit, parse=True)
for s in sheet.samples():
    if s["sample_id"] == "Sample2":
        print(f"  Sample2 index after edit: {s.get('index') or s.get('Index')}")
print()

# ---------------------------------------------------------------------------
# Scenario 4: Remove a sample before submission
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 4: Remove a sample before submission")
print("=" * 60)

src_sheet = SampleSheetFactory().create_parser(src, parse=True)
writer = SampleSheetWriter.from_sheet(src_sheet)
print(f"  Before removal: {writer.sample_count} samples — {writer.sample_ids}")

writer.remove_sample("Sample3")
print(f"  After  removal: {writer.sample_count} samples — {writer.sample_ids}")

out_removed = writer.write(OUT / "writer_v1_removed.csv")
print(f"  Written → {out_removed.name}")

# Clean up
for f in [out_v1, out_v2, out_edit, out_removed]:
    f.unlink(missing_ok=True)
