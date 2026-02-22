"""
BCLConvert V2 sample sheet parser.

Handles the modern sample sheet format required by Illumina BCLConvert
and by NovaSeq X series instruments. Identified by ``FileFormatVersion``
in the ``[Header]`` section, or by the presence of ``[BCLConvert_Settings]``
/ ``[BCLConvert_Data]`` sections.

Reference format
----------------
::

    [Header]
    FileFormatVersion,2
    RunName,MyRun_20240115
    InstrumentPlatform,NovaSeqXSeries

    [Reads]
    Read1Cycles,151
    Read2Cycles,151
    Index1Cycles,10
    Index2Cycles,10

    [BCLConvert_Settings]
    SoftwareVersion,3.9.3
    AdapterRead1,CTGTCTCTTATACACATCT
    AdapterRead2,CTGTCTCTTATACACATCT
    OverrideCycles,Y151;I10;I10;Y151

    [BCLConvert_Data]
    Lane,Sample_ID,Index,Index2,Sample_Project
    1,Sample1,ATTACTCG,TATAGCCT,Project1
    1,Sample2,TCCGGAGA,ATAGAGGC,Project1

Authors
-------
Chaitanya Kasaraneni — original BCLConvert pipeline enablement and
SSv2 parser implementation; this is the generalised public release.

References
----------
Illumina BCLConvert Software Guide (document # 1000000004084)
https://support.illumina.com/sequencing/sequencing_software/bcl-convert.html
"""

from __future__ import annotations

import os
import re
from collections import namedtuple
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

# ---------------------------------------------------------------------------
# Section constants
# ---------------------------------------------------------------------------

DEFAULT_SECTIONS = [
    "header",
    "reads",
    "bclconvert_settings",
    "bclconvert_data",
    "cloud_settings",
    "cloud_data",
]
SheetInfo = namedtuple("SheetInfo", DEFAULT_SECTIONS, defaults=([], [], [], [], [], []))

REQUIRED_HEADER_FIELDS: frozenset[str] = frozenset({
    "FileFormatVersion",
})

REQUIRED_DATA_COLUMNS: frozenset[str] = frozenset({
    "Sample_ID",
    "Index",
})

STANDARD_HEADER: frozenset[str] = frozenset({
    "FileFormatVersion", "RunName", "RunDescription",
    "InstrumentPlatform", "InstrumentType", "ExperimentName",
})

STANDARD_SETTINGS: frozenset[str] = frozenset({
    "SoftwareVersion", "AdapterRead1", "AdapterRead2",
    "OverrideCycles", "FastqCompressionFormat",
    "BarcodeMismatchesIndex1", "BarcodeMismatchesIndex2",
    "CreateFastqForIndexReads", "NoLaneSplitting",
    "TrimUMI",
})

STANDARD_DATA_COLUMNS: frozenset[str] = frozenset({
    "Lane", "Sample_ID", "Sample_Name", "Sample_Project",
    "Index", "Index2",
})

