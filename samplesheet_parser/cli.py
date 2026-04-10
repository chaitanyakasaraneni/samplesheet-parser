"""
Command-line interface for samplesheet-parser.

Entry point: ``samplesheet`` (configured in ``pyproject.toml``).

Commands
--------
info        Show a quick summary of a sample sheet.
validate    Validate a sheet — exit 0 if clean, exit 1 if errors.
convert     Convert between V1 and V2 formats.
diff        Diff two sheets — exit 1 if changes detected.
merge       Merge multiple project sheets into one combined sheet.
split       Split a combined sheet into per-project or per-lane files.
filter      Extract a subset of samples by project, lane, or sample ID.

Installation
------------
Install the CLI extra::

    pip install "samplesheet-parser[cli]"

Usage
-----
::

    samplesheet info SampleSheet.csv
    samplesheet info SampleSheet.csv --format json

    samplesheet validate SampleSheet.csv
    samplesheet validate SampleSheet.csv --format json
    samplesheet validate SampleSheet.csv --min-hamming 4

    samplesheet convert SampleSheet_v1.csv --to v2 --output SampleSheet_v2.csv
    samplesheet convert SampleSheet_v2.csv --to v1 --output SampleSheet_v1.csv
    samplesheet convert SampleSheet_v1.csv --to v2 --output out.csv --format json

    samplesheet diff old/SampleSheet.csv new/SampleSheet.csv
    samplesheet diff old/SampleSheet.csv new/SampleSheet.csv --format json

    samplesheet merge ProjectA.csv ProjectB.csv --output combined.csv
    samplesheet merge ProjectA.csv ProjectB.csv ProjectC.csv --output combined.csv --to v1

    samplesheet split combined.csv --output-dir ./per_project/
    samplesheet split combined.csv --by lane --output-dir ./per_lane/ --to v1

    samplesheet filter SampleSheet.csv --project ProjectA --output filtered.csv
    samplesheet filter SampleSheet.csv --lane 2 --output filtered.csv
    samplesheet filter SampleSheet.csv --sample-id "CTRL_*" --output controls.csv

Authors
-------
Chaitanya Kasaraneni
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

try:
    import typer

    _TYPER_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TYPER_AVAILABLE = False

from samplesheet_parser.enums import SampleSheetVersion
from samplesheet_parser.validators import MIN_HAMMING_DISTANCE as _MIN_HAMMING_DEFAULT

if _TYPER_AVAILABLE:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _metadata_version

    def _version_callback(value: bool) -> None:
        if value:
            try:
                _ver = _metadata_version("samplesheet-parser")
            except PackageNotFoundError:
                _ver = "unknown"
            typer.echo(f"samplesheet-parser {_ver}")
            raise typer.Exit()

    app = typer.Typer(
        name="samplesheet",
        help="Format-agnostic parser and toolkit for Illumina SampleSheet.csv files.",
        no_args_is_help=True,
        pretty_exceptions_enable=False,
    )

    @app.callback()
    def _main_callback(
        version: Annotated[
            bool,
            typer.Option(
                "--version",
                "-V",
                help="Show version and exit.",
                callback=_version_callback,
                is_eager=True,
                is_flag=True,
            ),
        ] = False,
    ) -> None:
        pass

    # ---------------------------------------------------------------------------
    # Shared option types
    # ---------------------------------------------------------------------------

    _FormatOption = Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: 'text' (default) or 'json'.",
            metavar="FORMAT",
        ),
    ]

    _OutputOption = Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Destination file path.",
            metavar="PATH",
        ),
    ]

    _VersionOption = Annotated[
        str,
        typer.Option(
            "--to",
            help="Target format: 'v1' or 'v2'.",
            metavar="VERSION",
        ),
    ]

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def _resolve_version(v: str) -> SampleSheetVersion:
        """Map 'v1'/'v2' CLI string to SampleSheetVersion enum."""
        v = v.strip().lower()
        if v == "v1":
            return SampleSheetVersion.V1
        if v == "v2":
            return SampleSheetVersion.V2
        typer.echo(f"Error: unknown version '{v}'. Use 'v1' or 'v2'.", err=True)
        raise typer.Exit(code=2)

    def _print_json(data: dict[str, object]) -> None:
        typer.echo(json.dumps(data, indent=2))

    def _validate_fmt(fmt: str) -> None:
        """Exit 2 if fmt is not a recognised output format."""
        if fmt not in ("text", "json"):
            typer.echo(f"Error: unknown format '{fmt}'. Use 'text' or 'json'.", err=True)
            raise typer.Exit(code=2)

    # ---------------------------------------------------------------------------
    # info
    # ---------------------------------------------------------------------------

    @app.command()
    def info(
        path: Annotated[Path, typer.Argument(help="Path to SampleSheet.csv.", metavar="FILE")],
        fmt: _FormatOption = "text",
    ) -> None:
        """Display a quick summary of a sample sheet without full validation.

        Shows format version, sample count, lanes, index type, read lengths,
        and adapter sequences at a glance.

        Exits 0 on success, 2 on unreadable files.
        """
        from samplesheet_parser.factory import SampleSheetFactory
        from samplesheet_parser.parsers.v1 import SampleSheetV1

        _validate_fmt(fmt)
        if not path.exists():
            typer.echo(f"Error: file not found: {path}", err=True)
            raise typer.Exit(code=2)

        try:
            factory = SampleSheetFactory()
            sheet = factory.create_parser(str(path), parse=True, clean=False)
        except Exception as exc:
            typer.echo(f"Error: could not parse {path}: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        if factory.version is None:  # pragma: no cover
            raise RuntimeError("SampleSheetFactory.version must be set after create_parser")

        samples = sheet.samples()
        lanes = sorted({str(s.get("lane") or "") for s in samples} - {""}) or ["(none)"]
        index_type = sheet.index_type()
        adapters: list[str] = getattr(sheet, "adapters", []) or []
        experiment_name: str | None = getattr(sheet, "experiment_name", None)

        if isinstance(sheet, SampleSheetV1):
            read_lengths = [str(r) for r in (sheet.read_lengths or [])]
            instrument = sheet.instrument_type
        else:
            reads_dict = sheet.reads or {}
            read_lengths = [
                str(reads_dict[k]) for k in ("Read1Cycles", "Read2Cycles") if k in reads_dict
            ]
            instrument = sheet.instrument_platform

        if fmt == "json":
            _print_json(
                {
                    "file": str(path),
                    "format": factory.version.value,
                    "sample_count": len(samples),
                    "lanes": lanes,
                    "index_type": index_type,
                    "read_lengths": read_lengths,
                    "adapters": adapters,
                    "experiment_name": experiment_name,
                    "instrument": instrument,
                }
            )
        else:
            typer.echo(f"File:          {path}")
            typer.echo(f"Format:        {factory.version.value}")
            typer.echo(f"Samples:       {len(samples)}")
            typer.echo(f"Lanes:         {', '.join(lanes)}")
            typer.echo(f"Index type:    {index_type}")
            typer.echo(
                f"Read lengths:  {' + '.join(read_lengths) if read_lengths else '(not set)'}"
            )
            typer.echo(f"Adapters:      {', '.join(adapters) if adapters else '(none)'}")
            if experiment_name:
                typer.echo(f"Experiment:    {experiment_name}")
            if instrument:
                typer.echo(f"Instrument:    {instrument}")

        raise typer.Exit(code=0)

    # ---------------------------------------------------------------------------
    # validate
    # ---------------------------------------------------------------------------

    @app.command()
    def validate(
        path: Annotated[Path, typer.Argument(help="Path to SampleSheet.csv.", metavar="FILE")],
        fmt: _FormatOption = "text",
        min_hamming: Annotated[
            int,
            typer.Option(
                "--min-hamming",
                help=(
                    f"Minimum Hamming distance between indexes "
                    f"(default: {_MIN_HAMMING_DEFAULT}, must be >= 1)."
                ),
                metavar="N",
            ),
        ] = _MIN_HAMMING_DEFAULT,
    ) -> None:
        """Validate a sample sheet for index, adapter, and structural issues.

        Exits 0 if the sheet is valid (warnings are allowed).
        Exits 1 if any errors are found.
        Exits 2 on usage errors or unreadable files.
        """
        from samplesheet_parser.factory import SampleSheetFactory
        from samplesheet_parser.validators import SampleSheetValidator

        _validate_fmt(fmt)
        if min_hamming < 1:
            typer.echo(f"Error: --min-hamming must be >= 1, got {min_hamming}.", err=True)
            raise typer.Exit(code=2)
        if not path.exists():
            typer.echo(f"Error: file not found: {path}", err=True)
            raise typer.Exit(code=2)

        try:
            factory = SampleSheetFactory()
            sheet = factory.create_parser(str(path), parse=True, clean=False)
        except Exception as exc:
            typer.echo(f"Error: could not parse {path}: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        if factory.version is None:  # pragma: no cover
            raise RuntimeError("SampleSheetFactory.version must be set after create_parser")
        version = factory.version

        result = SampleSheetValidator().validate(sheet, min_hamming_distance=min_hamming)

        if fmt == "json":
            _print_json(
                {
                    "file": str(path),
                    "version": version.value,
                    "is_valid": result.is_valid,
                    "min_hamming_distance": min_hamming,
                    "errors": [
                        {"code": e.code, "message": e.message, "context": e.context}
                        for e in result.errors
                    ],
                    "warnings": [
                        {"code": w.code, "message": w.message, "context": w.context}
                        for w in result.warnings
                    ],
                    "summary": result.summary(),
                }
            )
        else:
            typer.echo(f"File:    {path}")
            typer.echo(f"Format:  {version.value}")
            typer.echo(f"Result:  {result.summary()}")

            if result.warnings:
                typer.echo("\nWarnings:")
                for w in result.warnings:
                    typer.echo(f"  {w}")

            if result.errors:
                typer.echo("\nErrors:", err=True)
                for e in result.errors:
                    typer.echo(f"  {e}", err=True)

        raise typer.Exit(code=0 if result.is_valid else 1)

    # ---------------------------------------------------------------------------
    # convert
    # ---------------------------------------------------------------------------

    @app.command()
    def convert(
        path: Annotated[Path, typer.Argument(help="Input SampleSheet.csv.", metavar="FILE")],
        to: _VersionOption = "v2",
        output: _OutputOption = Path("SampleSheet_converted.csv"),
        fmt: _FormatOption = "text",
    ) -> None:
        """Convert a sample sheet between V1 (IEM/bcl2fastq) and V2 (BCLConvert) formats.

        V2→V1 conversion is lossy: V2-only fields (OverrideCycles, InstrumentPlatform,
        etc.) are dropped with a warning.

        Exits 0 on success, 1 on conversion error, 2 on bad arguments.
        """
        from samplesheet_parser.converter import SampleSheetConverter

        _validate_fmt(fmt)
        if not path.exists():
            typer.echo(f"Error: file not found: {path}", err=True)
            raise typer.Exit(code=2)

        target = _resolve_version(to)

        try:
            converter = SampleSheetConverter(str(path))
            if target == SampleSheetVersion.V2:
                out = converter.to_v2(str(output))
            else:
                out = converter.to_v1(str(output))
        except Exception as exc:
            typer.echo(f"Error: conversion failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        if converter.source_version is None:  # pragma: no cover
            raise RuntimeError("SampleSheetConverter.source_version must be set after conversion")

        if fmt == "json":
            _print_json(
                {
                    "input": str(path),
                    "output": str(out),
                    "source_version": converter.source_version.value,
                    "target_version": target.value,
                }
            )
        else:
            typer.echo(
                f"Converted {path.name} ({converter.source_version.value})"
                f" → {out} ({target.value})"
            )

    # ---------------------------------------------------------------------------
    # diff
    # ---------------------------------------------------------------------------

    @app.command()
    def diff(
        old: Annotated[Path, typer.Argument(help="Original SampleSheet.csv.", metavar="OLD")],
        new: Annotated[Path, typer.Argument(help="Updated SampleSheet.csv.", metavar="NEW")],
        fmt: _FormatOption = "text",
    ) -> None:
        """Compare two sample sheets across any combination of V1 and V2.

        Exits 0 if the sheets are identical.
        Exits 1 if any differences are detected (useful in CI pre-run checks).
        Exits 2 on unreadable files.
        """
        from samplesheet_parser.diff import SampleSheetDiff

        _validate_fmt(fmt)
        for p in (old, new):
            if not p.exists():
                typer.echo(f"Error: file not found: {p}", err=True)
                raise typer.Exit(code=2)

        try:
            result = SampleSheetDiff(str(old), str(new)).compare()
        except Exception as exc:
            typer.echo(f"Error: diff failed: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        if fmt == "json":
            _print_json(
                {
                    "has_changes": result.has_changes,
                    "source_version": result.source_version.value,
                    "target_version": result.target_version.value,
                    "summary": result.summary(),
                    "header_changes": [
                        {"field": c.field, "old": c.old_value, "new": c.new_value}
                        for c in result.header_changes
                    ],
                    "samples_added": result.samples_added,
                    "samples_removed": result.samples_removed,
                    "sample_changes": [
                        {
                            "sample_id": sc.sample_id,
                            "lane": sc.lane,
                            "changes": {
                                f: {"old": o, "new": n} for f, (o, n) in sc.changes.items()
                            },
                        }
                        for sc in result.sample_changes
                    ],
                }
            )
        else:
            typer.echo(result.summary())

            if result.header_changes:
                typer.echo("\nHeader / settings changes:")
                for c in result.header_changes:
                    typer.echo(f"  {c.field}: {c.old_value!r} → {c.new_value!r}")

            if result.samples_added:
                typer.echo(f"\nSamples added ({len(result.samples_added)}):")
                for s in result.samples_added:
                    typer.echo(f"  + {s.get('Sample_ID') or s.get('sample_id', '?')}")

            if result.samples_removed:
                typer.echo(f"\nSamples removed ({len(result.samples_removed)}):")
                for s in result.samples_removed:
                    typer.echo(f"  - {s.get('Sample_ID') or s.get('sample_id', '?')}")

            if result.sample_changes:
                typer.echo(f"\nSample field changes ({len(result.sample_changes)}):")
                for sc in result.sample_changes:
                    typer.echo(f"  {sc.sample_id} (lane {sc.lane}):")
                    for f, (o, n) in sc.changes.items():
                        typer.echo(f"    {f}: {o!r} → {n!r}")

        raise typer.Exit(code=1 if result.has_changes else 0)

    # ---------------------------------------------------------------------------
    # merge
    # ---------------------------------------------------------------------------

    @app.command()
    def merge(
        files: Annotated[
            list[Path],
            typer.Argument(
                help="Input SampleSheet.csv files to merge.",
                metavar="FILES",
            ),
        ],
        output: _OutputOption = Path("SampleSheet_combined.csv"),
        to: _VersionOption = "v2",
        fmt: _FormatOption = "text",
        force: Annotated[
            bool,
            typer.Option(
                "--force",
                help="Write output even if conflicts are found.",
            ),
        ] = False,
    ) -> None:
        """Merge multiple per-project sample sheets into one combined sheet.

        Detects index collisions, Hamming distance violations, and read-length
        mismatches across sheets. Mixed V1/V2 inputs are auto-converted to the
        target format.

        Exits 0 on clean merge.
        Exits 1 if conflicts or warnings were found.
        Exits 2 on bad arguments or unreadable files.
        """
        from samplesheet_parser.merger import SampleSheetMerger

        _validate_fmt(fmt)
        if len(files) < 2:
            typer.echo("Error: at least two input files are required.", err=True)
            raise typer.Exit(code=2)

        for p in files:
            if not p.exists():
                typer.echo(f"Error: file not found: {p}", err=True)
                raise typer.Exit(code=2)

        target = _resolve_version(to)
        merger = SampleSheetMerger(target_version=target)
        for p in files:
            merger.add(p)

        try:
            result = merger.merge(
                output,
                validate=True,
                abort_on_conflicts=not force,
            )
        except Exception as exc:
            typer.echo(f"Error: merge failed: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        if fmt == "json":
            _print_json(
                {
                    "has_conflicts": result.has_conflicts,
                    "sample_count": result.sample_count,
                    "output_path": str(result.output_path) if result.output_path else None,
                    "source_versions": result.source_versions,
                    "summary": result.summary(),
                    "conflicts": [
                        {"code": c.code, "message": c.message, "context": c.context}
                        for c in result.conflicts
                    ],
                    "warnings": [
                        {"code": w.code, "message": w.message, "context": w.context}
                        for w in result.warnings
                    ],
                }
            )
        else:
            typer.echo(result.summary())

            if result.warnings:
                typer.echo("\nWarnings:")
                for w in result.warnings:
                    typer.echo(f"  {w}")

            if result.conflicts:
                typer.echo("\nConflicts:", err=True)
                for c in result.conflicts:
                    typer.echo(f"  {c}", err=True)

            if result.output_path:
                typer.echo(f"\nOutput: {result.output_path}")

        has_issues = result.has_conflicts or bool(result.warnings)
        raise typer.Exit(code=1 if has_issues else 0)

    # ---------------------------------------------------------------------------
    # split
    # ---------------------------------------------------------------------------

    @app.command()
    def split(
        path: Annotated[Path, typer.Argument(help="Input SampleSheet.csv.", metavar="FILE")],
        by: Annotated[
            str,
            typer.Option(
                "--by",
                help="Grouping key: 'project' (default) or 'lane'.",
                metavar="KEY",
            ),
        ] = "project",
        output_dir: Annotated[
            Path,
            typer.Option(
                "--output-dir",
                "-d",
                help="Directory in which to write the split files.",
                metavar="DIR",
            ),
        ] = Path("."),
        to: _VersionOption = "v2",
        fmt: _FormatOption = "text",
        prefix: Annotated[
            str,
            typer.Option(
                "--prefix",
                help="String prepended to each output filename.",
                metavar="STR",
            ),
        ] = "",
    ) -> None:
        """Split a combined sheet into one file per project or per lane.

        Header, reads, and settings are copied into every output file; only
        the sample rows are divided.  Output filenames are
        ``{prefix}{group}_SampleSheet.csv``.

        Exits 0 on success.
        Exits 1 if warnings were produced (e.g. samples with no project).
        Exits 2 on bad arguments or unreadable files.
        """
        from samplesheet_parser.splitter import SampleSheetSplitter

        _validate_fmt(fmt)
        if by not in ("project", "lane"):
            typer.echo(f"Error: --by must be 'project' or 'lane', got {by!r}.", err=True)
            raise typer.Exit(code=2)
        if not path.exists():
            typer.echo(f"Error: file not found: {path}", err=True)
            raise typer.Exit(code=2)

        target = _resolve_version(to)

        try:
            splitter = SampleSheetSplitter(path, by=by, target_version=target)
            result = splitter.split(output_dir, prefix=prefix)
        except Exception as exc:
            typer.echo(f"Error: split failed: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        if fmt == "json":
            _print_json(
                {
                    "source_version": result.source_version,
                    "by": by,
                    "output_dir": str(output_dir),
                    "summary": result.summary(),
                    "files": {k: str(v) for k, v in result.output_files.items()},
                    "sample_counts": result.sample_counts,
                    "warnings": result.warnings,
                }
            )
        else:
            typer.echo(result.summary())
            if result.output_files:
                typer.echo(f"\nOutput files ({output_dir}):")
                for group, out_path in sorted(result.output_files.items()):
                    count = result.sample_counts[group]
                    typer.echo(f"  {out_path.name}  ({count} sample(s))  [{group}]")
            if result.warnings:
                typer.echo("\nWarnings:")
                for w in result.warnings:
                    typer.echo(f"  {w}")

        raise typer.Exit(code=1 if result.warnings else 0)

    # ---------------------------------------------------------------------------
    # filter
    # ---------------------------------------------------------------------------

    @app.command(name="filter")
    def filter_cmd(
        path: Annotated[Path, typer.Argument(help="Input SampleSheet.csv.", metavar="FILE")],
        output: _OutputOption = Path("SampleSheet_filtered.csv"),
        project: Annotated[
            str,
            typer.Option(
                "--project",
                "-p",
                help="Keep only samples matching this Sample_Project (exact).",
                metavar="NAME",
            ),
        ] = "",
        lane: Annotated[
            str,
            typer.Option(
                "--lane",
                "-l",
                help="Keep only samples from this lane.",
                metavar="N",
            ),
        ] = "",
        sample_id: Annotated[
            str,
            typer.Option(
                "--sample-id",
                "-s",
                help="Keep only samples matching this Sample_ID or glob pattern.",
                metavar="PATTERN",
            ),
        ] = "",
        to: _VersionOption = "v2",
        fmt: _FormatOption = "text",
    ) -> None:
        """Extract a subset of samples from a sheet by project, lane, or sample ID.

        Multiple criteria are ANDed — a sample must match all provided
        criteria.  ``--sample-id`` supports glob patterns (e.g. ``'CTRL_*'``).

        Exits 0 if at least one sample matched.
        Exits 1 if no samples matched the criteria.
        Exits 2 on bad arguments or unreadable files.
        """
        from samplesheet_parser.filter import SampleSheetFilter

        _validate_fmt(fmt)
        if not project and not lane and not sample_id:
            typer.echo(
                "Error: at least one of --project, --lane, or --sample-id is required.",
                err=True,
            )
            raise typer.Exit(code=2)
        if not path.exists():
            typer.echo(f"Error: file not found: {path}", err=True)
            raise typer.Exit(code=2)

        target = _resolve_version(to)

        try:
            flt = SampleSheetFilter(path, target_version=target)
            result = flt.filter(
                output,
                project=project or None,
                lane=lane or None,
                sample_id=sample_id or None,
            )
        except Exception as exc:
            typer.echo(f"Error: filter failed: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        if fmt == "json":
            _print_json(
                {
                    "source_version": result.source_version,
                    "matched_count": result.matched_count,
                    "total_count": result.total_count,
                    "output_path": str(result.output_path) if result.output_path else None,
                    "summary": result.summary(),
                    "criteria": {
                        "project": project or None,
                        "lane": lane or None,
                        "sample_id": sample_id or None,
                    },
                }
            )
        else:
            typer.echo(result.summary())
            if result.output_path:
                typer.echo(f"Output: {result.output_path}")

        raise typer.Exit(code=0 if result.matched_count > 0 else 1)

else:  # pragma: no cover
    # Fallbacks when Typer is not installed: keep simple type aliases so that
    # the module can be imported and type annotations remain usable.
    _FormatOption = str  # type: ignore[misc]
    _OutputOption = Path  # type: ignore[misc]
    _VersionOption = str  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:  # pragma: no cover
    """Entry point for the ``samplesheet`` CLI command."""
    if not _TYPER_AVAILABLE:
        import sys

        sys.stderr.write(
            "Error: the samplesheet-parser CLI requires 'typer'.\n"
            "Install it with: pip install 'samplesheet-parser[cli]'\n"
        )
        raise SystemExit(2)
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
