#!/usr/bin/env python3
"""
demo_diff.py — SampleSheetDiff usage examples.

Demonstrates comparing two sample sheets — same format or cross-format —
to detect header changes, added/removed samples, and per-field sample diffs.

    Scenario 1: Identical sheets   — diff reports no changes (exit-0 analogue)
    Scenario 2: Header change      — experiment name updated between runs
    Scenario 3: Sample added       — a new sample appears in the newer sheet
    Scenario 4: Sample field change — an index was corrected
    Scenario 5: Cross-format diff  — compare a V1 sheet against its V2 conversion

Run from the repo root::

    python3 examples/demo_diff.py
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from samplesheet_parser import SampleSheetDiff

SHEETS = Path(__file__).parent / "sample_sheets"

_V1_BASE = textwrap.dedent(
    """\
    [Header]
    IEMFileVersion,5
    Experiment Name,Run_001
    Date,2024-01-15
    Workflow,GenerateFASTQ
    Chemistry,Amplicon

    [Reads]
    151
    151

    [Settings]
    Adapter,AGATCGGAAGAGCACACGTCTGAACTCCAGTCA

    [Data]
    Lane,Sample_ID,Sample_Name,index,index2,Sample_Project
    1,SampleA,SampleAlpha,CAAGACAGAT,ACTATAGCCT,ProjectX
    1,SampleB,SampleBeta,TGAACCTGAT,TGATACGTCC,ProjectX
"""
)


def _write_tmp(name: str, content: str) -> Path:
    p = Path("/tmp") / name
    p.write_text(content, encoding="utf-8")
    return p


def _print_diff(label: str, old: Path, new: Path) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  old: {old.name}   new: {new.name}")
    print("=" * 60)

    result = SampleSheetDiff(str(old), str(new)).compare()
    print(f"  Has changes : {result.has_changes}")
    print(f"  Summary     : {result.summary()}")

    if result.header_changes:
        print("\n  Header / settings changes:")
        for c in result.header_changes:
            print(f"    {c.field}: {c.old_value!r} → {c.new_value!r}")

    if result.samples_added:
        print(f"\n  Samples added   : {result.samples_added}")

    if result.samples_removed:
        print(f"\n  Samples removed : {result.samples_removed}")

    if result.sample_changes:
        print("\n  Per-sample field changes:")
        for sc in result.sample_changes:
            for field, (old_val, new_val) in sc.changes.items():
                print(f"    {sc.sample_id} — {field}: {old_val!r} → {new_val!r}")


# ---------------------------------------------------------------------------
# Scenario 1: Identical sheets
# ---------------------------------------------------------------------------

old = _write_tmp("diff_base.csv", _V1_BASE)
new = _write_tmp("diff_identical.csv", _V1_BASE)
_print_diff("Scenario 1: Identical sheets", old, new)

# ---------------------------------------------------------------------------
# Scenario 2: Header change (experiment name updated)
# ---------------------------------------------------------------------------

updated_header = _V1_BASE.replace("Run_001", "Run_002")
new = _write_tmp("diff_header.csv", updated_header)
_print_diff("Scenario 2: Header change", old, new)

# ---------------------------------------------------------------------------
# Scenario 3: Sample added
# ---------------------------------------------------------------------------

with_extra = _V1_BASE + "1,SampleC,SampleGamma,GCACAACGTT,CATCTCACAG,ProjectX\n"
new = _write_tmp("diff_sample_added.csv", with_extra)
_print_diff("Scenario 3: Sample added", old, new)

# ---------------------------------------------------------------------------
# Scenario 4: Index corrected on SampleB
# ---------------------------------------------------------------------------

corrected = _V1_BASE.replace("TGAACCTGAT", "AACCGTGATC")
new = _write_tmp("diff_index_fix.csv", corrected)
_print_diff("Scenario 4: Index corrected", old, new)

# ---------------------------------------------------------------------------
# Scenario 5: Cross-format diff (V1 vs its V2 conversion)
# ---------------------------------------------------------------------------

from samplesheet_parser import SampleSheetConverter  # noqa: E402

v1_sheet = SHEETS / "v1_dual_index.csv"
v2_out = Path("/tmp/diff_v2_converted.csv")
SampleSheetConverter(str(v1_sheet)).to_v2(str(v2_out))

_print_diff("Scenario 5: Cross-format diff (V1 vs V2 conversion)", v1_sheet, v2_out)

# Clean up
for f in [
    old,
    new,
    v2_out,
    Path("/tmp/diff_base.csv"),
    Path("/tmp/diff_identical.csv"),
    Path("/tmp/diff_header.csv"),
    Path("/tmp/diff_sample_added.csv"),
    Path("/tmp/diff_index_fix.csv"),
]:
    f.unlink(missing_ok=True)
