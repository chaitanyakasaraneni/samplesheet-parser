"""Published vendor color-balance rules (the independent yardstick for label_reference).

Each function encodes a *vendor's published guidance* for a platform family and
returns a pass/fail verdict plus a human-readable reason. These rules are
deliberately independent of the library under test AND of the first-principles
``label_definitional`` in ``generate_corpus.py``, so the harness can quantify
where implementation, first principles, and published guidance diverge.

Design rules (per task constraints):

* Illumina guidance is **qualitative** ("signal in at least one channel,
  preferably both") -- it is encoded as a rule, NOT as an invented numeric
  threshold. No Illumina percentage is fabricated here.
* First-cycle constraints are **per platform**, not generalized.
* AVITI is treated permissively (no dark-base failure mode); its low-diversity
  note is **advisory only** and can never produce a hard fail.
* Dispatch is by **vendor/platform key** ("2channel" / "4channel" / "aviti"),
  not by physical channel count: the Element AVITI is physically four-channel
  but Element's *guidance* differs from Illumina's four-channel guidance.

Citations (document numbers / titles where known)
-------------------------------------------------
[ILL-POOL] Illumina, "Index Adapters Pooling Guide", document #1000000041074.
           (two-channel and four-channel color-balance sections.)
[ILL-2CH]  Illumina Knowledge, "Index color balancing for the NextSeq 500/550
           and MiniSeq systems."
[ILL-NVS]  Illumina Knowledge, "Index color balancing for the NovaSeq 6000
           system." (NextSeq 1000/2000 standard SBS substitutes blue for red;
           G is still the dark base, so the two-channel rule is identical.)
[ELE-MET]  Element Biosciences, "ElemBio Cloud / AVITI OS -- Metrics and
           Charts" (first-five-cycles low-diversity note).
[ELE-LOW]  Element Biosciences, "AVITI System: The Ideal Platform for
           Low-Diversity Sequencing."
"""

from __future__ import annotations

from dataclasses import dataclass

# ===========================================================================
# Tunable constants  (anything not directly vendor-specified is flagged)
# ===========================================================================

#: AVITI advisory: number of leading index/read cycles Element calls out for a
#: low-diversity advisory in its metrics docs. Source: [ELE-MET].
AVITI_ADVISORY_FIRST_CYCLES = 5

#: What counts as "low diversity" for the AVITI advisory. Element's docs flag
#: low base diversity qualitatively but do not publish a numeric cutoff, so we
#: use "a cycle read by a single base across the pool" (distinct non-N bases
#: <= 1). This is the strictest, least-noisy reading.
#:   # heuristic, not vendor-specified
AVITI_ADVISORY_MAX_DISTINCT_BASES = 1

#: Number of leading index cycles Illumina treats as registration-critical on
#: two-channel systems (must not be all-dark/all-G). Source: [ILL-2CH],[ILL-NVS].
TWO_CHANNEL_REGISTRATION_CYCLES = 2

#: Minimum assessable pool size. Vendor guidance addresses *pools*; a single
#: sample lights whatever its own bases dictate, so cycles with fewer than two
#: contributing indexes are skipped for comparability with the tool/definitional
#: labels (both of which guard pool < 2).
#:   # heuristic, not vendor-specified (comparability guard)
MIN_ASSESSABLE_POOL = 2


# ===========================================================================
# Result type
# ===========================================================================


@dataclass
class RuleResult:
    """Outcome of a vendor rule: ``verdict`` is 'pass' or 'fail'."""

    verdict: str
    reason: str


# ===========================================================================
# Helpers
# ===========================================================================


def _reads(index1: list[str], index2: list[str] | None) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = [("index1", [s for s in index1 if s])]
    if index2:
        i2 = [s for s in index2 if s]
        if i2:
            out.append(("index2", i2))
    return out


def _columns(seqs: list[str]) -> list[list[str]]:
    """Per-cycle uppercase base columns over indexes long enough to reach."""
    if not seqs:
        return []
    max_len = max(len(s) for s in seqs)
    return [[s[c].upper() for s in seqs if c < len(s)] for c in range(max_len)]


# ===========================================================================
# Two-channel rule  (NextSeq 500/550, MiniSeq, NovaSeq 6000, NextSeq 1000/2000)
# ===========================================================================
#
# Base -> channel encoding [ILL-2CH],[ILL-NVS]:
#     A = green + red (both)   C = red only   T = green only   G = dark (none)
# (NextSeq 1000/2000 standard SBS uses blue in place of red; G is still dark,
#  so the logic is identical -- all are treated as the same two-channel rule.)
#
# Per-cycle rule [ILL-POOL]: each index cycle must have signal in at least one
# channel across the pool -- i.e. NOT every index is G at that cycle.
#   * green present  <=> some index has A or T
#   * red present    <=> some index has A or C
#   * both channels  -> balanced
#   * exactly one    -> WEAK (flagged, but not a failure -- "at least one")
#   * neither (all-G)-> FAIL  (no signal; cluster cannot be called)
# Hard rule: the first two index cycles must not be all-G across the pool, or
# cluster registration fails [ILL-2CH],[ILL-NVS].


