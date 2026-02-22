"""
Illumina Experiment Manager (IEM) V1 sample sheet parser.

Handles the classic bcl2fastq-era SampleSheet.csv format, which uses
``IEMFileVersion`` in the ``[Header]`` section and a flat ``[Data]``
section with standard IEM columns.

Reference format
----------------
::

    [Header]
    IEMFileVersion,5
    Experiment Name,MyRun
    Date,2024-01-15
    Workflow,GenerateFASTQ
    Description,
    Chemistry,Amplicon

    [Reads]
    151
    151

    [Settings]
    Adapter,CTGTCTCTTATACACATCT

    [Data]
    Lane,Sample_ID,Sample_Name,Sample_Plate,Sample_Well,I7_Index_ID,index,I5_Index_ID,index2,Sample_Project,Description
    1,Sample1,Sample1,,A01,D701,ATTACTCG,D501,TATAGCCT,Project1,
    1,Sample2,Sample2,,B01,D702,TCCGGAGA,D502,ATAGAGGC,Project1,

Authors
-------
Chaitanya Kasaraneni — original V1 → V2 migration architect; this
generalised rewrite strips proprietary internals while preserving the
core parsing logic and public API.

References
----------
Illumina Experiment Manager User Guide (document # 15031320)
https://support.illumina.com/downloads/illumina-experiment-manager-software.html
"""

from __future__ import annotations

import os
import re
from collections import namedtuple
from pathlib import Path

from loguru import logger

# ---------------------------------------------------------------------------
# Standard IEM V1 column definitions (from Illumina's public documentation)
# ---------------------------------------------------------------------------

#: Standard columns in the [Data] section. Custom columns are allowed and
#: will be preserved as-is.
STANDARD_DATA_COLUMNS = {
    "Lane",
    "Sample_ID",
    "Sample_Name",
    "Sample_Plate",
    "Sample_Well",
    "I7_Index_ID",
    "index",
    "I5_Index_ID",
    "index2",
    "Sample_Project",
    "Description",
}

#: [Header] keys that carry well-known semantics.
#: Source: Illumina Knowledge Article #2204
STANDARD_HEADER_KEYS = {
    "IEMFileVersion",
    "Experiment Name",
    "Date",
    "Workflow",
    "Application",        # e.g. "FASTQ Only"
    "Instrument Type",    # e.g. "MiSeq" — note: NextSeq/MiniSeq auto-RC index2
    "Assay",              # LP kit identifier, irrelevant to sequencer
    "Index Adapters",     # Illumina index set name, irrelevant to sequencer
    "Chemistry",          # "Amplicon" = dual index, "Default" = no/single index
    "Description",
}

#: [Settings] keys that carry well-known semantics in V1 sheets.
STANDARD_SETTINGS_KEYS = {
    "ReverseComplement",  # 1 = reverse-complement R2 (Nextera Mate Pair), 0 = all others
    "Adapter",            # Read 1 adapter (legacy single-key form)
    "AdapterRead2",       # Read 2 adapter — used alongside Adapter key per IEM spec
    "AdapterRead1",       # Explicit Read 1 adapter (BCLConvert V1-mode alias)
}

#: Default IEM section names (lowercase, as stored internally).
DEFAULT_SECTIONS = ["header", "reads", "settings", "manifests", "data"]

#: Named tuple used to hold raw section content.
SheetInfo = namedtuple("SheetInfo", DEFAULT_SECTIONS, defaults=([], [], [], [], []))

#: Characters to strip during cleaning (quotes, carriage returns, tabs).
_RX_STRIP = re.compile(r"['\"\r\t]")
_RX_NO_WS = re.compile(r"[\s\t\r]+")


