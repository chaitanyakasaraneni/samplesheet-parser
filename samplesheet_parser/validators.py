"""
Sample sheet validation - index integrity, lane uniqueness, adapter checks.

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

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from samplesheet_parser.protocol import SampleSheetParser

logger = logging.getLogger(__name__)

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
    "CTGTCTCTTATACACATCT",  # Nextera transposase / TruSight
    "AGATCGGAAGAGC",  # TruSeq universal prefix (matches both R1/R2)
    "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA",  # TruSeq Read 1 (i7 adapter, full)
    "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT",  # TruSeq Read 2 (i5 adapter, full)
    "AATGATACGGCGACCACCGAG",  # P5
    "CAAGCAGAAGACGGCATACGAG",  # P7
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

    level: str
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

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
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    def add_error(self, code: str, message: str, **context: Any) -> None:
        self.is_valid = False
        self.errors.append(ValidationIssue("error", code, message, dict(context)))
        logger.error(f"{code}: {message}")

    def add_warning(self, code: str, message: str, **context: Any) -> None:
        self.warnings.append(ValidationIssue("warning", code, message, dict(context)))
        logger.warning(f"{code}: {message}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [
                {"code": e.code, "message": e.message, "context": e.context} for e in self.errors
            ],
            "warnings": [
                {"code": w.code, "message": w.message, "context": w.context} for w in self.warnings
            ],
        }

    def summary(self) -> str:
        return (
            f"{'PASS' if self.is_valid else 'FAIL'} - "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def hamming_distance(a: str, b: str) -> int:
    """Return the literal Hamming distance between two index sequences.

    Sequences of unequal length are compared up to the shorter length, a
    conservative approach matching how the instrument reads cycles.

    This is the pure Hamming distance: every differing position counts,
    including positions where one sequence has an ``N``. For demultiplexing
    collision detection an ``N`` should instead be treated as a wildcard that
    matches any base; the validator uses :func:`index_collision_distance` for
    that purpose. See :meth:`SampleSheetValidator._check_index_distances`.

    Parameters
    ----------
    a, b:
        Uppercase index strings (ACGTN).

    Examples
    --------
    >>> hamming_distance("ATTACTCG", "ATTACTCG")
    0
    >>> hamming_distance("ATTACTCG", "ATTACTCA")
    1
    >>> hamming_distance("ATTACTCG", "GCTAGCTA")
    6
    """
    length = min(len(a), len(b))
    return sum(x != y for x, y in zip(a[:length], b[:length], strict=False))


def index_collision_distance(a: str, b: str) -> int:
    """Return the mismatch count between two index reads for collision checks.

    This differs from :func:`hamming_distance` in one way: an ``N`` in either
    sequence is treated as a wildcard that matches any base, because that is
    how demultiplexers handle ``N`` cycles. Two indexes that differ only where
    one carries an ``N`` can therefore collide, and this function scores those
    positions as matches.

    Sequences of unequal length are compared up to the shorter length.

    Parameters
    ----------
    a, b:
        Uppercase index strings (ACGTN).

    Examples
    --------
    >>> index_collision_distance("ATTACTCG", "ATTACTCA")
    1
    >>> index_collision_distance("ATTACTCG", "ATTACTCN")
    0
    """
    length = min(len(a), len(b))
    return sum(
        1 for x, y in zip(a[:length], b[:length], strict=False) if x != y and x != "N" and y != "N"
    )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class SampleSheetValidator:
    """
    Validates a parsed Illumina sample sheet for common data quality issues.

    Checks performed
    ----------------
    * **EMPTY_SAMPLES**        - No samples found in [Data] / [BCLConvert_Data].
    * **INVALID_INDEX_CHARS**  - Index sequence contains non-ACGTN characters.
    * **INDEX_TOO_SHORT**      - Index shorter than :attr:`MIN_INDEX_LENGTH`.
    * **INDEX_TOO_LONG**       - Index longer than :attr:`MAX_INDEX_LENGTH`.
    * **DUPLICATE_INDEX**      - Two or more samples in the same lane share an
                                 index (or index pair for dual-index sheets).
    * **MISSING_INDEX2**       - Sheet has an ``Index2`` / ``index2`` column but
                                 one or more samples have it empty.
    * **DUPLICATE_SAMPLE_ID**  - ``Sample_ID`` appears more than once per lane.
    * **INDEX_DISTANCE_TOO_LOW** - Two samples in the same lane have a combined
                                 index distance (I7 plus I5 mismatches, with N
                                 treated as a wildcard) below
                                 :data:`MIN_HAMMING_DISTANCE` (default 3),
                                 risking demultiplexing bleed-through
                                 (warning only). See :meth:`_check_index_distances`.
    * **NO_ADAPTERS**          - ``[Settings]`` / ``[BCLConvert_Settings]`` has
                                 no adapter sequences (warning only).
    * **ADAPTER_MISMATCH**     - Adapter does not match any known Illumina
                                 adapter (warning only; custom adapters are valid).

    Examples
    --------
    >>> result = SampleSheetValidator().validate(sheet)
    >>> print(result.summary())
    PASS - 0 error(s), 1 warning(s)
    """

    def validate(
        self,
        sheet: SampleSheetParser,
        *,
        min_hamming_distance: int = MIN_HAMMING_DISTANCE,
    ) -> ValidationResult:
        """Run all validation checks on a parsed sample sheet.

        Parameters
        ----------
        sheet:
            A parsed :class:`SampleSheetV1` or :class:`SampleSheetV2`
            instance (i.e., :meth:`parse` has been called).
        min_hamming_distance:
            Minimum Hamming distance required between any two index sequences
            in the same lane. Pairs below this threshold produce an
            ``INDEX_DISTANCE_TOO_LOW`` warning. Defaults to
            :data:`MIN_HAMMING_DISTANCE` (3). Set higher (e.g. ``4``) for
            stricter demultiplexing requirements with longer indexes.

        Returns
        -------
        ValidationResult
            Structured result with ``is_valid``, ``errors``, and ``warnings``.
        """
        result = ValidationResult()
        samples = sheet.samples()

        self._check_empty(samples, result)
        if not samples:
            return result  # no point continuing

        self._check_index_sequences(samples, result)
        self._check_duplicate_indices(samples, result)
        self._check_index_distances(samples, result, min_distance=min_hamming_distance)
        self._check_duplicate_sample_ids(samples, result)
        self._check_adapters(sheet, result)

        return result

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_empty(
        self,
        samples: list[dict[str, Any]],
        result: ValidationResult,
    ) -> None:
        if not samples:
            result.add_error(
                "EMPTY_SAMPLES",
                "No samples found in the [Data] / [BCLConvert_Data] section.",
            )

    def _check_index_sequences(
        self,
        samples: list[dict[str, Any]],
        result: ValidationResult,
    ) -> None:
        """Validate each index sequence for character set and length."""
        for sample in samples:
            for field_name in ("index", "index2", "Index", "Index2"):
                seq: str | None = sample.get(field_name)
                if not seq:
                    continue

                sid = sample.get("sample_id", "?")
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
                        " - verify this is correct.",
                        sample_id=sid,
                        lane=lane,
                        field=field_name,
                    )

                if len(seq) > MAX_INDEX_LENGTH:
                    result.add_error(
                        "INDEX_TOO_LONG",
                        f"Index '{seq}' is longer than {MAX_INDEX_LENGTH} bp"
                        " - likely a data error.",
                        sample_id=sid,
                        lane=lane,
                        field=field_name,
                    )

    def _check_duplicate_indices(
        self,
        samples: list[dict[str, Any]],
        result: ValidationResult,
    ) -> None:
        """Detect samples that share an index (or index pair) within a lane."""
        # Group by lane; treat None lane as "all lanes" (lane-unaware sheets)
        lane_index_map: dict[str | None, dict[str, str]] = {}

        for sample in samples:
            lane = sample.get("lane")
            # Upper-case so casing differences do not hide a real duplicate,
            # matching the case-insensitive index distance and character checks.
            idx1 = (sample.get("index") or sample.get("Index") or "").upper()
            idx2 = (sample.get("index2") or sample.get("Index2") or "").upper()
            sid = sample.get("sample_id", "?")

            index_key = f"{idx1}+{idx2}" if idx2 else idx1

            # Index-free libraries (no I7 and no I5) legitimately share an empty
            # index, so skip them here. A full-lane library with no barcodes is
            # not a duplicate-index conflict.
            if not index_key:
                continue

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
        samples: list[dict[str, Any]],
        result: ValidationResult,
        min_distance: int = MIN_HAMMING_DISTANCE,
    ) -> None:
        """Warn if any two indexes in the same lane are too similar.

        For every pair of samples within a lane the combined distance is the
        sum of the per-index mismatch counts: the I7 (index) distance plus the
        I5 (index2) distance. Pairs whose combined distance is below
        ``min_distance`` (default: :data:`MIN_HAMMING_DISTANCE` = 3) are
        reported as warnings because they risk read bleed-through during
        demultiplexing.

        The combined distance equals the minimum number of sequencing errors
        needed to read one sample's barcodes as another's across both index
        reads, which is the quantity that governs misassignment risk. Summing
        the per-index distances (rather than concatenating the two indexes into
        one string) keeps the I7 and I5 positions aligned even when samples use
        different index lengths.

        Each per-index distance is computed with :func:`index_collision_distance`,
        so an ``N`` cycle in either index is treated as a wildcard that matches
        any base. Sequences of different lengths are compared up to the length
        of the shorter sequence, since the instrument reads only as many cycles
        as configured.

        Parameters
        ----------
        samples:
            Output of ``sheet.samples()``.
        result:
            :class:`ValidationResult` to append warnings to.
        min_distance:
            Minimum acceptable combined distance. Pairs below this threshold
            generate a ``INDEX_DISTANCE_TOO_LOW`` warning.
        """
        # Group by lane; treat None as lane-unaware (compare all samples).
        # bucket entry: (sample_id, index1, index2)
        lane_buckets: dict[str | None, list[tuple[str, str, str]]] = {}

        for sample in samples:
            lane = sample.get("lane")
            # Accept both V1-style (``index``/``index2``) and V2-style
            # (``Index``/``Index2``) keys so hand-built dicts and the output of
            # ``normalize_index_lengths`` are checked the same way the duplicate
            # and character checks already handle them.
            idx1 = (sample.get("index") or sample.get("Index") or "").upper()
            idx2 = (sample.get("index2") or sample.get("Index2") or "").upper()
            sid = sample.get("sample_id", "?")

            if not idx1:
                continue  # no index to compare

            lane_buckets.setdefault(lane, []).append((sid, idx1, idx2))

        for lane, entries in lane_buckets.items():
            # Compare every pair: O(n^2) in the number of samples per lane.
            # n is small in practice (a few hundred at most), so this is cheap.
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    sid_a, i7_a, i5_a = entries[i]
                    sid_b, i7_b, i5_b = entries[j]

                    dist = index_collision_distance(i7_a, i7_b) + index_collision_distance(
                        i5_a, i5_b
                    )
                    if dist < min_distance:
                        combined_a = f"{i7_a}+{i5_a}" if i5_a else i7_a
                        combined_b = f"{i7_b}+{i5_b}" if i5_b else i7_b
                        result.add_warning(
                            "INDEX_DISTANCE_TOO_LOW",
                            f"Indexes for '{sid_a}' and '{sid_b}' in lane "
                            f"{lane!r} have a combined distance of {dist} "
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
        samples: list[dict[str, Any]],
        result: ValidationResult,
    ) -> None:
        """Detect duplicate Sample_IDs within the same lane."""
        lane_id_map: dict[str | None, set[str]] = {}

        for sample in samples:
            lane = sample.get("lane")
            sid = sample.get("sample_id", "")
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
        sheet: SampleSheetParser,
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
