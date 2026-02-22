"""
Format-detection factory for Illumina sample sheets.

The factory inspects the ``[Header]`` section and section names of a
``SampleSheet.csv`` to select the correct parser — :class:`SampleSheetV1`
for classic IEM / bcl2fastq files and :class:`SampleSheetV2` for
BCLConvert files — without requiring the caller to know the format
upfront.

Detection logic
---------------
1. Read the ``[Header]`` section and look for a version discriminator:
   - ``FileFormatVersion``  → V2 (BCLConvert)
   - ``IEMFileVersion``     → V1 (IEM / bcl2fastq)

2. If no header discriminator is found, scan the full file for
   BCLConvert-specific section names (``[BCLConvert_Settings]``,
   ``[BCLConvert_Data]``) and fall back to V2 if found.

3. If nothing matches, default to V1 (broadest compatibility).

Examples
--------
>>> from samplesheet_parser import SampleSheetFactory
>>>
>>> # Auto-detect format
>>> sheet = SampleSheetFactory().create_parser("SampleSheet.csv")
>>> sheet.parse()
>>> print(sheet.samples())
>>>
>>> # Check what was detected
>>> factory = SampleSheetFactory()
>>> sheet = factory.create_parser("SampleSheet.csv")
>>> print(factory.version)   # SampleSheetVersion.V2
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2


class SampleSheetFactory:
    """
    Auto-detecting factory for Illumina sample sheet parsers.

    After calling :meth:`create_parser`, the detected version is
    available as ``factory.version`` and the parser as
    ``factory.parser``.

    Parameters
    ----------
    None — the factory is stateless until :meth:`create_parser` is called.

    Examples
    --------
    >>> factory = SampleSheetFactory()
    >>> sheet = factory.create_parser("SampleSheet.csv", parse=True)
    >>> print(factory.version)  # SampleSheetVersion.V1 or .V2
    >>> print(sheet.samples())
    """

    def __init__(self) -> None:
        self.version: SampleSheetVersion | None = None
        self.parser:  SampleSheetV1 | SampleSheetV2 | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_parser(
        self,
        path: str | Path,
        *,
        clean: bool = True,
        experiment_id: str | None = None,
        parse: bool | None = None,
    ) -> SampleSheetV1 | SampleSheetV2:
        """Detect the sample sheet format and return the appropriate parser.

        The returned parser shares the same interface:
        - :meth:`parse` — load and parse all sections
        - :meth:`samples` — return a list of sample records
        - :meth:`index_type` — return ``"dual"``, ``"single"``, or ``"none"``

        Parameters
        ----------
        path:
            Path to the ``SampleSheet.csv`` file.
        clean:
            Passed to the underlying parser's ``clean`` parameter.
        experiment_id:
            Override the experiment/run name in the header.
        parse:
            If ``True``, call ``parse()`` immediately on the returned
            parser. If ``False`` (default), defer until the caller
            calls ``parse()`` explicitly.

        Returns
        -------
        SampleSheetV1 | SampleSheetV2
            The version-appropriate parser instance.

        Raises
        ------
        FileNotFoundError
            If the given path does not exist.
        ValueError
            If the file cannot be read as a valid sample sheet.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Sample sheet not found: {path}")

        logger.info(f"Detecting sample sheet format for: {path}")
        detected = self._detect_version(path)

        self.version = detected
        kwargs: dict = dict(clean=clean, experiment_id=experiment_id, parse=parse)

        if detected == SampleSheetVersion.V2:
            logger.info("Detected BCLConvert V2 format — using SampleSheetV2")
            self.parser = SampleSheetV2(path, **kwargs)
        else:
            logger.info("Detected IEM V1 format — using SampleSheetV1")
            self.parser = SampleSheetV1(path, **kwargs)

        return self.parser

    def get_umi_length(self) -> int:
        """Return the UMI length for the currently selected parser.

        Delegates to ``parser.get_umi_length()`` for V2, or reads
        ``IndexUMILength`` from the V1 header if present.

        Returns
        -------
        int
            UMI length in bases. ``0`` if no UMI is present.

        Raises
        ------
        RuntimeError
            If called before :meth:`create_parser`.
        """
        if self.parser is None:
            raise RuntimeError("Call create_parser() before get_umi_length().")

        if self.version == SampleSheetVersion.V2:
            return self.parser.get_umi_length()  # type: ignore[union-attr]

        # V1: UMI length is occasionally stored as IndexUMILength in [Header]
        if isinstance(self.parser, SampleSheetV1):
            if self.parser.header:
                try:
                    return int(self.parser.header.get("IndexUMILength", 0))
                except (ValueError, TypeError):
                    pass
        return 0

    # ------------------------------------------------------------------
    # Format detection
    # ------------------------------------------------------------------

    def _detect_version(self, path: Path) -> SampleSheetVersion:
        """Inspect the file and return the appropriate SampleSheetVersion.

        Reads only as much of the file as needed:
        1. Scan [Header] for FileFormatVersion / IEMFileVersion.
        2. If undetermined, scan the full file for BCLConvert section names.
        3. Default to V1.

        Parameters
        ----------
        path:
            Path to the sample sheet.

        Returns
        -------
        SampleSheetVersion
            Detected version enum value.
        """
        # --- Phase 1: check [Header] section only ----------------------
        # Read lines until we leave the [Header] section (hit a new section
        # or EOF). Avoids loading the entire file for the common case.
        header_lines: list[str] = []
        full_content: list[str] = []

        with open(path, encoding="utf-8-sig") as fh:
            in_header = False
            for line in fh:
                full_content.append(line)
                stripped = line.strip()

                if stripped.lower().startswith("[header]"):
                    in_header = True
                    continue

                if stripped.startswith("[") and in_header:
                    # Leaving the header section
                    break

                if in_header and stripped:
                    header_lines.append(stripped)

        for line in header_lines:
            key = line.split(",")[0].strip()
            if key == "FileFormatVersion":
                logger.debug("Discriminator: FileFormatVersion → V2")
                return SampleSheetVersion.V2
            if key == "IEMFileVersion":
                logger.debug("Discriminator: IEMFileVersion → V1")
                return SampleSheetVersion.V1

        # --- Phase 2: scan for BCLConvert section names ----------------
        # Use the already-read content — no second file open needed.
        content = "".join(full_content)
        if "[BCLConvert_Settings]" in content or "[BCLConvert_Data]" in content:
            logger.debug("Discriminator: BCLConvert section names → V2")
            return SampleSheetVersion.V2

        # --- Phase 3: default to V1 ------------------------------------
        logger.debug("No discriminator found — defaulting to V1")
        return SampleSheetVersion.V1

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"SampleSheetFactory("
            f"version={self.version!r}, "
            f"parser={type(self.parser).__name__ if self.parser else None})"
        )