_RX_STRIP = re.compile(r"""['"\r\n\t]""")
_RX_NO_WS = re.compile(r"[\s\t\r]+")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ReadStructure:
    """Decoded OverrideCycles read structure.

    Attributes
    ----------
    umi_length:
        Total UMI length in bases. ``0`` if no UMI is present.
    umi_location:
        Which segment contains the UMI (e.g. ``"index1"``, ``"read1"``).
        ``None`` if no UMI.
    read_structure:
        Detailed per-segment breakdown:
        ``{"read1_template": 151, "index1_length": 10, "index1_umi": 9, ...}``
    """
    umi_length:     int = 0
    umi_location:   str | None = None
    read_structure: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class SampleSheetV2:
    """
    Parser for BCLConvert V2 sample sheets.

    This is the format required for Illumina BCLConvert ≥ 3.x and for
    NovaSeq X series instruments. It uses multi-section CSV layout with
    ``[BCLConvert_Settings]`` and ``[BCLConvert_Data]`` sections.

    Parameters
    ----------
    path:
        Path to the ``SampleSheet.csv`` file.
    clean:
        If ``True`` (default), apply in-place cleaning before parsing.
        A ``.backup`` copy of the original is preserved.
    experiment_id:
        Override the ``ExperimentName`` in the ``[Header]`` section.
    parse:
        If ``True``, call :meth:`parse` immediately on construction.
        Defaults to ``False``.

    Examples
    --------
    >>> sheet = SampleSheetV2("SampleSheet.csv")
    >>> sheet.parse()
    >>> print(sheet.get_umi_length())
    9
    >>> for s in sheet.samples():
    ...     print(s["sample_id"], s["index"])

    Notes
    -----
    Custom columns — any column in ``[BCLConvert_Data]`` whose name is not in
    :attr:`STANDARD_DATA_COLUMNS` or does not start with ``Custom_`` — are
    automatically detected and preserved in the parsed records. Access them
    via ``sheet.custom_fields["data"]``.
    """

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
        self.experiment_id = experiment_id

        # Populated by parse()
        self.raw: SheetInfo = SheetInfo()
        self.header:            dict[str, str] | None = None
        self.settings:          dict[str, str] | None = None
        self.reads:             dict[str, int]        = {}
        self.columns:           list[str] | None      = None
        self.records:           list[dict[str, str]]  = []
        self.adapters:          list[str]             = []
        self.cloud_data:        list[dict[str, str]]  = []
        self.sections:          list[str]             = []

        # Header-derived
        self.experiment_name:    str | None = None
        self.instrument_platform: str | None = None
        self.software_version:   str | None = None

        # Custom field tracking
        self.custom_fields: dict[str, set[str]] = {
            "header": set(), "settings": set(), "data": set()
        }

        if parse or (parse is None and self.AUTO_PARSE):
            self.parse(do_clean=clean)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def parse(self, do_clean: bool = True) -> None:
        """Parse all sections of the sample sheet.

        Parameters
        ----------
        do_clean:
            Run :meth:`clean` before parsing (default ``True``).

        Raises
        ------
        ValueError
            If ``[Header]`` or ``[BCLConvert_Data]`` cannot be parsed.
        """
        if do_clean:
            self.clean()
        self.read()

        for name, method in [("Header", self.parse_header), ("BCLConvert_Data", self.parse_data)]:
            try:
                method()
            except Exception as exc:
                raise ValueError(
                    f"Invalid V2 sample sheet. Error parsing [{name}]: {exc}"
                ) from exc

        for name, method in [
            ("Reads",             self.parse_reads),
            ("BCLConvert_Settings", self.parse_settings),
            ("Cloud_Data",        self.parse_cloud_data),
        ]:
            try:
                method()
            except Exception as exc:
                logger.warning(f'Error parsing "{name}": {exc}')

    def samples(self) -> list[dict[str, str | None]]:
        """Return one record per unique sample.

        Combines fields from ``[BCLConvert_Data]`` with run-level
        metadata from ``[Header]``. Custom columns are included.

        Returns
        -------
        list[dict]
            Each dict contains at minimum: ``sample_id``, ``index``,
            ``index2``, ``lane``, ``sample_project``, ``experiment_name``,
            ``run_name``, ``instrument_platform``.
        """
        seen: set[str] = set()
        result: list[dict[str, str | None]] = []

        for record in self.records:
            sid = record.get("Sample_ID", "")
            if sid in seen:
                continue
            seen.add(sid)

            sample: dict[str, str | None] = {
                "sample_id":          sid,
                "sample_name":        record.get("Sample_Name"),
                "lane":               record.get("Lane"),
                "index":              record.get("Index"),
                "index2":             record.get("Index2"),
                "sample_project":     record.get("Sample_Project"),
                "experiment_name":    self.header.get("ExperimentName") if self.header else None,
                "run_name":           self.header.get("RunName") if self.header else None,
                "instrument_platform": self.instrument_platform,
            }

            # Include custom data columns
            for col in self.custom_fields.get("data", set()):
                if col in record:
                    sample[col] = record[col]

            result.append(sample)

        return result

    def index_type(self) -> str:
        """Return ``"dual"``, ``"single"``, or ``"none"`` based on [BCLConvert_Data] columns.

        Returns
        -------
        str
            ``"dual"`` if both ``Index`` and ``Index2`` are present,
            ``"single"`` if only ``Index`` is present, otherwise ``"none"``.
        """
        if self.columns is None:
            raise RuntimeError("Call parse() before calling index_type().")
        cols = set(self.columns)
        if "Index2" in cols:
            return "dual"
        if "Index" in cols:
            return "single"
        return "none"

    def get_umi_length(self) -> int:
        """Return UMI length from the ``OverrideCycles`` setting.

        Returns
        -------
        int
            UMI length in bases. ``0`` if no UMI is present or if
            ``OverrideCycles`` is not set.
        """
        if not self.settings:
            return 0
        override = self.settings.get("OverrideCycles", "")
        return self._parse_override_cycles(override).umi_length

    def get_read_structure(self) -> ReadStructure:
        """Return the fully decoded read structure from ``OverrideCycles``.

        Returns
        -------
        ReadStructure
            Dataclass with ``umi_length``, ``umi_location``, and
            ``read_structure`` dict.
        """
        if not self.settings:
            return ReadStructure()
        override = self.settings.get("OverrideCycles", "")
        return self._parse_override_cycles(override)

    # ------------------------------------------------------------------
    # Parsing methods
    # ------------------------------------------------------------------

    def clean(self) -> str:
        """Clean the sample sheet in-place and keep a ``.backup`` copy.

        Actions
        -------
        1. Strip quotes, tabs, and extraneous whitespace.
        2. Standardise section names to ``[BCLConvert_Settings]`` /
           ``[BCLConvert_Data]``.
        3. Replace ``ExperimentName`` if ``experiment_id`` is set.
        4. Strip all whitespace from rows inside data sections.

        Returns
        -------
        str
            Path to the cleaned file.
        """
        tmp_path    = self.path + ".tmp"
        backup_path = self.path + ".backup"
        in_data = False

        with open(self.path, encoding="utf-8-sig") as ih, \
             open(tmp_path, "w", encoding="utf-8") as oh:
            for line in ih:
                line = _RX_STRIP.sub("", line.strip())

                if line.startswith("["):
                    section_lower = line.lower()
                    in_data = "data" in section_lower and "cloud" not in section_lower

                    # Standardise section names
                    if "settings" in section_lower and "cloud" not in section_lower:
                        line = "[BCLConvert_Settings]"
                    elif "data" in section_lower and "cloud" not in section_lower:
                        line = "[BCLConvert_Data]"

                    oh.write(line + "\n")
                    continue

                if self.experiment_id and line.lower().startswith("experimentname"):
                    cols = line.split(",")
                    if len(cols) >= 2:
                        self.experiment_name = cols[1].strip()
                        cols[1] = self.experiment_id
                        line = ",".join(cols)

                if in_data:
                    line = _RX_NO_WS.sub("", line)

                if line:
                    oh.write(line + "\n")
                else:
                    oh.write("\n")

        os.rename(self.path, backup_path)
        os.rename(tmp_path, self.path)
        return self.path

    def read(self) -> None:
        """Read the file and bucket lines by section into ``self.raw``."""
        section_dict: dict[str, list[str]] = {s: [] for s in DEFAULT_SECTIONS}
        section_list: list[str] = []
        curr: str | None = None

        with open(self.path, encoding="utf-8-sig") as fh:
            for line in fh:
                line_clean = _RX_STRIP.sub("", line)

                if line_clean.startswith("["):
                    try:
                        curr = line_clean[1 : line_clean.index("]")].lower()
                    except ValueError:
                        continue
                    if curr:
                        section_list.append(curr)
                        section_dict.setdefault(curr, [])
                    continue

                if not curr:
                    continue

                stripped = line_clean.strip()
                if not stripped or stripped.startswith("#") or not stripped.strip(","):
                    continue

                section_dict[curr].append(stripped)

        self.raw      = SheetInfo(**{s: section_dict.get(s, []) for s in DEFAULT_SECTIONS})
        self.sections = section_list

    def parse_header(self) -> None:
        """Parse the ``[Header]`` section."""
        header: dict[str, str] = {}
        custom: set[str]       = set()

        for line in self.raw.header:
            parts = line.split(",", 2)
            if len(parts) >= 2:
                key   = parts[0].strip()
                value = parts[1].strip()
                header[key] = value
                if key.startswith("Custom_") or key not in STANDARD_HEADER:
                    custom.add(key)

        missing = REQUIRED_HEADER_FIELDS - set(header.keys())
        if missing:
            raise ValueError(f"Missing required [Header] fields: {missing}")

        self.header             = header
        self.custom_fields["header"] = custom
        self.experiment_name    = header.get("ExperimentName") or header.get("RunName")
        self.instrument_platform = header.get("InstrumentPlatform")

        if self.experiment_id:
            self.experiment_name = self.experiment_id

    def parse_reads(self) -> None:
        """Parse the ``[Reads]`` section (key,value pairs in V2 format)."""
        reads: dict[str, int] = {}
        for line in self.raw.reads:
            parts = line.split(",", 1)
            if len(parts) == 2:
                key = parts[0].strip()
                try:
                    reads[key] = int(parts[1].strip())
                except ValueError:
                    logger.warning(f"Invalid read cycles value: {line!r}")
        self.reads = reads

    def parse_settings(self) -> None:
        """Parse the ``[BCLConvert_Settings]`` section."""
        settings: dict[str, str] = {}
        adapters: list[str]      = []
        custom: set[str]         = set()

        for line in self.raw.bclconvert_settings:
            parts = line.split(",", 2)
            if len(parts) >= 2:
                key   = parts[0].strip()
                value = parts[1].strip()
                settings[key] = value

                if "adapter" in key.lower():
                    adapters.append(value)

                if key.startswith("Custom_") or key not in STANDARD_SETTINGS:
                    custom.add(key)

        self.settings               = settings
        self.adapters               = adapters
        self.custom_fields["settings"] = custom
        self.software_version       = settings.get("SoftwareVersion")

    def parse_data(self) -> None:
        """Parse the ``[BCLConvert_Data]`` section."""
        lines = self.raw.bclconvert_data
        if not lines:
            raise ValueError("Empty [BCLConvert_Data] section.")

        columns = [c.strip() for c in lines[0].split(",")]
        custom  = {
            c for c in columns
            if c.startswith("Custom_") or c not in STANDARD_DATA_COLUMNS
        }

        missing = REQUIRED_DATA_COLUMNS - set(columns)
        if missing:
            raise ValueError(f"Missing required [BCLConvert_Data] columns: {missing}")

        records: list[dict[str, str]] = []
        for line in lines[1:]:
            values = line.split(",")
            if len(values) != len(columns):
                logger.warning(f"Skipping malformed BCLConvert_Data line: {line!r}")
                continue
            record = {k: v.strip() for k, v in zip(columns, values, strict=False) if k}
            record = {k: v for k, v in record.items() if v}
            records.append(record)

        self.columns                = columns
        self.records                = records
        self.custom_fields["data"]  = custom

    def parse_cloud_data(self) -> None:
        """Parse the optional ``[Cloud_Data]`` section."""
        if not self.raw.cloud_data:
            return

        headers = [c.strip() for c in self.raw.cloud_data[0].split(",")]
        records: list[dict[str, str]] = []

        for line in self.raw.cloud_data[1:]:
            values = line.split(",")
            if len(values) != len(headers):
                logger.warning(f"Skipping malformed Cloud_Data line: {line!r}")
                continue
            records.append({h: v.strip() for h, v in zip(headers, values, strict=False)})

        self.cloud_data = records

    # ------------------------------------------------------------------
    # OverrideCycles decoder
    # ------------------------------------------------------------------

    def _parse_override_cycles(self, override_str: str) -> ReadStructure:
        """Decode an Illumina OverrideCycles string.

        Parameters
        ----------
        override_str:
            E.g. ``"Y151;I10U9;I10;Y151"`` or ``"U5Y146;I8;I8;U5Y146"``.

        Returns
        -------
        ReadStructure
            Decoded structure with UMI length, location, and per-segment
            breakdown.

        Notes
        -----
        The OverrideCycles format is documented in the BCLConvert User
        Guide. Supported cycle type codes:

        - ``Y`` — template read
        - ``I`` — index
        - ``U`` — UMI
        - ``N`` — masked (skipped) bases
        """
        if not override_str:
            return ReadStructure()

        segments     = override_str.strip().split(";")
        read_struct: dict[str, int] = {}
        umi_length   = 0
        umi_location: str | None = None

        for i, segment in enumerate(segments, start=1):
            # Pattern like I10U9 — index immediately followed by UMI
            m = re.match(r"I(\d+)U(\d+)", segment)
            if m:
                idx_len, umi_len = int(m.group(1)), int(m.group(2))
                read_struct[f"index{i}_length"] = idx_len
                read_struct[f"index{i}_umi"]    = umi_len
                if umi_len > umi_length:
                    umi_length   = umi_len
                    umi_location = f"index{i}"
                continue

            # General case — iterate over (TypeCode, Length) pairs
            components = re.findall(r"([A-Z])(\d+)", segment)

            for _j, (code, length_str) in enumerate(components):
                length = int(length_str)

                if code == "U":
                    read_struct[f"read{i}_umi"] = length
                    if length > umi_length:
                        umi_length   = length
                        umi_location = f"read{i}"

                elif code == "Y":
                    if f"read{i}_template" not in read_struct:
                        read_struct[f"read{i}_template"] = length

                elif code == "I":
                    read_struct[f"index{i}_length"] = length

                elif code == "N":
                    read_struct[f"read{i}_masked"] = length

        return ReadStructure(
            umi_length=umi_length,
            umi_location=umi_location,
            read_structure=read_struct,
        )

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        n = len(self.records) if self.records else "?"
        return f"SampleSheetV2(path={self.path!r}, records={n})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SampleSheetV2):
            return NotImplemented
        return self.records == other.records
