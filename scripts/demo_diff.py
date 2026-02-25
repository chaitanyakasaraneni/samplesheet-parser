#!/usr/bin/env python3
"""
demo_diff.py — local smoke test for SampleSheetDiff.

Run this script from the repo root after installing the package in dev mode:

    pip install -e ".[dev]"
    python scripts/demo_diff.py

Demonstrates three diff scenarios using fixture files from tests/fixtures/:

    1. Identical V2 sheets       — expects zero changes
    2. V2 old vs V2 modified     — index change, project change, sample added
    3. V1 vs V2 (cross-format)   — field normalisation, no spurious diffs

Exit code 0 = all scenarios produced expected results.
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

INPUT_V1          = FIXTURES / "SampleSheet_v1_dual_index.csv"
INPUT_V2          = FIXTURES / "SampleSheet_v2_dual_index.csv"
INPUT_V2_MODIFIED = FIXTURES / "SampleSheet_v2_modified.csv"

# ---------------------------------------------------------------------------

def _separator(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def run() -> int:
    try:
        from samplesheet_parser.diff import SampleSheetDiff
    except ImportError as exc:
        print(
            f"ERROR: could not import samplesheet_parser — "
            f"did you run 'pip install -e .[dev]'?\n{exc}",
            file=sys.stderr,
        )
        return 1

    errors: list[str] = []

    # ------------------------------------------------------------------
    # Scenario 1 — identical V2 sheets: expect zero changes
    # ------------------------------------------------------------------
    _separator("1/3  Identical V2 sheets — expect zero changes")
    print(f"Old : {INPUT_V2}")
    print(f"New : {INPUT_V2}\n")

    result = SampleSheetDiff(INPUT_V2, INPUT_V2).compare()
    print(result.summary())

    if result.has_changes:
        msg = "✗ Expected no changes for identical sheets but got some"
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print("✓ Correctly reports no differences")

    # ------------------------------------------------------------------
    # Scenario 2 — V2 old vs V2 modified
    #   SAMPLE_002  index changed:  TCCGGAGACC → GGGGGGGGGG
    #   SAMPLE_003  project changed: Project_Amplicon → Project_Amplicon_NEW
    #   SAMPLE_009  added in new sheet
    # ------------------------------------------------------------------
    _separator("2/3  V2 old vs V2 modified — index, project, sample added")
    print(f"Old : {INPUT_V2}")
    print(f"New : {INPUT_V2_MODIFIED}\n")

    result = SampleSheetDiff(INPUT_V2, INPUT_V2_MODIFIED).compare()
    print(result)

    # Validate expected outcomes
    added_ids   = {r["Sample_ID"] for r in result.samples_added}
    changed_ids = {sc.sample_id  for sc in result.sample_changes}

    if "SAMPLE_009" not in added_ids:
        msg = f"✗ Expected SAMPLE_009 in samples_added, got: {added_ids}"
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print("\n✓ SAMPLE_009 correctly detected as added")

    if "SAMPLE_002" not in changed_ids:
        msg = f"✗ Expected SAMPLE_002 in sample_changes (index), got: {changed_ids}"
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        sc_002 = next(sc for sc in result.sample_changes if sc.sample_id == "SAMPLE_002")
        old_idx, new_idx = sc_002.changes.get("Index", (None, None))
        print(f"✓ SAMPLE_002 index change detected: {old_idx} → {new_idx}")

    if "SAMPLE_003" not in changed_ids:
        msg = f"✗ Expected SAMPLE_003 in sample_changes (project), got: {changed_ids}"
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        sc_003 = next(sc for sc in result.sample_changes if sc.sample_id == "SAMPLE_003")
        old_p, new_p = sc_003.changes.get("Sample_Project", (None, None))
        print(f"✓ SAMPLE_003 project change detected: {old_p} → {new_p}")

    if result.samples_removed:
        msg = f"✗ Unexpected removals: {[r['Sample_ID'] for r in result.samples_removed]}"
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print("✓ No false-positive removals")

    # ------------------------------------------------------------------
    # Scenario 3 — V1 vs V2 cross-format with matching samples
    #   Field normalisation should suppress I7_Index_ID, Sample_Name etc.
    #   Samples and indexes match → expect zero sample_changes
    # ------------------------------------------------------------------
    _separator("3/3  V1 vs V2 cross-format — field normalisation")
    print(f"Old (V1) : {INPUT_V1}")
    print(f"New (V2) : {INPUT_V2}\n")

    result = SampleSheetDiff(INPUT_V1, INPUT_V2).compare()
    print(result.summary())
    print(f"\nSource format : {result.source_version.value}")
    print(f"Target format : {result.target_version.value}")

    # Additions / removals: same 8 samples in both sheets → expect none
    if result.samples_added or result.samples_removed:
        msg = (
            f"✗ Unexpected additions/removals in V1→V2 cross-format diff\n"
            f"  added  : {[r['Sample_ID'] for r in result.samples_added]}\n"
            f"  removed: {[r['Sample_ID'] for r in result.samples_removed]}"
        )
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print("✓ No spurious additions or removals")

    # V1-only metadata fields (I7_Index_ID, Sample_Name etc.) are suppressed
    # by field normalisation — none should appear in sample_changes.
    v1_only_fields = {"I7_Index_ID", "I5_Index_ID", "Sample_Name", "Description"}
    spurious = [
        sc for sc in result.sample_changes
        if any(f in v1_only_fields for f in sc.changes)
    ]
    if spurious:
        msg = (
            "✗ V1-only metadata fields leaked into sample_changes "
            "— normalisation not working:\n"
            + "\n".join(str(sc) for sc in spurious)
        )
        print(msg, file=sys.stderr)
        errors.append(msg)
    else:
        print("✓ V1-only metadata fields correctly suppressed (I7_Index_ID etc.)")

    # Index length differences (8bp V1 → 10bp V2) are real content changes
    # and should be reported — this is expected behaviour, not a bug.
    index_changes = [
        sc for sc in result.sample_changes
        if "Index" in sc.changes or "Index2" in sc.changes
    ]
    if index_changes:
        print(
            "\n  (Index length changes V1→V2 are expected — "
            "V1 uses 8bp, V2 uses 10bp in these fixtures):"
        )
        for sc in index_changes[:3]:
            old_i = sc.changes.get("Index", (None, None))[0]
            new_i = sc.changes.get("Index", (None, None))[1]
            print(f"    {sc.sample_id}: {old_i} → {new_i}")
        if len(index_changes) > 3:
            print(f"    … and {len(index_changes) - 3} more")

    # Header/settings diffs between formats are also expected
    if result.header_changes:
        print("\n  (Header/settings diffs between V1 and V2 formats — expected):")
        for c in result.header_changes:
            print(f"    {c}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    _separator("Summary")
    if errors:
        print(f"FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")
        return 1

    print("✓ All 3 diff scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
