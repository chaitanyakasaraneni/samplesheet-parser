"""Tests for chemistry models and colour-balance analysis."""

from __future__ import annotations

import pytest

from samplesheet_parser.chemistry import (
    Chemistry,
    ColorBalanceMode,
    analyze_color_balance,
    chemistry_for_instrument,
)

CONSERVATIVE = ColorBalanceMode.CONSERVATIVE
VENDOR_FAITHFUL = ColorBalanceMode.VENDOR_FAITHFUL


class TestChemistryForInstrument:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("MiSeq", Chemistry.FOUR_CHANNEL),
            ("HiSeq 2500", Chemistry.FOUR_CHANNEL),
            ("NextSeq 550", Chemistry.TWO_CHANNEL),
            ("NextSeq1000/2000", Chemistry.TWO_CHANNEL),
            ("NovaSeq X Plus", Chemistry.TWO_CHANNEL),
            ("NovaSeqXSeries", Chemistry.TWO_CHANNEL),
            ("NovaSeq6000", Chemistry.TWO_CHANNEL),
            ("iSeq 100", Chemistry.ONE_CHANNEL),
            ("AVITI", Chemistry.AVIDITY),
            ("Element AVITI", Chemistry.AVIDITY),
        ],
    )
    def test_known_instruments(self, name: str, expected: Chemistry) -> None:
        assert chemistry_for_instrument(name) is expected

    def test_unknown_instrument_returns_none(self) -> None:
        assert chemistry_for_instrument("SomeFutureSeq") is None

    def test_empty_returns_none(self) -> None:
        assert chemistry_for_instrument(None) is None
        assert chemistry_for_instrument("") is None


class TestTwoChannelColorBalance:
    def test_dark_cycle_all_g_detected(self) -> None:
        # Every sample reads G at cycle 1 -> dark in both channels.
        report = analyze_color_balance(
            ["GAAA", "GCCC", "GTTT", "GACG"],
            chemistry=Chemistry.TWO_CHANNEL,
        )
        assert not report.is_balanced
        dark = [c for c in report.dark_cycles if c.cycle == 1]
        assert dark and dark[0].red_fraction == 0.0 and dark[0].green_fraction == 0.0

    def test_single_channel_cycle_is_weak_in_vendor_faithful(self) -> None:
        # Cycle 1 is all G/T -> green present, red absent. Illumina's hard
        # minimum is "at least one channel", so vendor_faithful treats this as
        # a weak warning (pass), not a failure.
        report = analyze_color_balance(
            ["GAAA", "TCCC", "GTTT", "TACG"],
            chemistry=Chemistry.TWO_CHANNEL,
        )
        assert report.is_balanced  # no dark/failing cycle
        weak = [c for c in report.weak_cycles if c.cycle == 1]
        assert weak and weak[0].red_fraction == 0.0 and weak[0].green_fraction > 0.0

    def test_single_channel_cycle_is_dark_in_conservative(self) -> None:
        report = analyze_color_balance(
            ["GAAA", "TCCC", "GTTT", "TACG"],
            chemistry=Chemistry.TWO_CHANNEL,
            mode=CONSERVATIVE,
        )
        assert not report.is_balanced
        dark = [c for c in report.dark_cycles if c.cycle == 1]
        assert dark and dark[0].red_fraction == 0.0

    def test_balanced_pool_has_no_findings(self) -> None:
        report = analyze_color_balance(
            ["ACGT", "CAGT", "TGCA", "GTAC"],
            chemistry=Chemistry.TWO_CHANNEL,
        )
        assert report.is_balanced

    def test_weak_channel_warns(self) -> None:
        # 9 samples carry no red base at cycle 1, 1 sample does -> 10% red.
        # Below the default 10%? exactly 10% (1/10) is not below, so push to 1/11.
        seqs = ["G"] * 10 + ["A"]
        report = analyze_color_balance(seqs, chemistry=Chemistry.TWO_CHANNEL)
        weak = [c for c in report.weak_cycles if c.cycle == 1]
        assert weak
        assert weak[0].red_fraction == pytest.approx(1 / 11)

    def test_single_sample_pool_not_flagged(self) -> None:
        # A lone sample cannot be "balanced"; should produce no dark/weak cycles.
        report = analyze_color_balance(["GGGG"], chemistry=Chemistry.TWO_CHANNEL)
        assert report.is_balanced

    def test_index2_is_scored(self) -> None:
        report = analyze_color_balance(
            ["ACGT", "CAGT"],
            ["GGGG", "GGGG"],  # index2 entirely dark
            chemistry=Chemistry.TWO_CHANNEL,
        )
        assert any(c.read == "index2" for c in report.dark_cycles)


class TestFourChannelColorBalance:
    # Illumina 4-channel: green laser {G,T}, red laser {A,C}; each cycle needs
    # both. Both modes (this is a correctness rule, not a strictness choice).

    def test_all_g_cycle_fails_red_laser_absent(self) -> None:
        # All-G cycle: green laser present (G), red laser {A,C} absent -> fail.
        for mode in (VENDOR_FAITHFUL, CONSERVATIVE):
            report = analyze_color_balance(
                ["GAAA", "GCCC", "GTTT"],
                chemistry=Chemistry.FOUR_CHANNEL,
                mode=mode,
            )
            dark = [c for c in report.dark_cycles if c.cycle == 1]
            assert dark, mode
            assert dark[0].red_fraction == 0.0

    def test_gt_only_cycle_fails_red_laser_absent(self) -> None:
        # Diverse ({G,T}) but the red {A,C} laser is dark -> fail (the bug fix).
        report = analyze_color_balance(
            ["GACT", "TCAG", "GATC", "TCGA"],
            chemistry=Chemistry.FOUR_CHANNEL,
        )
        dark = [c for c in report.dark_cycles if c.cycle == 1]
        assert dark and dark[0].red_fraction == 0.0

    def test_diverse_pool_passes(self) -> None:
        report = analyze_color_balance(
            ["ACGT", "CAGT", "TGCA"],
            chemistry=Chemistry.FOUR_CHANNEL,
        )
        assert report.is_balanced


class TestAvidityColorBalance:
    # Element AVITI: no dark base, low diversity tolerated.

    def test_low_diversity_is_advisory_in_vendor_faithful(self) -> None:
        # All-G cycle 1: an advisory only (never a failure) on AVITI.
        report = analyze_color_balance(
            ["GAAA", "GCCC", "GTTT"],
            chemistry=Chemistry.AVIDITY,
        )
        assert report.is_balanced  # not a failure
        assert report.dark_cycles == []
        assert [c.cycle for c in report.advisory_cycles] == [1]

    def test_low_diversity_fails_in_conservative(self) -> None:
        report = analyze_color_balance(
            ["GAAA", "GCCC", "GTTT"],
            chemistry=Chemistry.AVIDITY,
            mode=CONSERVATIVE,
        )
        assert not report.is_balanced
        assert [c.cycle for c in report.dark_cycles] == [1]

    def test_gt_only_cycle_passes_on_avidity(self) -> None:
        # A {G,T}-only cycle fails Illumina 4-channel (red laser) but is fine on
        # avidity (each base has its own dye; diversity is present).
        report = analyze_color_balance(
            ["GACT", "TCAG", "GATC", "TCGA"],
            chemistry=Chemistry.AVIDITY,
        )
        assert report.is_balanced
        assert report.advisory_cycles == []
