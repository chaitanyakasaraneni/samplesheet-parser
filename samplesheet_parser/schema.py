"""Bundled Illumina v2 JSON Schema and a resolvable schema registry.

This module ships a full JSON Schema (draft 2020-12) for the Illumina
BCLConvert v2 sample sheet and a :mod:`referencing` registry that resolves it
by URN, so a user schema can ``$ref`` the bundled document offline (no network,
no extra files).

Two URNs resolve to the same bundled schema:

* ``urn:samplesheet-parser:illuminav2/v1`` - this project's own URN.
* ``urn:samshee:illuminav2/v1`` - a compatibility alias so a schema written for
  `samshee <https://github.com/lit-regensburg/samshee>`_ that references that
  URN keeps resolving. The bundled schema is **equivalent** to samshee's intent
  (required fields, admissible values, index pattern), not byte-identical to it.

The schema is validated against the *sectioned* view of a sheet produced by
:func:`sheet_to_sections` (section names as top-level keys, Settings sections as
objects, Data sections as arrays of row objects), which mirrors how samshee
represents a sheet.

``referencing`` ships with ``jsonschema`` (>= 4.18), so no dependency beyond the
optional ``samplesheet-parser[schema]`` extra is introduced. When ``jsonschema``
is absent, :func:`build_registry` returns ``None`` and callers skip schema
checks.
"""

from __future__ import annotations

from typing import Any

#: This project's URN for the bundled Illumina v2 schema.
ILLUMINA_V2_URN = "urn:samplesheet-parser:illuminav2/v1"

#: Compatibility alias so samshee-authored schemas that ``$ref`` this URN
#: continue to resolve against the bundled equivalent schema.
SAMSHEE_V2_URN = "urn:samshee:illuminav2/v1"

#: Full JSON Schema (draft 2020-12) for a BCLConvert v2 sample sheet, matching
#: the value types produced by :func:`sheet_to_sections`: ``[Header]`` /
#: ``[BCLConvert_Settings]`` values are strings, ``[Reads]`` values are
#: integers, and ``[BCLConvert_Data]`` rows are objects of strings. Unknown
#: fields and columns are allowed (``additionalProperties: true``) so newer or
#: optional columns - including a per-sample ``OverrideCycles`` - still validate.
ILLUMINA_V2_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": ILLUMINA_V2_URN,
    "title": "Illumina Sample Sheet v2 (BCLConvert)",
    "type": "object",
    "required": ["Header", "Reads", "BCLConvert_Data"],
    "properties": {
        "Header": {
            "type": "object",
            "required": ["FileFormatVersion"],
            "properties": {
                "FileFormatVersion": {"type": "string", "enum": ["2"]},
                "RunName": {"type": "string"},
                "RunDescription": {"type": "string"},
                "InstrumentPlatform": {"type": "string"},
                "InstrumentType": {"type": "string"},
                "ExperimentName": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "Reads": {
            "type": "object",
            "required": ["Read1Cycles"],
            "properties": {
                "Read1Cycles": {"type": "integer", "minimum": 1},
                "Read2Cycles": {"type": "integer", "minimum": 1},
                "Index1Cycles": {"type": "integer", "minimum": 0},
                "Index2Cycles": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": True,
        },
        "Sequencing": {"type": "object", "additionalProperties": True},
        "BCLConvert_Settings": {
            "type": "object",
            "properties": {
                "SoftwareVersion": {"type": "string"},
                "AdapterRead1": {"type": "string", "pattern": "^[ACGTNacgtn]*$"},
                "AdapterRead2": {"type": "string", "pattern": "^[ACGTNacgtn]*$"},
                "BarcodeMismatchesIndex1": {"type": "string"},
                "BarcodeMismatchesIndex2": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "BCLConvert_Data": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["Sample_ID", "Index"],
                "properties": {
                    "Sample_ID": {"type": "string", "minLength": 1},
                    "Sample_Name": {"type": "string"},
                    "Sample_Project": {"type": "string"},
                    "Lane": {"type": "string"},
                    "Index": {"type": "string", "pattern": "^[ACGTNacgtn]+$"},
                    "Index2": {"type": "string", "pattern": "^[ACGTNacgtn]*$"},
                },
                "additionalProperties": True,
            },
        },
    },
    "additionalProperties": True,
}


def sheet_to_sections(sheet: Any) -> dict[str, Any]:
    """Return a sectioned view of a parsed sheet, as the v2 schema expects.

    Section names are top-level keys. ``[Header]`` / ``[*_Settings]`` sections
    are objects; ``[*_Data]`` sections are arrays of row objects with their
    original column names (e.g. ``Sample_ID``, ``Index``), so a schema written
    in terms of the sheet's real sections and columns applies directly.

    Best-effort across parser types: only the sections a given sheet exposes are
    included. For non-v2 sheets (no ``records`` attribute) the data rows are
    emitted under a generic ``Data`` key from :meth:`samples`.
    """
    out: dict[str, Any] = {}

    header = getattr(sheet, "header", None)
    if header:
        out["Header"] = dict(header)

    reads = getattr(sheet, "reads", None)
    if reads:
        out["Reads"] = dict(reads)

    settings = getattr(sheet, "settings", None)
    if settings:
        out["BCLConvert_Settings"] = dict(settings)

    records = getattr(sheet, "records", None)
    if records:
        out["BCLConvert_Data"] = [dict(r) for r in records]
    else:
        samples = sheet.samples()
        if samples:
            out["Data"] = [dict(s) for s in samples]

    cloud = getattr(sheet, "cloud_data", None)
    if cloud:
        out["Cloud_Data"] = [dict(r) for r in cloud]

    return out


def build_registry() -> Any | None:
    """Build a :mod:`referencing` registry resolving the bundled v2 schema.

    The bundled :data:`ILLUMINA_V2_SCHEMA` is registered under both
    :data:`ILLUMINA_V2_URN` and :data:`SAMSHEE_V2_URN`, so a ``$ref`` to either
    resolves offline. Returns ``None`` when ``referencing`` / ``jsonschema`` is
    not installed, so callers can degrade gracefully.
    """
    try:
        from referencing import Registry, Resource
    except ImportError:
        return None

    resource = Resource.from_contents(ILLUMINA_V2_SCHEMA)
    return Registry().with_resources([(ILLUMINA_V2_URN, resource), (SAMSHEE_V2_URN, resource)])
