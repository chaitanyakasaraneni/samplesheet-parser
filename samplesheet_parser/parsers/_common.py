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


def duplicate_columns(columns: list[str]) -> list[str]:
    """Return the non-empty column names in *columns* that appear more than once.

    A data-section header with a repeated column name (e.g. ``Sample_ID,Index,
    Index``) silently loses data: the parsers build each record as a dict keyed
    by column name, so the second occurrence overwrites the first and the
    earlier value is discarded. Callers use this to warn about that loss.

    The result is sorted and de-duplicated, so each repeated name is reported
    once. Empty column names (comma padding) are ignored - they are handled
    separately by :func:`strip_trailing_empty_fields` and the empty-name drop.

    >>> duplicate_columns(["Sample_ID", "Index", "Index"])
    ['Index']
    >>> duplicate_columns(["Sample_ID", "Index", "Index2"])
    []
    """
    counts: dict[str, int] = {}
    for col in columns:
        if col:
            counts[col] = counts.get(col, 0) + 1
    return sorted(name for name, n in counts.items() if n > 1)
