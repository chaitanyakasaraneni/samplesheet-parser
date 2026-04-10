"""
Split a combined Illumina SampleSheet.csv into per-project or per-lane files.

This is the inverse of :class:`samplesheet_parser.merger.SampleSheetMerger`
and the canonical workflow when distributing a run's combined sheet back to
individual projects after demultiplexing.

Examples
--------
>>> from samplesheet_parser.splitter import SampleSheetSplitter
>>>
>>> splitter = SampleSheetSplitter("SampleSheet_combined.csv")
>>> result = splitter.split("./per_project/")
>>> for project, path in result.output_files.items():
...     print(f"{project}: {path} ({result.sample_counts[project]} samples)")

Split by lane instead of project::

>>> splitter = SampleSheetSplitter("SampleSheet.csv", by="lane")
>>> result = splitter.split("./per_lane/")

Authors
-------
Chaitanya Kasaraneni
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.factory import SampleSheetFactory

# Characters unsafe in filenames across Windows/macOS/Linux
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f\s]+')

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


def _safe_filename(name: str) -> str:
    """Replace characters unsafe for filenames with underscores."""
    sanitised = _UNSAFE_FILENAME_RE.sub("_", name).strip("._")
    return sanitised or "unnamed"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class SplitResult:
    """Structured output from :class:`SampleSheetSplitter`.

    Attributes
    ----------
    output_files:
        Mapping from group key (project name or lane number) to the path of
        the file that was written for that group.
    sample_counts:
        Number of samples written to each output file, keyed by group key.
    warnings:
        Non-fatal issues encountered during the split (e.g. incomplete
        records, groups that produced no samples).
    source_version:
        Format version string detected for the input sheet (e.g. ``"V1"``).
    """

    output_files: dict[str, Path] = field(default_factory=dict)
    sample_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    source_version: str = ""

    def summary(self) -> str:
        """Return a human-readable one-line summary."""
        total = sum(self.sample_counts.values())
        return (
            f"Split into {len(self.output_files)} file(s), "
            f"{total} sample(s) total, "
            f"{len(self.warnings)} warning(s)"
        )


# ---------------------------------------------------------------------------
# Splitter
# ---------------------------------------------------------------------------


class SampleSheetSplitter:
    """Split a combined SampleSheet.csv into per-project or per-lane files.

    This is the inverse of :class:`~samplesheet_parser.merger.SampleSheetMerger`.
    Header, reads, and settings from the input sheet are copied into every
    output file; only the ``[Data]`` / ``[BCLConvert_Data]`` rows are divided.

    Parameters
    ----------
    path:
        Path to the input SampleSheet.csv (V1 or V2).
    by:
        Grouping strategy.  ``"project"`` (default) groups samples by
        ``Sample_Project``; ``"lane"`` groups by lane number.
    target_version:
        Output format for the split files.  Defaults to the same format as
        the input sheet.
    unassigned_label:
        Label used for samples that have no project (when ``by="project"``)
        or no lane (when ``by="lane"``).  Defaults to ``"unassigned"``.

    Examples
    --------
    >>> splitter = SampleSheetSplitter("combined.csv")
    >>> result = splitter.split("./output/")
    >>> print(result.summary())
    Split into 3 file(s), 48 samples total, 0 warning(s)
    """

    def __init__(
        self,
        path: str | Path,
        *,
        by: str = "project",
        target_version: SampleSheetVersion | None = None,
        unassigned_label: str = "unassigned",
    ) -> None:
        if by not in ("project", "lane"):
            raise ValueError(f"by must be 'project' or 'lane', got {by!r}")
        self._path = Path(path)
        self._by = by
        self._target_version = target_version
        self._unassigned_label = unassigned_label

    def split(
        self,
        output_dir: str | Path,
        *,
        prefix: str = "",
        suffix: str = "_SampleSheet.csv",
        validate: bool = True,
    ) -> SplitResult:
        """Parse the input sheet and write one output file per group.

        Output filenames are ``{prefix}{group_key}{suffix}``, where
        ``group_key`` is the project name or lane number with filesystem-unsafe
        characters replaced by underscores.

        Parameters
        ----------
        output_dir:
            Directory in which to write the split files.  Created if it does
            not exist.
        prefix:
            Optional string prepended to each output filename.
        suffix:
            Suffix (including extension) appended to each output filename.
            Defaults to ``"_SampleSheet.csv"``.
        validate:
            Run :class:`~samplesheet_parser.validators.SampleSheetValidator`
            on each output sheet before writing (default ``True``).

        Returns
        -------
        SplitResult

        Raises
        ------
        FileNotFoundError
            If the input file does not exist.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"SampleSheet not found: {self._path}")

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        result = SplitResult()

        # ── Parse input ──────────────────────────────────────────────────
        factory = SampleSheetFactory()
        sheet = factory.create_parser(str(self._path), parse=True, clean=False)
        result.source_version = factory.version.value if factory.version else ""
        target_version = self._target_version or factory.version or SampleSheetVersion.V2

        # ── Group records ────────────────────────────────────────────────
        groups: dict[str, list[dict[str, Any]]] = {}
        records: list[dict[str, Any]] = getattr(sheet, "records", None) or sheet.samples()

        for record in records:
            if self._by == "project":
                key = (
                    record.get("sample_project")
                    or record.get("Sample_Project")
                    or self._unassigned_label
                )
            else:  # lane
                key = str(record.get("lane") or record.get("Lane") or self._unassigned_label)
            groups.setdefault(key, []).append(record)

        if not groups:
            result.warnings.append("No samples found in input sheet — no files written.")
            return result

        if self._unassigned_label in groups:
            count = len(groups[self._unassigned_label])
            field_name = "project" if self._by == "project" else "lane"
            result.warnings.append(
                f"{count} sample(s) have no {field_name} and will be written "
                f"to '{prefix}{_safe_filename(self._unassigned_label)}{suffix}'."
            )

        # ── Write one file per group ──────────────────────────────────────
        from samplesheet_parser.writer import SampleSheetWriter

        for group_key, group_records in sorted(groups.items()):
            writer = SampleSheetWriter.from_sheet(sheet, version=target_version)
            # from_sheet loads all samples from the source; clear them so we
            # add only this group's rows.
            writer._samples.clear()

            for record in group_records:
                sid = record.get("sample_id") or record.get("Sample_ID") or ""
                idx = record.get("index") or record.get("Index") or ""
                if not sid or not idx:
                    missing = []
                    if not sid:
                        missing.append("Sample_ID")
                    if not idx:
                        missing.append("Index")
                    result.warnings.append(
                        f"Skipping incomplete record in group '{group_key}': " f"missing {missing}."
                    )
                    continue

                writer.add_sample(
                    sid,
                    index=idx,
                    index2=record.get("index2") or record.get("Index2") or "",
                    lane=str(record.get("lane") or record.get("Lane") or "1"),
                    sample_name=record.get("sample_name") or record.get("Sample_Name") or "",
                    i7_index_id=record.get("i7_index_id") or record.get("I7_Index_ID") or "",
                    i5_index_id=record.get("i5_index_id") or record.get("I5_Index_ID") or "",
                    project=record.get("sample_project") or record.get("Sample_Project") or "",
                    description=record.get("description") or record.get("Description") or "",
                    sample_plate=record.get("sample_plate") or record.get("Sample_Plate") or "",
                    sample_well=record.get("sample_well") or record.get("Sample_Well") or "",
                    **{
                        k: str(v)
                        for k, v in record.items()
                        if k not in _STANDARD_SAMPLE_KEYS and v is not None
                    },
                )

            if writer.sample_count == 0:
                result.warnings.append(f"Group '{group_key}' produced no valid samples — skipping.")
                continue

            filename = f"{prefix}{_safe_filename(group_key)}{suffix}"
            out_path = out_dir / filename
            written = writer.write(out_path, validate=validate)
            result.output_files[group_key] = written
            result.sample_counts[group_key] = writer.sample_count
            logger.info(
                f"Wrote {writer.sample_count} sample(s) → {written} " f"(group: {group_key!r})"
            )

        return result
