# Installation

## Requirements

- Python 3.12 or higher
- No mandatory runtime dependencies beyond [`loguru`](https://github.com/Delgan/loguru)

## pip (recommended)

```bash
# Core library — parsing, validation, conversion, diff, merge, writer
pip install samplesheet-parser

# With the CLI (adds typer as a dependency)
pip install "samplesheet-parser[cli]"
```

## conda / Bioconda

!!! note "Bioconda package pending"
    The Bioconda recipe has been submitted and is awaiting review. Once merged, install with:

    ```bash
    conda install -c bioconda samplesheet-parser
    ```

    The Bioconda package includes the `samplesheet` CLI by default.

## Development install

```bash
git clone https://github.com/chaitanyakasaraneni/samplesheet-parser.git
cd samplesheet-parser
pip install -e ".[dev,cli]"
```

## Verifying the install

```bash
python -c "import samplesheet_parser; print(samplesheet_parser.__version__)"

# If you installed the CLI extra:
samplesheet --version
```
