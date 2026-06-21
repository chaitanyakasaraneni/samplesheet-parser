"""Tests for the published-vendor color-balance rules (eval/reference_rules.py).

These assert the rules match the **cited vendor guidance**, independent of the
library under test. Hand-constructed pools with known vendor-rule outcomes.

Note on the all-G pool: the task brief's illustrative expectation listed an
all-G pool as "4-channel pass". The cited Illumina four-channel rule, however,
requires *both* lasers ({G,T} AND {A,C}) at every cycle, and an all-G cycle has
no {A,C} signal -> it fails the four-channel rule (the red laser is dark), not
just the two-channel rule. We follow the cited rule faithfully and assert the
rule's actual outcome rather than the brief's parenthetical, and flag this in
eval/FINDINGS.md rather than fudging it.
"""

from __future__ import annotations

from eval.reference_rules import (
    evaluate_aviti,
    evaluate_four_channel,
    evaluate_two_channel,
)

# ---------------------------------------------------------------------------
# Hand-built pools (length 4, n=4) with known column properties
# ---------------------------------------------------------------------------

# Every column is a full ACGT rotation -> all lasers/channels represented.
CLEAN = ["ACGT", "CGTA", "GTAC", "TACG"]

# Cycles 1-2 are all-G across the pool; cycles 3-4 are diverse.
ALL_G_FIRST2 = ["GGAT", "GGCA", "GGTC", "GGAG"]

# Cycle 1 uses only {G, T} -> green channel present, red/{A,C} absent.
# No all-G cycle anywhere; cycles 2-4 carry both channels/lasers.
GREEN_ONLY_CYCLE = ["GACT", "TCAG", "GATC", "TCGA"]

# Cycle 1 is all-A (single base -> low diversity) within the first 5 cycles;
# rest diverse. (A lights both 2-channel channels, so this is NOT a 2-channel
# dark cycle -- it is only an AVITI low-diversity advisory case.)
AVITI_LOWDIV_FIRST = ["ACGT", "AGTA", "ATAC", "AACG"]


# ---------------------------------------------------------------------------
# Two-channel rule (NextSeq/MiniSeq/NovaSeq 6000)
# ---------------------------------------------------------------------------


def test_two_channel_clean_passes():
    r = evaluate_two_channel(CLEAN, None)
    assert r.verdict == "pass"


def test_two_channel_all_G_fails_with_registration_note():
    r = evaluate_two_channel(ALL_G_FIRST2, None)
    assert r.verdict == "fail"
    assert "all-G" in r.reason
    # The all-G is in the first two cycles -> registration rationale cited.
    assert "registration" in r.reason


def test_two_channel_single_channel_cycle_is_weak_not_fail():
    # Illumina rule: "signal in at least one channel" -> a green-only cycle is
    # WEAK but PASSES. (The library/first-principles label treats this as a
    # failure; that divergence is the reportable finding, not tested here.)
    r = evaluate_two_channel(GREEN_ONLY_CYCLE, None)
    assert r.verdict == "pass"
    assert "weak" in r.reason.lower()


# ---------------------------------------------------------------------------
# Four-channel rule (MiSeq/HiSeq)
# ---------------------------------------------------------------------------


def test_four_channel_clean_passes():
    r = evaluate_four_channel(CLEAN, None)
    assert r.verdict == "pass"


def test_four_channel_all_G_fails_missing_red_laser():
    # All-G cycle has {G,T} (green laser) but no {A,C} (red laser) -> fail.
    # This is the cited-rule outcome; see module docstring re: the brief.
    r = evaluate_four_channel(ALL_G_FIRST2, None)
    assert r.verdict == "fail"
    assert "red" in r.reason


def test_four_channel_single_laser_cycle_fails():
    # A {G,T}-only cycle is diverse but the red {A,C} laser is unrepresented.
    r = evaluate_four_channel(GREEN_ONLY_CYCLE, None)
    assert r.verdict == "fail"
    assert "laser" in r.reason


# ---------------------------------------------------------------------------
# AVITI rule (Element, permissive)
# ---------------------------------------------------------------------------


def test_aviti_clean_passes_no_advisory():
    r = evaluate_aviti(CLEAN, None)
    assert r.verdict == "pass"
    assert "advisory" not in r.reason.lower()


def test_aviti_all_G_passes_never_fails():
    # AVITI has no dark-base failure mode; an all-G cycle must NOT fail.
    r = evaluate_aviti(ALL_G_FIRST2, None)
    assert r.verdict == "pass"


def test_aviti_low_diversity_first_cycles_is_advisory_not_fail():
    r = evaluate_aviti(AVITI_LOWDIV_FIRST, None)
    assert r.verdict == "pass"  # never a hard fail
    assert "advisory" in r.reason.lower()


def test_aviti_low_diversity_after_window_not_flagged():
    # Low diversity only AFTER the first-5 window -> no advisory.
    # Diverse first 5 cycles, all-A at cycle 6.
    pool = ["ACGTAA", "CGTACA", "GTACGA", "TACGTA"]
    r = evaluate_aviti(pool, None)
    assert r.verdict == "pass"
    assert "advisory" not in r.reason.lower()


# ---------------------------------------------------------------------------
# Dual-index reads are checked too
# ---------------------------------------------------------------------------


def test_two_channel_checks_index2():
    # index1 clean, index2 has an all-G cycle -> fail from index2.
    r = evaluate_two_channel(CLEAN, ALL_G_FIRST2)
    assert r.verdict == "fail"
    assert "index2" in r.reason
