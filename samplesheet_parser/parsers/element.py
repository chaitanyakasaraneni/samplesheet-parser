"""
Parser for Element Biosciences AVITI ``RunManifest.csv`` files.

The AVITI platform (Element Biosciences) is not an Illumina instrument, but
its run manifest is a sectioned CSV very much in the spirit of an Illumina
sample sheet, so it slots into this library through the structural
:class:`~samplesheet_parser.protocol.SampleSheetParser` protocol - no
inheritance from the Illumina parsers required. Registering it lets the same
factory, validator, and colour-balance machinery work across vendors.

Manifest layout
---------------
A RunManifest is made of named sections, each introduced by a
``[SectionName]`` line::

    [RUNVALUES]
    KeyName, Value
    run_name, MyRun

    [SETTINGS]
    SettingName, Value
    R1Adapter, AGATCGGAAGAGC

    [SAMPLES]
    SampleName, Index1, Index2, Lane
    Sample1, ACGTACGTAC, TGCATGCATG, 1
    Sample2, GGTTCCAAGG, CCAAGGTTCC, 1

``[RUNVALUES]`` and ``[SETTINGS]`` are key/value tables; ``[SAMPLES]`` is a
columnar table. Column and key names are matched case-insensitively because
Element manifests are not strict about casing.

Field mapping to the shared sample record
-----------------------------------------
==================  =========================
RunManifest column  Shared ``samples()`` key
==================  =========================
``SampleName``      ``sample_id``
``Index1``          ``index``
``Index2``          ``index2``
``Lane``            ``lane``
``Project``         ``sample_project``
==================  =========================

Authors
-------
Chaitanya Kasaraneni
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Section names, lowercased.
_RUNVALUES = "runvalues"
_SETTINGS = "settings"
_SAMPLES = "samples"

# Manifest sample-column name (lowercased) -> shared record key.
_SAMPLE_COLUMN_MAP = {
    "samplename": "sample_id",
    "index1": "index",
    "index2": "index2",
    "lane": "lane",
    "project": "sample_project",
}

# Settings keys (lowercased) that hold adapter sequences.
_ADAPTER_SETTING_KEYS = {"r1adapter", "r2adapter", "adapterread1", "adapterread2"}


def _split_sections(path: Path) -> dict[str, list[str]]:
    """Split a manifest into ``{lowercased_section_name: [raw_lines]}``."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for raw in fh:
            line = raw.rstrip("\n").rstrip("\r")
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                current = stripped[1:-1].strip().lower()
                sections.setdefault(current, [])
                continue
            if current is not None:
                sections[current].append(line)
    return sections


def _parse_kv(lines: list[str]) -> dict[str, str]:
    """Parse a key/value section, skipping an optional header row.

    A leading row whose first cell is a generic label (``KeyName`` /
    ``SettingName``) is treated as a header and dropped.
    """
    out: dict[str, str] = {}
    for row in csv.reader(lines):
        if not row:
            continue
        key = row[0].strip()
        if not key:
            continue
        if key.lower() in ("keyname", "settingname") and len(out) == 0:
            continue  # header row
        value = row[1].strip() if len(row) > 1 else ""
        out[key] = value
    return out