class SampleSheetV1:
    """
    Parser for Illumina Experiment Manager (IEM) V1 sample sheets.

    This is the classic format used with ``bcl2fastq``, characterised by
    ``IEMFileVersion`` in the ``[Header]`` section.

    Parameters
    ----------
    path:
        Path to the ``SampleSheet.csv`` file.
    clean:
        If ``True`` (default), apply whitespace and BOM cleaning before
        parsing. A ``.backup`` copy of the original is kept alongside the
        file.
    experiment_id:
        If provided, overrides the ``Experiment Name`` field in the header.
        Useful when running automated pipelines where the run folder name
        should be used as the experiment identifier.
    parse:
        If ``True``, call :meth:`parse` immediately. If ``False``, defer
        parsing until :meth:`parse` is called explicitly.  Defaults to
        ``False``.

    Examples
    --------
    >>> sheet = SampleSheetV1("SampleSheet.csv")
    >>> sheet.parse()
    >>> for sample in sheet.samples():
    ...     print(sample["sample_id"], sample["index"])

    Notes
    -----
    The ``[Manifests]`` section is read and preserved but not
    interpreted — it is instrument-specific metadata rarely needed
    downstream.
    """

    #: Set to ``True`` in subclasses to parse on instantiation.
    AUTO_PARSE: bool = False

    def __init__(
        self,
        path: str | Path,
        *,
        clean: bool = True,
        experiment_id: str | None = None,
        parse: bool | None = None,
    ) -> None:
        self.path: str = str(path)
        self.experiment_id: str | None = experiment_id

        # Parsed attributes — populated by parse()
        self.raw: SheetInfo = SheetInfo()
        self.header: dict[str, str] | None = None
        self.columns: list[str] | None = None
        self.records: list[dict[str, str]] | None = None
        self.adapters: list[str] = []
        self.adapter_read1: str = ""
        self.adapter_read2: str = ""
        self.settings: dict[str, str] = {}
        self.read_lengths: list[int] = []

        # Header-derived attributes
        self.experiment_name: str | None = None
        self.date: str | None = None
        self.workflow: str | None = None
        self.application: str | None = None
        self.instrument_type: str | None = None
        self.assay: str | None = None
        self.index_adapters: str | None = None
        self.chemistry: str | None = None
        self.iem_version: str | None = None

        # Settings-derived attributes
        self.reverse_complement: int = 0

        # Experiment ID breakdown (parsed by parse_experiment_id)
        self.seq_date: str | None = None
        self.instrument_id: str | None = None
        self.flowcell_id: str | None = None
        self.flowcell_side: str | None = None

        if parse or (parse is None and self.AUTO_PARSE):
            self.parse(do_clean=clean)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def parse(self, do_clean: bool = True) -> None:
        """Read and parse all sections.

        Parameters
        ----------
        do_clean:
            Apply cleaning before reading (default ``True``).

        Raises
        ------
        ValueError
            If required sections (``[Header]``, ``[Data]``) cannot be parsed.
        """
        if do_clean:
            self.clean()

        self.read()

        # Required sections — raise on failure
        for name, method in [("Header", self.parse_header), ("Data", self.parse_data)]:
            try:
                method()
            except Exception as exc:
                raise ValueError(
                    f"Invalid sample sheet. Error parsing [{name}]: {exc}"
                ) from exc

        # Optional sections — warn on failure
        for name, method in [
            ("Reads",    self.parse_reads),
            ("Settings", self.parse_settings),
        ]:
            try:
                method()
            except Exception as exc:
                logger.warning(f'Error parsing "{name}": {exc}')

        # Best-effort experiment ID parsing
        if self.experiment_id:
            try:
                self._parse_experiment_id()
            except ValueError as exc:
                logger.warning(f"Could not parse experiment ID: {exc}")

    def samples(self) -> list[dict[str, str | None]]:
        """Return one record per unique sample.

        Returns a list of dicts with normalised, lowercase keys. All
        standard IEM columns are included; custom columns from the
        ``[Data]`` section are preserved as-is.

        Returns
        -------
        list[dict]
            Each dict contains at minimum:
            ``sample_id``, ``sample_name``, ``lane``, ``index``,
            ``index2``, ``i7_index_id``, ``i5_index_id``,
            ``sample_project``, ``description``.
        """
        if self.records is None:
            raise RuntimeError("Call parse() before accessing samples().")

        seen: set[str] = set()
        sample_list: list[dict[str, str | None]] = []

        for record in self.records:
            sample_id = record.get("Sample_ID", "")
            if sample_id in seen:
                continue
            seen.add(sample_id)

            sample_list.append({
                "sample_id":       sample_id,
                "sample_name":     record.get("Sample_Name"),
                "lane":            record.get("Lane"),
                "i7_index_id":     record.get("I7_Index_ID"),
                "index":           record.get("index"),
                "i5_index_id":     record.get("I5_Index_ID"),
                "index2":          record.get("index2"),
                "sample_plate":    record.get("Sample_Plate"),
                "sample_well":     record.get("Sample_Well"),
                "sample_project":  record.get("Sample_Project"),
                "description":     record.get("Description"),
                "flowcell_id":     self.flowcell_id,
                "experiment_name": self.experiment_name,
                # pass through any custom columns
                **{
                    k: v for k, v in record.items()
                    if k not in STANDARD_DATA_COLUMNS
                },
            })

        return sample_list

    def index_type(self) -> str:
        """Return ``"dual"``, ``"single"``, or ``"none"`` based on [Data] columns.

        Returns
        -------
        str
            Index type string. See :class:`~samplesheet_parser.enums.IndexType`.
        """
        if self.columns is None:
            raise RuntimeError("Call parse() before calling index_type().")
        cols = set(self.columns)
        if "index2" in cols or "I5_Index_ID" in cols:
            return "dual"
        if "index" in cols or "I7_Index_ID" in cols:
            return "single"
        return "none"

    # ------------------------------------------------------------------
    # Parsing methods
    # ------------------------------------------------------------------

    def clean(self) -> str:
        """Clean the sample sheet in-place.

        Actions
        -------
        1. Strip quotes (single and double), carriage returns, and tabs.
        2. Replace ``Experiment Name`` value if ``experiment_id`` is set.
        3. Strip all whitespace from rows inside ``[Data]``.

        A backup of the original is written to ``<path>.backup``.

        Returns
        -------
        str
            Path to the cleaned file (same as ``self.path``).
        """
        tmp_path    = self.path + ".tmp"
        backup_path = self.path + ".backup"
        in_data = False

        with open(self.path, newline="\n", encoding="utf-8-sig") as ih, \
             open(tmp_path, "w", encoding="utf-8") as oh:
            for line in ih:
                # Strip tabs and carriage returns everywhere
                line = re.sub(r"[\t\r]", "", line)

                # Replace experiment name if requested
                if self.experiment_id and line.lower().startswith("experiment name"):
                    cols = line.split(",")
                    if len(cols) >= 2:
                        self.experiment_name = cols[1].strip()
                        cols[1] = self.experiment_id
                        line = ",".join(cols)
                        if not line.endswith("\n"):
                            line += "\n"

                oh.write(line)

                if "[data]" in line.lower():
                    # Write the column header line as-is
                    oh.write(next(ih))
                    in_data = True
                    break

            if in_data:
                for line in ih:
                    line = _RX_NO_WS.sub("", line)
                    oh.write(line + "\n")

        os.rename(self.path, backup_path)
        os.rename(tmp_path, self.path)
        return self.path

    def read(self) -> None:
        """Read the file and bucket lines by section into ``self.raw``."""
        section_dict: dict[str, list[str]] = {s: [] for s in DEFAULT_SECTIONS}
        curr_section: str | None = None

        with open(self.path, newline="\n", encoding="utf-8-sig") as fh:
            for line in fh:
                line = _RX_STRIP.sub("", line)

                if line.startswith("["):
                    try:
                        curr_section = line[1 : line.index("]")].lower()
                    except ValueError:
                        continue
                    if curr_section not in section_dict:
                        section_dict[curr_section] = []
                    continue

                if not curr_section:
                    continue

                stripped = line.strip()
                if not stripped or stripped.startswith("#") or not stripped.strip(","):
                    continue

                section_dict.setdefault(curr_section, []).append(stripped)

        self.raw = SheetInfo(**{k: section_dict.get(k, []) for k in DEFAULT_SECTIONS})

    def parse_header(self) -> None:
        """Parse the ``[Header]`` section into ``self.header``."""
        header: dict[str, str] = {}
        for line in self.raw.header:
            parts = line.split(",", 1)
            if len(parts) == 2:
                key, value = parts[0].strip(), parts[1].strip()
                header[key] = value

        self.header = header

        # Extract well-known attributes
        self.iem_version     = header.get("IEMFileVersion")
        self.experiment_name = header.get("Experiment Name")
        self.date            = header.get("Date")
        self.workflow        = header.get("Workflow")
        self.application     = header.get("Application")
        self.instrument_type = header.get("Instrument Type")
        self.assay           = header.get("Assay")
        self.index_adapters  = header.get("Index Adapters")
        self.chemistry       = header.get("Chemistry")

        # Honour experiment_id override
        if self.experiment_id and self.experiment_name != self.experiment_id:
            self.experiment_name = self.experiment_id

    def parse_reads(self) -> None:
        """Parse the ``[Reads]`` section into ``self.read_lengths``."""
        self.read_lengths = []
        for line in self.raw.reads:
            try:
                self.read_lengths.append(int(line.split(",")[0]))
            except ValueError:
                logger.warning(f"Skipping non-integer read length: {line!r}")

    def parse_settings(self) -> None:
        """Parse the ``[Settings]`` section; extract adapter sequences.

        Handles all three IEM adapter key variants:

        * ``Adapter``      -- single adapter applied to both reads (legacy bcl2fastq)
        * ``AdapterRead1`` -- Read 1 adapter (bcl2fastq v2.20+ and BCLConvert V1 mode)
        * ``AdapterRead2`` -- Read 2 adapter (bcl2fastq v2.20+ and BCLConvert V1 mode)

        ``self.adapters`` is kept as a flat list for backward compatibility.
        ``self.adapter_read1`` / ``self.adapter_read2`` give direct per-read access.
        """
        settings: dict[str, str] = {}
        for line in self.raw.settings:
            parts = line.split(",", 1)
            if len(parts) == 2:
                settings[parts[0].strip()] = parts[1].strip()

        self.settings = settings

        # Adapter precedence per IEM V1 spec (Illumina Knowledge Article #2204):
        #   "Adapter"      = Read 1 adapter (primary legacy key)
        #   "AdapterRead2" = Read 2 adapter (explicitly separate key)
        #   "AdapterRead1" = BCLConvert V1-mode alias for Adapter (lower precedence)
        #
        # Note: adapter_read2 does NOT fall back to Adapter — a sheet with only
        # Adapter configured is Read-1-only trimming, not symmetric trimming.
        self.adapter_read1 = settings.get("AdapterRead1") or settings.get("Adapter", "")
        self.adapter_read2 = settings.get("AdapterRead2", "")

        # ReverseComplement: 1 = reverse-complement R2 (Nextera Mate Pair only)
        try:
            self.reverse_complement = int(settings.get("ReverseComplement", 0))
        except ValueError:
            self.reverse_complement = 0
            logger.warning("Invalid ReverseComplement value; defaulting to 0")

        # Flat list for callers that just need all configured adapters
        self.adapters = [a for a in [self.adapter_read1, self.adapter_read2] if a]

    def parse_data(self) -> None:
        """Parse the ``[Data]`` section into ``self.columns`` and ``self.records``."""
        lines = self.raw.data
        if not lines:
            raise ValueError("Empty [Data] section.")

        columns  = [c.strip() for c in lines[0].split(",")]
        records: list[dict[str, str]] = []

        for line in lines[1:]:
            values = line.split(",")
            if len(values) != len(columns):
                logger.warning(f"Skipping malformed Data line: {line!r}")
                continue
            record = {k: v.strip() for k, v in zip(columns, values, strict=False)}
            records.append(record)

        self.columns = columns
        self.records = records

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_experiment_id(self) -> None:
        """Parse the Illumina run folder name into component attributes.

        Expected format (from Illumina documentation)::

            YYMMDD_<InstrumentID>_<RunNumber>_<FlowcellSide><FlowcellID>
            e.g. 240115_A01234_0042_AHJLG7DRXX

        Sets ``seq_date``, ``instrument_id``, ``flowcell_side``,
        ``flowcell_id`` attributes.
        """
        if not self.experiment_id:
            return

        pattern = re.compile(
            r"^(?P<seq_date>\d+)"
            r"_(?P<instrument_id>\w+)"
            r"_(?P<run_number>\d+)"
            r"_(?P<flowcell_side>[AB])"
            r"(?P<flowcell_id>\w+)$"
        )
        match = pattern.match(self.experiment_id)
        if not match:
            raise ValueError(
                f"Experiment ID '{self.experiment_id}' does not match expected "
                f"Illumina run folder format (YYMMDD_InstrumentID_RunNumber_SideFlowcellID)."
            )
        self.seq_date      = match.group("seq_date")
        self.instrument_id = match.group("instrument_id")
        self.flowcell_side = match.group("flowcell_side")
        self.flowcell_id   = match.group("flowcell_id")

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        n = len(self.records) if self.records else "?"
        return f"SampleSheetV1(path={self.path!r}, records={n})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SampleSheetV1):
            return NotImplemented
        return self.records == other.records
