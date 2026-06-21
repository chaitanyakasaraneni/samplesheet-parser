# FINDINGS

Summary of the Step-0 API inspection, where the real repo API changed the
implementation versus the task spec, and what the smoke/full run shows.

> **Note (later revision):** §§1–5 are a point-in-time record. They state that
> "AVITI ≡ 4-channel" and that the tool matched both labelings perfectly. Both
> were later refined: AVITI is now its own `Chemistry.AVIDITY` (more permissive
> than Illumina 4-channel), `label_reference` now encodes published vendor rules,
> and color balance has `vendor_faithful`/`conservative` modes. **§6 is the
> current reconciliation and supersedes the AVITI-as-4-channel framing below.**

## 1. Step-0 inspection: the real API

| Capability | Real API | Notes |
|---|---|---|
| Color-balance analysis | `analyze_color_balance(index1: list[str], index2: list[str] \| None = None, *, chemistry: Chemistry, min_signal_fraction=0.10) -> ColorBalanceReport` | Takes **raw index lists**, not a parsed sheet. `ColorBalanceReport.is_balanced`, `.dark_cycles`, `.weak_cycles`, `.cycles`. |
| Chemistry model | `Chemistry` enum: `ONE_CHANNEL`/`TWO_CHANNEL`/`FOUR_CHANNEL`; `chemistry_for_instrument(name) -> Chemistry \| None` | `G` is the dark base on 1-/2-channel; 4-channel flags only zero-diversity cycles. |
| Validator integration | `SampleSheetValidator.validate(sheet, *, check_color_balance=False, instrument=None, min_signal_fraction=0.10)` | Color balance is **opt-in**; emits `COLOR_BALANCE_NO_SIGNAL` (error) / `COLOR_BALANCE_LOW` (warning). |
| Parsers / factory | `SampleSheetFactory().create_parser(path, *, parse=True)` auto-detects → `.version` ∈ {`V1`, `V2`, `ELEMENT_AVITI`}; `sheet.samples()` → dicts with lowercase `index`/`index2` for **all three** formats | Uniform key casing simplified extraction. |
| Writer | `SampleSheetWriter(version=V1\|V2)` + `set_header/set_reads/set_adapter/add_sample/write(validate=...)` | **No AVITI writer exists** (see §2). |
| Hamming | `hamming_distance(a, b)`, `index_collision_distance(a, b)` (N-wildcard aware) | Both top-level exports. |
| Enums | `SampleSheetVersion.{V1,V2,ELEMENT_AVITI}` | |
| Fixtures | `examples/sample_sheets/{v1_*,v2_*,element_aviti_RunManifest}.csv` | Reused as format references during inspection. |

## 2. Where the real API changed the implementation vs. the spec

