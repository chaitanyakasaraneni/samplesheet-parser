"""Deterministic synthetic corpus generator for color-balance evaluation.

The unit of ground truth is a **logical pool**: a set of index sequences
(single- or dual-index, length 8 or 10 bp). Each logical pool is serialized to
all three formats this repo supports, using the repo's *real* writers/parsers,
so the identical pool flows through every format and the corpus doubles as a
cross-format round-trip correctness test.

For every (pool, chemistry) two independent labels are produced **here in the
generator** (never by calling the library under test):

* ``label_definitional`` -- from first-principles optical-channel rules
  implemented below (the construction logic). If this disagrees with the
  library, the library has a bug.
* ``label_reference``     -- from an encoded version of published vendor
  color-balance guidance. Thresholds live in the clearly-marked config block
  below so they can be adjusted; any ``# TODO: confirm`` constant is a
  best-effort placeholder, flagged rather than guessed silently.

Run ``python -m eval.generate_corpus --help`` for options.

NOTE ON AVITI (important, see eval/FINDINGS.md): this repo models the Element
AVITI as a **four-channel** avidity platform with no dark base (Arslan et al.,
Nat. Biotechnol. 2023). It therefore behaves like other 4-channel instruments,
NOT like a 2-channel instrument. Pools that are "G-dark" fail on 2-channel but
are fine on AVITI -- the opposite of the assumption that AVITI shares the
2-channel dark-base failure mode. The generator labels AVITI with 4-channel
rules accordingly, and the harness surfaces this rather than hiding it.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
from dataclasses import dataclass
from pathlib import Path

from eval import reference_rules
from samplesheet_parser import SampleSheetWriter
from samplesheet_parser.chemistry import Chemistry, chemistry_for_instrument
from samplesheet_parser.enums import SampleSheetVersion

# label_reference now encodes the actual published vendor rules, implemented in
# eval/reference_rules.py (with citations). The earlier placeholder threshold
# constants have been removed; any tunable lives in reference_rules.py, flagged
# with its source or as a heuristic.

# ===========================================================================
# Corpus shape
# ===========================================================================

DEFAULT_MASTER_SEED = 20260620

#: Chemistries scored in the evaluation, each pinned to a representative
#: instrument name so the harness exercises the real instrument->chemistry
#: mapping. AVITI resolves to FOUR_CHANNEL (see module note).
CHEMISTRY_INSTRUMENTS: dict[str, str] = {
    "4channel": "MiSeq",
    "2channel": "NovaSeq X",
    "aviti": "AVITI",
}

#: Scale tiers (number of indexes) for the scalable pool classes.
TIERS: tuple[int, ...] = (8, 24, 96, 384)

#: Pool classes that scale with tier size.
SCALABLE_CLASSES: tuple[str, ...] = (
    "clean_balanced",
    "twochannel_dark",
    "monobase_collision",
    "channel_absence",
    "hamming_collision",
    "realistic_mixed",
)

_BASES = "ACGT"

#: (index1, index2|None, index_len, notes) returned by each pool-class builder.
PoolBuild = tuple[list[str], "list[str] | None", str, str]


# ===========================================================================
# Logical pool
# ===========================================================================


@dataclass
class LogicalPool:
    """Ground-truth index pool, independent of any file format."""

    pool_id: str
    pool_class: str
    tier: int
    index1: list[str]
    index2: list[str] | None  # None => single-index
    index_len: str  # e.g. "10" or "8/10" for mixed
    notes: str = ""

    @property
    def n_indexes(self) -> int:
        return len(self.index1)

    @property
    def index_type(self) -> str:
        return "dual" if self.index2 else "single"


# ===========================================================================
# Deterministic RNG
# ===========================================================================


def _child_rng(master_seed: int, pool_id: str) -> random.Random:
    """Return an independent RNG seeded from (master_seed, pool_id).

    Deriving each pool's seed from a hash of its id makes regeneration
    reproducible regardless of generation order.
    """
    h = hashlib.sha256(f"{master_seed}:{pool_id}".encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


# ===========================================================================
# Balanced index construction
# ===========================================================================


def _balanced_index(row: int, length: int) -> str:
    """A maximally color-balanced index for a given row.

    Each column is a rotation of ACGT, so every column over a pool of >= 4
    rows contains all four bases (full diversity, both 2-channel channels
    well represented). Consecutive rows differ at every position, giving
    large Hamming separation.
    """
    return "".join(_BASES[(row + c) % 4] for c in range(length))


def _balanced_pool(n: int, length: int, *, offset: int = 0) -> list[str]:
    return [_balanced_index(i + offset, length) for i in range(n)]


# ===========================================================================
# Pool-class builders -- each returns (index1, index2|None, index_len, notes)
# ===========================================================================


def _build_clean(n: int, length: int, dual: bool, rng: random.Random) -> PoolBuild:
    i1 = _balanced_pool(n, length)
    i2 = _balanced_pool(n, length, offset=2) if dual else None
    return i1, i2, str(length), "fully balanced on all cycles"


def _overwrite_column(seqs: list[str], cycle: int, bases: list[str]) -> list[str]:
    """Return a copy of *seqs* with *cycle* replaced by *bases* (per row)."""
    out = []
    for i, s in enumerate(seqs):
        b = bases[i % len(bases)]
        out.append(s[:cycle] + b + s[cycle + 1 :])
    return out


def _build_twochannel_dark(n: int, length: int, dual: bool, rng: random.Random) -> PoolBuild:
    """One cycle uses only {G, T} -> red channel absent, diversity intact.

    Fails on 2-channel (no red signal) but passes on 4-channel/AVITI
    (two distinct bases present). This is the paper's key flip class.
    """
    i1 = _balanced_pool(n, length)
    cycle = rng.randrange(length)
    # Alternate G/T so the column has >= 2 distinct bases but zero A/C.
    i1 = _overwrite_column(i1, cycle, ["G", "T"])
    i2 = _balanced_pool(n, length, offset=2) if dual else None
    return i1, i2, str(length), f"index1 cycle {cycle + 1}: only G/T (red absent)"


def _build_channel_absence(n: int, length: int, dual: bool, rng: random.Random) -> PoolBuild:
    """One cycle uses only {G, C} -> green channel absent, diversity intact.

    Fails on 2-channel (no green signal) but passes on 4-channel/AVITI.
    """
    i1 = _balanced_pool(n, length)
    cycle = rng.randrange(length)
    i1 = _overwrite_column(i1, cycle, ["G", "C"])
    i2 = _balanced_pool(n, length, offset=2) if dual else None
    return i1, i2, str(length), f"index1 cycle {cycle + 1}: only G/C (green absent)"


def _build_monobase(n: int, length: int, dual: bool, rng: random.Random) -> PoolBuild:
    """One cycle reads a single base G across the whole pool.

    Universal failure: 2-channel sees a dark cycle (no red, no green) AND
    4-channel/AVITI sees zero diversity (single base).
    """
    i1 = _balanced_pool(n, length)
    cycle = rng.randrange(length)
    i1 = _overwrite_column(i1, cycle, ["G"])
    i2 = _balanced_pool(n, length, offset=2) if dual else None
    return i1, i2, str(length), f"index1 cycle {cycle + 1}: all-G (universal bad)"


def _build_hamming_collision(n: int, length: int, dual: bool, rng: random.Random) -> PoolBuild:
    """Color-balanced pool containing an index pair within edit distance <= 2.

    Exercises the index-distance check, not color balance: the pool should be
    color-balanced (pass) on all chemistries yet flagged by the Hamming check.
    """
    i1 = _balanced_pool(n, length)
    if n >= 2:
        # Make row 1 a near-duplicate of row 0 (distance 1 or 2).
        dist = rng.choice([1, 2])
        clone = list(i1[0])
        positions = rng.sample(range(length), dist)
        for p in positions:
            # Change to a different base (keeps it a near-duplicate, distance>0).
            clone[p] = rng.choice([b for b in _BASES if b != clone[p]])
        i1[1] = "".join(clone)
    i2 = _balanced_pool(n, length, offset=2) if dual else None
    return i1, i2, str(length), "contains an index pair within Hamming distance <= 2"


def _build_realistic_mixed(n: int, length: int, dual: bool, rng: random.Random) -> PoolBuild:
    """A plausible plate that occasionally carries one injected defect."""
    inject = rng.random() < 0.4
    if not inject:
        i1 = _balanced_pool(n, length)
        i2 = _balanced_pool(n, length, offset=2) if dual else None
        return i1, i2, str(length), "realistic plate, no defect"
    builder = rng.choice([_build_twochannel_dark, _build_channel_absence, _build_monobase])
    i1, i2, ln, note = builder(n, length, dual, rng)
    return i1, i2, ln, f"realistic plate with injected defect: {note}"


_SCALABLE_BUILDERS = {
    "clean_balanced": _build_clean,
    "twochannel_dark": _build_twochannel_dark,
    "monobase_collision": _build_monobase,
    "channel_absence": _build_channel_absence,
    "hamming_collision": _build_hamming_collision,
    "realistic_mixed": _build_realistic_mixed,
}


# ===========================================================================
# Edge-case pools (fixed sizes / shapes)
# ===========================================================================


def _build_edge_pools(master_seed: int) -> list[LogicalPool]:
    pools: list[LogicalPool] = []

    def add(
        pool_id: str,
        pool_class: str,
        i1: list[str],
        i2: list[str] | None,
        index_len: str,
        notes: str,
    ) -> None:
        pools.append(
            LogicalPool(
                pool_id=pool_id,
                pool_class=pool_class,
                tier=len(i1),
                index1=i1,
                index2=i2,
                index_len=index_len,
                notes=notes,
            )
        )

    # n=1 single sample (color balance is not assessable -> always pass).
    add(
        "edge_n1",
        "edge_n1",
        _balanced_pool(1, 10),
        None,
        "10",
        "single sample; pool<2 not assessable",
    )
    # n=2 minimal dual-index pool.
    add(
        "edge_n2",
        "edge_n2",
        _balanced_pool(2, 10),
        _balanced_pool(2, 10, offset=2),
        "10",
        "minimal n=2 dual pool",
    )
    # single-index 8 bp.
    add(
        "edge_single_index",
        "edge_single_index",
        _balanced_pool(12, 8),
        None,
        "8",
        "single-index, 8 bp",
    )
    # mixed index lengths (8 and 10 bp) in one pool.
    rng = _child_rng(master_seed, "edge_mixed_lengths")
    base8 = _balanced_pool(6, 8)
    base10 = _balanced_pool(6, 10, offset=1)
    mixed = base8 + base10
    rng.shuffle(mixed)
    add("edge_mixed_lengths", "edge_mixed_lengths", mixed, None, "8/10", "mixed 8/10 bp indexes")

    return pools


# ===========================================================================
# Corpus assembly
# ===========================================================================


def build_pools(master_seed: int, *, tiers: tuple[int, ...] = TIERS) -> list[LogicalPool]:
    """Construct every logical pool deterministically from *master_seed*."""
    pools: list[LogicalPool] = []
    for cls in SCALABLE_CLASSES:
        builder = _SCALABLE_BUILDERS[cls]
        for tier in tiers:
            for dual in (True, False):
                shape = "dual" if dual else "single"
                length = 10 if dual else 8
                pool_id = f"{cls}__t{tier}__{shape}"
                rng = _child_rng(master_seed, pool_id)
                i1, i2, index_len, notes = builder(tier, length, dual, rng)
                pools.append(
                    LogicalPool(
                        pool_id=pool_id,
                        pool_class=cls,
                        tier=tier,
                        index1=i1,
                        index2=i2,
                        index_len=index_len,
                        notes=notes,
                    )
                )
    pools.extend(_build_edge_pools(master_seed))
    return pools


# ===========================================================================
# Ground-truth labeling (first principles -- NOT the library under test)
# ===========================================================================


def _columns(seqs: list[str]) -> list[list[str]]:
    """Per-cycle base columns (uppercase) over indexes long enough to reach."""
    if not seqs:
        return []
    max_len = max(len(s) for s in seqs)
    cols = []
    for c in range(max_len):
        cols.append([s[c].upper() for s in seqs if c < len(s)])
    return cols


def label_definitional(pool: LogicalPool, chemistry: Chemistry) -> str:
    """First-principles (strict) channel-rule label: 'pass' or 'fail'.

    This encodes the conservative optical-physics view (the model the library's
    ``conservative`` mode implements), so ``tool(conservative)`` should match it
    exactly:

    * **4-channel** (Illumina): green laser reads ``{G,T}``, red laser reads
      ``{A,C}``; a cycle fails if either laser group is entirely absent (this
      includes mono-base/zero-diversity cycles).
    * **avidity** (AVITI): no laser pairs; a cycle fails (strict view) only when
      diversity collapses to a single base.
    * **2-/1-channel**: ``G`` is dark; a cycle fails if no sample carries a red
      base (``A/C``) or no sample carries a green base (``A/T``) -- i.e. either
      channel entirely absent (single-channel cycles fail in this strict view).

    Cycles with fewer than two assessable samples are treated as 'pass'
    (matching the library's pool<2 guard).
    """
    reads = [pool.index1] + ([pool.index2] if pool.index2 else [])
    for seqs in reads:
        seqs = [s for s in seqs if s]
        for col in _columns(seqs):
            pool_n = len(col)
            if pool_n < 2:
                continue
            distinct = len({b for b in col if b != "N"})
            if chemistry is Chemistry.FOUR_CHANNEL:
                green_laser = any(b in ("G", "T") for b in col)
                red_laser = any(b in ("A", "C") for b in col)
                if not green_laser or not red_laser:
                    return "fail"
            elif chemistry is Chemistry.AVIDITY:
                if distinct <= 1:
                    return "fail"
            else:  # TWO_CHANNEL / ONE_CHANNEL
                red = any(b in ("A", "C") for b in col)
                green = any(b in ("A", "T") for b in col)
                if not red or not green:
                    return "fail"
    return "pass"


def label_reference(pool: LogicalPool, chem_key: str) -> str:
    """Published-vendor-guidance label: 'pass' or 'fail'.

    Dispatches to :mod:`eval.reference_rules` by **vendor/platform key**
    ("2channel" / "4channel" / "aviti"), not by physical channel count: the
    Element AVITI is physically four-channel but Element's published guidance
    is more permissive than Illumina's four-channel guidance. Independent of
    both the library under test and :func:`label_definitional`, so the harness
    can quantify where they diverge.
    """
    return reference_rules.evaluate(chem_key, pool.index1, pool.index2).verdict


# ===========================================================================
# Serialization to the three formats (real writers / manual AVITI)
# ===========================================================================


def _write_illumina(pool: LogicalPool, version: SampleSheetVersion, path: Path) -> None:
    writer = SampleSheetWriter(version=version)
    if version is SampleSheetVersion.V2:
        writer.set_header(run_name=pool.pool_id, platform="NovaSeqXSeries")
        max1 = max(len(s) for s in pool.index1)
        max2 = max((len(s) for s in (pool.index2 or [])), default=0)
        writer.set_reads(read1=151, read2=151, index1=max1, index2=max2)
    else:
        writer.set_header(run_name=pool.pool_id)
        writer.set_reads(read1=151, read2=151)
    writer.set_adapter("CTGTCTCTTATACACATCT")
    for i, idx in enumerate(pool.index1):
        idx2 = pool.index2[i] if pool.index2 else ""
        writer.add_sample(
            sample_id=f"S{i + 1}",
            index=idx,
            index2=idx2,
            lane="1",
            project="EvalProj",
        )
    # validate=False: the corpus deliberately contains defective pools
    # (duplicate-ish / low-distance indexes) that pre-write validation would
    # reject. We are testing the validator, not gating on it.
    writer.write(path, validate=False)


def _write_aviti(pool: LogicalPool, path: Path) -> None:
    """Emit an Element AVITI RunManifest.csv manually (no AVITI writer exists)."""
    index2 = pool.index2
    dual = index2 is not None
    lines = [
        "[RUNVALUES]",
        "KeyName,Value",
        f"run_name,{pool.pool_id}",
        "instrument,AVITI",
        "",
        "[SETTINGS]",
        "SettingName,Value",
        "R1Adapter,CTGTCTCTTATACACATCT",
        "",
        "[SAMPLES]",
    ]
    header = ["SampleName", "Index1"]
    if dual:
        header.append("Index2")
    header += ["Lane", "Project"]
    lines.append(",".join(header))
    for i, idx in enumerate(pool.index1):
        row = [f"S{i + 1}", idx]
        if index2 is not None:
            row.append(index2[i])
        row += ["1", "EvalProj"]
        lines.append(",".join(row))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ===========================================================================
# Manifest
# ===========================================================================

MANIFEST_FIELDS = [
    "pool_id",
    "pool_class",
    "tier",
    "n_indexes",
    "index_type",
    "index_len",
    "notes",
    "path_iem_v1",
    "path_bclconvert_v2",
    "path_aviti",
    "def_4channel",
    "def_2channel",
    "def_aviti",
    "ref_4channel",
    "ref_2channel",
    "ref_aviti",
]


def generate(out_root: Path, master_seed: int, *, tiers: tuple[int, ...] = TIERS) -> Path:
    """Generate the full corpus under *out_root* and return the manifest path."""
    corpus = out_root
    (corpus / "iem_v1").mkdir(parents=True, exist_ok=True)
    (corpus / "bclconvert_v2").mkdir(parents=True, exist_ok=True)
    (corpus / "aviti").mkdir(parents=True, exist_ok=True)

    (corpus / "seed.txt").write_text(f"{master_seed}\n", encoding="utf-8")

    pools = build_pools(master_seed, tiers=tiers)

    rows: list[dict[str, str]] = []
    for pool in pools:
        p_v1 = corpus / "iem_v1" / f"{pool.pool_id}.csv"
        p_v2 = corpus / "bclconvert_v2" / f"{pool.pool_id}.csv"
        p_av = corpus / "aviti" / f"{pool.pool_id}_RunManifest.csv"

        _write_illumina(pool, SampleSheetVersion.V1, p_v1)
        _write_illumina(pool, SampleSheetVersion.V2, p_v2)
        _write_aviti(pool, p_av)

        chem: dict[str, Chemistry] = {}
        for k, v in CHEMISTRY_INSTRUMENTS.items():
            resolved = chemistry_for_instrument(v)
            assert resolved is not None, f"unknown instrument for chemistry key {k!r}: {v!r}"
            chem[k] = resolved
        rows.append(
            {
                "pool_id": pool.pool_id,
                "pool_class": pool.pool_class,
                "tier": str(pool.tier),
                "n_indexes": str(pool.n_indexes),
                "index_type": pool.index_type,
                "index_len": pool.index_len,
                "notes": pool.notes,
                "path_iem_v1": str(p_v1.relative_to(out_root.parent)),
                "path_bclconvert_v2": str(p_v2.relative_to(out_root.parent)),
                "path_aviti": str(p_av.relative_to(out_root.parent)),
                # Definitional labels are physics-based, keyed by Chemistry
                # (4channel and aviti are both physically FOUR_CHANNEL).
                "def_4channel": label_definitional(pool, chem["4channel"]),
                "def_2channel": label_definitional(pool, chem["2channel"]),
                "def_aviti": label_definitional(pool, chem["aviti"]),
                # Reference labels are vendor-guidance-based, keyed by platform
                # (aviti differs from 4channel despite identical physics).
                "ref_4channel": label_reference(pool, "4channel"),
                "ref_2channel": label_reference(pool, "2channel"),
                "ref_aviti": label_reference(pool, "aviti"),
            }
        )

    manifest = out_root / "manifest.csv"
    with open(manifest, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the synthetic color-balance corpus.")
    ap.add_argument("--out", type=Path, default=Path("corpus"), help="Output corpus directory.")
    ap.add_argument("--seed", type=int, default=DEFAULT_MASTER_SEED, help="Master seed.")
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="Tiny corpus (tiers 8,24 only) for quick smoke tests.",
    )
    args = ap.parse_args()
    tiers = (8, 24) if args.smoke else TIERS
    manifest = generate(args.out, args.seed, tiers=tiers)
    n = sum(1 for _ in open(manifest)) - 1
    print(f"Wrote {n} pools (x3 formats) under {args.out}/  (seed={args.seed})")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
