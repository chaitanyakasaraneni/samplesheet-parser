"""
Sequencing chemistry channel models and index colour-balance analysis.

Illumina (and Element) instruments call bases by detecting fluorescent
signal in one, two, or four optical channels per cycle. The number of
channels determines how a base is encoded as *signal*, and that in turn
determines what makes a pool of indexes safe to sequence together:

* **4-channel** (MiSeq, HiSeq 2000/2500/3000/4000, and Element AVITI) -
  each base has its own dye, so any base produces signal. Illumina images
  four colours per cycle; Element's avidity chemistry likewise captures
  four images per cycle, one per avidite dye (Arslan et al., *Nat.
  Biotechnol.* 2023), so the AVITI is a four-channel platform with no dark
  base. The only real risk is *low diversity*: if every sample reads the
  same base at a cycle, the instrument struggles to focus and phase,
  degrading base-call quality.

* **2-channel SBS** (NextSeq, NovaSeq 6000, NovaSeq X, MiniSeq) - two
  images (nominally "red" and "green") are captured and the base is
  inferred from which channels light up::

      A -> red + green      C -> red only
      T -> green only       G -> dark (no signal in either channel)

  Because **G is a dark base**, a cycle in which the whole pool reads G
  produces no signal at all: the instrument cannot register the tile and
  the cycle (often the whole index read) fails. Even a cycle that is only
  *mostly* G - leaving little red or green signal - calls bases poorly.

* **1-channel SBS** (iSeq 100) - a single image with a two-step chemistry.
  G is again a permanently dark base, so the same "no-signal" risk applies.

This module exposes the channel model for each chemistry, a mapping from
instrument name to chemistry, and :func:`analyze_color_balance`, which
scores an index pool cycle-by-cycle and reports dark cycles and weak
channels. :class:`~samplesheet_parser.validators.SampleSheetValidator`
consumes it to emit ``COLOR_BALANCE_NO_SIGNAL`` / ``COLOR_BALANCE_LOW``
findings.

Authors
-------
Chaitanya Kasaraneni
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from samplesheet_parser.instruments import _normalize

# Default minimum fraction of the pool that must produce signal in each
# optical channel at every index cycle. Below this (but above zero) the
# cycle is flagged as weak; exactly zero is flagged as a dark/no-signal
# cycle. 0.10 mirrors Illumina low-plex pooling guidance (each channel
# should carry meaningful signal, not a single stray sample).
DEFAULT_MIN_SIGNAL_FRACTION = 0.10


class Chemistry(str, Enum):
    """Optical detection chemistry of a sequencing instrument."""

    ONE_CHANNEL = "1-channel"
    TWO_CHANNEL = "2-channel"
    FOUR_CHANNEL = "4-channel"


# ---------------------------------------------------------------------------
# Per-base signal model
# ---------------------------------------------------------------------------

# For 1- and 2-channel chemistries, each base is encoded as the pair
# (red_channel_on, green_channel_on). ``G`` is the dark base in both
# chemistries. ``N`` is unknown and treated as contributing no guaranteed
# signal (conservative - an N cycle cannot be relied on for balance).
_TWO_CHANNEL_SIGNAL: dict[str, tuple[bool, bool]] = {
    "A": (True, True),
    "C": (True, False),
    "T": (False, True),
    "G": (False, False),
}

# 1-channel (iSeq) uses two sequential exposures rather than two colours,
# but the balance-relevant behaviour is identical to 2-channel: A/C carry
# signal in the first exposure, A/T in the second, and G is dark in both.
_ONE_CHANNEL_SIGNAL = _TWO_CHANNEL_SIGNAL


# ---------------------------------------------------------------------------
# Instrument -> chemistry mapping
# ---------------------------------------------------------------------------

# Keys are normalised (lowercase, non-alphanumerics stripped) by
# ``instruments._normalize`` so "NovaSeq X Plus" and "novaseqxplus" match.
_INSTRUMENT_CHEMISTRY: dict[str, Chemistry] = {
    # 4-channel
    "miseq": Chemistry.FOUR_CHANNEL,
    "hiseq2000": Chemistry.FOUR_CHANNEL,
    "hiseq2500": Chemistry.FOUR_CHANNEL,
    "hiseq3000": Chemistry.FOUR_CHANNEL,
    "hiseq4000": Chemistry.FOUR_CHANNEL,
    # Element Biosciences AVITI - avidity chemistry captures four images per
    # cycle (one per avidite dye), so it is a four-channel platform with no
    # dark base. Ref: Arslan et al., Nat. Biotechnol. 2023.
    "aviti": Chemistry.FOUR_CHANNEL,
    "elementaviti": Chemistry.FOUR_CHANNEL,
    # 2-channel
    "nextseq500": Chemistry.TWO_CHANNEL,
    "nextseq550": Chemistry.TWO_CHANNEL,
    "nextseq1000": Chemistry.TWO_CHANNEL,
    "nextseq2000": Chemistry.TWO_CHANNEL,
    "nextseq10002000": Chemistry.TWO_CHANNEL,
    "novaseq6000": Chemistry.TWO_CHANNEL,
    "novaseq": Chemistry.TWO_CHANNEL,
    "novaseqx": Chemistry.TWO_CHANNEL,
    "novaseqxplus": Chemistry.TWO_CHANNEL,
    "novaseqxseries": Chemistry.TWO_CHANNEL,
    "miniseq": Chemistry.TWO_CHANNEL,
    # 1-channel
    "iseq": Chemistry.ONE_CHANNEL,
    "iseq100": Chemistry.ONE_CHANNEL,
}


def chemistry_for_instrument(instrument: str | None) -> Chemistry | None:
    """Return the optical :class:`Chemistry` for an instrument name.

    Parameters
    ----------
    instrument:
        Free-form instrument name from a sample sheet header
        (``InstrumentPlatform`` in V2, ``Instrument Type`` in V1, or a
        vendor-specific field). Matched case- and punctuation-insensitively.

    Returns
    -------
    Chemistry | None
        The chemistry, or ``None`` if *instrument* is empty or unrecognised
        (in which case callers should skip colour-balance checking rather
        than guess).

    Examples
    --------
    >>> chemistry_for_instrument("NovaSeq X Plus")
    <Chemistry.TWO_CHANNEL: '2-channel'>
    >>> chemistry_for_instrument("MiSeq")
    <Chemistry.FOUR_CHANNEL: '4-channel'>
    >>> chemistry_for_instrument("Unknown") is None
    True
    """
    if not instrument:
        return None
    return _INSTRUMENT_CHEMISTRY.get(_normalize(instrument))


# ---------------------------------------------------------------------------
# Colour-balance analysis
# ---------------------------------------------------------------------------


@dataclass
class CycleBalance:
    """Per-cycle colour-balance diagnostics for one index read position.

    Attributes
    ----------
    read:
        ``"index1"`` or ``"index2"`` - which index read this cycle belongs to.
    cycle:
        1-based cycle position within that index read.
    base_counts:
        Count of each base (``A``/``C``/``G``/``T``/``N``) across the pool at
        this cycle.
    red_fraction, green_fraction:
        Fraction of the pool producing signal in each channel (2-/1-channel
        only). ``None`` for 4-channel chemistry.
    distinct_bases:
        Number of distinct non-``N`` bases observed (used for 4-channel
        low-diversity detection).
    pool_size:
        Number of samples contributing a base at this cycle.
    """

    read: str
    cycle: int
    base_counts: dict[str, int]
    pool_size: int
    red_fraction: float | None = None
    green_fraction: float | None = None
    distinct_bases: int = 0

    @property
    def is_dark(self) -> bool:
        """True if a channel has zero signal (2-/1-channel) - a failed cycle."""
        if self.red_fraction is None or self.green_fraction is None:
            return False
        return self.red_fraction == 0.0 or self.green_fraction == 0.0


@dataclass
class ColorBalanceReport:
    """Result of :func:`analyze_color_balance`.

    Attributes
    ----------
    chemistry:
        The chemistry the pool was scored against.
    cycles:
        Per-cycle diagnostics across both index reads.
    dark_cycles:
        Cycles with no signal in at least one channel (guaranteed failure).
    weak_cycles:
        Cycles with signal below ``min_signal_fraction`` in some channel, or
        single-base cycles for 4-channel chemistry (degraded quality).
    pool_size:
        Number of samples analysed.
    """

    chemistry: Chemistry
    pool_size: int
    cycles: list[CycleBalance] = field(default_factory=list)
    dark_cycles: list[CycleBalance] = field(default_factory=list)
    weak_cycles: list[CycleBalance] = field(default_factory=list)

    @property
    def is_balanced(self) -> bool:
        """True if no dark or weak cycles were found."""
        return not self.dark_cycles and not self.weak_cycles


def _column_bases(indexes: list[str], cycle: int) -> dict[str, int]:
    """Count bases at a 0-based ``cycle`` across indexes long enough to reach it."""
    counts: dict[str, int] = {}
    for seq in indexes:
        if cycle < len(seq):
            base = seq[cycle].upper()
            counts[base] = counts.get(base, 0) + 1
    return counts


def analyze_color_balance(
    index1: list[str],
    index2: list[str] | None = None,
    *,
    chemistry: Chemistry,
    min_signal_fraction: float = DEFAULT_MIN_SIGNAL_FRACTION,
) -> ColorBalanceReport:
    """Score an index pool for colour balance against a chemistry.

    The pool is analysed cycle-by-cycle. For 2-channel and 1-channel
    chemistries each cycle is checked for red and green signal: a channel
    with no contributing sample is a *dark cycle* (the run will fail to
    register), and a channel below *min_signal_fraction* is a *weak cycle*.
    For 4-channel chemistry, a cycle where the whole pool reads a single
    base is flagged as weak (low diversity degrades focusing and phasing).

    Parameters
    ----------
    index1:
        I7 index sequences, one per sample (empty strings are ignored).
    index2:
        Optional I5 index sequences, one per sample.
    chemistry:
        Chemistry to score against - see :func:`chemistry_for_instrument`.
    min_signal_fraction:
        Minimum fraction of the pool that must light each channel at every
        cycle before the cycle is flagged weak. Defaults to
        :data:`DEFAULT_MIN_SIGNAL_FRACTION`.

    Returns
    -------
    ColorBalanceReport
        Per-cycle diagnostics plus collected dark and weak cycles.
    """
    reads: list[tuple[str, list[str]]] = [("index1", [s for s in index1 if s])]
    if index2 is not None:
        reads.append(("index2", [s for s in index2 if s]))

    report = ColorBalanceReport(
        chemistry=chemistry,
        pool_size=len([s for s in index1 if s]),
    )

    for read_name, seqs in reads:
        if not seqs:
            continue
        max_len = max(len(s) for s in seqs)
        for c in range(max_len):
            counts = _column_bases(seqs, c)
            pool = sum(counts.values())
            if pool == 0:
                continue

            cb = CycleBalance(
                read=read_name,
                cycle=c + 1,
                base_counts=counts,
                pool_size=pool,
                distinct_bases=len([b for b in counts if b != "N"]),
            )

            if chemistry is Chemistry.FOUR_CHANNEL:
                # Any base produces signal; only flag total lack of diversity.
                if cb.distinct_bases <= 1 and pool >= 2:
                    report.weak_cycles.append(cb)
            else:
                red = green = 0
                for base, n in counts.items():
                    sig = _TWO_CHANNEL_SIGNAL.get(base)
                    if sig is None:
                        continue  # N or unexpected char: no guaranteed signal
                    if sig[0]:
                        red += n
                    if sig[1]:
                        green += n
                cb.red_fraction = red / pool
                cb.green_fraction = green / pool

                # Pool size 1 cannot be "balanced" - a single sample lights
                # whatever channels its own bases dictate. Skip it rather than
                # flag every cycle of a single-sample sheet.
                if pool < 2:
                    report.cycles.append(cb)
                    continue

                if cb.is_dark:
                    report.dark_cycles.append(cb)
                elif (
                    cb.red_fraction < min_signal_fraction or cb.green_fraction < min_signal_fraction
                ):
                    report.weak_cycles.append(cb)

            report.cycles.append(cb)

    return report
