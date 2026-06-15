"""
Demo: vendor-agnostic parsing of an Element Biosciences AVITI RunManifest.

The same ``SampleSheetFactory`` that auto-detects Illumina V1/V2 sheets also
recognises a non-Illumina AVITI ``RunManifest.csv`` and returns a parser with
the identical interface (``samples()``, ``index_type()``, ...). AVITI is a
four-channel avidity platform (no dark base), so the colour-balance validator
works on it too - flagging low-diversity index cycles rather than dark cycles.

Run with:  python3 examples/demo_element_aviti.py
"""

from __future__ import annotations

from pathlib import Path

from samplesheet_parser import (
    ElementRunManifest,
    SampleSheetFactory,
    SampleSheetParser,
    SampleSheetValidator,
)

MANIFEST = Path(__file__).parent / "sample_sheets" / "element_aviti_RunManifest.csv"


def main() -> None:
    factory = SampleSheetFactory()
    sheet = factory.create_parser(MANIFEST, parse=True)

    print(f"Detected format : {factory.version.value}")
    print(f"Parser class    : {type(sheet).__name__}")
    print(
        f"Same interface  : isinstance(sheet, SampleSheetParser) = "
        f"{isinstance(sheet, SampleSheetParser)}"
    )
    print(f"Is AVITI parser : {isinstance(sheet, ElementRunManifest)}")
    print(f"Index type      : {sheet.index_type()}")
    print(f"Adapters        : {sheet.adapters}")
    print()
    print("Samples (mapped to the shared schema):")
    for s in sheet.samples():
        print(
            f"  {s['sample_id']:4} {s['index']} + {s['index2']} "
            f"lane={s['lane']} project={s['sample_project']}"
        )
    print()

    # Colour balance runs on AVITI because it resolves to 4-channel chemistry.
    result = SampleSheetValidator().validate(sheet, check_color_balance=True)
    print(f"Validation (with colour balance): {result.summary()}")
    for issue in result.errors + result.warnings:
        print(f"  {issue}")


if __name__ == "__main__":
    main()
