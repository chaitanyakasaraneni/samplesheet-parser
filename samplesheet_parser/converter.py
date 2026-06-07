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
- ``FileFormatVersion`` (replaced by ``IEMFileVersion``)
- ``SoftwareVersion`` and other BCLConvert-specific settings

``InstrumentPlatform`` / ``InstrumentType`` are mapped to the V1
``Instrument Type`` header so the workflow signal survives a round
trip; they are not dropped.

Index 2 (i5) orientation
------------------------
``bcl2fastq`` and ``BCLConvert`` disagree on the orientation of i5 for
workflow-B instruments (NovaSeq X / X Plus, NextSeq 500/550/1000/2000,
iSeq 100, MiniSeq, HiSeq 3000/4000). For those instruments, ``Index2``
is reverse-complemented on conversion in both directions. The workflow
is auto-detected from the V1 ``Instrument Type`` or V2
``InstrumentPlatform`` header; pass ``workflow=`` to override.

If the sheet has a non-empty Index2 column and the workflow cannot be
determined and no override is given, conversion fails with a clear
error rather than silently producing a wrong sheet. See
:mod:`samplesheet_parser.instruments`.

Examples
--------
>>> from samplesheet_parser import SampleSheetConverter
>>>
>>> # V1 → V2 — workflow auto-detected from [Header] Instrument Type
>>> SampleSheetConverter("SampleSheet_v1.csv").to_v2("SampleSheet_v2.csv")
>>>
>>> # V2 → V1 with explicit workflow override (e.g. NovaSeq 6000 v1.5)
>>> SampleSheetConverter("SampleSheet_v2.csv", workflow="b").to_v1("SampleSheet_v1.csv")
"""

from __future__ import annotations

import logging
from pathlib import Path

from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.factory import SampleSheetFactory
from samplesheet_parser.instruments import (
    Workflow,
    detect_workflow,
    parse_workflow,
    reverse_complement,
)
from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field mappings
# ---------------------------------------------------------------------------

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

# Fields that have no V1 counterpart and are dropped silently on V2 → V1.
# (FileFormatVersion is replaced by IEMFileVersion.)
_V2_ONLY_HEADER: set[str] = {
    "FileFormatVersion",
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
    workflow:
        Instrument i5 workflow override. Accepts :class:`Workflow` or the
        strings ``"a"`` / ``"b"``. When ``None`` (default), the workflow
        is auto-detected from the V1 ``Instrument Type`` or V2
        ``InstrumentPlatform`` header. Pass an explicit value for
        chemistry-dependent instruments (e.g. NovaSeq 6000) or when the
        instrument field is missing.

    Examples
    --------
    >>> conv = SampleSheetConverter("SampleSheet_v1.csv")
    >>> print(conv.source_version)   # SampleSheetVersion.V1
    >>> conv.to_v2("SampleSheet_v2.csv")

    >>> conv = SampleSheetConverter("SampleSheet_v2.csv")
    >>> conv.to_v1("SampleSheet_v1.csv")  # emits warnings for dropped fields

    >>> # NovaSeq 6000 with v1.5 chemistry — must override (ambiguous)
    >>> SampleSheetConverter("SampleSheet.csv", workflow="b").to_v2("out.csv")
    """

    def __init__(
        self,
        path: str | Path,
        *,
        workflow: Workflow | str | None = None,
    ) -> None:
        self.path = Path(path)
        factory = SampleSheetFactory()
        # clean=False: converter must never modify or back up the source file
        self._sheet = factory.create_parser(self.path, parse=True, clean=False)
        self.source_version: SampleSheetVersion = factory.version  # type: ignore[assignment]
        self.workflow_override: Workflow | None = parse_workflow(workflow)
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
            raise ValueError("Source sheet is already V2. No conversion needed.")

        sheet = self._sheet
        if not isinstance(sheet, SampleSheetV1):
            raise TypeError(
                f"Expected SampleSheetV1 for V1 \N{RIGHTWARDS ARROW} V2 conversion, "
                f"got {type(sheet).__name__!r}."
            )

        # Resolve workflow before writing any output — fail fast if the
        # sheet has a non-empty Index2 column and we cannot tell whether
        # to RC it. See _needs_i5_rc().
        needs_rc = self._needs_i5_rc(
            instrument=sheet.instrument_type,
            records=sheet.records or [],
            index2_key="index2",
            direction="V1 → V2",
        )

        out = Path(output_path)
        lines: list[str] = []

        # [Header]
        lines.append("[Header]")
        lines.append("FileFormatVersion,2")
        run_name = sheet.experiment_name or ""
        if run_name:
            lines.append(f"RunName,{run_name}")
        description = getattr(sheet, "description", None) or ""
        if description:
            lines.append(f"RunDescription,{description}")
        # Preserve Instrument Type → InstrumentType so the workflow signal
        # survives a V1 → V2 → V1 round trip.
        if sheet.instrument_type:
            lines.append(f"InstrumentType,{sheet.instrument_type}")
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
        # Emit empty OverrideCycles — caller should fill in if using UMIs or custom cycle counts
        lines.append("OverrideCycles,")
        lines.append("")

        # [BCLConvert_Data]
        lines.append("[BCLConvert_Data]")
        if sheet.columns:
            # Always emit column header even when records == [] to keep the
            # section parseable by SampleSheetV2.parse_data()
            v2_columns = self._v1_data_columns_to_v2(sheet.columns)
            lines.append(",".join(v2_columns))
            for record in sheet.records or []:
                row = self._v1_record_to_v2(record, v2_columns, rc_index2=needs_rc)
                lines.append(",".join(row))
        lines.append("")

        out.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Wrote V2 sheet to {out}")
        return out.resolve()

    def to_v1(self, output_path: str | Path) -> Path:
        """Convert a V2 sheet to IEM V1 format and write to *output_path*.

        This is a **lossy** conversion. V2-only fields (``OverrideCycles``,
        ``Cloud_Data``, ``SoftwareVersion``, etc.) are dropped and a warning
        is logged for each dropped field. ``InstrumentPlatform`` /
        ``InstrumentType`` are preserved as the V1 ``Instrument Type``
        header so the workflow signal survives a round trip.

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
            raise ValueError("Source sheet is already V1. No conversion needed.")

        sheet = self._sheet
        if not isinstance(sheet, SampleSheetV2):
            raise TypeError(
                f"Expected SampleSheetV2 for V2 \N{RIGHTWARDS ARROW} V1 conversion, "
                f"got {type(sheet).__name__!r}."
            )

        # Resolve workflow up front. Prefer InstrumentPlatform; fall back
        # to InstrumentType (some V2 sheets only declare the latter).
        instrument = sheet.instrument_platform or (
            sheet.header.get("InstrumentType") if sheet.header else None
        )
        needs_rc = self._needs_i5_rc(
            instrument=instrument,
            records=sheet.records or [],
            index2_key="Index2",
            direction="V2 → V1",
        )

        out = Path(output_path)
        lines: list[str] = []
        dropped: list[str] = []

        # [Header]
        lines.append("[Header]")
        lines.append("IEMFileVersion,5")

        run_name = (
            sheet.experiment_name or (sheet.header.get("RunName") if sheet.header else None) or ""
        )
        if run_name:
            lines.append(f"Experiment Name,{run_name}")

        run_desc = sheet.header.get("RunDescription", "") if sheet.header else ""
        if run_desc:
            lines.append(f"Description,{run_desc}")

        # Preserve instrument so the workflow signal survives a round trip.
        # V2 may declare InstrumentType, InstrumentPlatform, or both —
        # prefer the more specific InstrumentType when present.
        v2_instrument = (sheet.header.get("InstrumentType") if sheet.header else None) or (
            sheet.header.get("InstrumentPlatform") if sheet.header else None
        )
        if v2_instrument:
            lines.append(f"Instrument Type,{v2_instrument}")

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
        if sheet.columns:
            v1_columns = self._v2_data_columns_to_v1(sheet.columns)

            # Track dropped V2-only data columns
            for col in _V2_ONLY_DATA_COLUMNS:
                if col in sheet.columns:
                    dropped.append(f"[BCLConvert_Data] column: {col}")

            # Always emit column header even when records == [] to keep the
            # section parseable by SampleSheetV1.parse_data()
            lines.append(",".join(v1_columns))
            for record in sheet.records or []:
                row = self._v2_record_to_v1(record, v1_columns, rc_index2=needs_rc)
                lines.append(",".join(row))
        lines.append("")

        # Warn about dropped fields
        # Check cloud_data first so the warning fires even when it is the only lossy part
        if sheet.cloud_data:
            dropped.append("[Cloud_Data] section (entire section — no V1 equivalent)")
        if dropped:
            logger.warning(
                f"V2 → V1 conversion dropped {len(dropped)} field(s) with no V1 equivalent:"
            )
            for field in dropped:
                logger.warning(f"  - {field}")

        out.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Wrote V1 sheet to {out}")
        return out.resolve()

    # ------------------------------------------------------------------
    # Column remapping helpers
    # ------------------------------------------------------------------

    def _v1_data_columns_to_v2(self, v1_columns: list[str]) -> list[str]:
        """Map V1 [Data] column names to V2 [BCLConvert_Data] equivalents."""
        mapping = {
            "Sample_ID": "Sample_ID",
            "Sample_Name": "Sample_Name",
            "Lane": "Lane",
            "index": "Index",
            "index2": "Index2",
            "Sample_Project": "Sample_Project",
            # Drop V1-only columns
            "I7_Index_ID": None,
            "I5_Index_ID": None,
            "Sample_Plate": None,
            "Sample_Well": None,
            "Description": None,
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
        v2_columns: list[str],
        *,
        rc_index2: bool = False,
    ) -> list[str]:
        """Convert a single V1 data record to a V2 row.

        When *rc_index2* is True, the ``index2`` value is reverse-
        complemented before being written under the V2 ``Index2`` column.
        """
        col_map = {
            "index": "Index",
            "index2": "Index2",
        }
        v2_record: dict[str, str] = {}
        for k, v in record.items():
            new_key = col_map.get(k, k)
            if new_key not in v2_columns:
                continue
            if rc_index2 and k == "index2" and v:
                v = reverse_complement(v)
            v2_record[new_key] = v

        return [v2_record.get(col, "") for col in v2_columns]

    def _v2_data_columns_to_v1(self, v2_columns: list[str]) -> list[str]:
        """Map V2 [BCLConvert_Data] column names to V1 [Data] equivalents."""
        mapping = {
            "Sample_ID": "Sample_ID",
            "Sample_Name": "Sample_Name",
            "Lane": "Lane",
            "Index": "index",
            "Index2": "index2",
            "Sample_Project": "Sample_Project",
        }
        result = []
        for col in v2_columns:
            if col in _V2_ONLY_DATA_COLUMNS:
                continue  # drop silently — already warned above
            mapped = mapping.get(col, col)
            result.append(mapped)
        return result

    def _v2_record_to_v1(
        self,
        record: dict[str, str],
        v1_columns: list[str],
        *,
        rc_index2: bool = False,
    ) -> list[str]:
        """Convert a single V2 data record to a V1 row.

        When *rc_index2* is True, the ``Index2`` value is reverse-
        complemented before being written under the V1 ``index2`` column.
        """
        col_map = {
            "Index": "index",
            "Index2": "index2",
        }
        v1_record: dict[str, str] = {}
        for k, v in record.items():
            if k in _V2_ONLY_DATA_COLUMNS:
                continue
            new_key = col_map.get(k, k)
            if new_key not in v1_columns:
                continue
            if rc_index2 and k == "Index2" and v:
                v = reverse_complement(v)
            v1_record[new_key] = v

        return [v1_record.get(col, "") for col in v1_columns]

    # ------------------------------------------------------------------
    # Workflow / i5 orientation
    # ------------------------------------------------------------------

    def _needs_i5_rc(
        self,
        *,
        instrument: str | None,
        records: list[dict[str, str]],
        index2_key: str,
        direction: str,
    ) -> bool:
        """Decide whether ``Index2`` should be reverse-complemented.

        Resolution order:
          1. Explicit ``workflow=`` constructor override wins.
          2. Otherwise auto-detect from *instrument*.
          3. If detection fails and any record carries a non-empty
             ``index2_key``, raise ``ValueError`` — silently passing the
             i5 through would produce a wrong sheet for workflow-B
             instruments.
          4. If no Index2 values are present, return ``False`` (no-op).
        """
        has_index2_values = any(rec.get(index2_key) for rec in records)

        def _log(wf: Workflow, source: str) -> None:
            action = "be reverse-complemented" if wf == Workflow.B else "be passed through"
            logger.info(f"{direction}: workflow={wf.value} ({source}); Index2 will {action}.")

        if self.workflow_override is not None:
            _log(self.workflow_override, "explicit override")
            return self.workflow_override == Workflow.B

        detected = detect_workflow(instrument)
        if detected is not None:
            _log(detected, f"auto-detected from {instrument!r}")
            return detected == Workflow.B

        # Workflow unknown.
        if has_index2_values:
            instr_repr = f"{instrument!r}" if instrument else "<missing>"
            raise ValueError(
                f"{direction}: cannot determine i5 orientation workflow for "
                f"instrument {instr_repr}. The sheet has dual indexes, and "
                f"workflow-A vs workflow-B instruments record Index2 in "
                f"opposite orientations. Pass workflow='a' or workflow='b' "
                f"explicitly (CLI: --workflow {{a,b}}). See "
                f"samplesheet_parser.instruments for the full instrument table."
            )

        # No Index2 to convert — silent pass-through is safe.
        logger.debug(f"{direction}: no Index2 values, skipping workflow detection.")
        return False

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"SampleSheetConverter("
            f"path={self.path!r}, "
            f"source_version={self.source_version!r})"
        )
