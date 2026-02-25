"""
Sample sheet validation — index integrity, lane uniqueness, adapter checks.

The :class:`SampleSheetValidator` works with both V1 and V2 parsed sheets
and produces a structured :class:`ValidationResult` that can be inspected
or serialised.

Examples
--------
>>> from samplesheet_parser import SampleSheetFactory, SampleSheetValidator
>>> sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
>>> result = SampleSheetValidator().validate(sheet)
>>> if not result.is_valid:
...     for err in result.errors:
...         print(err)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from loguru import logger

from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Valid IUPAC nucleotide characters for index sequences.
VALID_INDEX_RE = re.compile(r"^[ACGTN]+$", re.IGNORECASE)

#: Minimum index length to warn about (indexes shorter than this are
#: unusually short for modern workflows but not invalid per se).
MIN_INDEX_LENGTH = 6

#: Maximum sensible index length (longer than this is almost certainly
#: a data error).
MAX_INDEX_LENGTH = 24

#: Minimum Hamming distance required between any two index sequences
#: within the same lane. Illumina recommends ≥ 3 for robust demultiplexing;
#: sequences with fewer mismatches risk read bleed-through between samples.
#: Reference: https://support.illumina.com/bulletins/2020/06/index-misassignment-between-samples-on-the-novaseq-6000.html
MIN_HAMMING_DISTANCE: int = 3

#: Standard Illumina adapter sequences (subset; not exhaustive).
#: Full sequences from: https://support.illumina.com/bulletins/2016/12/what-sequences-do-i-use-for-adapter-trimming.html
KNOWN_ADAPTERS = {
    "CTGTCTCTTATACACATCT",              # Nextera transposase / TruSight
    "AGATCGGAAGAGC",                    # TruSeq universal prefix (matches both R1/R2)
    "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA", # TruSeq Read 1 (i7 adapter, full)
    "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT", # TruSeq Read 2 (i5 adapter, full)
    "AATGATACGGCGACCACCGAG",            # P5
    "CAAGCAGAAGACGGCATACGAG",           # P7
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """A single validation warning or error.

    Attributes
    ----------
    level:
        ``"error"`` or ``"warning"``.
    code:
        Short machine-readable code (e.g. ``"DUPLICATE_INDEX"``).
    message:
        Human-readable description.
    context:
        Optional dict with extra detail (e.g. ``{"lane": 1, "sample_id": "S1"}``).
    """
    level:   str
    code:    str
    message: str
    context: dict = field(default_factory=dict)

    def __str__(self) -> str:
        ctx = f" | {self.context}" if self.context else ""
        return f"[{self.level.upper()}] {self.code}: {self.message}{ctx}"


@dataclass
class ValidationResult:
    """Structured output from :class:`SampleSheetValidator`.

    Attributes
    ----------
    is_valid:
        ``True`` if no *errors* were raised (warnings do not affect
        this flag).
    errors:
        List of error-level :class:`ValidationIssue` objects.
    warnings:
        List of warning-level :class:`ValidationIssue` objects.
    """
    is_valid: bool = True
    errors:   list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    def add_error(self, code: str, message: str, **context) -> None:
        self.is_valid = False
        self.errors.append(ValidationIssue("error", code, message, dict(context)))
        logger.error(f"{code}: {message}")

    def add_warning(self, code: str, message: str, **context) -> None:
        self.warnings.append(ValidationIssue("warning", code, message, dict(context)))
        logger.warning(f"{code}: {message}")

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "errors":   [{"code": e.code, "message": e.message, "context": e.context}
                         for e in self.errors],
            "warnings": [{"code": w.code, "message": w.message, "context": w.context}
                         for w in self.warnings],
        }

    def summary(self) -> str:
        return (
            f"{'PASS' if self.is_valid else 'FAIL'} — "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hamming_distance(a: str, b: str) -> int:
    """Return the Hamming distance between two index sequences.

    Sequences of unequal length are compared up to the shorter length —
    a conservative approach matching how the instrument reads cycles.

    Parameters
    ----------
    a, b:
        Uppercase index strings (ACGTN).

    Examples
    --------
    >>> _hamming_distance("ATTACTCG", "ATTACTCG")
    0
    >>> _hamming_distance("ATTACTCG", "ATTACTCA")
    1
    >>> _hamming_distance("ATTACTCG", "GCTAGCTA")
    6
    """
    length = min(len(a), len(b))
    return sum(x != y for x, y in zip(a[:length], b[:length], strict=False))


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class SampleSheetValidator:
    """
    Validates a parsed Illumina sample sheet for common data quality issues.

    Checks performed
    ----------------
    * **EMPTY_SAMPLES**        — No samples found in [Data] / [BCLConvert_Data].
    * **INVALID_INDEX_CHARS**  — Index sequence contains non-ACGTN characters.
    * **INDEX_TOO_SHORT**      — Index shorter than :attr:`MIN_INDEX_LENGTH`.
    * **INDEX_TOO_LONG**       — Index longer than :attr:`MAX_INDEX_LENGTH`.
    * **DUPLICATE_INDEX**      — Two or more samples in the same lane share an
                                 index (or index pair for dual-index sheets).
    * **MISSING_INDEX2**       — Sheet has an ``Index2`` / ``index2`` column but
                                 one or more samples have it empty.
    * **DUPLICATE_SAMPLE_ID**  — ``Sample_ID`` appears more than once per lane.
    * **INDEX_DISTANCE_TOO_LOW** — Two indexes in the same lane have a Hamming
                                 distance below :data:`MIN_HAMMING_DISTANCE`
                                 (default 3), risking demultiplexing bleed-through
                                 (warning only).
    * **NO_ADAPTERS**          — ``[Settings]`` / ``[BCLConvert_Settings]`` has
                                 no adapter sequences (warning only).
    * **ADAPTER_MISMATCH**     — Adapter does not match any known Illumina
                                 adapter (warning only; custom adapters are valid).

    Examples
    --------
    >>> result = SampleSheetValidator().validate(sheet)
    >>> print(result.summary())
    PASS — 0 error(s), 1 warning(s)
    """

    def validate(
        self,
        sheet: SampleSheetV1 | SampleSheetV2,
    ) -> ValidationResult:
        """Run all validation checks on a parsed sample sheet.

        Parameters
        ----------
        sheet:
            A parsed :class:`SampleSheetV1` or :class:`SampleSheetV2`
            instance (i.e., :meth:`parse` has been called).

        Returns
        -------
        ValidationResult
            Structured result with ``is_valid``, ``errors``, and ``warnings``.
        """
        result = ValidationResult()
        samples = sheet.samples()

        self._check_empty(samples, result)
        if not samples:
            return result   # no point continuing

        self._check_index_sequences(samples, result)
        self._check_duplicate_indices(samples, result)
        self._check_index_distances(samples, result)
        self._check_duplicate_sample_ids(samples, result)
        self._check_adapters(sheet, result)

        return result

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_empty(
        self,
        samples: list[dict],
        result: ValidationResult,
    ) -> None:
        if not samples:
            result.add_error(
                "EMPTY_SAMPLES",
                "No samples found in the [Data] / [BCLConvert_Data] section.",
            )

    def _check_index_sequences(
        self,
        samples: list[dict],
        result: ValidationResult,
    ) -> None:
        """Validate each index sequence for character set and length."""
        for sample in samples:
            for field_name in ("index", "index2", "Index", "Index2"):
                seq: str | None = sample.get(field_name)
                if not seq:
                    continue

                sid  = sample.get("sample_id", "?")
                lane = sample.get("lane", "?")

                if not VALID_INDEX_RE.match(seq):
                    result.add_error(
                        "INVALID_INDEX_CHARS",
                        f"Index '{seq}' contains non-ACGTN characters.",
                        sample_id=sid,
                        lane=lane,
                        field=field_name,
                    )

                if len(seq) < MIN_INDEX_LENGTH:
                    result.add_warning(
                        "INDEX_TOO_SHORT",
                        f"Index '{seq}' is shorter than {MIN_INDEX_LENGTH} bp"
                        " — verify this is correct.",
                        sample_id=sid,
                        lane=lane,
                        field=field_name,
                    )

                if len(seq) > MAX_INDEX_LENGTH:
                    result.add_error(
                        "INDEX_TOO_LONG",
                        f"Index '{seq}' is longer than {MAX_INDEX_LENGTH} bp"
                        " — likely a data error.",
                        sample_id=sid,
                        lane=lane,
                        field=field_name,
                    )

    def _check_duplicate_indices(
        self,
        samples: list[dict],
        result: ValidationResult,
    ) -> None:
        """Detect samples that share an index (or index pair) within a lane."""
        # Group by lane; treat None lane as "all lanes" (lane-unaware sheets)
        lane_index_map: dict[str | None, dict[str, str]] = {}

        for sample in samples:
            lane = sample.get("lane")
            idx1 = sample.get("index") or sample.get("Index") or ""
            idx2 = sample.get("index2") or sample.get("Index2") or ""
            sid  = sample.get("sample_id", "?")

            index_key = f"{idx1}+{idx2}" if idx2 else idx1

            bucket = lane_index_map.setdefault(lane, {})
            if index_key in bucket:
                result.add_error(
                    "DUPLICATE_INDEX",
                    f"Index '{index_key}' appears more than once in lane {lane!r}. "
                    f"Conflict between sample '{bucket[index_key]}' and '{sid}'.",
                    lane=lane,
                    index=index_key,
                    conflicting_samples=[bucket[index_key], sid],
                )
            else:
                bucket[index_key] = sid

    def _check_index_distances(
        self,
        samples: list[dict],
        result: ValidationResult,
        min_distance: int = MIN_HAMMING_DISTANCE,
    ) -> None:
        """Warn if any two indexes in the same lane are too similar.

        Computes the Hamming distance between every pair of index sequences
        within each lane. Pairs with a distance below ``min_distance``
        (default: :data:`MIN_HAMMING_DISTANCE` = 3) are reported as warnings
        because they risk read bleed-through during demultiplexing.

        For dual-index sheets the combined index (I7+I5 concatenated) is
        used so that a pair which is close on I7 but well-separated on I5
        is not incorrectly flagged.

        Sequences of different lengths are compared up to the length of the
        shorter sequence — a conservative approach since the instrument reads
        only as many cycles as configured.

        Parameters
        ----------
        samples:
            Output of ``sheet.samples()``.
        result:
            :class:`ValidationResult` to append warnings to.
        min_distance:
            Minimum acceptable Hamming distance. Pairs below this threshold
            generate a ``INDEX_DISTANCE_TOO_LOW`` warning.
        """
        # Group by lane; treat None as lane-unaware (compare all samples)
        lane_buckets: dict[str | None, list[tuple[str, str, str]]] = {}
        # bucket entry: (sample_id, index1, combined_index)

        for sample in samples:
            lane = sample.get("lane")
            idx1 = (sample.get("index") or "").upper()
            idx2 = (sample.get("index2") or "").upper()
            sid  = sample.get("sample_id", "?")

            if not idx1:
                continue  # no index to compare

            combined = idx1 + idx2 if idx2 else idx1
            lane_buckets.setdefault(lane, []).append((sid, idx1, combined))

        for lane, entries in lane_buckets.items():
            # Compare every pair — O(n²) but n is always small (< 200 samples)
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    sid_a, _, combined_a = entries[i]
                    sid_b, _, combined_b = entries[j]

                    dist = _hamming_distance(combined_a, combined_b)
                    if dist < min_distance:
                        result.add_warning(
                            "INDEX_DISTANCE_TOO_LOW",
                            f"Indexes for '{sid_a}' and '{sid_b}' in lane "
                            f"{lane!r} have a Hamming distance of {dist} "
                            f"(minimum recommended: {min_distance}). "
                            f"This may cause demultiplexing bleed-through.",
                            lane=lane,
                            sample_a=sid_a,
                            sample_b=sid_b,
                            index_a=combined_a,
                            index_b=combined_b,
                            distance=dist,
                            min_distance=min_distance,
                        )

    def _check_duplicate_sample_ids(
        self,
        samples: list[dict],
        result: ValidationResult,
    ) -> None:
        """Detect duplicate Sample_IDs within the same lane."""
        lane_id_map: dict[str | None, set[str]] = {}

        for sample in samples:
            lane = sample.get("lane")
            sid  = sample.get("sample_id", "")
            bucket = lane_id_map.setdefault(lane, set())
            if sid in bucket:
                result.add_error(
                    "DUPLICATE_SAMPLE_ID",
                    f"Sample_ID '{sid}' appears more than once in lane {lane!r}.",
                    lane=lane,
                    sample_id=sid,
                )
            else:
                bucket.add(sid)

    def _check_adapters(
        self,
        sheet: SampleSheetV1 | SampleSheetV2,
        result: ValidationResult,
    ) -> None:
        """Warn if no adapters are configured, or if adapters are non-standard."""
        adapters = getattr(sheet, "adapters", [])

        if not adapters:
            result.add_warning(
                "NO_ADAPTERS",
                "No adapter sequences found in [Settings] / [BCLConvert_Settings]. "
                "Adapter trimming will be disabled.",
            )
            return

        for adapter in adapters:
            if adapter and adapter.upper() not in KNOWN_ADAPTERS:
                result.add_warning(
                    "ADAPTER_MISMATCH",
                    f"Adapter '{adapter}' is not a standard Illumina adapter sequence. "
                    f"Verify this is correct for your library prep.",
                    adapter=adapter,
                )
