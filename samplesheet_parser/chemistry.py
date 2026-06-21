"""
Sequencing chemistry channel models and index colour-balance analysis.

Illumina (and Element) instruments call bases by detecting fluorescent
signal in one, two, or four optical channels per cycle. The number of
channels determines how a base is encoded as *signal*, and that in turn
determines what makes a pool of indexes safe to sequence together:

* **4-channel** (Illumina MiSeq, HiSeq 2000/2500/3000/4000) - four colours
  imaged with two lasers: a green laser reads ``{G,T}`` and a red laser
  reads ``{A,C}``. Every base produces signal, but each cycle still needs at
  least one base from *each* laser group across the pool, or one laser is
  dark and clusters cannot be registered.

* **avidity** (Element AVITI) - each base is labelled with its own avidite
  dye (four images per cycle, no dark base; Arslan et al., *Nat. Biotechnol.*
  2023). Unlike Illumina's two-laser SBS there is no laser-pair constraint,
  so the platform tolerates low-diversity pools; low diversity is at most an
  advisory, never a failure.

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
# cycle. 0.10 is a heuristic (not a published vendor number); Illumina's
# stated rule is qualitative.
DEFAULT_MIN_SIGNAL_FRACTION = 0.10

# AVITI (avidity) advisory window: Element's metrics flag low base diversity in
# the first few cycles of an index/read for attention, but never as a failure.
# Ref: Element "ElemBio Cloud / AVITI OS - Metrics and Charts"; Element "AVITI
# System: The Ideal Platform for Low-Diversity Sequencing."
AVIDITY_ADVISORY_FIRST_CYCLES = 5


class Chemistry(str, Enum):
    """Optical detection chemistry of a sequencing instrument.

    ``FOUR_CHANNEL`` and ``AVIDITY`` are both "four-colour" in that every base
    produces signal (no single dark base), but they differ in registration
    structure and therefore in color-balance rules:

    * ``FOUR_CHANNEL`` (Illumina MiSeq/HiSeq) images two lasers - a green laser
      reads ``{G,T}`` and a red laser reads ``{A,C}`` - so each cycle needs at
      least one base from *each* laser group across the pool.
    * ``AVIDITY`` (Element AVITI) labels each base with its own avidite dye, so
      there is no laser-pair constraint and the platform tolerates low-diversity
      pools (Arslan et al., Nat. Biotechnol. 2023).
    """

    ONE_CHANNEL = "1-channel"
    TWO_CHANNEL = "2-channel"
    FOUR_CHANNEL = "4-channel"
    AVIDITY = "avidity"


class ColorBalanceMode(str, Enum):
    """How strictly to score color balance.

    ``VENDOR_FAITHFUL`` (default) encodes each platform's *published* rule
    exactly. ``CONSERVATIVE`` is stricter than the published hard minimum,
    flagging risks the vendor's minimum permits (e.g. single-channel 2-channel
    cycles, or AVITI low diversity).
    """

    VENDOR_FAITHFUL = "vendor_faithful"
    CONSERVATIVE = "conservative"


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
    # Element Biosciences AVITI - avidity chemistry labels each base with its
    # own avidite dye (four images per cycle, no dark base) and, unlike
    # Illumina's two-laser four-colour SBS, has no laser-pair constraint, so it
    # tolerates low-diversity pools. Modelled as its own chemistry.
    # Ref: Arslan et al., Nat. Biotechnol. 2023.
    "aviti": Chemistry.AVIDITY,
    "elementaviti": Chemistry.AVIDITY,
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
    mode: ColorBalanceMode = ColorBalanceMode.VENDOR_FAITHFUL
    cycles: list[CycleBalance] = field(default_factory=list)
    dark_cycles: list[CycleBalance] = field(default_factory=list)
    weak_cycles: list[CycleBalance] = field(default_factory=list)
    advisory_cycles: list[CycleBalance] = field(default_factory=list)

    @property
    def is_balanced(self) -> bool:
        """True if no *failing* (dark) cycles were found.

        Weak cycles (single-channel-but-present, or below the soft signal
        threshold) and advisory cycles (AVITI low diversity) are quality flags
        that do not fail the pool.
        """
        return not self.dark_cycles


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
    mode: ColorBalanceMode | str = ColorBalanceMode.VENDOR_FAITHFUL,
    min_signal_fraction: float = DEFAULT_MIN_SIGNAL_FRACTION,
) -> ColorBalanceReport:
    """Score an index pool for colour balance against a chemistry and mode.

    Rules per chemistry (sources cited inline below):

    * **2-/1-channel** (NextSeq/MiniSeq/NovaSeq, iSeq). ``G`` is the dark base.
      An all-``G`` cycle (no signal in either channel) is a *dark* failure in
      both modes. A single-channel cycle (one channel present, the other dark)
      is a *failure* in ``CONSERVATIVE`` mode but only a *weak* warning in
      ``VENDOR_FAITHFUL`` mode, matching Illumina's hard minimum of "signal in
      at least one channel" (Index Adapters Pooling Guide #1000000041074).
    * **4-channel** (Illumina MiSeq/HiSeq). A green laser reads ``{G,T}`` and a
      red laser reads ``{A,C}``; each cycle must include at least one base from
      each laser group across the pool, else a laser is dark. A cycle missing
      either laser is a *dark* failure in **both** modes (correctness, not a
      strictness choice).
    * **avidity** (Element AVITI). No dark base and no laser-pair constraint, so
      low diversity never fails. In ``VENDOR_FAITHFUL`` mode low diversity in
      the first :data:`AVIDITY_ADVISORY_FIRST_CYCLES` cycles is an *advisory*
      (never a failure); in ``CONSERVATIVE`` mode any low-diversity cycle is
      escalated to a *dark* failure.

    Parameters
    ----------
    index1, index2:
        I7 (and optional I5) index sequences; empty strings are ignored.
    chemistry:
        Chemistry to score against - see :func:`chemistry_for_instrument`.
    mode:
        :class:`ColorBalanceMode` (or its string value). Defaults to
        ``VENDOR_FAITHFUL``.
    min_signal_fraction:
        Soft threshold below which an otherwise-present channel is flagged weak
        (heuristic; not a published vendor number).

    Returns
    -------
    ColorBalanceReport
        Per-cycle diagnostics with dark (failing), weak (warning), and advisory
        cycles collected separately.
    """
    mode = ColorBalanceMode(mode)
    conservative = mode is ColorBalanceMode.CONSERVATIVE

    reads: list[tuple[str, list[str]]] = [("index1", [s for s in index1 if s])]
    if index2 is not None:
        reads.append(("index2", [s for s in index2 if s]))

    report = ColorBalanceReport(
        chemistry=chemistry,
        pool_size=len([s for s in index1 if s]),
        mode=mode,
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

            # A single sample lights whatever its own bases dictate; not
            # assessable as a pool. Record but never flag.
            if pool < 2:
                report.cycles.append(cb)
                continue

            if chemistry is Chemistry.FOUR_CHANNEL:
                _score_four_channel(cb, counts, pool, report)
            elif chemistry is Chemistry.AVIDITY:
                _score_avidity(cb, report, conservative=conservative)
            else:  # TWO_CHANNEL / ONE_CHANNEL
                _score_two_channel(
                    cb,
                    counts,
                    pool,
                    report,
                    conservative=conservative,
                    min_signal_fraction=min_signal_fraction,
                )

            report.cycles.append(cb)

    return report


def _score_two_channel(
    cb: CycleBalance,
    counts: dict[str, int],
    pool: int,
    report: ColorBalanceReport,
    *,
    conservative: bool,
    min_signal_fraction: float,
) -> None:
    """2-/1-channel rule. Red = {A,C}, green = {A,T}; G is dark.

    Illumina hard minimum: signal in at least one channel (Index Adapters
    Pooling Guide #1000000041074; NextSeq/MiniSeq and NovaSeq 6000
    color-balancing knowledge articles).
    """
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

    red_present = red > 0
    green_present = green > 0
    if not red_present and not green_present:
        report.dark_cycles.append(cb)  # all-G: no signal either channel (both modes)
    elif not red_present or not green_present:
        # Single channel: vendor minimum met (>=1 channel), but imbalanced.
        if conservative:
            report.dark_cycles.append(cb)
        else:
            report.weak_cycles.append(cb)
    elif cb.red_fraction < min_signal_fraction or cb.green_fraction < min_signal_fraction:
        report.weak_cycles.append(cb)  # both present but one is faint (both modes)


def _score_four_channel(
    cb: CycleBalance,
    counts: dict[str, int],
    pool: int,
    report: ColorBalanceReport,
) -> None:
    """Illumina 4-colour rule (both modes). Green laser = {G,T}, red laser = {A,C}.

    Each cycle must include at least one base from each laser group across the
    pool, or a laser is dark and clusters cannot be registered. Ref: Index
    Adapters Pooling Guide #1000000041074, four-channel section.
    """
    red_laser = counts.get("A", 0) + counts.get("C", 0)  # {A,C}
    green_laser = counts.get("G", 0) + counts.get("T", 0)  # {G,T}
    cb.red_fraction = red_laser / pool
    cb.green_fraction = green_laser / pool
    if red_laser == 0 or green_laser == 0:
        report.dark_cycles.append(cb)


def _score_avidity(
    cb: CycleBalance,
    report: ColorBalanceReport,
    *,
    conservative: bool,
) -> None:
    """Element AVITI (avidity) rule. No dark base; low diversity is tolerated.

    Ref: Element "ElemBio Cloud / AVITI OS - Metrics and Charts"; Element
    "AVITI System: The Ideal Platform for Low-Diversity Sequencing."
    """
    low_diversity = cb.distinct_bases <= 1
    if not low_diversity:
        return
    if conservative:
        report.dark_cycles.append(cb)  # escalate low diversity to a failure
    elif cb.cycle <= AVIDITY_ADVISORY_FIRST_CYCLES:
        report.advisory_cycles.append(cb)  # first-cycles low diversity: advisory only
