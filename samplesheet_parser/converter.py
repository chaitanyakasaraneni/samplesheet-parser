"""
Format converter for Illumina sample sheets.

Converts between IEM V1 (bcl2fastq) and BCLConvert V2 formats using
the existing parsers as the read layer and writing the output directly.

V1 → V2
--------
- [Header] IEM fields are mapped to BCLConvert equivalents
- [Reads] list format is converted to key-value Read1Cycles / Read2Cycles
- [Settings] Adapter keys are mapped to AdapterRead1 / AdapterRead2
- [Data] columns are remapped: ``index`` → ``Index``, ``index2`` → ``Index2``
- V2-only fields (OverrideCycles) are left empty unless explicitly provided

V2 → V1
--------
This is a **lossy** conversion. The following V2 fields have no V1
equivalent and are dropped with a warning:

- ``OverrideCycles``
- ``Cloud_Data`` / ``Cloud_Settings`` sections
- Per-sample ``OverrideCycles`` column
- ``InstrumentPlatform``, ``SoftwareVersion`` (BCLConvert-specific)

Examples
--------
>>> from samplesheet_parser import SampleSheetConverter
>>>
>>> # V1 → V2
>>> SampleSheetConverter("SampleSheet_v1.csv").to_v2("SampleSheet_v2.csv")
>>>
>>> # V2 → V1 (lossy)
>>> SampleSheetConverter("SampleSheet_v2.csv").to_v1("SampleSheet_v1.csv")
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.factory import SampleSheetFactory
from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2

# ---------------------------------------------------------------------------
# Field mappings
# ---------------------------------------------------------------------------

# IEM V1 [Header] key → BCLConvert V2 [Header] key
_V1_TO_V2_HEADER: dict[str, str] = {
    "Experiment Name": "RunName",
    "Date":            "RunDescription",   # closest V2 equivalent
    "Description":     "RunDescription",
}

# V2-only fields that have no V1 equivalent — dropped on V2 → V1
_V2_ONLY_SETTINGS: set[str] = {
    "OverrideCycles",
    "FastqCompressionFormat",
    "BarcodeMismatchesIndex1",
    "BarcodeMismatchesIndex2",
    "CreateFastqForIndexReads",
    "NoLaneSplitting",
    "TrimUMI",
    "SoftwareVersion",
}

_V2_ONLY_HEADER: set[str] = {
    "FileFormatVersion",
    "InstrumentPlatform",
    "InstrumentType",
}

_V2_ONLY_DATA_COLUMNS: set[str] = {
    "OverrideCycles",
}


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------

class SampleSheetConverter:
    """
    Converts Illumina sample sheets between IEM V1 and BCLConvert V2 formats.

    Parameters
    ----------
    path:
        Path to the source ``SampleSheet.csv`` file. The format is
        auto-detected using :class:`~samplesheet_parser.SampleSheetFactory`.

    Examples
    --------
    >>> conv = SampleSheetConverter("SampleSheet_v1.csv")
    >>> print(conv.source_version)   # SampleSheetVersion.V1
    >>> conv.to_v2("SampleSheet_v2.csv")

    >>> conv = SampleSheetConverter("SampleSheet_v2.csv")
    >>> conv.to_v1("SampleSheet_v1.csv")  # emits warnings for dropped fields
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        factory   = SampleSheetFactory()
        self._sheet = factory.create_parser(self.path, parse=True)
        self.source_version: SampleSheetVersion = factory.version  # type: ignore[assignment]
        logger.info(f"SampleSheetConverter: detected {self.source_version} for {self.path}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def to_v2(self, output_path: str | Path) -> Path:
        """Convert a V1 sheet to BCLConvert V2 format and write to *output_path*.

        Parameters
        ----------
        output_path:
            Destination path for the converted sheet.

        Returns
        -------
        Path
            Absolute path to the written file.

        Raises
        ------
        ValueError
            If the source sheet is already V2.
        """
        if self.source_version == SampleSheetVersion.V2:
            raise ValueError(
                "Source sheet is already V2. No conversion needed."
            )

        sheet = self._sheet
        assert isinstance(sheet, SampleSheetV1)

        out = Path(output_path)
        lines: list[str] = []

        # [Header]
        lines.append("[Header]")
        lines.append("FileFormatVersion,2")
        run_name = sheet.experiment_name or ""
        if run_name:
            lines.append(f"RunName,{run_name}")
        if sheet.date:
            lines.append(f"RunDescription,{sheet.date}")
        lines.append("")

        # [Reads]
        lines.append("[Reads]")
        if sheet.read_lengths:
            lines.append(f"Read1Cycles,{sheet.read_lengths[0]}")
            if len(sheet.read_lengths) > 1:
                lines.append(f"Read2Cycles,{sheet.read_lengths[1]}")
        lines.append("")

        # [BCLConvert_Settings]
        lines.append("[BCLConvert_Settings]")
        if sheet.adapter_read1:
            lines.append(f"AdapterRead1,{sheet.adapter_read1}")
        if sheet.adapter_read2:
            lines.append(f"AdapterRead2,{sheet.adapter_read2}")
        # Emit empty OverrideCycles placeholder — caller can fill in
        lines.append("# OverrideCycles — fill in if using UMIs or custom cycle counts")
        lines.append("")

        # [BCLConvert_Data]
        lines.append("[BCLConvert_Data]")
        if sheet.records:
            # Build V2 column header — remap V1 column names to V2
            v2_columns = self._v1_data_columns_to_v2(sheet.columns or [])
            lines.append(",".join(v2_columns))
            for record in sheet.records:
                row = self._v1_record_to_v2(record, sheet.columns or [], v2_columns)
                lines.append(",".join(row))
        lines.append("")

        out.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Wrote V2 sheet to {out}")
        return out.resolve()

    def to_v1(self, output_path: str | Path) -> Path:
        """Convert a V2 sheet to IEM V1 format and write to *output_path*.

        This is a **lossy** conversion. V2-only fields (``OverrideCycles``,
        ``Cloud_Data``, ``InstrumentPlatform``, etc.) are dropped and a
        warning is logged for each dropped field.

        Parameters
        ----------
        output_path:
            Destination path for the converted sheet.

        Returns
        -------
        Path
            Absolute path to the written file.

        Raises
        ------
        ValueError
            If the source sheet is already V1.
        """
        if self.source_version == SampleSheetVersion.V1:
            raise ValueError(
                "Source sheet is already V1. No conversion needed."
            )

        sheet = self._sheet
        assert isinstance(sheet, SampleSheetV2)

        out = Path(output_path)
        lines: list[str] = []
        dropped: list[str] = []

        # [Header]
        lines.append("[Header]")
        lines.append("IEMFileVersion,5")

        run_name = (
            sheet.experiment_name
            or (sheet.header.get("RunName") if sheet.header else None)
            or ""
        )
        if run_name:
            lines.append(f"Experiment Name,{run_name}")

        run_desc = sheet.header.get("RunDescription", "") if sheet.header else ""
        if run_desc:
            lines.append(f"Date,{run_desc}")

        # Track dropped V2-only header fields
        if sheet.header:
            for key in _V2_ONLY_HEADER:
                if key in sheet.header:
                    dropped.append(f"[Header] {key}")

        lines.append("Workflow,GenerateFASTQ")
        lines.append("Application,FASTQ Only")
        lines.append("")

        # [Reads]
        lines.append("[Reads]")
        if sheet.reads:
            r1 = sheet.reads.get("Read1Cycles")
            r2 = sheet.reads.get("Read2Cycles")
            if r1:
                lines.append(str(r1))
            if r2:
                lines.append(str(r2))
        lines.append("")

        # [Settings]
        lines.append("[Settings]")
        if sheet.settings:
            adapter_r1 = sheet.settings.get("AdapterRead1", "")
            adapter_r2 = sheet.settings.get("AdapterRead2", "")
            if adapter_r1:
                lines.append(f"AdapterRead1,{adapter_r1}")
            if adapter_r2:
                lines.append(f"AdapterRead2,{adapter_r2}")

            # Track dropped V2-only settings
            for key in _V2_ONLY_SETTINGS:
                if key in sheet.settings:
                    dropped.append(f"[BCLConvert_Settings] {key}")
        lines.append("")

        # [Data]
        lines.append("[Data]")
        if sheet.records and sheet.columns:
            v1_columns = self._v2_data_columns_to_v1(sheet.columns)

            # Track dropped V2-only data columns
            for col in _V2_ONLY_DATA_COLUMNS:
                if col in sheet.columns:
                    dropped.append(f"[BCLConvert_Data] column: {col}")

            lines.append(",".join(v1_columns))
            for record in sheet.records:
                row = self._v2_record_to_v1(record, sheet.columns, v1_columns)
                lines.append(",".join(row))
        lines.append("")

        # Warn about dropped fields
        if dropped:
            logger.warning(
                f"V2 → V1 conversion dropped {len(dropped)} field(s) with no V1 equivalent:"
            )
            for field in dropped:
                logger.warning(f"  - {field}")
            if sheet.cloud_data:
                logger.warning(
                    "  - [Cloud_Data] section (entire section dropped — no V1 equivalent)"
                )

        out.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Wrote V1 sheet to {out}")
        return out.resolve()

    # ------------------------------------------------------------------
    # Column remapping helpers
    # ------------------------------------------------------------------

    def _v1_data_columns_to_v2(self, v1_columns: list[str]) -> list[str]:
        """Map V1 [Data] column names to V2 [BCLConvert_Data] equivalents."""
        mapping = {
            "Sample_ID":      "Sample_ID",
            "Sample_Name":    "Sample_Name",
            "Lane":           "Lane",
            "index":          "Index",
            "index2":         "Index2",
            "Sample_Project": "Sample_Project",
            # Drop V1-only columns
            "I7_Index_ID":    None,
            "I5_Index_ID":    None,
            "Sample_Plate":   None,
            "Sample_Well":    None,
            "Description":    None,
        }
        result = []
        for col in v1_columns:
            mapped = mapping.get(col, col)  # preserve unknown/custom columns
            if mapped is not None:
                result.append(mapped)
        return result

    def _v1_record_to_v2(
        self,
        record: dict[str, str],
        v1_columns: list[str],
        v2_columns: list[str],
    ) -> list[str]:
        """Convert a single V1 data record to a V2 row."""
        col_map = {
            "index":  "Index",
            "index2": "Index2",
        }
        # Build intermediate dict with V2 keys
        v2_record: dict[str, str] = {}
        for k, v in record.items():
            new_key = col_map.get(k, k)
            if new_key in v2_columns:
                v2_record[new_key] = v

        return [v2_record.get(col, "") for col in v2_columns]

    def _v2_data_columns_to_v1(self, v2_columns: list[str]) -> list[str]:
        """Map V2 [BCLConvert_Data] column names to V1 [Data] equivalents."""
        mapping = {
            "Sample_ID":      "Sample_ID",
            "Sample_Name":    "Sample_Name",
            "Lane":           "Lane",
            "Index":          "index",
            "Index2":         "index2",
            "Sample_Project": "Sample_Project",
        }
        result = []
        for col in v2_columns:
            if col in _V2_ONLY_DATA_COLUMNS:
                continue   # drop silently — already warned above
            mapped = mapping.get(col, col)
            result.append(mapped)
        return result

    def _v2_record_to_v1(
        self,
        record: dict[str, str],
        v2_columns: list[str],
        v1_columns: list[str],
    ) -> list[str]:
        """Convert a single V2 data record to a V1 row."""
        col_map = {
            "Index":  "index",
            "Index2": "index2",
        }
        v1_record: dict[str, str] = {}
        for k, v in record.items():
            if k in _V2_ONLY_DATA_COLUMNS:
                continue
            new_key = col_map.get(k, k)
            if new_key in v1_columns:
                v1_record[new_key] = v

        return [v1_record.get(col, "") for col in v1_columns]

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"SampleSheetConverter("
            f"path={self.path!r}, "
            f"source_version={self.source_version!r})"
        )
