"""
Enumerations for samplesheet-parser.
"""

from enum import Enum


class SampleSheetVersion(str, Enum):
    """Illumina sample sheet format version.

    V1 — Illumina Experiment Manager (IEM) format, used with bcl2fastq.
         Identified by ``IEMFileVersion`` in the [Header] section.

    V2 — BCLConvert format, used with BCLConvert and required for
         NovaSeq X series instruments.
         Identified by ``FileFormatVersion`` in the [Header] section,
         or by the presence of ``[BCLConvert_Settings]`` / ``[BCLConvert_Data]``
         sections.
    """
    V1 = "V1"
    V2 = "V2"


class IndexType(str, Enum):
    """Sequencing index configuration.

    SINGLE — I7 index only (single-index libraries).
    DUAL   — I7 + I5 indexes (dual-index libraries, standard for modern workflows).
    NONE   — No index (rare; full-lane libraries).
    """
    SINGLE = "single"
    DUAL   = "dual"
    NONE   = "none"


class InstrumentPlatform(str, Enum):
    """Standard Illumina instrument platform identifiers used in V2 sample sheets."""
    NOVASEQ_6000       = "NovaSeq6000"
    NOVASEQ_X_SERIES   = "NovaSeqXSeries"
    NEXTSEQ_1000_2000  = "NextSeq1000/2000"
    NEXTSEQ_550        = "NextSeq550"
    MISEQ              = "MiSeq"
    HISEQ_X            = "HiSeqX"


class UMILocation(str, Enum):
    """Where the UMI is encoded in the read structure (OverrideCycles string)."""
    READ1  = "read1"
    READ2  = "read2"
    INDEX1 = "index1"
    INDEX2 = "index2"
