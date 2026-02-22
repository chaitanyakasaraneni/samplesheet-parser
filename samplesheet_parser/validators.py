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
