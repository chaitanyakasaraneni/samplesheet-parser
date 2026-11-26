"""Shared helpers for the version-specific sample sheet parsers."""

from __future__ import annotations


def strip_trailing_empty_fields(line: str) -> str:
    """Drop trailing empty comma-separated fields from a CSV line.

    Spreadsheet exports (Excel, Numbers, Google Sheets) pad every row to the
    width of the widest row, so a ``key,value`` pair is written out as
    ``key,value,,,``. Those trailing empty fields are padding, not data.
    Without removing them a ``split(",", 1)`` folds the padding into the
    value (``"value,,,"``), which then fails to parse as an integer or is
    rejected as a malformed adapter.

    Only *trailing* empty fields are removed; interior fields and the key are
    always preserved, so a genuine value is never truncated.

    >>> strip_trailing_empty_fields("Read1Cycles,28,,,,")
    'Read1Cycles,28'
    >>> strip_trailing_empty_fields("Adapter,CTGTCTCTTATACACATCT,,,")
    'Adapter,CTGTCTCTTATACACATCT'
    >>> strip_trailing_empty_fields("Read1Cycles,28")
    'Read1Cycles,28'
    """
    fields = line.split(",")
    while len(fields) > 1 and fields[-1].strip() == "":
        fields.pop()
    return ",".join(fields)
