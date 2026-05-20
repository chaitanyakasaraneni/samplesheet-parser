"""Tests for samplesheet_parser.instruments — workflow detection & i5 RC."""

# mypy: disable-error-code="misc"
# `@pytest.fixture` and `@pytest.mark.parametrize` are typed as `Any` when
# pytest's type stubs aren't installed in the pre-commit env, which makes
# every decorated function "untyped" under strict mypy. The functions
# themselves are fully annotated.

from __future__ import annotations

import pytest

from samplesheet_parser.instruments import (
    AMBIGUOUS_INSTRUMENTS,
    WORKFLOW_A_INSTRUMENTS,
    WORKFLOW_B_INSTRUMENTS,
    Workflow,
    detect_workflow,
    parse_workflow,
    reverse_complement,
)


class TestReverseComplement:

    @pytest.mark.parametrize(
        "seq, expected",
        [
            ("ATCG", "CGAT"),
            ("TATAGCCT", "AGGCTATA"),
            ("ATTACTCG", "CGAGTAAT"),
            ("", ""),
            ("A", "T"),
            ("N", "N"),
            ("ACGTN", "NACGT"),
            ("acgt", "acgt"),  # case preserved
        ],
    )
    def test_reverse_complement(self, seq: str, expected: str) -> None:
        assert reverse_complement(seq) == expected

    def test_double_rc_is_identity(self) -> None:
        for seq in ("ATTACTCG", "TATAGCCT", "GCATGCTA", "AAGGTTCC"):
            assert reverse_complement(reverse_complement(seq)) == seq


class TestDetectWorkflow:

    @pytest.mark.parametrize("name", ["MiSeq", "miseq", "MISEQ", "HiSeq 2500", "HiSeq2000"])
    def test_workflow_a_instruments(self, name: str) -> None:
        assert detect_workflow(name) == Workflow.A

    @pytest.mark.parametrize(
        "name",
        [
            "NovaSeq X Plus",
            "NovaSeqXPlus",
            "NovaSeq X Series",
            "NovaSeqXSeries",
            "NextSeq 500",
            "NextSeq500",
            "NextSeq 550",
            "NextSeq 1000",
            "NextSeq2000",
            "NextSeq1000/2000",  # combined V2 InstrumentPlatform value
            "NextSeq 1000/2000",
            "iSeq",
            "iSeq 100",
            "MiniSeq",
            "HiSeq 3000",
            "HiSeq4000",
        ],
    )
    def test_workflow_b_instruments(self, name: str) -> None:
        assert detect_workflow(name) == Workflow.B

    def test_empty_returns_none(self) -> None:
        assert detect_workflow("") is None
        assert detect_workflow(None) is None

    @pytest.mark.parametrize("name", ["NovaSeq", "NovaSeq 6000", "NovaSeq6000"])
    def test_ambiguous_novaseq_returns_none(self, name: str) -> None:
        """NovaSeq 6000 is chemistry-dependent and must require an explicit override."""
        assert detect_workflow(name) is None

    @pytest.mark.parametrize("name", ["Unknown", "MagicSeq", "PacBio"])
    def test_unknown_instrument_returns_none(self, name: str) -> None:
        assert detect_workflow(name) is None

    def test_workflow_a_b_sets_are_disjoint(self) -> None:
        assert WORKFLOW_A_INSTRUMENTS.isdisjoint(WORKFLOW_B_INSTRUMENTS)

    def test_ambiguous_does_not_appear_in_a_or_b(self) -> None:
        assert AMBIGUOUS_INSTRUMENTS.isdisjoint(WORKFLOW_A_INSTRUMENTS)
        assert AMBIGUOUS_INSTRUMENTS.isdisjoint(WORKFLOW_B_INSTRUMENTS)


class TestParseWorkflow:

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("a", Workflow.A),
            ("A", Workflow.A),
            (" a ", Workflow.A),
            ("b", Workflow.B),
            ("B", Workflow.B),
            ("workflow_a", Workflow.A),
            ("workflow_b", Workflow.B),
        ],
    )
    def test_parse_valid(self, value: str, expected: Workflow) -> None:
        assert parse_workflow(value) == expected

    def test_parse_none(self) -> None:
        assert parse_workflow(None) is None
        assert parse_workflow("") is None

    def test_parse_enum_passthrough(self) -> None:
        assert parse_workflow(Workflow.A) == Workflow.A
        assert parse_workflow(Workflow.B) == Workflow.B

    @pytest.mark.parametrize("bad", ["c", "x", "1", "z"])
    def test_parse_invalid_raises(self, bad: str) -> None:
        with pytest.raises(ValueError, match="Unknown workflow"):
            parse_workflow(bad)
