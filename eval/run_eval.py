"""Evaluation harness: score the corpus with the repo's real color-balance validator.

For every pool in ``corpus/manifest.csv`` this:

1. Parses all three serialized formats back through the real
   :class:`SampleSheetFactory` (round-trip correctness: the three formats must
   yield identical index sets).
2. Runs the repo's color-balance analysis under each chemistry
   (4-channel, 2-channel, AVITI) to obtain ``label_tool``.
3. Compares ``label_tool`` against both ground-truth labelings from the
   manifest (definitional and reference).

Outputs (under ``eval/results/``):

* ``per_pool.csv``        -- every (pool, chemistry) verdict and labels.
* ``metrics.csv``         -- precision/recall/F1 + confusion counts, per
                             chemistry, for tool-vs-definitional and
                             tool-vs-reference.
* ``cross_vendor.csv``    -- pools whose verdict flips across chemistries.
* ``runtime.csv``         -- analysis runtime vs tier size.
* ``summary.md``          -- human-readable summary.
* ``cross_vendor.png/.pdf`` -- the cross-vendor flip figure.

Run: ``python -m eval.run_eval``  (after ``python -m eval.generate_corpus``)
"""

from __future__ import annotations

import argparse
import csv
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from eval import reference_rules
from eval.generate_corpus import CHEMISTRY_INSTRUMENTS
from samplesheet_parser import SampleSheetFactory
from samplesheet_parser.chemistry import (
    ColorBalanceMode,
    analyze_color_balance,
    chemistry_for_instrument,
)

# Positive class for precision/recall: we are *detecting failures*.
POSITIVE = "fail"
CHEMS = list(CHEMISTRY_INSTRUMENTS)  # ["4channel", "2channel", "aviti"]
MODES = [ColorBalanceMode.VENDOR_FAITHFUL, ColorBalanceMode.CONSERVATIVE]


# ===========================================================================
# Round-trip parsing
# ===========================================================================


