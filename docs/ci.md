# CI Integration

The CLI exits with meaningful codes (`0` = clean, `1` = issues, `2` = error), making it easy to wire into automated pipelines.

## GitHub Actions

Add a validation step to any workflow that touches `SampleSheet.csv`:

```yaml
# .github/workflows/validate-samplesheet.yml
name: Validate SampleSheet

on:
  push:
    paths:
      - '**/SampleSheet.csv'
  pull_request:
    paths:
      - '**/SampleSheet.csv'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install "samplesheet-parser[cli]"

      - name: Validate SampleSheet
        run: samplesheet validate SampleSheet.csv --format json
```

## pre-commit hook

Gate commits that touch any `SampleSheet.csv` in the repository:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: samplesheet-validate
        name: Validate SampleSheet.csv
        entry: samplesheet validate
        language: python
        additional_dependencies: ["samplesheet-parser[cli]"]
        files: SampleSheet\.csv$
        pass_filenames: true
```

Install and run once to verify:

```bash
pip install pre-commit
pre-commit install
pre-commit run samplesheet-validate --all-files
```

## Stricter Hamming distance in CI

If your lab uses longer indexes (10 bp+), raise the minimum Hamming distance threshold to catch borderline cases earlier:

```bash
samplesheet validate SampleSheet.csv --min-hamming 4
```

## Using JSON output in scripts

All commands support `--format json` for machine-readable output:

```bash
result=$(samplesheet validate SampleSheet.csv --format json)
is_valid=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['is_valid'])")

if [ "$is_valid" != "True" ]; then
  echo "SampleSheet validation failed"
  exit 1
fi
```
