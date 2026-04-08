# Writing & Editing

`SampleSheetWriter` provides a fluent API for building new sheets from scratch or editing existing ones.

## Build a V2 sheet from scratch

```python
from samplesheet_parser import SampleSheetWriter
from samplesheet_parser.enums import SampleSheetVersion

writer = SampleSheetWriter(version=SampleSheetVersion.V2)
writer.set_header(run_name="MyRun_20240115", platform="NovaSeqXSeries")
writer.set_reads(read1=151, read2=151, index1=10, index2=10)
writer.set_adapter("CTGTCTCTTATACACATCT")
writer.set_override_cycles("Y151;I10;I10;Y151")
writer.add_sample("SAMPLE_001", index="ATTACTCGAT", index2="TATAGCCTGT", project="Proj")
writer.add_sample("SAMPLE_002", index="TCCGGAGACC", index2="ATAGAGGCAC", project="Proj")
writer.write("SampleSheet.csv")   # validates before writing by default
```

## Build a V1 sheet from scratch

```python
writer = SampleSheetWriter(version=SampleSheetVersion.V1)
writer.set_header(run_name="MyRun_20240115", experiment_name="Experiment1")
writer.set_reads(read1=151, read2=151)
writer.set_adapter("CTGTCTCTTATACACATCT")
writer.add_sample(
    "SAMPLE_001", lane="1",
    index="ATTACTCG", index2="TATAGCCT",
    project="ProjectA",
)
writer.write("SampleSheet_v1.csv")
```

## Edit an existing sheet

```python
from samplesheet_parser import SampleSheetFactory, SampleSheetWriter

sheet = SampleSheetFactory().create_parser("SampleSheet.csv", parse=True)
editor = SampleSheetWriter.from_sheet(sheet)

# Fix a wrong index
editor.update_sample("SAMPLE_002", index="GGGGGGGGGG")

# Remove a sample that was added by mistake
editor.remove_sample("SAMPLE_005")

editor.write("SampleSheet_updated.csv")
```

## Convert format while editing

```python
# Load V1, edit, write out as V2
editor = SampleSheetWriter.from_sheet(sheet, version=SampleSheetVersion.V2)
editor.set_override_cycles("Y151;I10;I10;Y151")
editor.write("SampleSheet_v2.csv")
```

## Inspect without writing

```python
print(writer.sample_count)   # 2
print(writer.sample_ids)     # ["SAMPLE_001", "SAMPLE_002"]
print(writer.to_string())    # full CSV content as a string
```

## Validation on write

`write()` runs `SampleSheetValidator` before writing by default. Pass `validate=False` to skip:

```python
writer.write("out.csv", validate=False)
```

If validation fails, a `ValueError` is raised with the full list of errors — the file is not written.

## CSV safety

`SampleSheetWriter` rejects commas, newlines, and quotes in all free-text inputs (`sample_id`, `index`, `project`, adapter sequences, custom column keys/values) at input time with a clear error message — preventing malformed CSVs.
