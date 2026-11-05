# Research reports

`chapters_3_and_4.md` is the editable report source. `benchmarks/` holds the seven
CSV exports used as evidence; these are retained research artifacts rather than
temporary application output. The snapshot contains 400 runs across four
protocols, ten held-out scenarios, and ten repetitions.

The report builder checks the raw records against the scenario oracles in
`../backend/app/evaluation/heldout_scenarios.py` and cross-checks aggregates before
generating HTML, DOCX, PDF, preview images, and `evidence_checks.json`.
Generated files are ignored by Git; local report exports can be regenerated.

From the repository root, using uv:

```sh
uv run --no-project --with PyMuPDF python reports/build_report.py
```

Alternatively, use a Python environment with PyMuPDF installed:

```sh
python reports/build_report.py
```

This reads the saved CSVs and does not connect to MongoDB, call a model, or rerun
benchmarks. A report assertion failure means the saved evidence or report content
needs review.
