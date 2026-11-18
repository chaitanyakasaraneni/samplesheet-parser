"""
samplesheet-parser
====================

Multi-vendor, format-agnostic parser for sequencing sample sheets.

Supports:
  - Illumina Experiment Manager (IEM) V1 format  - bcl2fastq era
  - BCLConvert V2 format                          - NovaSeq X / modern era
  - Element Biosciences AVITI RunManifest.csv     - non-Illumina, avidity chemistry

Quickstart
----------
>>> from samplesheet_parser import SampleSheetFactory
>>> sheet = SampleSheetFactory().create_parser("SampleSheet.csv")
>>> sheet.parse()
>>> for sample in sheet.samples():
...     print(sample["sample_id"], sample["index"])

Or use the version-specific parsers directly:

>>> from samplesheet_parser import SampleSheetV1, SampleSheetV2
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("samplesheet-parser")
except PackageNotFoundError:
    __version__ = "0.1.0-dev"

__author__ = "Chaitanya Kasaraneni"
__email__ = "kc.kasaraneni@gmail.com"
__license__ = "Apache 2.0"

from samplesheet_parser.chemistry import (
    Chemistry,
    ColorBalanceMode,
    ColorBalanceReport,
    analyze_color_balance,
    chemistry_for_instrument,
)
from samplesheet_parser.converter import SampleSheetConverter
from samplesheet_parser.diff import DiffResult, SampleSheetDiff
from samplesheet_parser.enums import IndexType, InstrumentPlatform, SampleSheetVersion, UMILocation
from samplesheet_parser.factory import SampleSheetFactory
from samplesheet_parser.filter import FilterResult, SampleSheetFilter
from samplesheet_parser.index_utils import normalize_index_lengths
from samplesheet_parser.merger import MergeResult, SampleSheetMerger
from samplesheet_parser.parsers.element import ElementRunManifest
from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2
from samplesheet_parser.protocol import SampleSheetParser
from samplesheet_parser.schema import (
    ILLUMINA_V2_SCHEMA,
    ILLUMINA_V2_URN,
    SAMSHEE_V2_URN,
    build_registry,
    sheet_to_sections,
)
from samplesheet_parser.splitter import SampleSheetSplitter, SplitResult
from samplesheet_parser.validators import (
    SampleSheetValidator,
    Strictness,
    ValidationIssue,
    ValidationResult,
    Validator,
    ValidatorError,
    hamming_distance,
    illumina_v2_conformance,
    illumina_v2_schema_validator,
    index_collision_distance,
    json_schema_validator,
    sheet_to_dict,
)
from samplesheet_parser.writer import SampleSheetWriter

__all__ = [
    "ILLUMINA_V2_SCHEMA",
    "ILLUMINA_V2_URN",
    "SAMSHEE_V2_URN",
    "Chemistry",
    "ColorBalanceMode",
    "ColorBalanceReport",
    "DiffResult",
    "ElementRunManifest",
    "FilterResult",
    "IndexType",
    "InstrumentPlatform",
    "MergeResult",
    "SampleSheetConverter",
    "SampleSheetDiff",
    "SampleSheetFactory",
    "SampleSheetFilter",
    "SampleSheetMerger",
    "SampleSheetParser",
    "SampleSheetSplitter",
    "SampleSheetV1",
    "SampleSheetV2",
    "SampleSheetValidator",
    "SampleSheetVersion",
    "SampleSheetWriter",
    "SplitResult",
    "Strictness",
    "UMILocation",
    "ValidationIssue",
    "ValidationResult",
    "Validator",
    "ValidatorError",
    "__version__",
    "analyze_color_balance",
    "build_registry",
    "chemistry_for_instrument",
    "hamming_distance",
    "illumina_v2_conformance",
    "illumina_v2_schema_validator",
    "index_collision_distance",
    "json_schema_validator",
    "normalize_index_lengths",
    "sheet_to_dict",
    "sheet_to_sections",
]
