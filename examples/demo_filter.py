"""
demo_filter.py — SampleSheetFilter usage examples.

Demonstrates four scenarios:

    1. Filter by project   — keep only one project's samples.
    2. Filter by lane      — keep only samples from a specific lane.
    3. Filter by sample ID — exact match and glob pattern.
    4. Combined criteria   — project + lane ANDed together.

Run from the repo root::

    python examples/demo_filter.py

Sample sheets used are in examples/sample_sheets/.
Output files are written to examples/sample_sheets/filtered/.
"""

from __future__ import annotations

from pathlib import Path

from samplesheet_parser import FilterResult
from samplesheet_parser.filter import SampleSheetFilter

SHEETS = Path(__file__).parent / "sample_sheets"
OUT = SHEETS / "filtered"
OUT.mkdir(parents=True, exist_ok=True)


def print_result(result: FilterResult) -> None:
    print(f"  Summary       : {result.summary()}")
    print(f"  Source version: {result.source_version}")
    print(f"  Matched/Total : {result.matched_count}/{result.total_count}")
    if result.output_path:
        print(f"  Output        : {result.output_path.name}")


# ---------------------------------------------------------------------------
# Scenario 1: Filter by project
# Keep only ProjectAlpha samples from the combined sheet.
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 1: Filter by project (keep ProjectAlpha only)")
print("=" * 60)

flt = SampleSheetFilter(SHEETS / "combined_clean.csv")
result = flt.filter(OUT / "ProjectAlpha_only.csv", project="ProjectAlpha")

print_result(result)
print()

# ---------------------------------------------------------------------------
# Scenario 2: Filter by lane
# Keep only samples assigned to lane 1.
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 2: Filter by lane (keep lane 1 only)")
print("=" * 60)

flt = SampleSheetFilter(SHEETS / "v1_multi_lane.csv")
result = flt.filter(OUT / "lane1_only.csv", lane=1)

print_result(result)
print()

# ---------------------------------------------------------------------------
# Scenario 3a: Filter by sample ID — exact match
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 3a: Filter by sample ID (exact match)")
print("=" * 60)

flt = SampleSheetFilter(SHEETS / "combined_clean.csv")
result = flt.filter(OUT / "AlphaSample1_only.csv", sample_id="AlphaSample1")

print_result(result)
print()

# ---------------------------------------------------------------------------
# Scenario 3b: Filter by sample ID — glob pattern
# Keep all samples whose ID starts with "Alpha".
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 3b: Filter by sample ID glob ('Alpha*')")
print("=" * 60)

flt = SampleSheetFilter(SHEETS / "combined_clean.csv")
result = flt.filter(OUT / "Alpha_samples.csv", sample_id="Alpha*")

print_result(result)
print()

# ---------------------------------------------------------------------------
# Scenario 4: Combined criteria — project AND lane
# Multiple criteria are ANDed: a sample must satisfy all of them.
# ---------------------------------------------------------------------------

print("=" * 60)
print("Scenario 4: Combined criteria (project=Oncology AND lane=1)")
print("=" * 60)

flt = SampleSheetFilter(SHEETS / "v1_multi_lane.csv")
result = flt.filter(OUT / "Oncology_lane1.csv", project="Oncology", lane=1)

print_result(result)
