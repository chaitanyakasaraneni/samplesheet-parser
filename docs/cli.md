# CLI Reference

Install the CLI extra to get the `samplesheet` command:

```bash
pip install "samplesheet-parser[cli]"
# or via conda:
conda install -c bioconda samplesheet-parser
```

## Global options

```
samplesheet --version   # Print version and exit
samplesheet --help      # Show help
```

## Exit codes

All commands use consistent exit codes:

| Code | Meaning |
|---|---|
| `0` | Success / no issues |
| `1` | Issues found (errors, conflicts, or differences detected) |
| `2` | Usage error (missing file, bad argument, parse failure) |

---

## info

Show a quick summary of a sheet without full validation.

```bash
samplesheet info SampleSheet.csv
samplesheet info SampleSheet.csv --format json
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--format` / `-f` | `text` | Output format: `text` or `json` |

**Text output:**
```
File:          SampleSheet.csv
Format:        V2
Samples:       8
Lanes:         1
Index type:    dual
Read lengths:  151 + 151
Adapters:      CTGTCTCTTATACACATCT
Experiment:    MyRun_20240115
```

**JSON output:**
```json
{
  "file": "SampleSheet.csv",
  "format": "V2",
  "sample_count": 8,
  "lanes": ["1"],
  "index_type": "dual",
  "read_lengths": ["151", "151"],
  "adapters": ["CTGTCTCTTATACACATCT"],
  "experiment_name": "MyRun_20240115",
  "instrument": null
}
```

---

## validate

Validate a sheet for index, adapter, and structural issues.

```bash
samplesheet validate SampleSheet.csv
samplesheet validate SampleSheet.csv --format json
samplesheet validate SampleSheet.csv --min-hamming 4
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--format` / `-f` | `text` | Output format: `text` or `json` |
| `--min-hamming` | `3` | Minimum Hamming distance between indexes |

**Exit codes:** `0` = valid, `1` = errors found, `2` = parse/usage error.

---

## convert

Convert between V1 (IEM/bcl2fastq) and V2 (BCLConvert) formats.

```bash
samplesheet convert SampleSheet_v1.csv --to v2 --output SampleSheet_v2.csv
samplesheet convert SampleSheet_v2.csv --to v1 --output SampleSheet_v1.csv
samplesheet convert SampleSheet_v1.csv --to v2 --output out.csv --format json
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--to` | `v2` | Target format: `v1` or `v2` |
| `--output` / `-o` | `SampleSheet_converted.csv` | Output file path |
| `--format` / `-f` | `text` | Output format: `text` or `json` |

!!! warning "V2 → V1 is lossy"
    V2-only fields (`OverrideCycles`, `InstrumentPlatform`, etc.) are dropped with a warning.

**JSON output:**
```json
{
  "input": "SampleSheet_v1.csv",
  "output": "SampleSheet_v2.csv",
  "source_version": "V1",
  "target_version": "V2"
}
```

---

## diff

Compare two sheets across any combination of V1 and V2.

```bash
samplesheet diff old/SampleSheet.csv new/SampleSheet.csv
samplesheet diff old/SampleSheet.csv new/SampleSheet.csv --format json
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--format` / `-f` | `text` | Output format: `text` or `json` |

**Exit codes:** `0` = identical, `1` = differences detected, `2` = parse/usage error.

Useful in CI pre-run checks — gate a pipeline on sheet changes.

---

## merge

Merge multiple per-project sheets into one combined sheet.

```bash
samplesheet merge ProjectA.csv ProjectB.csv --output combined.csv
samplesheet merge ProjectA.csv ProjectB.csv ProjectC.csv --to v1 --output combined.csv
samplesheet merge ProjectA.csv ProjectB.csv --output combined.csv --force
samplesheet merge ProjectA.csv ProjectB.csv --output combined.csv --format json
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--output` / `-o` | `SampleSheet_combined.csv` | Output file path |
| `--to` | `v2` | Target format: `v1` or `v2` |
| `--format` / `-f` | `text` | Output format: `text` or `json` |
| `--force` | `False` | Write output even if conflicts are found |

**Exit codes:** `0` = clean merge, `1` = conflicts or warnings, `2` = bad arguments or unreadable files.

---

## split

Split a combined sheet into one file per project or per lane.

```bash
samplesheet split combined.csv --output-dir ./per_project/
samplesheet split combined.csv --by lane --output-dir ./per_lane/
samplesheet split combined.csv --output-dir ./out/ --to v1
samplesheet split combined.csv --output-dir ./out/ --prefix Run001_ --format json
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--by` | `project` | Grouping strategy: `project` or `lane` |
| `--output-dir` / `-d` | `./split/` | Directory in which to write output files |
| `--to` | (same as input) | Target format: `v1` or `v2` |
| `--format` / `-f` | `text` | Output format: `text` or `json` |
| `--prefix` | `""` | String prepended to each output filename |

Output filenames follow the pattern `{prefix}{group}_SampleSheet.csv`.

**Exit codes:** `0` = success, `1` = warnings produced (e.g. unassigned samples), `2` = bad arguments or unreadable files.

**JSON output:**
```json
{
  "source_version": "V2",
  "groups": {
    "ProjectA": {"file": "ProjectA_SampleSheet.csv", "sample_count": 4},
    "ProjectB": {"file": "ProjectB_SampleSheet.csv", "sample_count": 6}
  },
  "warnings": []
}
```

---

## filter

Extract a subset of samples from a sheet by project, lane, or sample ID.

```bash
samplesheet filter combined.csv --project ProjectA --output ProjectA.csv
samplesheet filter combined.csv --lane 1 --output lane1.csv
samplesheet filter combined.csv --sample-id "CTRL_*" --output controls.csv
samplesheet filter combined.csv --project ProjectA --lane 1 --output out.csv
samplesheet filter combined.csv --project ProjectA --output out.csv --format json
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--project` / `-p` | — | Keep only samples matching this `Sample_Project` |
| `--lane` / `-l` | — | Keep only samples from this lane |
| `--sample-id` / `-s` | — | Keep only samples matching this ID or glob pattern |
| `--output` / `-o` | `SampleSheet_filtered.csv` | Output file path |
| `--to` | (same as input) | Target format: `v1` or `v2` |
| `--format` / `-f` | `text` | Output format: `text` or `json` |

At least one of `--project`, `--lane`, or `--sample-id` is required.  Multiple criteria are ANDed.

`--sample-id` supports glob patterns (e.g. `"CTRL_*"`, `"SAMPLE_00[1-3]"`); matching is case-sensitive on all platforms.

**Exit codes:** `0` = samples matched and written, `1` = no samples matched (no output written), `2` = bad arguments or unreadable files.

**JSON output:**
```json
{
  "matched_count": 2,
  "total_count": 12,
  "source_version": "V2",
  "output": "ProjectA.csv",
  "criteria": {"project": "ProjectA", "lane": null, "sample_id": null}
}
```
