"""
Diff engine for Illumina sample sheets.

Compares two sample sheets (any combination of V1 / V2) and reports
structured differences across four dimensions:

- **Header** — key/value changes in [Header] / [BCLConvert_Settings]
- **Reads** — changes in read lengths or cycle counts
- **Samples added / removed** — keyed on ``Sample_ID`` + ``Lane``
- **Sample fields changed** — per-sample field-level diffs (index
  changes, project reassignment, etc.)

The comparison is format-aware: V1 ``index`` is compared against V2
``Index`` as the same logical field, so a round-tripped sheet that
only changes field name casing does not generate spurious diffs.

Examples
--------
>>> from samplesheet_parser import SampleSheetDiff
>>>
>>> diff = SampleSheetDiff("old/SampleSheet.csv", "new/SampleSheet.csv")
>>> result = diff.compare()
>>>
>>> print(result.summary())
>>> if result.has_changes:
...     for change in result.sample_changes:
...         print(change)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.factory import SampleSheetFactory

# ---------------------------------------------------------------------------
# Field normalisation map
# V1 and V2 use different names for the same logical field.
# We normalise to the V2 canonical name before comparing.
# ---------------------------------------------------------------------------

_FIELD_ALIASES: dict[str, str] = {
    # index
    "index":          "Index",
    "i7_index_id":    "I7_Index_ID",
    # index2
    "index2":         "Index2",
    "i5_index_id":    "I5_Index_ID",
    # project
    "sample_project": "Sample_Project",
    # name
    "sample_name":    "Sample_Name",
}

# Fields to skip when comparing samples — these are metadata that differ
# between formats by design and do not represent meaningful changes.
#
# V1-only fields (no V2 equivalent):
#   I7_Index_ID / I5_Index_ID — index name columns; V2 stores index values only
#   Sample_Name  — V1 carries a display name; V2 omits it
#   Sample_Plate / Sample_Well / Description — IEM metadata not present in V2
_SKIP_FIELDS: frozenset[str] = frozenset({
    "experiment_name",
    "run_name",
    "iem_version",
    # V1 IEM metadata columns absent from V2
    "I7_Index_ID",
    "I5_Index_ID",
    "Sample_Name",
    "Sample_Plate",
    "Sample_Well",
    "Description",
})


def _normalise_key(k: str) -> str:
    """Return the canonical field name for ``k``."""
    return _FIELD_ALIASES.get(k, k)


def _normalise_record(record: dict[str, str]) -> dict[str, str]:
    """Return a copy of ``record`` with normalised keys, skipping metadata."""
    out: dict[str, str] = {}
    for k, v in record.items():
        if k in _SKIP_FIELDS:
            continue
        out[_normalise_key(k)] = v
    return out


def _sample_key(record: dict[str, str]) -> tuple[str, str]:
    """Return a ``(lane, sample_id)`` tuple for keying samples."""
    lane = record.get("Lane") or record.get("lane") or "1"
    sid  = record.get("Sample_ID") or record.get("sample_id") or ""
    return (lane.strip(), sid.strip())


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class HeaderChange:
    """A single key/value change in the header or settings section."""
    field:     str
    old_value: str | None
    new_value: str | None
    section:   str = "header"  # "header" | "reads" | "settings"

    def __str__(self) -> str:
        old = repr(self.old_value) if self.old_value is not None else "—"
        new = repr(self.new_value) if self.new_value is not None else "—"
        return f"[{self.section}] {self.field}: {old} → {new}"


@dataclass
class SampleChange:
    """A set of field-level changes for a single sample."""
    lane:      str
    sample_id: str
    changes:   dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    # changes maps field_name → (old_value, new_value)

    def __str__(self) -> str:
        lines = [f"Sample {self.sample_id!r} (lane {self.lane}):"]
        for f, (old, new) in self.changes.items():
            old_s = repr(old) if old is not None else "—"
            new_s = repr(new) if new is not None else "—"
            lines.append(f"  {f}: {old_s} → {new_s}")
        return "\n".join(lines)


@dataclass
class DiffResult:
    """
    Structured result of a :class:`SampleSheetDiff` comparison.

    Attributes
    ----------
    source_version:
        Format of the *left* (old) sheet.
    target_version:
        Format of the *right* (new) sheet.
    header_changes:
        Key/value changes in header, reads, and settings sections.
    samples_added:
        Sample IDs present in the new sheet but not the old.
    samples_removed:
        Sample IDs present in the old sheet but not the new.
    sample_changes:
        Per-sample field-level diffs for samples present in both sheets.
    """
    source_version:  SampleSheetVersion
    target_version:  SampleSheetVersion
    header_changes:  list[HeaderChange]  = field(default_factory=list)
    samples_added:   list[dict[str, str]] = field(default_factory=list)
    samples_removed: list[dict[str, str]] = field(default_factory=list)
    sample_changes:  list[SampleChange]  = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """``True`` if any difference was detected."""
        return bool(
            self.header_changes
            or self.samples_added
            or self.samples_removed
            or self.sample_changes
        )

    def summary(self) -> str:
        """Return a human-readable one-paragraph summary."""
        if not self.has_changes:
            return (
                f"No differences detected "
                f"({self.source_version.value} → {self.target_version.value})."
            )

        parts: list[str] = [
            f"Diff ({self.source_version.value} → {self.target_version.value}):"
        ]
        if self.header_changes:
            parts.append(f"  {len(self.header_changes)} header/settings change(s)")
        if self.samples_added:
            ids = ", ".join(r.get("Sample_ID", "?") for r in self.samples_added[:5])
            tail = f" … +{len(self.samples_added) - 5} more" if len(self.samples_added) > 5 else ""
            parts.append(f"  {len(self.samples_added)} sample(s) added: {ids}{tail}")
        if self.samples_removed:
            ids = ", ".join(r.get("Sample_ID", "?") for r in self.samples_removed[:5])
            tail = (
                f" … +{len(self.samples_removed) - 5} more"
                if len(self.samples_removed) > 5
                else ""
            )
            parts.append(f"  {len(self.samples_removed)} sample(s) removed: {ids}{tail}")
        if self.sample_changes:
            parts.append(f"  {len(self.sample_changes)} sample(s) with field changes")
        return "\n".join(parts)

    def __str__(self) -> str:
        lines = [self.summary()]
        if self.header_changes:
            lines.append("\n── Header / Settings ──")
            lines.extend(str(c) for c in self.header_changes)
        if self.samples_added:
            lines.append("\n── Added samples ──")
            for r in self.samples_added:
                lines.append(f"  + {r.get('Sample_ID', '?')} (lane {r.get('Lane', '1')})")
        if self.samples_removed:
            lines.append("\n── Removed samples ──")
            for r in self.samples_removed:
                lines.append(f"  - {r.get('Sample_ID', '?')} (lane {r.get('Lane', '1')})")
        if self.sample_changes:
            lines.append("\n── Changed samples ──")
            lines.extend(str(c) for c in self.sample_changes)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------

class SampleSheetDiff:
    """
    Compare two Illumina sample sheets and return a structured diff.

    Accepts any combination of V1 and V2 sheets. Field names are
    normalised before comparison so that V1 ``index`` and V2 ``Index``
    are treated as the same logical field.

    Parameters
    ----------
    old_path:
        Path to the *old* (left) sample sheet.
    new_path:
        Path to the *new* (right) sample sheet.

    Examples
    --------
    >>> diff   = SampleSheetDiff("SampleSheet_v1.csv", "SampleSheet_v2.csv")
    >>> result = diff.compare()
    >>> print(result.summary())

    >>> # Check for index changes only
    >>> index_changes = [
    ...     c for c in result.sample_changes
    ...     if "Index" in c.changes
    ... ]
    """

    def __init__(self, old_path: str | Path, new_path: str | Path) -> None:
        self.old_path = Path(old_path)
        self.new_path = Path(new_path)

        factory_old = SampleSheetFactory()
        factory_new = SampleSheetFactory()

        self._old = factory_old.create_parser(self.old_path, parse=True, clean=False)
        self._new = factory_new.create_parser(self.new_path, parse=True, clean=False)

        self.old_version: SampleSheetVersion = factory_old.version  # type: ignore[assignment]
        self.new_version: SampleSheetVersion = factory_new.version  # type: ignore[assignment]

        logger.info(
            f"SampleSheetDiff: {self.old_path.name} ({self.old_version.value}) "
            f"↔ {self.new_path.name} ({self.new_version.value})"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compare(self) -> DiffResult:
        """
        Run the full comparison and return a :class:`DiffResult`.

        Returns
        -------
        DiffResult
            Structured diff across header, reads, settings, and samples.
        """
        result = DiffResult(
            source_version=self.old_version,
            target_version=self.new_version,
        )

        self._diff_header(result)
        self._diff_reads(result)
        self._diff_settings(result)
        self._diff_samples(result)

        if result.has_changes:
            logger.info(f"SampleSheetDiff: {result.summary()}")
        else:
            logger.info("SampleSheetDiff: no differences detected")

        return result

    # ------------------------------------------------------------------
    # Internal diff helpers
    # ------------------------------------------------------------------

    def _diff_header(self, result: DiffResult) -> None:
        """Diff the [Header] key/value pairs."""
        old_h = self._old.header or {}
        new_h = self._new.header or {}

        # Normalise keys for cross-format comparison
        old_norm = {_normalise_key(k): v for k, v in old_h.items()}
        new_norm = {_normalise_key(k): v for k, v in new_h.items()}

        all_keys = set(old_norm) | set(new_norm)
        for key in sorted(all_keys):
            old_val = old_norm.get(key)
            new_val = new_norm.get(key)
            if old_val != new_val:
                result.header_changes.append(
                    HeaderChange(
                        field=key,
                        old_value=old_val,
                        new_value=new_val,
                        section="header",
                    )
                )

    def _diff_reads(self, result: DiffResult) -> None:
        """Diff the [Reads] section."""
        old_r = self._get_reads(self._old)
        new_r = self._get_reads(self._new)

        all_keys = set(old_r) | set(new_r)
        for key in sorted(all_keys):
            old_val = str(old_r.get(key, "")) or None
            new_val = str(new_r.get(key, "")) or None
            if old_val != new_val:
                result.header_changes.append(
                    HeaderChange(
                        field=key,
                        old_value=old_val,
                        new_value=new_val,
                        section="reads",
                    )
                )

    def _diff_settings(self, result: DiffResult) -> None:
        """Diff the [Settings] / [BCLConvert_Settings] section."""
        old_s = self._old.settings or {}
        new_s = self._new.settings or {}

        all_keys = set(old_s) | set(new_s)
        for key in sorted(all_keys):
            old_val = old_s.get(key)
            new_val = new_s.get(key)
            if old_val != new_val:
                result.header_changes.append(
                    HeaderChange(
                        field=key,
                        old_value=old_val,
                        new_value=new_val,
                        section="settings",
                    )
                )

    def _diff_samples(self, result: DiffResult) -> None:
        """Diff the [Data] / [BCLConvert_Data] records."""
        old_records = self._old.records or []
        new_records = self._new.records or []

        # Build lookup dicts keyed on (lane, sample_id)
        old_map: dict[tuple[str, str], dict[str, str]] = {
            _sample_key(r): _normalise_record(r) for r in old_records
        }
        new_map: dict[tuple[str, str], dict[str, str]] = {
            _sample_key(r): _normalise_record(r) for r in new_records
        }

        old_keys = set(old_map)
        new_keys = set(new_map)

        # Added
        for key in sorted(new_keys - old_keys):
            result.samples_added.append(new_map[key])

        # Removed
        for key in sorted(old_keys - new_keys):
            result.samples_removed.append(old_map[key])

        # Changed
        for key in sorted(old_keys & new_keys):
            old_rec = old_map[key]
            new_rec = new_map[key]
            all_fields = set(old_rec) | set(new_rec)
            changes: dict[str, tuple[str | None, str | None]] = {}
            for f in sorted(all_fields):
                old_val = old_rec.get(f)
                new_val = new_rec.get(f)
                if old_val != new_val:
                    changes[f] = (old_val, new_val)
            if changes:
                lane, sid = key
                result.sample_changes.append(
                    SampleChange(lane=lane, sample_id=sid, changes=changes)
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_reads(self, sheet: Any) -> dict[str, int | str]:
        """
        Return a normalised reads dict regardless of V1/V2 format.

        V1 stores reads as a list [151, 151].
        V2 stores reads as a dict {"Read1Cycles": 151, "Read2Cycles": 151}.
        """
        reads = getattr(sheet, "reads", None) or getattr(sheet, "read_lengths", None)
        if reads is None:
            return {}
        if isinstance(reads, dict):
            return reads
        # V1: list of ints → synthesise key names
        result: dict[str, int | str] = {}
        for i, val in enumerate(reads, start=1):
            result[f"Read{i}Cycles"] = val
        return result
