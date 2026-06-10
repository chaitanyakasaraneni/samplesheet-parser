"""
Format-detection factory for Illumina sample sheets.

The factory inspects the ``[Header]`` section and section names of a
``SampleSheet.csv`` to select the correct parser - :class:`SampleSheetV1`
for classic IEM / bcl2fastq files and :class:`SampleSheetV2` for
BCLConvert files - without requiring the caller to know the format
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
>>>
>>> # Register a custom parser for a hypothetical V3 format
>>> def _is_v3(path):
...     with open(path) as fh:
...         return "FileFormatVersion,3" in fh.read(512)
>>> SampleSheetFactory.register(_is_v3, MyV3Parser, SampleSheetVersion.V2)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2
from samplesheet_parser.protocol import SampleSheetParser

logger = logging.getLogger(__name__)


class SampleSheetFactory:
    """
    Auto-detecting factory for Illumina sample sheet parsers.

    After calling :meth:`create_parser`, the detected version is
    available as ``factory.version`` and the parser as
    ``factory.parser``.

    Parameters
    ----------
    None - the factory is stateless until :meth:`create_parser` is called.

    Examples
    --------
    >>> factory = SampleSheetFactory()
    >>> sheet = factory.create_parser("SampleSheet.csv", parse=True)
    >>> print(factory.version)  # SampleSheetVersion.V1 or .V2
    >>> print(sheet.samples())
    """

    # Class-level registry: (detector_fn, parser_class, version) tuples, LIFO.
    # This is process-global shared state: registering a parser affects every
    # SampleSheetFactory instance in the process, and registration is not
    # synchronised, so register custom parsers at import or startup rather than
    # concurrently from worker threads. Call clear_registry() to reset it.
    _registry: list[tuple[Callable[[Path], bool], type[Any], SampleSheetVersion]] = []

    def __init__(self) -> None:
        self.version: SampleSheetVersion | None = None
        self.parser: SampleSheetParser | None = None

    # ------------------------------------------------------------------
    # Class-level registration
    # ------------------------------------------------------------------

    @classmethod
    def register(
        cls,
        detector: Callable[[Path], bool],
        parser_class: type[Any],
        version: SampleSheetVersion,
    ) -> None:
        """Register a custom format detector and parser.

        Registered detectors are tried before the built-in V1/V2 detection,
        in LIFO order - the most recently registered detector wins when
        multiple detectors match.

        Parameters
        ----------
        detector:
            Callable that receives the file :class:`~pathlib.Path` and returns
            ``True`` if *parser_class* should handle this file.
        parser_class:
            Parser class to instantiate when *detector* returns ``True``.
        version:
            :class:`~samplesheet_parser.SampleSheetVersion` to record for
            this format.
        """
        cls._registry.insert(0, (detector, parser_class, version))
        logger.debug(
            f"Registered custom parser {parser_class.__name__!r} " f"for version {version.value!r}."
        )

    @classmethod
    def clear_registry(cls) -> None:
        """Remove all custom registrations (useful in tests)."""
        cls._registry.clear()

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
    ) -> SampleSheetParser:
        """Detect the sample sheet format and return the appropriate parser.

        The returned parser shares the same interface:
        - :meth:`parse` - load and parse all sections
        - :meth:`samples` - return a list of sample records
        - :meth:`index_type` - return ``"dual"``, ``"single"``, or ``"none"``

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
        SampleSheetParser
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
        kwargs: dict[str, Any] = dict(clean=clean, experiment_id=experiment_id, parse=parse)

        # Try registered custom detectors first (LIFO order).
        for detector, parser_class, ver in self._registry:
            try:
                if detector(path):
                    logger.info(
                        f"Custom detector matched - using {parser_class.__name__!r} "
                        f"(version={ver.value!r})"
                    )
                    self.version = ver
                    parser: SampleSheetParser = parser_class(path, **kwargs)
                    self.parser = parser
                    return parser
            except Exception as exc:
                logger.debug(f"Custom detector {detector!r} raised {exc!r} for {path} - skipping.")

        # Built-in V1/V2 detection.
        detected = self._detect_version(path)
        self.version = detected

        if detected == SampleSheetVersion.V2:
            logger.info("Detected BCLConvert V2 format - using SampleSheetV2")
            parser = SampleSheetV2(path, **kwargs)
        else:
            logger.info("Detected IEM V1 format - using SampleSheetV1")
            parser = SampleSheetV1(path, **kwargs)

        self.parser = parser
        return parser

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

        if self.version == SampleSheetVersion.V2 and isinstance(self.parser, SampleSheetV2):
            return self.parser.get_umi_length()

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

        Detection runs in three phases:
        1. Scan [Header] for FileFormatVersion / IEMFileVersion.
        2. If undetermined, scan the whole file for BCLConvert section names.
        3. Default to V1.

        The full file is read once up front. Sample sheets are small (a few
        KB), so this is cheap, and it guarantees Phase 2 sees BCLConvert
        sections that appear after intervening sections such as [Reads].

        Parameters
        ----------
        path:
            Path to the sample sheet.

        Returns
        -------
        SampleSheetVersion
            Detected version enum value.
        """
        # --- Phase 1: collect [Header] lines and the full file content ---
        # header_lines collects only lines inside the [Header] section.
        # full_content accumulates every line so Phase 2 can scan the whole
        # file, not just the part read before the header ends.
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
                    # Left the header section; keep reading for Phase 2.
                    in_header = False
                    continue

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
        # Use the already-read content - no second file open needed. Compare
        # case-insensitively because the V2 parser normalises section names
        # that way, so e.g. "[bclconvert_data]" must also detect as V2.
        content_lower = "".join(full_content).lower()
        if "[bclconvert_settings]" in content_lower or "[bclconvert_data]" in content_lower:
            logger.debug("Discriminator: BCLConvert section names → V2")
            return SampleSheetVersion.V2

        # --- Phase 3: default to V1 ------------------------------------
        logger.debug("No discriminator found - defaulting to V1")
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
