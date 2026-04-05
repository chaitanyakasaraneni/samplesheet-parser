"""
Index normalization utilities for Illumina sample sheets.

When merging sheets from different projects, indexes may have been designed
with different lengths (e.g. 8 bp vs 10 bp).  This can cause
``INDEX_DISTANCE_TOO_LOW`` or ``INDEX_COLLISION`` errors at merge time because
the comparison is length-aware (shorter sequence wins).

Two strategies are provided:

``"trim"``
    Trim all index sequences to the length of the *shortest* index in the
    sample list.  Safe when the extra cycles are padding bases.

``"pad"``
    Pad shorter indexes to the length of the *longest* index using ``"N"``
    wildcard characters.  ``"N"`` matches any base during demultiplexing in
    BCLConvert ≥ 3.9 and bcl2fastq ≥ 2.20.

Examples
--------
>>> from samplesheet_parser import SampleSheetFactory
>>> from samplesheet_parser.index_utils import normalize_index_lengths
>>>
>>> sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
>>> normalized = normalize_index_lengths(sheet.samples(), strategy="trim")
>>> for s in normalized:
...     print(s["sample_id"], s.get("index") or s.get("Index"))

Authors
-------
Chaitanya Kasaraneni
"""

from __future__ import annotations

from typing import Any, Literal


def normalize_index_lengths(
    samples: list[dict[str, Any]],
    strategy: Literal["trim", "pad"] = "trim",
    *,
    index1_key: str | None = None,
    index2_key: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize index sequence lengths across all samples.

    Detects whether the samples use V1-style keys (``"index"`` / ``"index2"``)
    or V2-style keys (``"Index"`` / ``"Index2"``) automatically, unless
    ``index1_key`` / ``index2_key`` are supplied explicitly.

    Parameters
    ----------
    samples:
        Output of ``sheet.samples()``.  Not modified in place — the
        function returns new dicts with the index values replaced.
    strategy:
        ``"trim"`` — trim all indexes to the length of the shortest
        sequence in *samples* (default).

        ``"pad"``  — pad all indexes to the length of the longest
        sequence using ``"N"`` wildcard characters.
    index1_key:
        Override the dict key for the primary index (I7).  Auto-detected
        from the first sample that has an index value if ``None``.
    index2_key:
        Override the dict key for the secondary index (I5).  Auto-detected
        from the first sample that has an index2 value if ``None``.  Pass
        an explicit value of ``""`` to suppress I5 normalization entirely.

    Returns
    -------
    list[dict]
        Shallow copies of the input dicts with index values replaced.
        Samples that have no index are returned unchanged.

    Raises
    ------
    ValueError
        If *strategy* is not ``"trim"`` or ``"pad"``.

    Examples
    --------
    >>> samples = [
    ...     {"sample_id": "S1", "index": "ATTACTCG",   "index2": "TATAGCCT"},
    ...     {"sample_id": "S2", "index": "TCCGGAGAGG", "index2": "ATAGAGGCTA"},
    ... ]
    >>> normalize_index_lengths(samples, strategy="trim")
    [{'sample_id': 'S1', 'index': 'ATTACTCG', 'index2': 'TATAGCCT'},
     {'sample_id': 'S2', 'index': 'TCCGGAGA', 'index2': 'ATAGAGGC'}]

    >>> normalize_index_lengths(samples, strategy="pad")
    [{'sample_id': 'S1', 'index': 'ATTACTCGNN', 'index2': 'TATAGCCTNN'},
     {'sample_id': 'S2', 'index': 'TCCGGAGAGG', 'index2': 'ATAGAGGCTA'}]
    """
    if strategy not in ("trim", "pad"):
        raise ValueError(f"strategy must be 'trim' or 'pad', got {strategy!r}")

    if not samples:
        return []

    # ── Auto-detect key names ────────────────────────────────────────────────
    if index1_key is None:
        index1_key = _detect_key(samples, ("index", "Index"))
    if index2_key is None:
        index2_key = _detect_key(samples, ("index2", "Index2"))

    # ── Collect index lengths ────────────────────────────────────────────────
    i1_lengths: list[int] = []
    i2_lengths: list[int] = []

    for s in samples:
        if index1_key:
            v = s.get(index1_key)
            if v:
                i1_lengths.append(len(v))
        if index2_key:
            v = s.get(index2_key)
            if v:
                i2_lengths.append(len(v))

    # If all samples have the same length already, return copies unchanged.
    i1_uniform = len(set(i1_lengths)) <= 1
    i2_uniform = len(set(i2_lengths)) <= 1
    if i1_uniform and i2_uniform:
        return [dict(s) for s in samples]

    # ── Determine target lengths ─────────────────────────────────────────────
    if strategy == "trim":
        target_i1 = min(i1_lengths) if i1_lengths else 0
        target_i2 = min(i2_lengths) if i2_lengths else 0
    else:  # pad
        target_i1 = max(i1_lengths) if i1_lengths else 0
        target_i2 = max(i2_lengths) if i2_lengths else 0

    # ── Apply normalization ──────────────────────────────────────────────────
    result: list[dict[str, Any]] = []
    for sample in samples:
        out = dict(sample)

        if index1_key and target_i1:
            v1: str | None = out.get(index1_key)
            if v1:
                out[index1_key] = _apply(v1, target_i1, strategy)

        if index2_key and target_i2:
            v2: str | None = out.get(index2_key)
            if v2:
                out[index2_key] = _apply(v2, target_i2, strategy)

        result.append(out)

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_key(samples: list[dict[str, Any]], candidates: tuple[str, ...]) -> str:
    """Return the first candidate key that has at least one non-empty value.

    Falls back to key *presence* (regardless of value) if no candidate has
    any non-empty value, and finally to the first candidate name if none are
    present at all.
    """
    # Prefer a key that actually carries data
    for key in candidates:
        if any(s.get(key) for s in samples):
            return key
    # Fall back to key presence (all values empty/None but key exists)
    for key in candidates:
        if any(key in s for s in samples):
            return key
    return candidates[0]


def _apply(seq: str, target_length: int, strategy: str) -> str:
    """Trim or pad *seq* to *target_length*."""
    if strategy == "trim":
        return seq[:target_length]
    # pad
    return seq.ljust(target_length, "N")
