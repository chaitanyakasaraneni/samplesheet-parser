"""
Demo: colour-balance validation on a 2-channel instrument.

Colour balance is a property of the *index sequences* in the sheet, so it can
be predicted before a run starts - no sequencing data required. On 2-channel
chemistry (NextSeq, NovaSeq, AVITI) ``G`` is a dark base: a cycle where every
sample reads ``G`` produces no optical signal and the index read fails.

This builds a small NovaSeq X pool that is fine on Hamming distance but has a
dark cycle, and shows the validator catching it.

Run with:  python3 examples/demo_color_balance.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from samplesheet_parser import (
    SampleSheetFactory,
    SampleSheetValidator,
    analyze_color_balance,
    chemistry_for_instrument,
)

# A NovaSeq X (2-channel) pool. Look down each column of the I7 index:
# every sample reads 'G' at cycle 3 and cycle 4 -> a dark, no-signal cycle.
# The indexes are still far apart in Hamming distance, so the usual index
# checks would pass this sheet.
SHEET = """\
[Header]
FileFormatVersion,2
RunName,DarkCycleDemo
InstrumentPlatform,NovaSeqXSeries

[Reads]
Read1Cycles,151
Read2Cycles,151
Index1Cycles,8
Index2Cycles,8

[BCLConvert_Settings]
AdapterRead1,CTGTCTCTTATACACATCT

[BCLConvert_Data]
Sample_ID,Index,Index2
S1,ATGGCTAC,TATAGCCT
S2,CAGGTACG,ATAGAGGC
S3,TCGGACGT,CCTATCCT
S4,GATGGCTA,GGCTCTGA
"""


def main() -> None:
    print("Chemistry for 'NovaSeqXSeries':", chemistry_for_instrument("NovaSeqXSeries").value)
    print()

    # The standalone analyzer, straight on the index list:
    index1 = ["ATGGCTAC", "CAGGTACG", "TCGGACGT", "GATGGCTA"]
    report = analyze_color_balance(index1, chemistry=chemistry_for_instrument("NovaSeqXSeries"))
    print(f"Pool of {report.pool_size} samples - per-cycle scan of I7:")
    for cb in report.cycles:
        flag = "  <-- DARK (no signal)" if cb.is_dark else ""
        print(
            f"  cycle {cb.cycle}: {cb.base_counts} "
            f"red={cb.red_fraction:.0%} green={cb.green_fraction:.0%}{flag}"
        )
    print()

    # End to end through the factory + validator:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "SampleSheet.csv"
        path.write_text(SHEET)

        sheet = SampleSheetFactory().create_parser(path, parse=True)
        result = SampleSheetValidator().validate(sheet, check_color_balance=True)

        print(result.summary())
        for issue in result.errors + result.warnings:
            print(f"  {issue}")


if __name__ == "__main__":
    main()
