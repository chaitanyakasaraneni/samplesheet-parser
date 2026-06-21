"""Synthetic sample-sheet corpus generator and color-balance evaluation harness.

This package builds a fully synthetic, deterministic corpus of index pools,
serializes each pool to all three formats supported by ``samplesheet-parser``
(Illumina IEM V1, Illumina BCLConvert V2, Element AVITI RunManifest), and
evaluates the library's chemistry-aware color-balance validator against two
independent ground-truth labelings. No real or proprietary data is used.
"""
