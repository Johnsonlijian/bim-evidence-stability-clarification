# Reproducibility package: decision-stable automated code checking under conflicting BIM evidence

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23361167.svg)](https://doi.org/10.5281/zenodo.23361167)

This repository contains the code and derived records for the manuscript **Decision-stable automated code checking under conflicting BIM evidence**. An archived, citable snapshot of release v0.1.0 is published on Zenodo at [10.5281/zenodo.23361167](https://doi.org/10.5281/zenodo.23361167). The target journal is *Computer-Aided Civil and Infrastructure Engineering*.

The study represents conflicting IFC evidence by admissible readings, derives decision-stable code conclusions, and ranks clarification actions by stability-based value of information. The package contains the frozen code, pre-registration, evidence ledgers, compressed experiment records, aggregate tables and vector figures.

The sole author is Lijian Ren (Inner Mongolia University of Technology; Inner Mongolia Autonomous Region Key Laboratory of Green Construction and Intelligent Operation and Maintenance of Civil Engineering; renlijian@imut.edu.cn).

## Reproduce

Follow [REPRODUCIBLE_RUNBOOK.md](REPRODUCIBLE_RUNBOOK.md). Raw IFC files are fetched from IFC-Bench v2 and are excluded from this repository. Dataset URLs, hashes and license instructions are in [DATASETS_AND_LINKS.csv](DATASETS_AND_LINKS.csv) and `lineage/`.

## Release status

Release v0.1.0 is archived on Zenodo under DOI [10.5281/zenodo.23361167](https://doi.org/10.5281/zenodo.23361167) and is developed at https://github.com/Johnsonlijian/bim-evidence-stability-clarification. Integrities of the archived files are listed in [RELEASE_HASHES.sha256](RELEASE_HASHES.sha256).

Released under a split licence: the source code in `src/` and `scripts/` is MIT ([LICENSE](LICENSE)); derived data, result tables, figures and documentation are CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)). Raw third-party IFC models are not redistributed and remain under their own model-card terms.

The active manuscript, cover letter, submission forms, internal logs, credentials and the companion-corpus reference index are excluded.

## Citation

Cite the archived release:

> Ren, Lijian. (2026). *Reproducibility package for decision-stable automated code checking under conflicting BIM evidence* (v0.1.0) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.23361167

Machine-readable metadata is in [CITATION.cff](CITATION.cff).
