"""
demo_splitter.py — SampleSheetSplitter usage examples.

Demonstrates three scenarios:

    1. Split by project  — combined V2 sheet → one file per Sample_Project.
    2. Split by lane     — same sheet → one file per lane.
    3. Target version    — split a V2 combined sheet into V1 per-project files.

Run from the repo root::

    python examples/demo_splitter.py

Sample sheets used are in examples/sample_sheets/.
Output files are written to examples/sample_sheets/split/.
"""

from __future__ import annotations

from pathlib import Path

from samplesheet_parser import SplitResult
from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.splitter import SampleSheetSplitter

SHEETS = Path(__file__).parent / "sample_sheets"
OUT = SHEETS / "split"


def print_result(result: SplitResult) -> None:
    print(f"  Summary       : {result.summary()}")
    print(f"  Source version: {result.source_version}")
    for group, path in sorted(result.output_files.items()):
        count = result.sample_counts[group]
        print(f"  [{group}] → {path.name}  ({count} sample(s))")
    if result.warnings:
        print("  Warnings:")
        for w in result.warnings:
            print(f"    {w}")


# ---------------------------------------------------------------------------
# Scenario 1: Split by project — combined V2 → one file per Sample_Project
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 1: Split by project (V2 combined → per-project files)")
print("=" * 60)

splitter = SampleSheetSplitter(SHEETS / "combined_clean.csv", by="project")
result = splitter.split(OUT / "by_project")

print_result(result)
print()

# ---------------------------------------------------------------------------
# Scenario 2: Split by lane — V1 multi-lane sheet → one file per lane
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 2: Split by lane (V1 multi-lane → per-lane files)")
print("=" * 60)

splitter = SampleSheetSplitter(SHEETS / "v1_multi_lane.csv", by="lane")
result = splitter.split(OUT / "by_lane")

print_result(result)
print()

# ---------------------------------------------------------------------------
# Scenario 3: Target version override — split V2 input into V1 output files
# Useful when downstream tools (bcl2fastq) require V1 format but your
# combined sheet is V2.
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 3: V2 input → V1 per-project output files")
print("=" * 60)

splitter = SampleSheetSplitter(
    SHEETS / "combined_clean.csv",
    by="project",
    target_version=SampleSheetVersion.V1,
)
result = splitter.split(OUT / "by_project_v1", prefix="v1_")

print_result(result)
