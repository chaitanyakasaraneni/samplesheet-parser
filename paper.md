---
title: 'samplesheet-parser: A multi-vendor parser, validator, and converter for sequencing sample sheets'
tags:
  - Python
  - bioinformatics
  - genomics
  - next-generation sequencing
  - Illumina
  - Element AVITI
  - demultiplexing
authors:
  - name: Chaitanya Krishna Kasaraneni
    orcid: 0000-0001-5792-1095
    affiliation: 1
affiliations:
  - name: Independent Researcher
    index: 1
date: 13 July 2026
bibliography: paper.bib
---

# Summary

Every high-throughput sequencing run begins with a *sample sheet*: a small CSV
file that maps each sample to its index barcodes and tells the demultiplexer how
to split raw signal into per-sample reads. Despite being the linchpin of every
run, the sample sheet has no single standard. Illumina alone ships two mutually
incompatible layouts, the legacy IEM V1 format consumed by `bcl2fastq`
[@bcl2fastq] and the modern BCLConvert V2 format [@bclconvert_guide], and
non-Illumina platforms such as the Element AVITI [@arslan2023avidity] introduce
their own run-manifest dialect. A single error in any of these files, whether a
duplicated index, a barcode collision, or an index design that produces no
optical signal, can invalidate an entire flow cell after the reagents and machine
time have already been spent.

`samplesheet-parser` is a dependency-free Python library and command-line tool
that parses, validates, converts, diffs, merges, splits, filters, and
programmatically writes sequencing sample sheets behind one consistent interface.
It auto-detects the file format across vendors and exposes the same `samples()`
and `index_type()` API regardless of origin, so downstream code never has to
branch on format. Beyond structural parsing, it performs index-integrity checks
(character set, length, duplicates, and wildcard-aware Hamming distance), decodes
`OverrideCycles` strings to locate unique molecular identifiers [@smith2017umi],
and models each instrument's optical detection chemistry to flag index pools that
are not color balanced. The library is typed (`mypy --strict`), tested with an
automated suite of over 750 unit tests at roughly 98% line coverage, and
documented with a full user guide and API reference.

![Architecture of `samplesheet-parser`. A single factory auto-detects the input
format, either Illumina V1/V2 or an Element AVITI run manifest, and routes it to a
parser that exposes a shared interface; validation, conversion, diffing, merging,
and writing all operate on the common representation.\label{fig:arch}](images/samplesheet_parser_arch_v2.3.png)

# Statement of need

Core facilities and sequencing labs routinely operate mixed instrument fleets,
producing sample sheets in several incompatible formats that must be validated
before a run is committed. Existing open-source tools address only a slice of
this problem. The widely used `sample-sheet` library [@sample_sheet_clintval]
reads and writes the IEM V1 format but does not support BCLConvert V2, while
`samshee` [@samshee] validates V2 sheets against the Illumina schema but does not
handle V1, convert between formats, or address non-Illumina vendors. In both
cases the validation is *structural*: it confirms that fields are present and
well-formed, but cannot catch design errors that are syntactically valid yet
will fail on the instrument.

`samplesheet-parser` fills these gaps with three capabilities not available
together elsewhere:

1. **Cross-format support and conversion.** A single auto-detecting factory
   parses IEM V1 and BCLConvert V2 sheets through a shared interface and converts
   between them where possible, with explicit warnings when V2-only fields cannot
   be represented in V1. This lets a lab standardize tooling across old and new
   instruments without rewriting pipelines (\autoref{fig:arch}).

2. **Optical color-balance validation.** Two-channel instruments (for example
   NextSeq and NovaSeq X) read the base `G` as a dark, no-dye signal; an index
   cycle in which the entire pool reads `G` therefore registers no light and
   silently fails to demultiplex, an error that index-distance checks cannot
   detect. The library models the four-, two-, and one-channel chemistries of
   Illumina instruments, as well as the avidity chemistry of the Element AVITI,
   and scores an index pool cycle by cycle. It offers a `vendor_faithful` mode
   that encodes each platform's published rule and a stricter `conservative`
   mode, moving a class of run-ending mistakes from post-hoc troubleshooting to
   pre-run validation.

3. **Multi-vendor parsing.** The same factory recognizes Element AVITI
   `RunManifest.csv` files and parses them through the identical interface,
   mapping manifest fields onto the shared sample schema. Because AVITI uses an
   avidity chemistry [@arslan2023avidity] in which each base carries its own dye
   and there is no dark base, the color-balance model applies the appropriate
   rules automatically. The parser is built around a structural `Protocol`, so
   support for additional platforms can be added without modifying the core.

The tool is usable both as a library, for embedding in laboratory information
management systems and demultiplexing pipelines, and as a `Typer`-based
command-line application [@typer] with machine-readable JSON output for
continuous-integration gating of sample sheets before sequencing. It also ships
a set of nf-core-style Nextflow modules (validate, convert, diff, merge, split,
filter, and info) so the same operations can be dropped into existing Nextflow
workflows.

# Acknowledgements

The author thanks the open-source bioinformatics community for the public format
documentation and reference tools that informed this work. Parts of the code,
tests, and documentation were developed with the assistance of generative AI
tools; all output was reviewed and verified by the author.

# References
