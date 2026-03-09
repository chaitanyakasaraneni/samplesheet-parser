"""
Merge multiple per-project Illumina SampleSheet.csv files into a single
combined sheet for a flow-cell run.

This is the canonical workflow at sequencing cores that receive one sheet
per project and need to consolidate them before starting BCLConvert or
bcl2fastq.

Examples
--------
>>> from samplesheet_parser.merger import SampleSheetMerger
>>>
>>> merger = SampleSheetMerger()
>>> merger.add("ProjectA/SampleSheet.csv")
>>> merger.add("ProjectB/SampleSheet.csv")
>>> result = merger.merge("SampleSheet_combined.csv")
>>>
>>> if result.has_conflicts:
...     for c in result.conflicts:
...         print(c)
... else:
...     print(f"Merged {result.sample_count} samples → {result.output_path}")

Authors
-------
Chaitanya Kasaraneni

References
----------
Illumina BCLConvert Software Guide (document # 1000000004084)
Illumina Experiment Manager User Guide (document # 15031320)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.validators import (
    MIN_HAMMING_DISTANCE,
    SampleSheetValidator,
    _hamming_distance,
)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class MergeConflict:
    """A single error or warning produced during a merge.

    Attributes
    ----------
    level:
        ``"error"`` or ``"warning"``.
    code:
        Short machine-readable code, e.g. ``"INDEX_COLLISION"``.
    message:
        Human-readable description.
    context:
        Optional dict with extra detail.
    """
    level:   str
    code:    str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        ctx = f" | {self.context}" if self.context else ""
        return f"[{self.level.upper()}] {self.code}: {self.message}{ctx}"


@dataclass
class MergeResult:
    """Structured output from :class:`SampleSheetMerger`.

    Attributes
    ----------
    has_conflicts:
        ``True`` if any *error*-level conflicts were found.
    conflicts:
        List of error-level :class:`MergeConflict` objects.
    warnings:
        List of warning-level :class:`MergeConflict` objects.
    output_path:
        Path to the written file, or ``None`` if merge was aborted due
        to errors.
    sample_count:
        Total number of samples in the merged sheet.
    source_versions:
        Format version detected for each input file, keyed by file path.
    """
    has_conflicts:   bool = False
    conflicts:       list[MergeConflict] = field(default_factory=list)
    warnings:        list[MergeConflict] = field(default_factory=list)
    output_path:     Path | None = None
    sample_count:    int = 0
    source_versions: dict[str, str] = field(default_factory=dict)

    def add_conflict(self, code: str, message: str, **context: Any) -> None:
        self.has_conflicts = True
        self.conflicts.append(MergeConflict("error", code, message, dict(context)))
        logger.error(f"Merge conflict — {code}: {message}")

    def add_warning(self, code: str, message: str, **context: Any) -> None:
        self.warnings.append(MergeConflict("warning", code, message, dict(context)))
        logger.warning(f"Merge warning — {code}: {message}")

    def summary(self) -> str:
        """Return a human-readable one-line summary."""
        status = "FAIL" if self.has_conflicts else "OK"
        return (
            f"{status} — {len(self.conflicts)} conflict(s), "
            f"{len(self.warnings)} warning(s), "
            f"{self.sample_count} sample(s) merged"
        )


# ---------------------------------------------------------------------------
# Merger
# ---------------------------------------------------------------------------

class SampleSheetMerger:
    """Combine multiple per-project SampleSheet.csv files for one flow cell.

    Checks performed at merge time
    --------------------------------
    * **INDEX_COLLISION**       — Same lane + index (or index pair) appears
                                  in more than one input sheet → error.
    * **INDEX_DISTANCE_TOO_LOW** — Two indexes across sheets in the same lane
                                  have Hamming distance < 3 → warning.
    * **READ_LENGTH_CONFLICT**  — Input sheets specify different read lengths
                                  → error.
    * **ADAPTER_CONFLICT**      — Input sheets specify different adapter
                                  sequences → warning.
    * **MIXED_FORMAT**          — Input sheets are a mix of V1 and V2; all
                                  are auto-converted to the target format →
                                  warning (not an error).

    Parameters
    ----------
    target_version:
        Output format for the merged sheet. Defaults to
        :attr:`SampleSheetVersion.V2`. If inputs are mixed V1/V2, all
        are converted to this format.

    Examples
    --------
    >>> merger = SampleSheetMerger(target_version=SampleSheetVersion.V2)
    >>> merger.add("ProjectA/SampleSheet.csv")
    >>> merger.add("ProjectB/SampleSheet.csv")
    >>> result = merger.merge("combined.csv")
    >>> print(result.summary())
    OK — 0 conflict(s), 1 warning(s), 48 samples merged
    """

    def __init__(
        self,
        target_version: SampleSheetVersion = SampleSheetVersion.V2,
    ) -> None:
        self.target_version = target_version
        self._paths: list[Path] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, path: str | Path) -> SampleSheetMerger:
        """Register an input sheet for merging.

        Parameters
        ----------
        path:
            Path to a ``SampleSheet.csv`` file (V1 or V2).

        Returns
        -------
        SampleSheetMerger
            ``self``, for method chaining.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"SampleSheet not found: {p}")
        self._paths.append(p)
        logger.debug(f"Registered input sheet: {p}")
        return self

    def merge(
        self,
        output_path: str | Path,
        *,
        validate: bool = True,
        abort_on_conflicts: bool = True,
    ) -> MergeResult:
        """Parse all registered sheets, run conflict checks, and write output.

        Parameters
        ----------
        output_path:
            Destination path for the combined ``SampleSheet.csv``.
        validate:
            Run :class:`SampleSheetValidator` on the final merged sheet
            before writing (default ``True``).
        abort_on_conflicts:
            If ``True`` (default), do **not** write the output file when
            error-level conflicts are found.  Set to ``False`` to write
            the merged sheet even if conflicts exist (useful for
            inspection / debugging).

        Returns
        -------
        MergeResult
            Structured result. Check :attr:`MergeResult.has_conflicts`
            before consuming the output file.

        Raises
        ------
        ValueError
            If no input sheets have been registered, or if fewer than
            two sheets are registered.
        """
        if not self._paths:
            raise ValueError("No input sheets registered — call add() first.")
        if len(self._paths) < 2:
            raise ValueError(
                "At least two input sheets are required for a merge. "
                "Use SampleSheetWriter.from_sheet() to copy a single sheet."
            )

        result = MergeResult()

        # ── 1. Parse all inputs ──────────────────────────────────────────
        parsed = self._parse_all(result)
        if not parsed:
            return result  # all files failed to parse

        # ── 2. Cross-sheet checks ────────────────────────────────────────
        self._check_read_lengths(parsed, result)
        self._check_adapters(parsed, result)
        self._check_index_collisions(parsed, result)
        self._check_index_distances(parsed, result)

        # ── 3. Abort early if hard conflicts found ───────────────────────
        if result.has_conflicts and abort_on_conflicts:
            logger.error(
                f"Merge aborted — {len(result.conflicts)} conflict(s) found. "
                "Fix errors before merging."
            )
            return result

        # ── 4. Build combined writer ─────────────────────────────────────
        writer = self._build_writer(parsed, result)
        result.sample_count = writer.sample_count

        # ── 5. Validate merged sheet ─────────────────────────────────────
        if validate:
            self._validate_merged(writer, result)
            if result.has_conflicts and abort_on_conflicts:
                return result

        # ── 6. Write ─────────────────────────────────────────────────────
        out = writer.write(output_path, validate=False)  # already validated above
        result.output_path = out
        logger.info(
            f"Merged {len(parsed)} sheet(s) → {out} "
            f"({result.sample_count} samples)"
        )
        return result

    # ------------------------------------------------------------------
    # Internal — parsing
    # ------------------------------------------------------------------

    def _parse_all(
        self,
        result: MergeResult,
    ) -> list[tuple[Path, Any]]:
        """Parse each registered path; return list of (path, sheet) tuples."""
        from samplesheet_parser.factory import SampleSheetFactory

        parsed: list[tuple[Path, Any]] = []
        versions_seen: set[SampleSheetVersion] = set()

        for p in self._paths:
            try:
                factory = SampleSheetFactory()
                # clean=False keeps the merge read-only on source files;
                # cleaning could modify input sheets or create .backup files.
                sheet = factory.create_parser(str(p), parse=True, clean=False)
                parsed.append((p, sheet))
                versions_seen.add(factory.version)
                result.source_versions[str(p)] = factory.version.value
                logger.debug(f"Parsed {p} as {factory.version.value}")
            except Exception as exc:
                result.add_conflict(
                    "PARSE_ERROR",
                    f"Failed to parse {p}: {exc}",
                    path=str(p),
                )

        # Warn on mixed V1/V2 input
        if len(versions_seen) > 1:
            result.add_warning(
                "MIXED_FORMAT",
                f"Input sheets are a mix of V1 and V2 formats "
                f"({', '.join(v.value for v in sorted(versions_seen, key=str))}). "
                f"All will be converted to {self.target_version.value} for output.",
                target_version=self.target_version.value,
            )

        return parsed

    # ------------------------------------------------------------------
    # Internal — conflict checks
    # ------------------------------------------------------------------

    def _check_read_lengths(
        self,
        parsed: list[tuple[Path, Any]],
        result: MergeResult,
    ) -> None:
        """Error if read lengths differ across sheets."""
        from samplesheet_parser.parsers.v1 import SampleSheetV1

        length_map: dict[str, tuple[list[int], Path]] = {}

        for p, sheet in parsed:
            if isinstance(sheet, SampleSheetV1):
                lengths = sheet.read_lengths or []
            else:
                r = sheet.reads or {}
                lengths = [
                    v for k, v in r.items()
                    if k in ("Read1Cycles", "Read2Cycles") and v
                ]
            key = ",".join(str(rl) for rl in lengths)
            if key and key not in length_map:
                length_map[key] = (lengths, p)
            elif key and key in length_map:
                pass  # same — no conflict

        if len(length_map) > 1:
            detail = "; ".join(
                f"{p.name}: {lens}" for lens, p in length_map.values()
            )
            result.add_conflict(
                "READ_LENGTH_CONFLICT",
                f"Input sheets specify different read lengths: {detail}. "
                "All sheets in a merge must use the same read structure.",
            )

    def _check_adapters(
        self,
        parsed: list[tuple[Path, Any]],
        result: MergeResult,
    ) -> None:
        """Warn if adapter sequences differ across sheets.

        The primary sheet (``parsed[0]``) is used as the adapter reference
        because :meth:`_build_writer` calls ``SampleSheetWriter.from_sheet``
        on that sheet, which copies its adapter settings into the merged
        output.  The warning reflects this actual behaviour.
        """
        # Adapters always come from the primary (first) sheet in the merged
        # output.  Collect adapters from all sheets and warn if any differ
        # from the primary.
        primary_path, primary_sheet = parsed[0]
        primary_adapters = frozenset(
            a.upper() for a in (getattr(primary_sheet, "adapters", []) or []) if a
        )

        for p, sheet in parsed[1:]:
            adapters = frozenset(
                a.upper() for a in (getattr(sheet, "adapters", []) or []) if a
            )
            # Only warn when both sheets have adapters and they differ; if the
            # secondary sheet has no adapters, there is nothing to conflict.
            if adapters and adapters != primary_adapters:
                result.add_warning(
                    "ADAPTER_CONFLICT",
                    f"Adapter sequences differ between {primary_path.name} and "
                    f"{p.name}. The adapters from {primary_path.name} (the "
                    "primary sheet) will be used in the merged output.",
                    sheet_a=str(primary_path),
                    sheet_b=str(p),
                )

    def _check_index_collisions(
        self,
        parsed: list[tuple[Path, Any]],
        result: MergeResult,
    ) -> None:
        """Error if two sheets place the same index in the same lane.

        Uses ``sheet.records`` (raw per-row dicts) rather than
        ``sheet.samples()`` so that multi-lane sheets — where the same
        ``Sample_ID`` appears in multiple lanes — are not silently
        de-duplicated before the collision check.  Falls back to
        ``sheet.samples()`` for any parser that doesn't expose ``.records``.
        """
        # lane → index_key → (sample_id, source_path)
        seen: dict[str | None, dict[str, tuple[str, Path]]] = {}

        for p, sheet in parsed:
            # Prefer per-row records; fall back to samples() if unavailable.
            records = getattr(sheet, "records", None) or sheet.samples()
            for record in records:
                lane  = record.get("lane") or record.get("Lane")
                idx1  = (record.get("index") or record.get("Index") or "").upper()
                idx2  = (record.get("index2") or record.get("Index2") or "").upper()
                sid   = record.get("sample_id") or record.get("Sample_ID") or "?"
                key   = f"{idx1}+{idx2}" if idx2 else idx1

                # Silently skip incomplete rows — _build_writer will emit
                # INCOMPLETE_SAMPLE_RECORD for them; no duplicate warning here.
                if not idx1:
                    continue

                bucket = seen.setdefault(lane, {})
                if key in bucket:
                    existing_sid, existing_path = bucket[key]
                    result.add_conflict(
                        "INDEX_COLLISION",
                        f"Index '{key}' in lane {lane!r} appears in both "
                        f"'{existing_path.name}' (sample '{existing_sid}') and "
                        f"'{p.name}' (sample '{sid}'). "
                        "Index collisions will cause failed demultiplexing.",
                        lane=lane,
                        index=key,
                        sheet_a=str(existing_path),
                        sample_a=existing_sid,
                        sheet_b=str(p),
                        sample_b=sid,
                    )
                else:
                    bucket[key] = (sid, p)

    def _check_index_distances(
        self,
        parsed: list[tuple[Path, Any]],
        result: MergeResult,
        min_distance: int = MIN_HAMMING_DISTANCE,
    ) -> None:
        """Warn if indexes from different sheets are too similar (Hamming).

        Uses ``sheet.records`` (raw per-row dicts) for the same reason as
        :meth:`_check_index_collisions` — to avoid losing multi-lane rows
        that ``sheet.samples()`` de-duplicates by ``Sample_ID``.
        """
        # Build per-lane list of (sample_id, combined_index, source_path)
        lane_entries: dict[str | None, list[tuple[str, str, Path]]] = {}

        for p, sheet in parsed:
            records = getattr(sheet, "records", None) or sheet.samples()
            for record in records:
                lane = record.get("lane") or record.get("Lane")
                idx1 = (record.get("index") or record.get("Index") or "").upper()
                idx2 = (record.get("index2") or record.get("Index2") or "").upper()
                sid  = record.get("sample_id") or record.get("Sample_ID") or "?"
                if not idx1:
                    continue
                combined = idx1 + idx2 if idx2 else idx1
                lane_entries.setdefault(lane, []).append((sid, combined, p))

        for lane, entries in lane_entries.items():
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    sid_a, combined_a, path_a = entries[i]
                    sid_b, combined_b, path_b = entries[j]

                    # Skip pairs from the same sheet — intra-sheet distance
                    # is already checked by SampleSheetValidator
                    if path_a == path_b:
                        continue

                    dist = _hamming_distance(combined_a, combined_b)
                    if dist < min_distance:
                        result.add_warning(
                            "INDEX_DISTANCE_TOO_LOW",
                            f"Cross-sheet index distance warning: '{sid_a}' "
                            f"({path_a.name}) and '{sid_b}' ({path_b.name}) "
                            f"in lane {lane!r} have Hamming distance {dist} "
                            f"(minimum recommended: {min_distance}). "
                            "This may cause demultiplexing bleed-through.",
                            lane=lane,
                            sample_a=sid_a,
                            sheet_a=str(path_a),
                            index_a=combined_a,
                            sample_b=sid_b,
                            sheet_b=str(path_b),
                            index_b=combined_b,
                            distance=dist,
                            min_distance=min_distance,
                        )

    # ------------------------------------------------------------------
    # Internal — building the merged writer
    # ------------------------------------------------------------------

    def _build_writer(
        self,
        parsed: list[tuple[Path, Any]],
        result: MergeResult,
    ) -> Any:
        """Construct a SampleSheetWriter from all parsed sheets."""
        from samplesheet_parser.writer import SampleSheetWriter

        # Use the first successfully-parsed sheet as the header/reads source
        primary_path, primary = parsed[0]

        # Pre-scan the primary sheet for incomplete records.
        # SampleSheetWriter.from_sheet() silently drops rows missing Sample_ID
        # or Index; emit INCOMPLETE_SAMPLE_RECORD here so warnings are
        # consistent with the treatment of all subsequent sheets below.
        for sample in primary.samples():
            sid = sample.get("sample_id", "")
            idx = sample.get("index") or sample.get("Index") or ""
            if sid and idx:
                continue
            missing = []
            if not sid:
                missing.append("Sample_ID")
            if not idx:
                missing.append("Index")
            result.add_warning(
                "INCOMPLETE_SAMPLE_RECORD",
                f"Sample record from '{primary_path.name}' (primary sheet) is "
                f"missing required field(s) {missing} and will be skipped in "
                "the merged output.",
                sheet=str(primary_path),
                missing_fields=missing,
                record=dict(sample),
            )

        writer = SampleSheetWriter.from_sheet(primary, version=self.target_version)

        # Keys that belong in [Header]/[BCLConvert_Settings] or are handled
        # explicitly below — must not leak into [Data]/[BCLConvert_Data] as
        # extra per-sample columns.
        _STANDARD_SAMPLE_KEYS: frozenset[str] = frozenset({
            # core sample fields (lowercase — V1/V2 shared interface)
            "sample_id", "sample_name", "lane", "index", "index2",
            "sample_project", "description", "sample_plate", "sample_well",
            "i7_index_id", "i5_index_id",
            # capitalised variants returned by some parser versions
            "Index", "Index2", "Sample_Project",
            "I7_Index_ID", "I5_Index_ID",
            # run-level metadata that sheet.samples() may include for V2
            "flowcell_id", "experiment_name",
            "run_name", "instrument_platform", "instrument_type",
            "run_description", "file_format_version",
        })

        # Add samples from all other sheets
        for p, sheet in parsed[1:]:
            logger.debug(f"Adding samples from {p.name}")
            for sample in sheet.samples():
                sid  = sample.get("sample_id", "")
                idx  = sample.get("index") or sample.get("Index") or ""
                idx2 = sample.get("index2") or sample.get("Index2") or ""
                lane = sample.get("lane") or "1"
                # Fix: fall back to capitalised key for V2 sheets
                proj = sample.get("sample_project") or sample.get("Sample_Project") or ""
                i7   = sample.get("i7_index_id") or sample.get("I7_Index_ID") or ""
                i5   = sample.get("i5_index_id") or sample.get("I5_Index_ID") or ""

                if not sid or not idx:
                    missing = []
                    if not sid:
                        missing.append("Sample_ID")
                    if not idx:
                        missing.append("Index")
                    result.add_warning(
                        "INCOMPLETE_SAMPLE_RECORD",
                        f"Sample record from '{p.name}' is missing required "
                        f"field(s) {missing} and will be skipped in the merged "
                        "output.",
                        sheet=str(p),
                        missing_fields=missing,
                        record=dict(sample),
                    )
                    continue

                # Only pass through genuine per-sample extra columns
                extra = {
                    k: v for k, v in sample.items()
                    if k not in _STANDARD_SAMPLE_KEYS and v is not None
                }

                writer.add_sample(
                    sid,
                    index=idx,
                    index2=idx2 or "",
                    lane=str(lane),
                    sample_name=sample.get("sample_name") or "",
                    i7_index_id=i7,
                    i5_index_id=i5,
                    project=proj or "",
                    description=sample.get("description") or "",
                    **{k: str(v) for k, v in extra.items()},
                )

        return writer

    def _validate_merged(
        self,
        writer: Any,
        result: MergeResult,
    ) -> None:
        """Run SampleSheetValidator on the merged writer content."""
        import tempfile

        from samplesheet_parser.factory import SampleSheetFactory

        content = writer.to_string()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            sheet = SampleSheetFactory().create_parser(
                tmp_path, parse=True, clean=False
            )
            vresult = SampleSheetValidator().validate(sheet)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        for w in vresult.warnings:
            result.add_warning(w.code, w.message, **w.context)

        for e in vresult.errors:
            result.add_conflict(e.code, e.message, **e.context)
