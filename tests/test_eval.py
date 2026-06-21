"""Tests for the synthetic corpus generator and evaluation harness (eval/).

Covers:
* first-principles label correctness on hand-constructed pools,
* agreement between the generator's definitional labels and the library's
  own color-balance verdict (the corpus's correctness guarantee),
* a tiny end-to-end smoke corpus: generate -> round-trip parse -> evaluate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.generate_corpus import (
    CHEMISTRY_INSTRUMENTS,
    LogicalPool,
    generate,
    label_definitional,
    label_reference,
)
from eval.run_eval import evaluate, tool_label
from samplesheet_parser.chemistry import (
    Chemistry,
    ColorBalanceMode,
    chemistry_for_instrument,
)

FOUR = Chemistry.FOUR_CHANNEL
TWO = Chemistry.TWO_CHANNEL
AVIDITY = Chemistry.AVIDITY


def _pool(i1, i2=None, cls="hand", pool_id="hand"):
    return LogicalPool(
        pool_id=pool_id,
        pool_class=cls,
        tier=len(i1),
        index1=list(i1),
        index2=list(i2) if i2 else None,
        index_len="x",
    )


# ---------------------------------------------------------------------------
# Definitional label correctness
# ---------------------------------------------------------------------------


def test_clean_pool_passes_all_chemistries():
    # Fully diverse columns: ACGT rotation.
    pool = _pool(["ACGT", "CGTA", "GTAC", "TACG"])
    assert label_definitional(pool, FOUR) == "pass"
    assert label_definitional(pool, TWO) == "pass"


def test_all_G_cycle_is_universal_fail():
    # Cycle 1 is all-G: dark on 2-channel, zero-diversity on 4-channel.
    pool = _pool(["GACT", "GCTA", "GTAC", "GAGT"])
    assert label_definitional(pool, FOUR) == "fail"  # single base
    assert label_definitional(pool, TWO) == "fail"  # no red, no green


def test_GT_only_cycle_fails_2channel_and_4channel_passes_avidity():
    # Cycle 1 uses only G/T. On 2-channel the red channel is absent (fail); on
    # 4-channel the red {A,C} laser is absent (fail, the bug fix); on avidity
    # each base has its own dye so diversity is enough (pass).
    pool = _pool(["GACT", "TCTA", "GTAC", "TAGT"])
    assert label_definitional(pool, FOUR) == "fail"  # red laser dark
    assert label_definitional(pool, TWO) == "fail"  # red channel dark
    assert label_definitional(pool, AVIDITY) == "pass"  # diversity present


def test_GC_only_cycle_fails_2channel_passes_4channel():
    # Cycle 1 uses only G/C -> green channel absent.
    pool = _pool(["GACT", "CCTA", "GTAC", "CAGT"])
    assert label_definitional(pool, FOUR) == "pass"
    assert label_definitional(pool, TWO) == "fail"  # green == 0


def test_single_sample_is_never_failed():
    # pool < 2 is not assessable; matches the library's guard.
    pool = _pool(["GGGG"])
    assert label_definitional(pool, FOUR) == "pass"
    assert label_definitional(pool, TWO) == "pass"


def test_aviti_uses_avidity_rules():
    # AVITI resolves to its own avidity chemistry (not Illumina 4-channel); a
    # G/T-only cycle PASSES on avidity (no laser-pair constraint), unlike both
    # Illumina 2-channel and 4-channel.
    aviti = chemistry_for_instrument(CHEMISTRY_INSTRUMENTS["aviti"])
    assert aviti is AVIDITY
    pool = _pool(["GACT", "TCTA", "GTAC", "TAGT"])
    assert label_definitional(pool, aviti) == "pass"


def test_reference_label_dispatches_by_vendor_key_and_diverges_from_definitional():
    # label_reference now encodes published vendor rules and is keyed by
    # platform string, not by Chemistry. It legitimately diverges from the
    # first-principles definitional label in known places.
    #
    # A cycle with only G/T (red absent): first principles FAILS on 2-channel
    # (both channels required), but Illumina's published "at least one channel"
    # rule PASSES it (weak). This divergence is the reportable finding.
    gt_pool = _pool(["GACT", "TCTA", "GTAC", "TAGT"])
    assert label_definitional(gt_pool, TWO) == "fail"
    assert label_reference(gt_pool, "2channel") == "pass"

    # A clean pool agrees under both labelings.
    clean = _pool(["ACGT", "CGTA", "GTAC", "TACG"])
    assert label_definitional(clean, TWO) == "pass"
    assert label_reference(clean, "2channel") == "pass"

    # AVITI is permissive: an all-G cycle is a hard fail under first principles
    # (zero diversity) but only an advisory (pass) under Element's guidance.
    allg = _pool(["GACT", "GCTA", "GTAC", "GAGT"])
    assert label_definitional(allg, FOUR) == "fail"
    assert label_reference(allg, "aviti") == "pass"


# ---------------------------------------------------------------------------
# Generator definitional labels agree with the library under test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("chem_key", list(CHEMISTRY_INSTRUMENTS))
def test_tool_agrees_with_definitional_on_hand_pools(chem_key):
    chem = chemistry_for_instrument(CHEMISTRY_INSTRUMENTS[chem_key])
    cases = [
        _pool(["ACGT", "CGTA", "GTAC", "TACG"]),
        _pool(["GACT", "GCTA", "GTAC", "GAGT"]),
        _pool(["GACT", "TCTA", "GTAC", "TAGT"]),
        _pool(["GACT", "CCTA", "GTAC", "CAGT"]),
    ]
    # definitional encodes the strict model, which the CONSERVATIVE tool mode
    # implements -- so they must agree exactly.
    for pool in cases:
        expected = label_definitional(pool, chem)
        got = tool_label(
            pool.index1, pool.index2 or [], chem_key, ColorBalanceMode.CONSERVATIVE
        ).label
        assert got == expected, f"{pool.index1} under {chem_key}"


# ---------------------------------------------------------------------------
# End-to-end smoke corpus
# ---------------------------------------------------------------------------


def test_smoke_corpus_generate_and_evaluate(tmp_path: Path):
    corpus = tmp_path / "corpus"
    manifest = generate(corpus, master_seed=123, tiers=(8,))
    assert manifest.exists()
    assert (corpus / "seed.txt").read_text().strip() == "123"
    # all three format dirs populated
    assert list((corpus / "iem_v1").glob("*.csv"))
    assert list((corpus / "bclconvert_v2").glob("*.csv"))
    assert list((corpus / "aviti").glob("*.csv"))

    res = evaluate(corpus, tmp_path / "results")
    # Cross-format round-trip must be exact.
    assert res.roundtrip_failures == []
    # Library correctness: the CONSERVATIVE tool must match the strict
    # first-principles definitional label exactly (no implementation bug).
    for (comparison, _chem), c in res.confusion.items():
        if comparison == "tool_conservative_vs_definitional":
            assert c.fp == 0 and c.fn == 0
    # Vendor_faithful tool should AGREE with published guidance (the goal of
    # this change): zero vendor_faithful tool-vs-reference disagreements.
    assert res.disagree_vs_reference["vendor_faithful"] == 0
    # Conservative is stricter than vendor minimums, so it disagrees with the
    # permissive published rule -- surfaced, not hidden.
    assert res.disagree_vs_reference["conservative"] > 0
    # At least one pool still flips verdict across chemistries.
    assert len(res.cross_vendor) > 0


def test_determinism_same_seed_same_corpus(tmp_path: Path):
    import csv

    m1 = generate(tmp_path / "a", master_seed=999, tiers=(8,))
    m2 = generate(tmp_path / "b", master_seed=999, tiers=(8,))

    def _non_path(manifest: Path):
        with open(manifest) as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            for k in ("path_iem_v1", "path_bclconvert_v2", "path_aviti"):
                r.pop(k)
        return rows

    # Everything except the output-dir-dependent paths must be identical.
    assert _non_path(m1) == _non_path(m2)
    # And the actual serialized files must be byte-identical across runs.
    f1 = (tmp_path / "a" / "iem_v1").glob("*.csv")
    for p1 in sorted(f1):
        p2 = tmp_path / "b" / "iem_v1" / p1.name
        assert p1.read_text() == p2.read_text()
