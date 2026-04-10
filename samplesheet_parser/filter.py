"""
Filter samples from an Illumina SampleSheet.csv by project, lane, or sample ID.

Examples
--------
>>> from samplesheet_parser.filter import SampleSheetFilter
>>>
>>> f = SampleSheetFilter("SampleSheet.csv")
>>> result = f.filter("filtered.csv", project="ProjectA")
>>> print(f"Kept {result.matched_count} of {result.total_count} samples")

Combine multiple criteria (ANDed)::

>>> result = f.filter("out.csv", project="ProjectA", lane="2")

Use a glob pattern on Sample_ID::

>>> result = f.filter("out.csv", sample_id="CTRL_*")

Authors
-------
Chaitanya Kasaraneni
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.factory import SampleSheetFactory

# Raw record keys that are standard sample fields — not extra columns
_STANDARD_SAMPLE_KEYS: frozenset[str] = frozenset(
    {
        "lane",
        "Lane",
        "sample_id",
        "Sample_ID",
        "sample_name",
        "Sample_Name",
        "index",
        "Index",
        "index2",
        "Index2",
        "sample_project",
        "Sample_Project",
        "description",
        "Description",
        "sample_plate",
        "Sample_Plate",
        "sample_well",
        "Sample_Well",
        "i7_index_id",
        "I7_Index_ID",
        "i5_index_id",
        "I5_Index_ID",
    }
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class FilterResult:
    """Structured output from :class:`SampleSheetFilter`.

    Attributes
    ----------
    matched_count:
        Number of samples that passed all filter criteria.
    total_count:
        Total number of samples in the input sheet.
    output_path:
        Path to the written file, or ``None`` if no samples matched and
        no file was written.
    source_version:
        Format version string detected for the input sheet (e.g. ``"V2"``).
    """

    matched_count: int = 0
    total_count: int = 0
    output_path: Path | None = None
    source_version: str = ""

    def summary(self) -> str:
        """Return a human-readable one-line summary."""
        suffix = f" → {self.output_path}" if self.output_path else " (no output written)"
        return f"Kept {self.matched_count} of {self.total_count} sample(s){suffix}"


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


class SampleSheetFilter:
    """Filter samples from a SampleSheet.csv by project, lane, or sample ID.

    Header, reads, and settings from the input sheet are preserved in the
    output; only the sample rows are filtered.

    Parameters
    ----------
    path:
        Path to the input SampleSheet.csv (V1 or V2).
    target_version:
        Output format for the filtered file.  Defaults to the same format as
        the input sheet.

    Examples
    --------
    >>> flt = SampleSheetFilter("combined.csv")
    >>> result = flt.filter("projectA.csv", project="ProjectA")
    >>> result = flt.filter("lane2.csv", lane=2)
    >>> result = flt.filter("controls.csv", sample_id="CTRL_*")
    """

    def __init__(
        self,
        path: str | Path,
        *,
        target_version: SampleSheetVersion | None = None,
    ) -> None:
        self._path = Path(path)
        self._target_version = target_version

    def filter(
        self,
        output_path: str | Path,
        *,
        project: str | None = None,
        lane: str | int | None = None,
        sample_id: str | None = None,
        validate: bool = True,
    ) -> FilterResult:
        """Write a filtered copy of the sheet to *output_path*.

        Multiple criteria are ANDed — a sample must match **all** provided
        criteria to be included.  ``sample_id`` supports glob patterns (e.g.
        ``"CTRL_*"`` or ``"SAMPLE_00[1-3]"``).

        Parameters
        ----------
        output_path:
            Destination file path.
        project:
            Keep only samples whose ``Sample_Project`` matches exactly.
        lane:
            Keep only samples from this lane (compared as a string, so
            ``lane=2`` and ``lane="2"`` are equivalent).
        sample_id:
            Keep only samples whose ``Sample_ID`` matches this value or glob
            pattern.
        validate:
            Run :class:`~samplesheet_parser.validators.SampleSheetValidator`
            on the filtered sheet before writing (default ``True``).

        Returns
        -------
        FilterResult

        Raises
        ------
        ValueError
            If no filter criteria are provided.
        FileNotFoundError
            If the input file does not exist.
        """
        if project is None and lane is None and sample_id is None:
            raise ValueError(
                "At least one filter criterion must be provided: " "project, lane, or sample_id."
            )
        if not self._path.exists():
            raise FileNotFoundError(f"SampleSheet not found: {self._path}")

        factory = SampleSheetFactory()
        sheet = factory.create_parser(str(self._path), parse=True, clean=False)
        target_version = self._target_version or factory.version or SampleSheetVersion.V2

        result = FilterResult(source_version=factory.version.value if factory.version else "")

        records: list[dict[str, Any]] = getattr(sheet, "records", None) or sheet.samples()
        result.total_count = len(records)
        lane_str = str(lane) if lane is not None else None

        from samplesheet_parser.writer import SampleSheetWriter

        writer = SampleSheetWriter.from_sheet(sheet, version=target_version)
        # from_sheet loads all samples; clear so only matched rows are added.
        writer.clear_samples()

        for record in records:
            rec_project = record.get("sample_project") or record.get("Sample_Project") or ""
            rec_lane = str(record.get("lane") or record.get("Lane") or "")
            rec_sid = record.get("sample_id") or record.get("Sample_ID") or ""

            if project is not None and rec_project != project:
                continue
            if lane_str is not None and rec_lane != lane_str:
                continue
            if sample_id is not None and not fnmatch.fnmatchcase(rec_sid, sample_id):
                continue

            idx = record.get("index") or record.get("Index") or ""
            if not rec_sid or not idx:
                continue

            writer.add_sample(
                rec_sid,
                index=idx,
                index2=record.get("index2") or record.get("Index2") or "",
                lane=str(record.get("lane") or record.get("Lane") or "1"),
                sample_name=record.get("sample_name") or record.get("Sample_Name") or "",
                i7_index_id=record.get("i7_index_id") or record.get("I7_Index_ID") or "",
                i5_index_id=record.get("i5_index_id") or record.get("I5_Index_ID") or "",
                project=rec_project,
                description=record.get("description") or record.get("Description") or "",
                sample_plate=record.get("sample_plate") or record.get("Sample_Plate") or "",
                sample_well=record.get("sample_well") or record.get("Sample_Well") or "",
                **{
                    k: str(v)
                    for k, v in record.items()
                    if k not in _STANDARD_SAMPLE_KEYS and v is not None
                },
            )
            result.matched_count += 1

        if result.matched_count == 0:
            logger.warning("No samples matched the filter criteria — no output written.")
            return result

        out = writer.write(output_path, validate=validate)
        result.output_path = out
        logger.info(f"Filtered {result.matched_count}/{result.total_count} samples → {out}")
        return result