class ElementRunManifest:
    """Parser for an Element Biosciences AVITI ``RunManifest.csv``.

    Implements the :class:`~samplesheet_parser.protocol.SampleSheetParser`
    protocol so it works with :class:`~samplesheet_parser.factory.SampleSheetFactory`,
    :class:`~samplesheet_parser.validators.SampleSheetValidator`, and the
    colour-balance checks. AVITI uses four-channel avidity chemistry, so
    colour-balance validation flags low-diversity index cycles once the
    instrument is resolved (the parser reports ``instrument = "AVITI"``
    unless the manifest overrides it).

    Parameters
    ----------
    path:
        Path to the ``RunManifest.csv`` file.
    clean:
        Accepted for signature compatibility with the Illumina parsers; the
        manifest parser already trims whitespace, so this is a no-op.
    experiment_id:
        Optional override stored on the instance for callers that key on it.
    parse:
        If truthy, parse immediately on construction (matches the factory's
        ``parse=`` contract).
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
        self.header: dict[str, str] | None = None
        self.settings: dict[str, str] | None = None
        self.columns: list[str] | None = None
        self.records: list[dict[str, str]] = []
        self.adapters: list[str] = []
        self.sections: list[str] = []
        self.instrument: str | None = None
        self._section_dict: dict[str, list[str]] = {}

        if parse or (parse is None and self.AUTO_PARSE):
            self.parse(do_clean=clean)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse(
        self,
        do_clean: bool = True,
        required_sections: list[str] | None = None,
    ) -> None:
        """Read and parse the manifest sections.

        Parameters
        ----------
        do_clean:
            No-op; accepted for protocol compatibility.
        required_sections:
            Section names that must be present (case-insensitive); a missing
            one raises :class:`ValueError`. ``[SAMPLES]`` is always required.
        """
        path = Path(self.path)
        if not path.exists():
            raise FileNotFoundError(f"RunManifest not found: {path}")

        section_dict = _split_sections(path)
        self._section_dict = section_dict
        self.sections = list(section_dict.keys())

        required = {s.lower() for s in (required_sections or [])} | {_SAMPLES}
        missing = [s for s in required if s not in section_dict]
        if missing:
            raise ValueError(
                f"RunManifest {path} is missing required section(s): "
                f"{', '.join('[' + m + ']' for m in sorted(missing))}"
            )

        self.header = _parse_kv(section_dict.get(_RUNVALUES, []))
        self.settings = _parse_kv(section_dict.get(_SETTINGS, []))

        # Instrument: honour an explicit manifest value, else default to AVITI.
        self.instrument = next(
            (
                self.header[k]
                for k in self.header
                if k.lower() in ("instrument", "instrumentplatform", "platform")
            ),
            "AVITI",
        )

        self.adapters = [
            v for k, v in self.settings.items() if k.lower() in _ADAPTER_SETTING_KEYS and v
        ]

        self._parse_samples(section_dict.get(_SAMPLES, []))

    def _parse_samples(self, lines: list[str]) -> None:
        rows = list(csv.reader(lines))
        if not rows:
            self.columns = []
            self.records = []
            return
        self.columns = [c.strip() for c in rows[0]]
        records: list[dict[str, str]] = []
        for row in rows[1:]:
            if not any(cell.strip() for cell in row):
                continue
            record = {
                self.columns[i]: (row[i].strip() if i < len(row) else "")
                for i in range(len(self.columns))
            }
            records.append(record)
        self.records = records

    # ------------------------------------------------------------------
    # Shared interface
    # ------------------------------------------------------------------

    def samples(self) -> list[dict[str, Any]]:
        """Return one record per sample, mapped to the shared schema.

        Manifest columns are renamed to the shared keys (``sample_id``,
        ``index``, ``index2``, ``lane``, ``sample_project``); any other
        columns are preserved under their original names.
        """
        if self.columns is None:
            raise RuntimeError("Call parse() before samples().")

        result: list[dict[str, Any]] = []
        for record in self.records:
            sample: dict[str, Any] = {
                "sample_id": None,
                "index": None,
                "index2": None,
                "lane": None,
                "sample_project": None,
                "instrument_platform": self.instrument,
            }
            for col, value in record.items():
                mapped = _SAMPLE_COLUMN_MAP.get(col.lower())
                if mapped:
                    sample[mapped] = value or None
                else:
                    sample[col] = value
            result.append(sample)
        return result

    def index_type(self) -> str:
        """Return ``"dual"``, ``"single"``, or ``"none"`` from the columns."""
        if self.columns is None:
            raise RuntimeError("Call parse() before index_type().")
        lower = {c.lower() for c in self.columns}
        if "index2" in lower:
            return "dual"
        if "index1" in lower:
            return "single"
        return "none"

    def parse_custom_section(
        self,
        section_name: str,
        *,
        required: bool = False,
    ) -> dict[str, str]:
        """Parse any manifest section as a key/value dict (case-insensitive)."""
        key = section_name.strip().lower()
        lines = self._section_dict.get(key)
        if lines is None:
            if required:
                raise ValueError(f"Required section [{section_name}] not found.")
            return {}
        return _parse_kv(lines)

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    @staticmethod
    def is_manifest(path: str | Path) -> bool:
        """Return ``True`` if *path* looks like an AVITI RunManifest.

        The discriminator is a ``[SAMPLES]`` section (Illumina sheets use
        ``[Data]`` / ``[BCLConvert_Data]``) together with a ``[RUNVALUES]``
        section or a ``SampleName`` column header - markers Illumina formats
        never use. ``Index1`` is *not* required, since an AVITI manifest may
        describe an index-free run.
        """
        try:
            sections = _split_sections(Path(path))
        except (OSError, UnicodeDecodeError):
            return False
        if _SAMPLES not in sections:
            return False
        if _RUNVALUES in sections:
            return True
        sample_lines = sections.get(_SAMPLES, [])
        if sample_lines:
            header = next(csv.reader(sample_lines[:1]), [])
            cols = {c.strip().lower() for c in header}
            return "samplename" in cols
        return False

    def __repr__(self) -> str:
        n = len(self.records)
        return f"ElementRunManifest(path={self.path!r}, samples={n})"
