"""
demo_merger.py — SampleSheetMerger usage examples.

Demonstrates three scenarios:

    1. Clean merge     — two V1 sheets, no conflicts, output written.
    2. Mixed formats   — V1 + V1 + V2, auto-converted to a target version.
    3. Conflict handling — index collision detected; abort vs. force write.

Run from the repo root::

    python examples/demo_merger.py

Sample sheets used are in examples/samplesheets/.
"""

from __future__ import annotations

from pathlib import Path

from samplesheet_parser import MergeResult, SampleSheetMerger
from samplesheet_parser.enums import SampleSheetVersion

SHEETS = Path(__file__).parent / "sample_sheets"


def print_result(result: MergeResult) -> None:
    print(f"  Summary      : {result.summary()}")
    print(f"  Sample count : {result.sample_count}")
    print(f"  Has conflicts: {result.has_conflicts}")
    print(f"  Output path  : {result.output_path}")
    if result.warnings:
        print("  Warnings:")
        for w in result.warnings:
            print(f"    [{w.code}] {w.message}")
    if result.conflicts:
        print("  Conflicts:")
        for c in result.conflicts:
            print(f"    [{c.code}] {c.message}")


# ---------------------------------------------------------------------------
# Scenario 1: Clean merge — two V1 sheets → combined V2
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 1: Clean merge (V1 + V1 → V2)")
print("=" * 60)

merger = SampleSheetMerger(target_version=SampleSheetVersion.V2)
merger.add(SHEETS / "ProjectAlpha_SampleSheet.csv")
merger.add(SHEETS / "ProjectBeta_SampleSheet.csv")

result = merger.merge(
    SHEETS / "combined_clean.csv",
    validate=True,
    abort_on_conflicts=True,
)

print_result(result)
print()

# ---------------------------------------------------------------------------
# Scenario 2: Mixed formats — V1 + V1 + V2 → combined V2
# ProjectGamma supplies a V2 sheet; merger auto-converts all inputs to V2.
# Mixed-format inputs produce a warning but are not a conflict.
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 2: Mixed formats (V1 + V1 + V2 → V2)")
print("=" * 60)

merger = SampleSheetMerger(target_version=SampleSheetVersion.V2)
merger.add(SHEETS / "ProjectAlpha_SampleSheet.csv")
merger.add(SHEETS / "ProjectBeta_SampleSheet.csv")
merger.add(SHEETS / "ProjectGamma_SampleSheet.csv")

result = merger.merge(
    SHEETS / "combined_mixed_formats.csv",
    validate=True,
    abort_on_conflicts=True,
)

print_result(result)
print()

# ---------------------------------------------------------------------------
# Scenario 3a: Index collision — abort_on_conflicts=True (default)
# ProjectDelta reuses an index from ProjectAlpha on the same lane.
# The output file is NOT written; result.output_path is None.
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 3a: Index collision — abort (default)")
print("=" * 60)

merger = SampleSheetMerger(target_version=SampleSheetVersion.V2)
merger.add(SHEETS / "ProjectAlpha_SampleSheet.csv")
merger.add(SHEETS / "ProjectDelta_SampleSheet_collision.csv")

result = merger.merge(
    SHEETS / "combined_collision_aborted.csv",
    validate=True,
    abort_on_conflicts=True,   # default — file not written on conflict
)

print_result(result)
print()

# ---------------------------------------------------------------------------
# Scenario 3b: Index collision — abort_on_conflicts=False (force write)
# Same collision as above, but the file is written anyway.
# Equivalent to passing --force on the CLI.
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 3b: Index collision — force write")
print("=" * 60)

merger = SampleSheetMerger(target_version=SampleSheetVersion.V2)
merger.add(SHEETS / "ProjectAlpha_SampleSheet.csv")
merger.add(SHEETS / "ProjectDelta_SampleSheet_collision.csv")

result = merger.merge(
    SHEETS / "combined_collision_forced.csv",
    validate=True,
    abort_on_conflicts=False,   # write despite conflicts
)

print_result(result)
