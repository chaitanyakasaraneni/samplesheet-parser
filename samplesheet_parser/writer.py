"""
Programmatic writer for Illumina SampleSheet.csv files.

Supports both IEM V1 (bcl2fastq era) and BCLConvert V2 formats.
Build a sheet from scratch or load an existing parsed sheet, make
edits, then write to disk — with optional pre-write validation.

Examples
--------
Build a V2 sheet from scratch::

    from samplesheet_parser.writer import SampleSheetWriter
    from samplesheet_parser.enums import SampleSheetVersion

    writer = SampleSheetWriter(version=SampleSheetVersion.V2)
    writer.set_header(run_name="MyRun_20240115", platform="NovaSeqXSeries")
    writer.set_reads(read1=151, read2=151, index1=10, index2=10)
    writer.set_adapter("CTGTCTCTTATACACATCT")
    writer.add_sample(
        sample_id="SAMPLE_001",
        index="ATTACTCGAT",
        index2="TATAGCCTGT",
        project="ProjectA",
    )
    writer.write("SampleSheet.csv")

Load an existing sheet, remove a failed sample, write back::

    from samplesheet_parser import SampleSheetFactory
    from samplesheet_parser.writer import SampleSheetWriter

    sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
    writer = SampleSheetWriter.from_sheet(sheet)
    writer.remove_sample("SAMPLE_005")
    writer.write("SampleSheet_updated.csv")

Authors
-------
Chaitanya Kasaraneni

References
----------
Illumina Experiment Manager User Guide (document # 15031320)
Illumina BCLConvert Software Guide (document # 1000000004084)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger

from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2

# ---------------------------------------------------------------------------
# CSV safety
# ---------------------------------------------------------------------------

#: Characters that would corrupt the simple comma-delimited CSV structure
#: that Illumina SampleSheet.csv uses (no quoting or escaping is applied).
_UNSAFE_CHARS = frozenset(",\n\r\"'")


def _validate_field(value: str, field_name: str) -> str:
    """Raise ``ValueError`` if *value* contains characters unsafe for CSV.

    Parameters
    ----------
    value:
        The string to check.
    field_name:
        Human-readable field name used in the error message.

    Returns
    -------
    str
        *value* unchanged if safe.

    Raises
    ------
    ValueError
        If *value* contains a comma, newline, carriage return, or quote.
    """
    bad = _UNSAFE_CHARS & set(value)
    if bad:
        escaped = ", ".join(repr(c) for c in sorted(bad))
        raise ValueError(
            f"Field '{field_name}' contains character(s) that would corrupt "
            f"the SampleSheet CSV structure: {escaped}. "
            f"Value was: {value!r}"
        )
    return value



# ---------------------------------------------------------------------------
# Internal sample record
# ---------------------------------------------------------------------------

@dataclass
class _SampleRecord:
    """Internal representation of a single sample row."""
    sample_id:    str
    index:        str
    index2:       str        = ""
    lane:         str        = "1"
    sample_name:  str        = ""
    sample_plate: str        = ""
    sample_well:  str        = ""
    i7_index_id:  str        = ""
    i5_index_id:  str        = ""
    project:      str        = ""
    description:  str        = ""
    extra:        dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

class SampleSheetWriter:
    """
    Build and write Illumina SampleSheet.csv files programmatically.

    Supports both IEM V1 (bcl2fastq) and BCLConvert V2 (NovaSeq X series)
    output formats.  The writer validates the sheet before writing by
    default — pass ``validate=False`` to :meth:`write` to skip this.

    Parameters
    ----------
    version:
        Output format. :attr:`SampleSheetVersion.V1` or
        :attr:`SampleSheetVersion.V2`.

    Examples
    --------
    >>> writer = SampleSheetWriter(version=SampleSheetVersion.V2)
    >>> writer.set_header(run_name="Run001", platform="NovaSeqXSeries")
    >>> writer.set_reads(read1=151, read2=151, index1=10, index2=10)
    >>> writer.set_adapter("CTGTCTCTTATACACATCT")
    >>> writer.add_sample("S1", index="ATTACTCGAT", index2="TATAGCCTGT")
    >>> writer.write("SampleSheet.csv")
    """

    def __init__(self, version: SampleSheetVersion = SampleSheetVersion.V2) -> None:
        self.version = version

        # Header fields
        self._run_name:    str        = ""
        self._run_desc:    str        = ""
        self._platform:    str        = ""
        self._instrument:  str        = ""
        self._date:        str        = ""
        self._workflow:    str        = ""
        self._chemistry:   str        = ""
        self._iem_version: str        = "5"
        self._extra_header: dict[str, str] = {}

        # Reads
        self._read1:   int = 0
        self._read2:   int = 0
        self._index1:  int = 0
        self._index2:  int = 0

        # Settings
        self._adapter_read1:    str = ""
        self._adapter_read2:    str = ""
        self._override_cycles:  str = ""
        self._software_version: str = ""
        self._extra_settings:   dict[str, str] = {}

        # Samples
        self._samples: list[_SampleRecord] = []

    # ------------------------------------------------------------------
    # Class method — build from existing parsed sheet
    # ------------------------------------------------------------------

    @classmethod
    def from_sheet(
        cls,
        sheet: SampleSheetV1 | SampleSheetV2,
        *,
        version: SampleSheetVersion | None = None,
    ) -> SampleSheetWriter:
        """
        Create a writer pre-populated from an existing parsed sheet.

        Parameters
        ----------
        sheet:
            A parsed :class:`SampleSheetV1` or :class:`SampleSheetV2`.
        version:
            Output format to write.  Defaults to the same format as
            the input sheet.  Pass a different version to convert while
            editing.

        Returns
        -------
        SampleSheetWriter

        Examples
        --------
        >>> sheet = SampleSheetFactory().create_parser("in.csv", parse=True)
        >>> writer = SampleSheetWriter.from_sheet(sheet)
        >>> writer.remove_sample("FAILED_001")
        >>> writer.write("out.csv")
        """
        if isinstance(sheet, SampleSheetV1):
            detected = SampleSheetVersion.V1
        else:
            detected = SampleSheetVersion.V2

        out_version = version if version is not None else detected
        writer = cls(version=out_version)

        if isinstance(sheet, SampleSheetV1):
            writer._load_from_v1(sheet)
        else:
            writer._load_from_v2(sheet)

        return writer

    # ------------------------------------------------------------------
    # Configuration — header
    # ------------------------------------------------------------------

    def set_header(
        self,
        *,
        run_name:   str = "",
        run_desc:   str = "",
        platform:   str = "",
        instrument: str = "",
        date_str:   str = "",
        workflow:   str = "",
        chemistry:  str = "",
        **extra: str,
    ) -> SampleSheetWriter:
        """
        Set [Header] / header fields.

        Parameters
        ----------
        run_name:
            Run or experiment name (``RunName`` in V2, ``Experiment Name``
            in V1).
        run_desc:
            Run description (V2 only; silently ignored for V1 output).
        platform:
            Instrument platform string, e.g. ``"NovaSeqXSeries"`` (V2 only).
        instrument:
            Instrument type string, e.g. ``"NovaSeqX"`` (V2 only).
        date_str:
            Run date in ``YYYY-MM-DD`` format (V1 ``Date`` field).
            Defaults to today if empty and writing V1.
        workflow:
            Workflow string, e.g. ``"GenerateFASTQ"`` (V1 only).
        chemistry:
            Chemistry string, e.g. ``"Amplicon"`` (V1 only).
        **extra:
            Additional header key/value pairs passed through verbatim.

        Returns
        -------
        SampleSheetWriter
            ``self``, for method chaining.
        """
        _validate_field(run_name,   "run_name")
        _validate_field(run_desc,   "run_desc")
        _validate_field(platform,   "platform")
        _validate_field(instrument, "instrument")
        _validate_field(date_str,   "date_str")
        _validate_field(workflow,   "workflow")
        _validate_field(chemistry,  "chemistry")
        for k, v in extra.items():
            _validate_field(k, f"extra header key '{k}'")
            _validate_field(v, k)
        self._run_name   = run_name
        self._run_desc   = run_desc
        self._platform   = platform
        self._instrument = instrument
        self._date       = date_str
        self._workflow   = workflow
        self._chemistry  = chemistry
        self._extra_header.update(extra)
        return self

    # ------------------------------------------------------------------
    # Configuration — reads
    # ------------------------------------------------------------------

    def set_reads(
        self,
        *,
        read1:  int,
        read2:  int = 0,
        index1: int = 0,
        index2: int = 0,
    ) -> SampleSheetWriter:
        """
        Set read cycle counts.

        Parameters
        ----------
        read1:
            Read 1 cycle count (required).
        read2:
            Read 2 cycle count (0 = single-end).
        index1:
            Index 1 cycle count (V2 only).
        index2:
            Index 2 cycle count (V2 only).

        Returns
        -------
        SampleSheetWriter
            ``self``, for method chaining.
        """
        self._read1  = read1
        self._read2  = read2
        self._index1 = index1
        self._index2 = index2
        return self

    # ------------------------------------------------------------------
    # Configuration — settings / adapters
    # ------------------------------------------------------------------

    def set_adapter(
        self,
        adapter_read1: str,
        adapter_read2: str = "",
    ) -> SampleSheetWriter:
        """
        Set adapter sequences.

        Parameters
        ----------
        adapter_read1:
            Read 1 adapter (written as ``AdapterRead1`` in V2,
            ``Adapter`` in V1).
        adapter_read2:
            Read 2 adapter (omitted if empty).

        Returns
        -------
        SampleSheetWriter
            ``self``, for method chaining.
        """
        _validate_field(adapter_read1, "adapter_read1")
        _validate_field(adapter_read2, "adapter_read2")
        self._adapter_read1 = adapter_read1
        self._adapter_read2 = adapter_read2
        return self

    def set_override_cycles(self, override: str) -> SampleSheetWriter:
        """
        Set the ``OverrideCycles`` string (V2 only).

        Parameters
        ----------
        override:
            OverrideCycles string, e.g. ``"Y151;I10;I10;Y151"``.

        Returns
        -------
        SampleSheetWriter
            ``self``, for method chaining.
        """
        _validate_field(override, "override_cycles")
        self._override_cycles = override
        return self

    def set_software_version(self, version: str) -> SampleSheetWriter:
        """
        Set ``SoftwareVersion`` in ``[BCLConvert_Settings]`` (V2 only).

        Returns
        -------
        SampleSheetWriter
            ``self``, for method chaining.
        """
        self._software_version = version
        return self

    def set_setting(self, key: str, value: str) -> SampleSheetWriter:
        """
        Set an arbitrary key/value in the settings section.

        Returns
        -------
        SampleSheetWriter
            ``self``, for method chaining.
        """
        _validate_field(key,   "key")
        _validate_field(value, key)
        self._extra_settings[key] = value
        return self

    # ------------------------------------------------------------------
    # Sample management
    # ------------------------------------------------------------------

    def add_sample(
        self,
        sample_id: str,
        *,
        index:        str,
        index2:       str = "",
        lane:         str = "1",
        sample_name:  str = "",
        sample_plate: str = "",
        sample_well:  str = "",
        i7_index_id:  str = "",
        i5_index_id:  str = "",
        project:      str = "",
        description:  str = "",
        **extra: str,
    ) -> SampleSheetWriter:
        """
        Append a sample to the sheet.

        Parameters
        ----------
        sample_id:
            Unique sample identifier (required).
        index:
            I7 / Index 1 sequence (required).
        index2:
            I5 / Index 2 sequence (dual-index sheets).
        lane:
            Lane number as a string (default ``"1"``).
        sample_name:
            Sample display name (V1; defaults to ``sample_id``).
        project:
            ``Sample_Project`` value.
        **extra:
            Additional columns passed through verbatim.

        Returns
        -------
        SampleSheetWriter
            ``self``, for method chaining.

        Raises
        ------
        ValueError
            If ``sample_id`` is empty or ``index`` is empty.
        """
        if not sample_id:
            raise ValueError("sample_id must not be empty.")
        if not index:
            raise ValueError(f"index must not be empty for sample '{sample_id}'.")

        _validate_field(sample_id,    "sample_id")
        _validate_field(index,        "index")
        _validate_field(index2,       "index2")
        _validate_field(lane,         "lane")
        _validate_field(sample_name,  "sample_name")
        _validate_field(sample_plate, "sample_plate")
        _validate_field(sample_well,  "sample_well")
        _validate_field(i7_index_id,  "i7_index_id")
        _validate_field(i5_index_id,  "i5_index_id")
        _validate_field(project,      "project")
        _validate_field(description,  "description")
        for k, v in extra.items():
            _validate_field(k, f"extra key '{k}'")
            _validate_field(v, k)

        self._samples.append(
            _SampleRecord(
                sample_id=sample_id,
                index=index.upper(),
                index2=index2.upper() if index2 else "",
                lane=str(lane),
                sample_name=sample_name or sample_id,
                sample_plate=sample_plate,
                sample_well=sample_well,
                i7_index_id=i7_index_id,
                i5_index_id=i5_index_id,
                project=project,
                description=description,
                extra=dict(extra),
            )
        )
        return self

    def remove_sample(
        self,
        sample_id: str,
        *,
        lane: str | None = None,
    ) -> SampleSheetWriter:
        """
        Remove sample(s) by ``sample_id``.

        Parameters
        ----------
        sample_id:
            ``Sample_ID`` to remove.
        lane:
            If provided, only remove the sample from this lane. If ``None``
            (default), removes all samples with the given ``sample_id``
            regardless of lane.

        Returns
        -------
        SampleSheetWriter
            ``self``, for method chaining.

        Raises
        ------
        KeyError
            If no matching sample is found.
        """
        before = len(self._samples)
        if lane is not None:
            self._samples = [
                s for s in self._samples
                if not (s.sample_id == sample_id and s.lane == str(lane))
            ]
        else:
            self._samples = [
                s for s in self._samples if s.sample_id != sample_id
            ]
        if len(self._samples) == before:
            raise KeyError(
                f"Sample '{sample_id}'"
                + (f" in lane {lane!r}" if lane is not None else "")
                + " not found."
            )
        return self

    def update_sample(
        self,
        sample_id: str,
        *,
        lane: str | None = None,
        **fields: Any,
    ) -> SampleSheetWriter:
        """
        Update fields on an existing sample in-place.

        Parameters
        ----------
        sample_id:
            ``Sample_ID`` to update.
        lane:
            If provided, only update the sample in this lane.
        **fields:
            Field names and new values. Valid names: ``index``, ``index2``,
            ``project``, ``lane``, ``sample_name``, ``sample_plate``,
            ``sample_well``, ``i7_index_id``, ``i5_index_id``,
            ``description``.  Unknown names are stored in ``extra``.

        Returns
        -------
        SampleSheetWriter
            ``self``, for method chaining.

        Raises
        ------
        KeyError
            If no matching sample is found.
        """
        _KNOWN = {
            "index", "index2", "lane", "sample_name", "sample_plate",
            "sample_well", "i7_index_id", "i5_index_id", "project",
            "description",
        }
        matched = False
        for s in self._samples:
            if s.sample_id != sample_id:
                continue
            if lane is not None and s.lane != str(lane):
                continue
            matched = True
            for k, v in fields.items():
                if k in _KNOWN:
                    value_str = _validate_field(str(v), k)
                    setattr(s, k, value_str.upper() if k in ("index", "index2") else value_str)
                else:
                    s.extra[k] = _validate_field(str(v), k)
        if not matched:
            raise KeyError(
                f"Sample '{sample_id}'"
                + (f" in lane {lane!r}" if lane is not None else "")
                + " not found."
            )
        return self

    @property
    def sample_count(self) -> int:
        """Number of samples currently in the writer."""
        return len(self._samples)

    @property
    def sample_ids(self) -> list[str]:
        """List of sample IDs currently in the writer."""
        return [s.sample_id for s in self._samples]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(
        self,
        path: str | Path,
        *,
        validate: bool = True,
    ) -> Path:
        """
        Serialise the sheet to a ``SampleSheet.csv`` file.

        Parameters
        ----------
        path:
            Destination file path.
        validate:
            If ``True`` (default), run :class:`SampleSheetValidator`
            before writing and raise :exc:`ValueError` if any *errors*
            (not warnings) are found.

        Returns
        -------
        Path
            Absolute path to the written file.

        Raises
        ------
        ValueError
            If ``validate=True`` and the sheet has validation errors,
            or if no samples have been added.
        """
        if not self._samples:
            raise ValueError("Cannot write an empty sheet — add at least one sample.")

        if validate:
            self._validate_before_write()

        out = Path(path)
        if self.version == SampleSheetVersion.V2:
            content = self._render_v2()
        else:
            content = self._render_v1()

        out.write_text(content, encoding="utf-8")
        logger.info(
            f"Wrote {self.version.value} sheet with {len(self._samples)} "
            f"sample(s) to {out}"
        )
        return out.resolve()

    def to_string(self) -> str:
        """
        Return the sheet as a string without writing to disk.

        Validation is **not** run by this method.

        Returns
        -------
        str
            Full CSV content of the sample sheet.
        """
        if self.version == SampleSheetVersion.V2:
            return self._render_v2()
        return self._render_v1()

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    def _render_v2(self) -> str:
        lines: list[str] = []

        # [Header]
        lines.append("[Header]")
        lines.append("FileFormatVersion,2")
        if self._run_name:
            lines.append(f"RunName,{self._run_name}")
        if self._run_desc:
            lines.append(f"RunDescription,{self._run_desc}")
        if self._platform:
            lines.append(f"InstrumentPlatform,{self._platform}")
        if self._instrument:
            lines.append(f"InstrumentType,{self._instrument}")
        for k, v in self._extra_header.items():
            lines.append(f"{k},{v}")
        lines.append("")

        # [Reads]
        lines.append("[Reads]")
        if self._read1:
            lines.append(f"Read1Cycles,{self._read1}")
        if self._read2:
            lines.append(f"Read2Cycles,{self._read2}")
        if self._index1:
            lines.append(f"Index1Cycles,{self._index1}")
        if self._index2:
            lines.append(f"Index2Cycles,{self._index2}")
        lines.append("")

        # [BCLConvert_Settings]
        lines.append("[BCLConvert_Settings]")
        if self._software_version:
            lines.append(f"SoftwareVersion,{self._software_version}")
        if self._adapter_read1:
            lines.append(f"AdapterRead1,{self._adapter_read1}")
        if self._adapter_read2:
            lines.append(f"AdapterRead2,{self._adapter_read2}")
        if self._override_cycles:
            lines.append(f"OverrideCycles,{self._override_cycles}")
        for k, v in self._extra_settings.items():
            lines.append(f"{k},{v}")
        lines.append("")

        # [BCLConvert_Data]
        lines.append("[BCLConvert_Data]")
        has_index2  = any(s.index2 for s in self._samples)
        has_project = any(s.project for s in self._samples)
        extra_cols  = self._extra_columns()

        cols = ["Lane", "Sample_ID", "Index"]
        if has_index2:
            cols.append("Index2")
        if has_project:
            cols.append("Sample_Project")
        cols.extend(extra_cols)

        lines.append(",".join(cols))
        for s in self._samples:
            row = [s.lane, s.sample_id, s.index]
            if has_index2:
                row.append(s.index2)
            if has_project:
                row.append(s.project)
            for col in extra_cols:
                row.append(s.extra.get(col, ""))
            lines.append(",".join(row))
        lines.append("")

        return "\n".join(lines)

    def _render_v1(self) -> str:
        lines: list[str] = []

        # [Header]
        lines.append("[Header]")
        lines.append(f"IEMFileVersion,{self._iem_version}")
        if self._run_name:
            lines.append(f"Experiment Name,{self._run_name}")
        date_val = (
            self._date or date.today().strftime("%Y-%m-%d")
        )
        lines.append(f"Date,{date_val}")
        if self._workflow:
            lines.append(f"Workflow,{self._workflow}")
        else:
            lines.append("Workflow,GenerateFASTQ")
        if self._chemistry:
            lines.append(f"Chemistry,{self._chemistry}")
        for k, v in self._extra_header.items():
            lines.append(f"{k},{v}")
        lines.append("")

        # [Reads]
        lines.append("[Reads]")
        if self._read1:
            lines.append(str(self._read1))
        if self._read2:
            lines.append(str(self._read2))
        lines.append("")

        # [Settings]
        lines.append("[Settings]")
        if self._adapter_read1:
            lines.append(f"Adapter,{self._adapter_read1}")
        if self._adapter_read2:
            lines.append(f"AdapterRead2,{self._adapter_read2}")
        for k, v in self._extra_settings.items():
            lines.append(f"{k},{v}")
        lines.append("")

        # [Data]
        lines.append("[Data]")
        has_index2     = any(s.index2 for s in self._samples)
        has_i7_name    = any(s.i7_index_id for s in self._samples)
        has_i5_name    = any(s.i5_index_id for s in self._samples)
        has_plate      = any(s.sample_plate for s in self._samples)
        has_well       = any(s.sample_well for s in self._samples)
        has_project    = any(s.project for s in self._samples)
        has_desc       = any(s.description for s in self._samples)
        extra_cols     = self._extra_columns()

        cols = ["Lane", "Sample_ID", "Sample_Name"]
        if has_plate:
            cols.append("Sample_Plate")
        if has_well:
            cols.append("Sample_Well")
        if has_i7_name:
            cols.append("I7_Index_ID")
        cols.append("index")
        if has_index2:
            if has_i5_name:
                cols.append("I5_Index_ID")
            cols.append("index2")
        if has_project:
            cols.append("Sample_Project")
        if has_desc:
            cols.append("Description")
        cols.extend(extra_cols)

        lines.append(",".join(cols))
        for s in self._samples:
            row = [s.lane, s.sample_id, s.sample_name]
            if has_plate:
                row.append(s.sample_plate)
            if has_well:
                row.append(s.sample_well)
            if has_i7_name:
                row.append(s.i7_index_id)
            row.append(s.index)
            if has_index2:
                if has_i5_name:
                    row.append(s.i5_index_id)
                row.append(s.index2)
            if has_project:
                row.append(s.project)
            if has_desc:
                row.append(s.description)
            for col in extra_cols:
                row.append(s.extra.get(col, ""))
            lines.append(",".join(row))
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extra_columns(self) -> list[str]:
        """Return sorted list of extra column names present in any sample."""
        seen: set[str] = set()
        for s in self._samples:
            seen.update(s.extra.keys())
        return sorted(seen)

    def _validate_before_write(self) -> None:
        """Parse the to-be-written content and run SampleSheetValidator."""
        from samplesheet_parser.factory import SampleSheetFactory
        from samplesheet_parser.validators import SampleSheetValidator

        content = self.to_string()
        # Write to a temp buffer and parse back
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            sheet = SampleSheetFactory().create_parser(
                tmp_path, parse=True, clean=False
            )
            result = SampleSheetValidator().validate(sheet)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if result.warnings:
            for w in result.warnings:
                logger.warning(f"Pre-write validation: {w}")

        if not result.is_valid:
            error_lines = "\n".join(f"  {e}" for e in result.errors)
            raise ValueError(
                f"Sheet failed validation — fix errors before writing:\n"
                f"{error_lines}"
            )

    def _load_from_v1(self, sheet: SampleSheetV1) -> None:
        """Populate writer state from a parsed V1 sheet."""
        self._run_name  = sheet.experiment_name or ""
        self._date      = sheet.date or ""
        self._workflow  = sheet.workflow or ""
        self._chemistry = sheet.chemistry or ""
        self._iem_version = sheet.iem_version or "5"

        if sheet.read_lengths:
            self._read1 = sheet.read_lengths[0]
            if len(sheet.read_lengths) > 1:
                self._read2 = sheet.read_lengths[1]

        self._adapter_read1 = sheet.adapter_read1 or ""
        self._adapter_read2 = sheet.adapter_read2 or ""

        for record in (sheet.records or []):
            std = {k: v for k, v in record.items() if k in (
                "Lane", "Sample_ID", "Sample_Name", "Sample_Plate",
                "Sample_Well", "I7_Index_ID", "index", "I5_Index_ID",
                "index2", "Sample_Project", "Description",
            )}
            extra = {k: v for k, v in record.items() if k not in (
                "Lane", "Sample_ID", "Sample_Name", "Sample_Plate",
                "Sample_Well", "I7_Index_ID", "index", "I5_Index_ID",
                "index2", "Sample_Project", "Description",
            )}
            sid = std.get("Sample_ID", "")
            idx = std.get("index", "")
            if not sid or not idx:
                continue
            self._samples.append(_SampleRecord(
                sample_id=sid,
                index=idx,
                index2=std.get("index2", "") or "",
                lane=std.get("Lane", "1") or "1",
                sample_name=std.get("Sample_Name", "") or "",
                sample_plate=std.get("Sample_Plate", "") or "",
                sample_well=std.get("Sample_Well", "") or "",
                i7_index_id=std.get("I7_Index_ID", "") or "",
                i5_index_id=std.get("I5_Index_ID", "") or "",
                project=std.get("Sample_Project", "") or "",
                description=std.get("Description", "") or "",
                extra=extra,
            ))

    def _load_from_v2(self, sheet: SampleSheetV2) -> None:
        """Populate writer state from a parsed V2 sheet."""
        h = sheet.header or {}
        self._run_name    = sheet.experiment_name or h.get("RunName", "")
        self._run_desc    = h.get("RunDescription", "")
        self._platform    = h.get("InstrumentPlatform", "")
        self._instrument  = h.get("InstrumentType", "")

        r = sheet.reads or {}
        self._read1  = r.get("Read1Cycles", 0)
        self._read2  = r.get("Read2Cycles", 0)
        self._index1 = r.get("Index1Cycles", 0)
        self._index2 = r.get("Index2Cycles", 0)

        s = sheet.settings or {}
        self._adapter_read1    = s.get("AdapterRead1", "")
        self._adapter_read2    = s.get("AdapterRead2", "")
        self._override_cycles  = s.get("OverrideCycles", "")
        self._software_version = s.get("SoftwareVersion", "")
        # remaining settings → extra
        skip = {
            "AdapterRead1", "AdapterRead2", "OverrideCycles", "SoftwareVersion"
        }
        for k, v in s.items():
            if k not in skip:
                self._extra_settings[k] = v

        std_cols = {"Lane", "Sample_ID", "Index", "Index2", "Sample_Project"}
        for record in (sheet.records or []):
            sid = record.get("Sample_ID", "")
            idx = record.get("Index", "")
            if not sid or not idx:
                continue
            extra = {k: v for k, v in record.items() if k not in std_cols}
            self._samples.append(_SampleRecord(
                sample_id=sid,
                index=idx,
                index2=record.get("Index2", "") or "",
                lane=record.get("Lane", "1") or "1",
                project=record.get("Sample_Project", "") or "",
                extra=extra,
            ))
