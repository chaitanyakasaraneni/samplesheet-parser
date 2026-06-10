"""
Structural protocol for Illumina sample sheet parsers.

Any class that implements the methods and attributes below is a valid
``SampleSheetParser`` - no inheritance required.  The protocol lets third
parties add new format parsers (e.g. a V3 BCLConvert format) and register
them with :class:`~samplesheet_parser.factory.SampleSheetFactory` without
modifying library internals.

Examples
--------
>>> from samplesheet_parser.protocol import SampleSheetParser
>>> from samplesheet_parser import SampleSheetV1, SampleSheetV2
>>> assert isinstance(SampleSheetV1("sheet.csv"), SampleSheetParser)
>>> assert isinstance(SampleSheetV2("sheet.csv"), SampleSheetParser)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SampleSheetParser(Protocol):
    """Structural protocol satisfied by all sample sheet parser classes.

    Third-party parsers that implement these methods and attributes can be
    registered with :meth:`~samplesheet_parser.factory.SampleSheetFactory.register`
    and used transparently throughout the library.

    Attributes
    ----------
    path:
        Absolute path to the sample sheet file as a string.
    header:
        Parsed key/value pairs from the ``[Header]`` section, or ``None``
        before :meth:`parse` is called.
    adapters:
        Adapter sequences parsed from the settings section.  Empty list if
        no adapters are configured.
    sections:
        Lowercased names of the sections actually present in the file,
        in the order they were encountered.
    columns:
        Column names from the data section header row, or ``None`` before
        :meth:`parse` is called.
    """

    path: str
    header: dict[str, str] | None
    adapters: list[str]
    sections: list[str]
    columns: list[str] | None

    def parse(
        self,
        do_clean: bool = True,
        required_sections: list[str] | None = None,
    ) -> None:
        """Read and parse all sections of the sample sheet.

        Parameters
        ----------
        do_clean:
            Apply whitespace and encoding cleaning before parsing.
        required_sections:
            Section names that must be present; raises ``ValueError`` if any
            are missing.
        """
        ...

    def samples(self) -> list[dict[str, Any]]:
        """Return one record per sample row.

        Returns
        -------
        list[dict]
            Each dict contains at minimum: ``sample_id``, ``index``,
            ``index2``, ``lane``, ``sample_project``.
        """
        ...

    def index_type(self) -> str:
        """Return ``"dual"``, ``"single"``, or ``"none"``."""
        ...

    def parse_custom_section(
        self,
        section_name: str,
        *,
        required: bool = False,
    ) -> dict[str, str]:
        """Parse a non-standard section as a key/value dict.

        Parameters
        ----------
        section_name:
            Case-insensitive section name.
        required:
            Raise ``ValueError`` if the section is absent.
        """
        ...