def _indexes_from_sheet(path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Parse a sheet via the factory and return (index1, index2) tuples."""
    sheet = SampleSheetFactory().create_parser(str(path), parse=True)
    samples = sheet.samples()
    i1 = tuple((s.get("index") or "").upper() for s in samples)
    i2 = tuple((s.get("index2") or "").upper() for s in samples)
    if not any(i2):
        i2 = tuple()
    return i1, i2


def _roundtrip_indexes(
    row: dict[str, str], corpus_parent: Path
) -> tuple[list[str], list[str], bool]:
    """Parse all three formats; return canonical indexes and round-trip agreement."""
    per_format: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for key in ("path_iem_v1", "path_bclconvert_v2", "path_aviti"):
        i1, i2 = _indexes_from_sheet(corpus_parent / row[key])
        per_format[key] = (i1, i2)

    values = list(per_format.values())
    ok = all(v == values[0] for v in values)
    i1, i2 = values[0]
    return list(i1), list(i2), ok


# ===========================================================================
# Tool labeling
# ===========================================================================


@dataclass
class ToolVerdict:
    label: str  # "pass" / "fail"
    n_dark: int
    n_weak: int
    seconds: float


def tool_label(
    index1: list[str], index2: list[str], chem_key: str, mode: ColorBalanceMode
) -> ToolVerdict:
    """Run the repo's analyze_color_balance in *mode* and derive a verdict."""
    chemistry = chemistry_for_instrument(CHEMISTRY_INSTRUMENTS[chem_key])
    assert chemistry is not None, f"unknown instrument for {chem_key}"
    idx2 = index2 if index2 else None
    t0 = time.perf_counter()
    report = analyze_color_balance(index1, idx2, chemistry=chemistry, mode=mode)
    elapsed = time.perf_counter() - t0
    label = POSITIVE if not report.is_balanced else "pass"
    return ToolVerdict(label, len(report.dark_cycles), len(report.weak_cycles), elapsed)


# ===========================================================================
# Metrics
# ===========================================================================


@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def add(self, pred: str, truth: str) -> None:
        if pred == POSITIVE and truth == POSITIVE:
            self.tp += 1
        elif pred == POSITIVE and truth != POSITIVE:
            self.fp += 1
        elif pred != POSITIVE and truth != POSITIVE:
            self.tn += 1
        else:
            self.fn += 1

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else float("nan")

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else float("nan")

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        if p != p or r != r or (p + r) == 0:
            return float("nan")
        return 2 * p * r / (p + r)


def _fmt(x: float) -> str:
    return "n/a" if x != x else f"{x:.3f}"


# ===========================================================================
# Main evaluation
# ===========================================================================


@dataclass
class EvalResult:
    per_pool: list[dict[str, object]]
    runtime: list[dict[str, object]]
    confusion: dict[tuple[str, str], Confusion]
    roundtrip_failures: list[str]
    disagreements: list[dict[str, object]]
    cross_vendor: list[dict[str, object]]
    n_pools: int
    # tool-vs-reference disagreement counts per mode (the headline before/after).
    disagree_vs_reference: dict[str, int]


def evaluate(corpus_dir: Path, results_dir: Path) -> EvalResult:
    manifest = corpus_dir / "manifest.csv"
    if not manifest.exists():
        raise FileNotFoundError(
            f"{manifest} not found. Run `python -m eval.generate_corpus` first."
        )
    corpus_parent = corpus_dir.parent
    results_dir.mkdir(parents=True, exist_ok=True)

    with open(manifest, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    per_pool_rows: list[dict[str, object]] = []
    runtime_rows: list[dict[str, object]] = []
    # confusion[(reference_kind, chem)] -> Confusion
    conf: dict[tuple[str, str], Confusion] = defaultdict(Confusion)
    roundtrip_failures: list[str] = []
    disagreements: list[dict[str, object]] = []
    cross_vendor: list[dict[str, object]] = []

    for row in rows:
        i1, i2, rt_ok = _roundtrip_indexes(row, corpus_parent)
        if not rt_ok:
            roundtrip_failures.append(row["pool_id"])

    disagree_vs_reference: dict[str, int] = {m.value: 0 for m in MODES}

    for row in rows:
        i1, i2, rt_ok = _roundtrip_indexes(row, corpus_parent)
        if not rt_ok:
            roundtrip_failures.append(row["pool_id"])

        vf_labels: dict[str, str] = {}
        for chem in CHEMS:
            def_lbl = row[f"def_{chem}"]
            ref_lbl = row[f"ref_{chem}"]
            rr = reference_rules.evaluate(chem, i1, i2)
            vf = tool_label(i1, i2, chem, ColorBalanceMode.VENDOR_FAITHFUL)
            cons = tool_label(i1, i2, chem, ColorBalanceMode.CONSERVATIVE)
            vf_labels[chem] = vf.label

            # Three headline comparisons (positive class = "fail"):
            #   vendor_faithful tool vs published vendor rule  (should agree)
            #   conservative tool vs strict first-principles    (should agree)
            #   first-principles vs published vendor rule        (the real gap)
            conf[("tool_vendor_faithful_vs_reference", chem)].add(vf.label, ref_lbl)
            conf[("tool_conservative_vs_definitional", chem)].add(cons.label, def_lbl)
            conf[("definitional_vs_reference", chem)].add(def_lbl, ref_lbl)

            per_pool_rows.append(
                {
                    "pool_id": row["pool_id"],
                    "pool_class": row["pool_class"],
                    "tier": row["tier"],
                    "chemistry": chem,
                    "tool_vendor_faithful": vf.label,
                    "tool_conservative": cons.label,
                    "label_definitional": def_lbl,
                    "label_reference": ref_lbl,
                    "vf_vs_ref": "agree" if vf.label == ref_lbl else "DISAGREE",
                    "cons_vs_def": "agree" if cons.label == def_lbl else "DISAGREE",
                    "def_vs_ref": "agree" if def_lbl == ref_lbl else "DISAGREE",
                    "reference_reason": rr.reason,
                    "roundtrip_ok": rt_ok,
                }
            )
            runtime_rows.append(
                {
                    "pool_id": row["pool_id"],
                    "tier": row["tier"],
                    "chemistry": chem,
                    "seconds": f"{vf.seconds:.6f}",
                }
            )

            # Disagreements per mode: tool(mode) vs the published vendor rule.
            for mode, verdict in (
                (ColorBalanceMode.VENDOR_FAITHFUL, vf),
                (ColorBalanceMode.CONSERVATIVE, cons),
            ):
                if verdict.label != ref_lbl:
                    disagree_vs_reference[mode.value] += 1
                    disagreements.append(
                        {
                            "pool_id": row["pool_id"],
                            "pool_class": row["pool_class"],
                            "chemistry": chem,
                            "mode": mode.value,
                            "label_tool": verdict.label,
                            "label_definitional": def_lbl,
                            "label_reference": ref_lbl,
                            "reference_reason": rr.reason,
                            "tool_detail": f"dark={verdict.n_dark} weak={verdict.n_weak}",
                        }
                    )

        # Cross-vendor flip (default vendor_faithful verdicts) across chemistries.
        if len(set(vf_labels.values())) > 1:
            cross_vendor.append(
                {
                    "pool_id": row["pool_id"],
                    "pool_class": row["pool_class"],
                    "tier": row["tier"],
                    **{f"verdict_{c}": vf_labels[c] for c in CHEMS},
                }
            )

    return EvalResult(
        per_pool=per_pool_rows,
        runtime=runtime_rows,
        confusion=conf,
        roundtrip_failures=roundtrip_failures,
        disagreements=disagreements,
        cross_vendor=cross_vendor,
        n_pools=len(rows),
        disagree_vs_reference=disagree_vs_reference,
    )


# ===========================================================================
# Output writers
# ===========================================================================


def _write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_outputs(res: EvalResult, results_dir: Path) -> None:
    # per_pool.csv
    if res.per_pool:
        _write_csv(results_dir / "per_pool.csv", res.per_pool, list(res.per_pool[0]))
    # runtime.csv
    if res.runtime:
        _write_csv(results_dir / "runtime.csv", res.runtime, list(res.runtime[0]))
    # cross_vendor.csv
    cv_fields = ["pool_id", "pool_class", "tier"] + [f"verdict_{c}" for c in CHEMS]
    _write_csv(results_dir / "cross_vendor.csv", res.cross_vendor, cv_fields)

    # metrics.csv -- three comparisons x chemistry.
    metric_rows = []
    for (comparison, chem), c in sorted(res.confusion.items()):
        metric_rows.append(
            {
                "comparison": comparison,
                "chemistry": chem,
                "tp": c.tp,
                "fp": c.fp,
                "tn": c.tn,
                "fn": c.fn,
                "precision": _fmt(c.precision),
                "recall": _fmt(c.recall),
                "f1": _fmt(c.f1),
            }
        )
    _write_csv(
        results_dir / "metrics.csv",
        metric_rows,
        ["comparison", "chemistry", "tp", "fp", "tn", "fn", "precision", "recall", "f1"],
    )

    # disagreements.csv -- every (pool, chemistry, mode) where tool != reference.
    dis_fields = [
        "pool_id",
        "pool_class",
        "chemistry",
        "mode",
        "label_tool",
        "label_definitional",
        "label_reference",
        "reference_reason",
        "tool_detail",
    ]
    _write_csv(results_dir / "disagreements.csv", res.disagreements, dis_fields)

    _write_summary(res, metric_rows, results_dir)
    _write_figure(res, results_dir)


def _write_summary(
    res: EvalResult, metric_rows: list[dict[str, object]], results_dir: Path
) -> None:
    lines = ["# Color-balance evaluation summary", ""]
    lines.append(
        f"- Pools evaluated: **{res.n_pools}** (each scored under {len(CHEMS)} chemistries)"
    )
    rt = res.roundtrip_failures
    lines.append(
        f"- Cross-format round-trip: **{'all pass' if not rt else str(len(rt)) + ' FAILED'}**"
        + (f" ({', '.join(rt[:10])}{'...' if len(rt) > 10 else ''})" if rt else "")
    )
    lines.append(f"- Pools that flip verdict across chemistries: **{len(res.cross_vendor)}**")
    lines.append("")

    # Headline before/after: tool-vs-reference disagreements per mode.
    vf = res.disagree_vs_reference.get("vendor_faithful", 0)
    cons = res.disagree_vs_reference.get("conservative", 0)
    lines.append("## Tool vs. published vendor guidance — before/after by mode")
    lines.append("")
    lines.append(
        "Prior single-mode run (before this change): **37** tool-vs-reference "
        "disagreements (see FINDINGS §5)."
    )
    lines.append("")
    lines.append("| mode | tool-vs-reference disagreements |")
    lines.append("|---|---|")
    lines.append(f"| vendor_faithful (default) | **{vf}** |")
    lines.append(f"| conservative | {cons} |")
    lines.append("")

    lines.append("## Comparison metrics (positive class = `fail`)")
    lines.append("")
    lines.append(
        "Three comparisons per chemistry: `tool_vendor_faithful_vs_reference` "
        "(should agree with published guidance), `tool_conservative_vs_definitional` "
        "(implementation matches the strict first-principles model), and "
        "`definitional_vs_reference` (the inherent strict-vs-permissive gap). For "
        "each, the first label is the prediction and the second the truth."
    )
    lines.append("")
    lines.append("| comparison | chemistry | TP | FP | TN | FN | precision | recall | F1 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for m in metric_rows:
        lines.append(
            f"| {m['comparison']} | {m['chemistry']} | {m['tp']} | {m['fp']} | {m['tn']} | "
            f"{m['fn']} | {m['precision']} | {m['recall']} | {m['f1']} |"
        )
    lines.append("")

    # Cross-vendor flip breakdown by class
    by_class: dict[str, int] = defaultdict(int)
    for r in res.cross_vendor:
        by_class[str(r["pool_class"])] += 1
    lines.append("## Cross-vendor verdict flips by pool class")
    lines.append("")
    lines.append(
        "These pools receive a different pass/fail verdict depending on chemistry "
        "— the paper's key result."
    )
    lines.append("")
    if by_class:
        lines.append("| pool class | # flipping pools | example verdicts (4ch / 2ch / aviti) |")
        lines.append("|---|---|---|")
        seen: set[str] = set()
        for r in res.cross_vendor:
            cls = str(r["pool_class"])
            if cls in seen:
                continue
            seen.add(cls)
            lines.append(
                f"| {cls} | {by_class[cls]} | "
                f"{r['verdict_4channel']} / {r['verdict_2channel']} / {r['verdict_aviti']} |"
            )
    else:
        lines.append("_No flips found._")
    lines.append("")

    # Tool-vs-reference disagreements, broken out by mode (falsifiability).
    dis = res.disagreements
    lines.append("## Tool vs. reference disagreements (by mode)")
    lines.append("")
    if not dis:
        lines.append(
            "**Zero disagreements** in either mode — the tool agrees with the "
            "published vendor rule on every (pool, chemistry). (Stated explicitly; "
            "not assumed.)"
        )
        lines.append("")
    else:
        lines.append(
            f"**{len(dis)}** (pool, chemistry, mode) tool-vs-reference disagreements "
            "— surfaced, not hidden. Full list in `disagreements.csv`."
        )
        lines.append("")
        lines.append("| pool_id | chemistry | mode | tool | def | ref | reason (reference rule) |")
        lines.append("|---|---|---|---|---|---|---|")
        for d in dis[:60]:
            lines.append(
                f"| {d['pool_id']} | {d['chemistry']} | {d['mode']} | {d['label_tool']} | "
                f"{d['label_definitional']} | {d['label_reference']} | {d['reference_reason']} |"
            )
        if len(dis) > 60:
            lines.append(f"| ... | _{len(dis) - 60} more (see CSV)_ | | | | | |")
        lines.append("")

    (results_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _write_figure(res: EvalResult, results_dir: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - figure is optional
        (results_dir / "FIGURE_SKIPPED.txt").write_text(
            f"matplotlib unavailable, figure skipped: {exc}\n", encoding="utf-8"
        )
        return

    # Fail-rate per chemistry per pool class (vendor_faithful tool verdict).
    classes = sorted({str(r["pool_class"]) for r in res.per_pool})
    fail_rate: dict[str, dict[str, list[int]]] = {
        c: {cls: [0, 0] for cls in classes} for c in CHEMS
    }  # [fails, total]
    for r in res.per_pool:
        cell = fail_rate[str(r["chemistry"])][str(r["pool_class"])]
        cell[1] += 1
        if r["tool_vendor_faithful"] == POSITIVE:
            cell[0] += 1

    import numpy as np

    x = np.arange(len(classes))
    width = 0.25
    fig, ax = plt.subplots(figsize=(max(8, len(classes) * 1.3), 5))
    for i, chem in enumerate(CHEMS):
        rates = [
            (fail_rate[chem][cls][0] / fail_rate[chem][cls][1]) if fail_rate[chem][cls][1] else 0
            for cls in classes
        ]
        ax.bar(x + (i - 1) * width, rates, width, label=chem)
    ax.set_xticks(x)
    ax.set_xticklabels(classes, rotation=30, ha="right")
    ax.set_ylabel("tool fail-rate")
    ax.set_ylim(0, 1.05)
    ax.set_title(
        "Color-balance fail-rate by pool class and chemistry (vendor_faithful)\n"
        "(AVITI/avidity is most permissive; 4-channel adds the laser rule)"
    )
    ax.legend(title="chemistry")
    fig.tight_layout()
    fig.savefig(results_dir / "cross_vendor.png", dpi=150)
    fig.savefig(results_dir / "cross_vendor.pdf")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate the color-balance corpus.")
    ap.add_argument("--corpus", type=Path, default=Path("corpus"), help="Corpus directory.")
    ap.add_argument(
        "--results", type=Path, default=Path("eval/results"), help="Results output dir."
    )
    args = ap.parse_args()

    res = evaluate(args.corpus, args.results)
    write_outputs(res, args.results)

    rt = res.roundtrip_failures
    print(f"Evaluated {res.n_pools} pools x {len(CHEMS)} chemistries x {len(MODES)} modes.")
    print(f"Round-trip: {'OK' if not rt else f'{len(rt)} FAILED'}")
    print(f"Cross-vendor flips (vendor_faithful): {len(res.cross_vendor)}")
    print("Tool-vs-reference disagreements (prior single-mode run was 37):")
    print(f"  vendor_faithful: {res.disagree_vs_reference.get('vendor_faithful', 0)}")
    print(f"  conservative:    {res.disagree_vs_reference.get('conservative', 0)}")
    print(f"Results written to {args.results}/")


if __name__ == "__main__":
    main()
