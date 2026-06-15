"""Tests for chemistry models and colour-balance analysis."""

from __future__ import annotations

import pytest

from samplesheet_parser.chemistry import (
    Chemistry,
    analyze_color_balance,
    chemistry_for_instrument,
)


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
            ("AVITI", Chemistry.FOUR_CHANNEL),
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

    def test_no_red_signal_is_dark(self) -> None:
        # Cycle 1 is all G/T -> green present, red absent.
        report = analyze_color_balance(
            ["GAAA", "TCCC", "GTTT", "TACG"],
            chemistry=Chemistry.TWO_CHANNEL,
        )
        dark = [c for c in report.dark_cycles if c.cycle == 1]
        assert dark
        assert dark[0].red_fraction == 0.0
        assert dark[0].green_fraction > 0.0

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
    def test_no_dark_cycles_on_four_channel(self) -> None:
        # All-G cycle is fine on 4-channel (G has its own dye), but it is
        # zero-diversity so it should be a weak cycle, never a dark error.
        report = analyze_color_balance(
            ["GAAA", "GCCC", "GTTT"],
            chemistry=Chemistry.FOUR_CHANNEL,
        )
        assert report.dark_cycles == []
        weak = [c for c in report.weak_cycles if c.cycle == 1]
        assert weak and weak[0].distinct_bases == 1

    def test_diverse_pool_passes(self) -> None:
        report = analyze_color_balance(
            ["ACGT", "CAGT", "TGCA"],
            chemistry=Chemistry.FOUR_CHANNEL,
        )
        assert report.is_balanced
