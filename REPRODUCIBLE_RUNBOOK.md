# Reproducible runbook

## Environment

Use Python 3.11 or newer in a clean environment and install `requirements.txt`. The tested analysis stack is IfcOpenShell 0.8.5, NumPy, SciPy and Matplotlib. Run all commands from the repository root.

## 1. Obtain the external data

The raw IFC files are not stored in this repository. Read every project model card and license first. Fetch the four development models with:

```powershell
python -E -P scripts\fetch_development.py data\external\ifc-bench-v2
python -E -P src\fetch_heldout.py data\external\ifc-bench-v2-heldout lineage\heldout_fetch_manifest.json
```

The fetch script records URLs, retrieval times and SHA-256 hashes. Do not commit the resulting `data/` directory.

## 2. Extract evidence ledgers

```powershell
powershell -File src\run_extract_all.ps1 -py python
```

This generates declared, +50% and +100% catalogue ledgers under `outputs/dev/` and `outputs/heldout/`.

## 3. Run the frozen experiments

```powershell
powershell -File src\run_experiments.ps1 -py python -sets dev,heldout -procs 8
```

The command runs E1 (delivered evidence), E2 (acquisition simulation), E3 (robustness) and E4 (withheld explicit values). Seeds and policy definitions are fixed in `PREREGISTRATION.md`.

## 4. Aggregate and draw

```powershell
python -E -P scripts\reproduce_aggregates.py
```

This regenerates `outputs/results/`, `outputs/tables/`, `outputs/generated_numbers/` and the vector figures. The wrapper creates and removes a temporary macro directory because the active manuscript is intentionally excluded.

## 5. Verify

Compare regenerated aggregate files with the committed derived artifacts using SHA-256. Inspect PDF figures and confirm that no raw IFC, absolute local path, credential or active manuscript enters the release. Exact lineage reruns against the companion corpus require the withheld reference index; the public redacted summaries preserve the reported hashes and match counts.

## Public deposit sequence

The clean tree is publicly available at https://github.com/Johnsonlijian/bim-evidence-stability-clarification. For an archival record, upload the same clean tree (or a tagged source archive) to Zenodo and then add the resulting DOI to the manuscript's Data availability statement. No Zenodo DOI is claimed by this package.

