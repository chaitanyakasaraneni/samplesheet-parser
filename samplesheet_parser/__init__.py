"""
samplesheet-parser
====================

Format-agnostic parser for Illumina SampleSheet.csv files.

Supports:
  - Illumina Experiment Manager (IEM) V1 format  — bcl2fastq era
  - BCLConvert V2 format                          — NovaSeq X / modern era

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
__email__  = "kc.kasaraneni@gmail.com"
__license__ = "Apache 2.0"

from samplesheet_parser.converter import SampleSheetConverter
from samplesheet_parser.enums import IndexType, SampleSheetVersion
from samplesheet_parser.factory import SampleSheetFactory
from samplesheet_parser.parsers.v1 import SampleSheetV1
from samplesheet_parser.parsers.v2 import SampleSheetV2
from samplesheet_parser.validators import SampleSheetValidator, ValidationResult

__all__ = [
    "SampleSheetV1",
    "SampleSheetV2",
    "SampleSheetFactory",
    "SampleSheetVersion",
    "IndexType",
    "SampleSheetValidator",
    "ValidationResult",
    "SampleSheetConverter",
    "__version__",
]
