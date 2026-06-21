# Synthetic color-balance evaluation corpus & harness

A fully synthetic, deterministic evaluation of `samplesheet-parser`'s
chemistry-aware index **color-balance** validator. It builds a corpus of index
pools, serializes each pool to all three supported formats (Illumina IEM V1,
Illumina BCLConvert V2, Element AVITI RunManifest) using the library's real
writers/parsers, and scores the library's validator against two independent
ground-truth labelings under 4-channel, 2-channel, and AVITI chemistries.

**No real or proprietary data is used.** Every index is procedurally generated.

## Central claim under test

A vendor-agnostic, chemistry-aware color-balance validator catches index-pool
failure modes that **differ across sequencing chemistries** — in particular,
pools that pass on 4-channel chemistry but fail on 2-channel.

> **Important nuance (see [FINDINGS.md](FINDINGS.md)):** this library models the
> Element AVITI as a **four-channel** avidity platform (no dark base; Arslan et
> al., *Nat. Biotechnol.* 2023). AVITI therefore behaves like 4-channel, **not**
> like 2-channel. The harness reports this explicitly rather than assuming AVITI
> shares the 2-channel dark-base failure mode.

## Layout

```
eval/
  generate_corpus.py   # build the corpus (deterministic, seeded)
  run_eval.py          # parse it back, score it, emit metrics + figure
  results/             # CSVs, summary.md, cross_vendor.png/.pdf (generated)
corpus/
  seed.txt             # master seed used (reproducibility)
  manifest.csv         # one row per pool: class, tier, paths, 6 ground-truth labels
  iem_v1/              # each pool as an Illumina V1 sheet
  bclconvert_v2/       # each pool as an Illumina V2 sheet
  aviti/               # each pool as an Element AVITI RunManifest
```

## Regenerate the corpus

```bash
python -m eval.generate_corpus              # full corpus (tiers 8/24/96/384)
python -m eval.generate_corpus --seed 123   # different master seed
python -m eval.generate_corpus --smoke      # tiny corpus (tiers 8/24) for quick checks
```

The corpus is a pure function of the master seed (written to `corpus/seed.txt`):
the same seed reproduces every pool and every serialized file byte-for-byte.

## Rerun the evaluation

```bash
python -m eval.run_eval                      # reads corpus/, writes eval/results/
```

Outputs in `eval/results/`:

| File | Contents |
|---|---|
| `per_pool.csv` | every (pool, chemistry): tool verdict, all three labels, agreement flags, reference reason |
| `metrics.csv` | confusion counts + precision/recall/F1 per chemistry, for all three comparisons |
| `disagreements.csv` | every (pool, chemistry, mode) where the tool disagrees with the published vendor rule, with reason strings |
| `cross_vendor.csv` | pools whose pass/fail verdict flips across chemistries (vendor_faithful) |
| `runtime.csv` | analysis runtime vs tier size |
| `summary.md` | human-readable summary (start here) |
| `cross_vendor.png` / `.pdf` | fail-rate by pool class × chemistry figure |

The tool is scored in **both modes** (`vendor_faithful` default, `conservative`).
The three comparisons are: `tool_vendor_faithful_vs_reference` (agreement with
published vendor guidance — should be ~perfect), `tool_conservative_vs_definitional`
(the conservative tool matches the strict first-principles model — implementation
correctness), and `definitional_vs_reference` (the inherent strict-vs-permissive
gap). `summary.md` reports tool-vs-reference disagreement counts per mode.

## Pool classes

| Class | Construction | Expected behavior |
|---|---|---|
| `clean_balanced` | every cycle fully diverse | pass on all chemistries |
| `twochannel_dark` | one cycle only `G`/`T` (red absent) | **fail 2-channel, pass 4-channel/AVITI** |
| `channel_absence` | one cycle only `G`/`C` (green absent) | **fail 2-channel, pass 4-channel/AVITI** |
| `monobase_collision` | one cycle all-`G` | fail on all chemistries (universal-bad) |
| `hamming_collision` | a near-duplicate index pair (≤2 mismatches) | color-balanced; exercises the index-distance check |
| `realistic_mixed` | ~plausible plate, occasional injected defect | mixed |
| `edge_*` | n=1, n=2, single-index, mixed 8/10 bp lengths | robustness |

## Two independent ground-truth labelings

Both are computed **in the generator** (never by calling the library under test):

- **`label_definitional`** — the strict first-principles optical-channel model
  (the conservative view: 4-channel needs both lasers, 2-channel needs both
  channels, avidity fails only on collapsed diversity). The library's
  `conservative` mode implements exactly this, so they agree by construction.
- **`label_reference`** — the actual **published vendor rules**, implemented in
  [`reference_rules.py`](reference_rules.py) with source citations (Illumina
  Index Adapters Pooling Guide #1000000041074 and the NextSeq/MiniSeq/NovaSeq
  color-balancing knowledge articles; Element AVITI metrics & low-diversity
  docs). Dispatched by **vendor/platform key** (`2channel`/`4channel`/`aviti`),
  *not* by physical channel count — the AVITI is physically four-channel but
  Element's guidance is more permissive than Illumina's four-channel guidance.
  Illumina's qualitative rules ("signal in at least one channel") are encoded as
  rules, not invented numeric thresholds. Anything not vendor-specified (e.g. the
  AVITI low-diversity advisory window) is in a constants block flagged
  `# heuristic, not vendor-specified`.

The harness scores the tool in both modes and reports all three comparisons
separately, so disagreement is surfaced and quantified, not hidden — keeping the
paper's claim falsifiable. After the mode change and the 4-channel fix,
`vendor_faithful` matches published vendor guidance exactly (0 disagreements,
down from 37) while `conservative` reproduces the prior stricter behavior; see
[FINDINGS.md](FINDINGS.md) §6 for the reconciliation.

## Reproducibility artifact

This corpus + harness is self-contained and deterministic, suitable for
publication as a reproducibility artifact (e.g. archived on **Zenodo** alongside
the paper). To archive: record the `samplesheet-parser` version, the master seed
(`corpus/seed.txt`), and this `eval/` directory; `python -m eval.generate_corpus
&& python -m eval.run_eval` regenerates everything from scratch.

## Tests

```bash
pytest tests/test_eval.py
```

covers first-principles label correctness on hand-built pools, tool/definitional
agreement, determinism, and an end-to-end smoke corpus (generate → round-trip →
evaluate).
