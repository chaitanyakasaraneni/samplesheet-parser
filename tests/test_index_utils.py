"""Tests for samplesheet_parser.index_utils."""

import pytest

from samplesheet_parser.index_utils import normalize_index_lengths

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_samples(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Build minimal V1-style sample dicts from (index, index2) pairs."""
    return [
        {"sample_id": f"S{i+1}", "index": idx1, "index2": idx2}
        for i, (idx1, idx2) in enumerate(pairs)
    ]


def _make_v2_samples(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Build minimal V2-style sample dicts from (Index, Index2) pairs."""
    return [
        {"sample_id": f"S{i+1}", "Index": idx1, "Index2": idx2}
        for i, (idx1, idx2) in enumerate(pairs)
    ]


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------

class TestNormalizeEmpty:

    def test_empty_input_returns_empty(self) -> None:
        assert normalize_index_lengths([]) == []


class TestNormalizeTrim:

    def test_trim_i7_to_shortest(self) -> None:
        samples = _make_samples([("ATTACTCG", "TATAGCCT"), ("TCCGGAGAGG", "ATAGAGGC")])
        result = normalize_index_lengths(samples, strategy="trim")
        assert result[0]["index"] == "ATTACTCG"   # already shortest (8)
        assert result[1]["index"] == "TCCGGAGA"   # trimmed from 10 → 8

    def test_trim_i5_to_shortest(self) -> None:
        samples = _make_samples([("ATTACTCG", "TATAGCCT"), ("TCCGGAGA", "ATAGAGGCTA")])
        result = normalize_index_lengths(samples, strategy="trim")
        assert result[0]["index2"] == "TATAGCCT"
        assert result[1]["index2"] == "ATAGAGGC"  # trimmed from 10 → 8

    def test_trim_does_not_modify_originals(self) -> None:
        samples = _make_samples([("ATTACTCG", "TATAGCCT"), ("TCCGGAGAGG", "ATAGAGGCTA")])
        orig_idx = samples[1]["index"]
        normalize_index_lengths(samples, strategy="trim")
        assert samples[1]["index"] == orig_idx  # original unchanged

    def test_trim_uniform_lengths_returns_copies(self) -> None:
        samples = _make_samples([("ATTACTCG", "TATAGCCT"), ("TCCGGAGA", "ATAGAGGC")])
        result = normalize_index_lengths(samples, strategy="trim")
        assert result[0]["index"] == "ATTACTCG"
        assert result[1]["index"] == "TCCGGAGA"
        # Must be new dicts, not the same objects
        assert result[0] is not samples[0]


class TestNormalizePad:

    def test_pad_i7_to_longest(self) -> None:
        samples = _make_samples([("ATTACTCG", "TATAGCCT"), ("TCCGGAGAGG", "ATAGAGGCTA")])
        result = normalize_index_lengths(samples, strategy="pad")
        assert result[0]["index"] == "ATTACTCGNN"  # padded 8 → 10
        assert result[1]["index"] == "TCCGGAGAGG"  # unchanged

    def test_pad_i5_to_longest(self) -> None:
        samples = _make_samples([("ATTACTCG", "TATAGCCT"), ("TCCGGAGA", "ATAGAGGCTA")])
        result = normalize_index_lengths(samples, strategy="pad")
        assert result[0]["index2"] == "TATAGCCTNN"
        assert result[1]["index2"] == "ATAGAGGCTA"

    def test_pad_uses_n_character(self) -> None:
        samples = _make_samples([("ATCG", ""), ("ATCGATCG", "")])
        result = normalize_index_lengths(samples, strategy="pad")
        assert result[0]["index"].endswith("NNNN")


# ---------------------------------------------------------------------------
# V2-style key detection
# ---------------------------------------------------------------------------

class TestKeyDetection:

    def test_detects_v2_keys_automatically(self) -> None:
        samples = _make_v2_samples([("ATTACTCG", "TATAGCCT"), ("TCCGGAGAGG", "ATAGAGGCTA")])
        result = normalize_index_lengths(samples, strategy="trim")
        assert "Index" in result[0]
        assert result[1]["Index"] == "TCCGGAGA"

    def test_explicit_key_override(self) -> None:
        samples = [
            {"sample_id": "S1", "MyIdx": "ATTACTCG"},
            {"sample_id": "S2", "MyIdx": "TCCGGAGAGG"},
        ]
        result = normalize_index_lengths(
            samples, strategy="trim", index1_key="MyIdx", index2_key=""
        )
        assert result[1]["MyIdx"] == "TCCGGAGA"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_invalid_strategy_raises(self) -> None:
        samples = _make_samples([("ATTACTCG", "TATAGCCT")])
        with pytest.raises(ValueError, match="strategy"):
            normalize_index_lengths(samples, strategy="reverse")  # type: ignore[arg-type]

    def test_single_sample_unchanged(self) -> None:
        samples = _make_samples([("ATTACTCG", "TATAGCCT")])
        result = normalize_index_lengths(samples, strategy="trim")
        assert result[0]["index"] == "ATTACTCG"

    def test_samples_without_index2_handled(self) -> None:
        samples = [
            {"sample_id": "S1", "index": "ATTACTCG"},
            {"sample_id": "S2", "index": "TCCGGAGAGG"},
        ]
        result = normalize_index_lengths(samples, strategy="trim")
        assert result[1]["index"] == "TCCGGAGA"
        # No index2 key should not be added
        assert "index2" not in result[0]

    def test_none_index_values_skipped(self) -> None:
        """Samples with None index values are copied unchanged."""
        samples: list[dict[str, str | None]] = [
            {"sample_id": "S1", "index": None, "index2": None},
            {"sample_id": "S2", "index": "TCCGGAGAGG", "index2": None},
        ]
        result = normalize_index_lengths(samples, strategy="trim")  # type: ignore[arg-type]
        assert result[0]["index"] is None

    def test_return_value_is_new_list(self) -> None:
        samples = _make_samples([("ATTACTCG", "TATAGCCT")])
        result = normalize_index_lengths(samples)
        assert result is not samples

    def test_key_with_all_none_values_skips_to_real_key(self) -> None:
        """_detect_key must prefer the key that has non-empty values.

        If 'index' is present but all None and 'Index' has real sequences,
        auto-detection should pick 'Index', not 'index'.
        """
        samples = [
            {"sample_id": "S1", "index": None, "Index": "ATTACTCG"},
            {"sample_id": "S2", "index": None, "Index": "TCCGGAGAGG"},
        ]
        result = normalize_index_lengths(samples, strategy="trim")
        # 'Index' was correctly detected — trimmed to 8
        assert result[1]["Index"] == "TCCGGAGA"
        # 'index' key untouched (all None)
        assert result[0]["index"] is None
