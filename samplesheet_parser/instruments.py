"""
Illumina instrument workflow classification and i5 orientation helpers.

The two demultiplexers — ``bcl2fastq`` (V1 sheets) and ``BCLConvert``
(V2 sheets) — disagree on the orientation of index 2 (i5) for some
instruments:

* **Workflow A** instruments read i5 in the *forward* orientation. Both
  demultiplexers record i5 in the forward orientation, so no conversion
  is needed when moving between V1 and V2.
* **Workflow B** instruments read i5 *reverse-complemented* on the
  chip. ``bcl2fastq`` records i5 as it was read (i.e. reverse-
  complemented); ``BCLConvert`` always expects i5 in the forward
  orientation and reverse-complements internally based on the declared
  ``InstrumentPlatform``. A faithful V1 → V2 conversion must therefore
  reverse-complement ``Index2`` for workflow-B instruments.

Workflow split
--------------

============= ========================================================
Workflow      Instruments
============= ========================================================
A (forward)   MiSeq, HiSeq 2000, HiSeq 2500, NovaSeq 6000 (v1.0 chem)
B (RC on chip) NovaSeq X / X Plus, NextSeq 500/550/1000/2000, iSeq 100,
              MiniSeq, HiSeq 3000, HiSeq 4000, NovaSeq 6000 (v1.5 chem)
============= ========================================================

``NovaSeq 6000`` is chemistry-dependent (v1.0 → workflow A,
v1.5 → workflow B) and cannot be classified from instrument name alone;
:func:`detect_workflow` returns ``None`` for it and callers must pass an
explicit override.

Authors
-------
Chaitanya Kasaraneni
"""

from __future__ import annotations

import re
from enum import StrEnum


class Workflow(StrEnum):
    """i5 orientation workflow for an Illumina instrument."""

    A = "a"
    """i5 read in forward orientation. V1 and V2 sheets use the same i5 sequence."""

    B = "b"
    """i5 read reverse-complemented on the chip.  V1 records the RC form;
    V2 expects the forward form. Conversion between V1 and V2 must RC Index2."""


# ---------------------------------------------------------------------------
# Instrument tables
# ---------------------------------------------------------------------------

# Normalised instrument identifiers (lowercase, non-alphanumerics stripped)
# for instruments known to read i5 in the forward orientation.
WORKFLOW_A_INSTRUMENTS: frozenset[str] = frozenset(
    {
        "miseq",
        "hiseq2000",
        "hiseq2500",
    }
)

# Normalised instrument identifiers for instruments that RC i5 on the chip.
# Aliases for the same instrument family (e.g. "NovaSeqXPlus" vs
# "NovaSeqXSeries") are all included so detection works against both V1
# ``Instrument Type`` strings and V2 ``InstrumentPlatform`` values.
WORKFLOW_B_INSTRUMENTS: frozenset[str] = frozenset(
    {
        # NovaSeq X family — V2 sheets typically declare "NovaSeqXSeries"
        "novaseqx",
        "novaseqxplus",
        "novaseqxseries",
        # NextSeq family
        "nextseq500",
        "nextseq550",
        "nextseq1000",
        "nextseq2000",
        # Small / benchtop sequencers
        "iseq",
        "iseq100",
        "miniseq",
        # HiSeq 3000/4000 use patterned flow cells with RC'd i5
        "hiseq3000",
        "hiseq4000",
    }
)

# Instruments whose workflow depends on chemistry version and cannot be
# inferred from the name alone. Callers must supply an explicit override.
AMBIGUOUS_INSTRUMENTS: frozenset[str] = frozenset(
    {
        "novaseq",
        "novaseq6000",
    }
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

_RX_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize(name: str) -> str:
    """Lowercase and strip non-alphanumerics so ``"NovaSeq X Plus"`` and
    ``"NovaSeqXPlus"`` compare equal."""
    return _RX_NON_ALNUM.sub("", name.lower())


def detect_workflow(instrument: str | None) -> Workflow | None:
    """Classify an instrument name as workflow A or B.

    Parameters
    ----------
    instrument:
        Free-form instrument name. Matches against a normalised form of
        :data:`WORKFLOW_A_INSTRUMENTS` and :data:`WORKFLOW_B_INSTRUMENTS`
        so spacing, case, and punctuation are ignored
        (``"NovaSeq X Plus"`` ≡ ``"novaseqxplus"``).

    Returns
    -------
    Workflow | None
        :attr:`Workflow.A` or :attr:`Workflow.B` if the instrument is in
        one of the tables. ``None`` if *instrument* is empty, ambiguous
        (e.g. ``NovaSeq 6000`` — chemistry-dependent), or unrecognised.
    """
    if not instrument:
        return None
    key = _normalize(instrument)
    if key in WORKFLOW_A_INSTRUMENTS:
        return Workflow.A
    if key in WORKFLOW_B_INSTRUMENTS:
        return Workflow.B
    return None


def parse_workflow(value: str | Workflow | None) -> Workflow | None:
    """Coerce a CLI string (``"a"`` / ``"b"`` / ``"A"`` / ``"B"``) to
    :class:`Workflow`, or ``None`` if *value* is empty.

    Raises
    ------
    ValueError
        If *value* is non-empty but does not name a known workflow.
    """
    if value is None or value == "":
        return None
    if isinstance(value, Workflow):
        return value
    v = str(value).strip().lower()
    if v in ("a", "workflow_a"):
        return Workflow.A
    if v in ("b", "workflow_b"):
        return Workflow.B
    raise ValueError(f"Unknown workflow {value!r}. Use 'a' or 'b'.")


# ---------------------------------------------------------------------------
# Sequence helpers
# ---------------------------------------------------------------------------

_COMPLEMENT = str.maketrans("ACGTNacgtn", "TGCANtgcan")


def reverse_complement(seq: str) -> str:
    """Return the reverse complement of *seq*.

    Handles upper and lower case, preserves ``N`` wildcards, and returns
    the input unchanged if it is empty. Non-IUPAC characters are passed
    through (this is a permissive transform; validation happens upstream).

    Examples
    --------
    >>> reverse_complement("ATTACTCG")
    'CGAGTAAT'
    >>> reverse_complement("")
    ''
    """
    if not seq:
        return seq
    return seq.translate(_COMPLEMENT)[::-1]