def evaluate_two_channel(index1: list[str], index2: list[str] | None) -> RuleResult:
    weak_cycles: list[str] = []
    for read, seqs in _reads(index1, index2):
        for c, col in enumerate(_columns(seqs)):
            if len(col) < MIN_ASSESSABLE_POOL:
                continue
            green = any(b in ("A", "T") for b in col)
            red = any(b in ("A", "C") for b in col)
            if not green and not red:
                where = (
                    " (within the first two registration cycles)"
                    if read == "index1" and c < TWO_CHANNEL_REGISTRATION_CYCLES
                    else ""
                )
                return RuleResult(
                    "fail",
                    f"{read} cycle {c + 1} is all-G across the pool: no signal in "
                    f"either channel{where} [ILL-2CH/ILL-NVS].",
                )
            if green != red:
                lit = "green" if green else "red"
                weak_cycles.append(f"{read} cycle {c + 1} ({lit} only)")
    if weak_cycles:
        return RuleResult(
            "pass",
            "pass with weak cycles (one channel only, permitted by the "
            f"'at least one channel' rule): {'; '.join(weak_cycles)} [ILL-POOL].",
        )
    return RuleResult("pass", "both channels represented at every cycle [ILL-POOL].")


# ===========================================================================
# Four-channel rule  (MiSeq, HiSeq)
# ===========================================================================
#
# Green laser images {G, T}; red laser images {A, C} [ILL-POOL, four-channel
# section]. Each cycle must include at least one of {G, T} AND at least one of
# {A, C} across the pool, because image registration needs both lasers
# represented. A cycle missing either laser is a failure.


def evaluate_four_channel(index1: list[str], index2: list[str] | None) -> RuleResult:
    for read, seqs in _reads(index1, index2):
        for c, col in enumerate(_columns(seqs)):
            if len(col) < MIN_ASSESSABLE_POOL:
                continue
            green_laser = any(b in ("G", "T") for b in col)
            red_laser = any(b in ("A", "C") for b in col)
            if not (green_laser and red_laser):
                missing = "red {A,C}" if green_laser else "green {G,T}"
                return RuleResult(
                    "fail",
                    f"{read} cycle {c + 1}: the {missing} laser is unrepresented "
                    f"across the pool; both lasers are required [ILL-POOL].",
                )
    return RuleResult("pass", "both lasers represented at every cycle [ILL-POOL].")


# ===========================================================================
# AVITI rule  (Element Biosciences, avidity sequencing)
# ===========================================================================
#
# Element markets the AVITI as suited to low-diversity sequencing and there is
# no dark-base failure mode [ELE-LOW]. The two-/four-channel color-balance
# rules do NOT apply. The only signal encoded here is an ADVISORY (never a
# failure): if the first few cycles are low-diversity, Element's metrics flag
# them for attention [ELE-MET]. This function therefore always returns 'pass'.


def evaluate_aviti(index1: list[str], index2: list[str] | None) -> RuleResult:
    advisory: list[str] = []
    for read, seqs in _reads(index1, index2):
        for c, col in enumerate(_columns(seqs)):
            if c >= AVITI_ADVISORY_FIRST_CYCLES:
                break
            if len(col) < MIN_ASSESSABLE_POOL:
                continue
            distinct = len({b for b in col if b != "N"})
            if distinct <= AVITI_ADVISORY_MAX_DISTINCT_BASES:
                advisory.append(f"{read} cycle {c + 1}")
    if advisory:
        return RuleResult(
            "pass",
            "pass (advisory only): low base diversity in the first "
            f"{AVITI_ADVISORY_FIRST_CYCLES} cycles at {'; '.join(advisory)}; "
            "AVITI tolerates low diversity, so this is not a failure [ELE-MET/ELE-LOW].",
        )
    return RuleResult("pass", "AVITI is permissive; no dark-base rule applies [ELE-LOW].")


# ===========================================================================
# Dispatch by vendor/platform key
# ===========================================================================

_RULES = {
    "2channel": evaluate_two_channel,
    "4channel": evaluate_four_channel,
    "aviti": evaluate_aviti,
}


def evaluate(chem_key: str, index1: list[str], index2: list[str] | None) -> RuleResult:
    """Evaluate a pool against the published vendor rule for *chem_key*.

    *chem_key* is the platform key used throughout the corpus
    ("2channel", "4channel", "aviti"), NOT a physical channel count.
    """
    try:
        rule = _RULES[chem_key]
    except KeyError:
        raise ValueError(f"no published rule for chemistry key {chem_key!r}") from None
    return rule(index1, index2)