**(a) AVITI is 4-channel, not 2-channel — this revises the paper's framing.**
The task context assumed pools "valid on 4-channel … fail on 2-channel **/ AVITI**,"
i.e. that AVITI shares the 2-channel dark-base failure mode. **It does not.** This
library models the Element AVITI as a four-channel avidity platform with **no dark
base** (Arslan et al., *Nat. Biotechnol.* 2023; encoded in
`chemistry.py::_INSTRUMENT_CHEMISTRY`). A G-heavy/G-dark index cycle therefore
**fails on 2-channel but passes on AVITI**. We did **not** stub AVITI to behave
like 2-channel. Instead the harness scores AVITI as its own column (resolving to
4-channel via the library's own instrument map) and the results show AVITI
tracking 4-channel exactly. The defensible paper claim is:

> *Color-balance failure modes are chemistry-specific: pools valid on 4-channel
> chemistry (including the Element AVITI) can fail on 2-channel chemistry.*

**(b) No AVITI writer.** `SampleSheetWriter` only emits V1/V2. AVITI
`RunManifest.csv` files are written manually (`generate_corpus.py::_write_aviti`)
in the exact sectioned layout the real `ElementRunManifest` parser expects
(`[RUNVALUES]`/`[SETTINGS]`/`[SAMPLES]`), and the harness parses them back
through the real factory to prove the manual emission round-trips.

**(c) The color-balance core takes raw indexes, not sheets.** `label_tool` is
derived from `analyze_color_balance(...).is_balanced` (the exact function the
opt-in validator path calls). This lets the same ground-truth pool be scored
under all three chemistries cleanly. The full validator path
(`create_parser` → `validate(..., check_color_balance=True)`) is still exercised
because every pool is parsed back through the factory for the round-trip check.

**(d) Pre-write validation must be disabled to serialize defective pools.**
`SampleSheetWriter.write()` validates by default and raises on errors (e.g.
near-duplicate indexes). The corpus deliberately contains defective pools, so it
is written with `validate=False` — we are testing the validator, not gating on it.

**(e) Manifest granularity.** The spec listed a single `format` column; because
the ground-truth object is the **logical pool** and labels are format-invariant,
`manifest.csv` uses **one row per pool** with three path columns
(`path_iem_v1`, `path_bclconvert_v2`, `path_aviti`) and six per-chemistry label
columns (`def_*` / `ref_*` × {4channel, 2channel, aviti}). This avoids redundant
rows while still covering all three serialized files in the round-trip check.

## 3. What the run shows (full corpus, seed 20260620, 52 pools × 3 chemistries)

**Cross-format round-trip: 52/52 pools identical** across V1, V2, and AVITI —
the corpus doubles as a passing cross-format correctness test.

**Tool vs. ground truth: perfect agreement.** Precision/recall/F1 = **1.000**
for the tool against *both* the definitional and the reference labelings, on all
three chemistries, with **zero** disagreements. Because the definitional label is
the independent first-principles channel rule, this validates the library's
color-balance implementation (no bug surfaced). Confusion counts:

| chemistry | TP | FP | TN | FN |
|---|---|---|---|---|
| 2-channel | 28 | 0 | 24 | 0 |
| 4-channel | 9 | 0 | 43 | 0 |
| AVITI | 9 | 0 | 43 | 0 |

**AVITI ≡ 4-channel, ≠ 2-channel.** The AVITI and 4-channel columns are
*identical* (9 fails each); 2-channel detects 28 — the extra 19 are exactly the
chemistry-specific failures.

**Cross-vendor verdict flips: 19 pools** receive a different pass/fail verdict
depending on chemistry (the paper's key result), broken down as:

| pool class | flips | verdict (4ch / 2ch / aviti) |
|---|---|---|
| `twochannel_dark` | 8 | pass / **fail** / pass |
| `channel_absence` | 8 | pass / **fail** / pass |
| `realistic_mixed` | 2 | pass / **fail** / pass |
| `edge_n2` | 1 | pass / **fail** / pass |

Every flip is a 2-channel-only failure with 4-channel == AVITI, confirming the
chemistry-specific nature of the failure mode. `monobase_collision` (all-`G`
cycle) fails on **all** chemistries and so does *not* flip — a useful
universal-bad control. The `edge_n2` flip is a genuine property, not noise:
two-sample pools are inherently prone to a 2-channel channel dropping to zero.

**Runtime scales ~linearly** with pool size (mean per analysis):

| tier (indexes) | 8 | 24 | 96 | 384 |
|---|---|---|---|---|
| mean time | ~79 µs | ~134 µs | ~472 µs | ~1.26 ms |

## 4. Falsifiability

The harness reports all three comparisons (tool-vs-definitional,
tool-vs-reference, definitional-vs-reference) separately and lists every
disagreement in `summary.md` and `disagreements.csv`.

## 5. label_reference now encodes published vendor rules — where things diverge

The earlier `label_reference` was a first-principles placeholder, so it agreed
with `label_definitional` and the tool perfectly (P/R/F1 = 1.000 everywhere).
It has been replaced (`eval/reference_rules.py`, with citations) by the actual
published vendor rules. The tool still matches the first-principles label
exactly (**`tool_vs_definitional` = 1.000 on all chemistries → no implementation
bug**), but the tool/first-principles model now diverges from published vendor
guidance in three systematic, reportable ways (37 (pool, chemistry)
disagreements total, all `tool == definitional ≠ reference`):

| # | Where | tool / def | vendor rule | count | My read |
|---|---|---|---|---|---|
| 1 | **2-channel**, single-channel-only cycle (e.g. only `G/T` → red absent) | `fail` | `pass` (weak) | 19 | **Conservative tool choice.** Illumina's published rule only requires "signal in at least one channel"; the tool/first-principles model requires *both*. Not a bug — a deliberately stricter policy. Worth stating in the paper as the tool being stricter than Illumina's stated minimum. |
| 2 | **4-channel**, diverse cycle missing one laser (e.g. only `G/T` → no red `{A,C}` laser) | `pass` | `fail` | 9 | **Genuine gap / under-detection in the tool.** The library's 4-channel model flags only zero-diversity cycles; Illumina's 4-channel guidance requires *both lasers* represented. A `{G,T}`-only cycle is diverse yet fails on a real MiSeq/HiSeq. This is the one divergence that looks like a tool limitation worth fixing (extend the 4-channel check to per-laser representation). |
| 3 | **AVITI**, low-diversity / all-`G` cycle | `fail` | `pass` (advisory) | 9 | **Vendor-guidance divergence / over-strict tool.** The library applies 4-channel low-diversity flagging to AVITI, but Element markets the AVITI as low-diversity-tolerant, so its guidance makes this advisory-only. Defensible either way; the conservative paper framing is that the tool is stricter than Element recommends. |

Note the **direction differs by chemistry**: the tool is *stricter* than vendor
guidance on 2-channel and AVITI (divergences 1, 3) but *more permissive* on
4-channel (divergence 2). That asymmetry is the substantive result this
reference-rule comparison surfaces.

### Caveat on the brief's illustrative expectation

The task brief's parenthetical listed an all-`G` pool as "4-channel **pass**".
The brief's *own* cited 4-channel rule (both lasers required) makes an all-`G`
cycle **fail** on 4-channel, because the red `{A,C}` laser is dark. We
implemented and tested the cited rule faithfully (all-`G` → 4-channel fail), and
flag the discrepancy here rather than silently matching the parenthetical. `G`
is not a universal dark base on 4-channel (it images on the green laser), but an
all-`G` cycle still fails because the *red* laser has no signal.

## 6. Reconciliation: modes added, 4-channel bug closed

The three divergences from §5 are now resolved by adding two color-balance modes
(`vendor_faithful` default, `conservative`) and a 4-channel correctness fix, and
by modelling AVITI as its own `Chemistry.AVIDITY`.

**Headline (tool vs. published vendor rule, per mode):**

| | tool-vs-reference disagreements |
|---|---|
| prior single-mode run (§5) | 37 |
| **`vendor_faithful` (new default)** | **0** |
| `conservative` | 28 |

`vendor_faithful` now matches published vendor guidance exactly on every
(pool, chemistry) — precision/recall/F1 = 1.000 (or n/a where a chemistry has no
failures) across 2-channel, 4-channel, and avidity. `conservative` reproduces
the prior stricter behavior as a documented, opt-in mode.

**Per-divergence resolution:**

1. **4-channel laser absence — genuine bug, now closed (both modes).** The
   four-channel check now fails a cycle when the green `{G,T}` or red `{A,C}`
   laser is entirely absent (e.g. all-`G`, or `G/T`-only). `definitional_vs_reference`
   for 4-channel went from F1 0.667 (§5) to **1.000** — the gap is gone, in both
   modes. This was a correctness fix, not a strictness choice.

2. **2-channel single-channel cycles — now a mode choice.** `vendor_faithful`
   follows Illumina's "signal in at least one channel" hard minimum: a
   single-channel cycle is a `COLOR_BALANCE_LOW` warning (pass). `conservative`
   keeps the stricter "both channels" rule (failure). The 19 prior 2-channel
   divergences are now intended `vendor_faithful` passes; they reappear only as
   `conservative`-vs-reference disagreements (documented).

3. **AVITI low diversity — now a mode choice on a distinct chemistry.** AVITI
   maps to `Chemistry.AVIDITY` (per-base dye, no laser-pair rule). In
   `vendor_faithful`, first-cycles low diversity is a `COLOR_BALANCE_ADVISORY`
   (never a failure); in `conservative` it is escalated to a failure. The 9
   prior AVITI divergences are now intended `vendor_faithful` passes.

**Residual divergence (expected, not a bug).** `definitional_vs_reference` still
shows 19 (2-channel) + 9 (avidity) = 28 disagreements. This is the *inherent*
strict-vs-permissive gap between the conservative first-principles model and the
permissive published vendor minimum — exactly what `conservative` mode is for. It
is surfaced in `disagreements.csv` (rows tagged `mode=conservative`), not hidden.
The 4-channel column of `definitional_vs_reference` is now clean (0), confirming
the bug — not a philosophy difference — is closed.
