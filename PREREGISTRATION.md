# R10 pre-registration — frozen before any held-out model was downloaded

Frozen: 2026-10-11 16:57 (workstation clock, UTC−07:00). Target journal: *Computer-Aided Civil and Infrastructure
Engineering* (CACAIE). This file fixes the data rules, code, experiments and endpoints of R10 **before** the
held-out models are obtained. It is not modified after that point; deviations are recorded in `DEVIATIONS.md`.

## 1. Why R10 exists

R09 used nine IFC-Bench v2 models. A lineage audit (2026-10-11) found that five of them are the same IFC projects as
inputs of the companion manuscript CPENG-9113 (ASCE JCCE, under consideration): 4351 and DigitalHub (byte-identical),
FZK-Haus (identical after line-ending normalisation), the medical-dental clinic (identical element GlobalIds,
differently processed file) and the KIT institute building `ac20` (same IfcProject, different ArchiCAD export).
R09 also tuned its interpretation catalogue on the same models it reported. R10 therefore (a) removes every model
that shares project identity with a companion input, (b) freezes code and catalogue on a development set, and
(c) evaluates on held-out models never inspected before this freeze.

## 2. Frozen code (SHA-256)

Analysis and decision code is frozen; reporting scripts (`make_results.py`, `make_figures.py`, `make_dialogue.py`)
only aggregate frozen outputs and may change.

| File | SHA-256 |
|---|---|
| `src/bimev/__init__.py` | `DDD5FFCB873F16C0FB17EC3C3050133278F1FADF7C5493612D8FBBBB503FA695` |
| `src/bimev/audit.py` | `789DD7972A36CC2A615C2C69455ECEE9D83B654BA26D268A25B676B31CABC31D` |
| `src/bimev/catalog.py` | `B703438B3C4ADF4C0AA506A27F142E0A02D7D0DB2ED9ED62D6A41BF7010ECC4A` |
| `src/bimev/engine.py` | `01D516ACC71D38A1E5E1B5A5FF09900D5C14D481E1D2D5373A35B2C844097FD4` |
| `src/bimev/extract.py` | `FE3FCEB8088C0F3E124F5FB0FC1D81C7173B6D052F4A6D8D7D16301DAF2B4242` |
| `src/bimev/ifcutil.py` | `456CA9CF522524973108EDA65D0A64AAE7627D3E69E111CF48B7825EC6A7DC9E` |
| `src/bimev/planner.py` | `B881FA7044EC35CC1B09BCE14DE09BA61BCB889D3690E3CC68A87C8EDB47909F` |
| `src/lineage_audit.py` | `EDB7BCEF81FA2C54D08F9D628A7C759B1EFBAEA9E076E2229FB40C8A6B1BE90D` |
| `src/run_e1_audit.py` | `9961E3F075FF57DA9259C4B9C7C9DC8218AE25A47769E354B096506F2E1AAAED` |
| `src/run_e2_acquisition.py` | `049EB662B430A823D70AF7FFFAED046D2A6EB4B1FC8E66855206B655EED3399F` |
| `src/run_e4_validation.py` | `6C096C589C00CF72E605505D59506C45C7F2DE68FA38993050313D25ED23036E` |
| `src/run_extract.py` | `00DC18A9B2A33805D487780A47D5127133EB93F2097DC193A8EE79D73FC6C4F8` |

## 3. Development-stage changes relative to R09 (made on the development set before this freeze)

1. **Design intent is non-binding.** Stair calculation rules ("Maximum Riser Height", "Minimum Tread Depth") and
   design limits encoded in type names now have weight 0 (`WEIGHT_INTENT`): they are recorded in the ledger but
   overruling them costs nothing, so they can never settle a check. Reason: E4 on the development set found two
   City-house flights whose risers (209.3 and 206.4 mm, three concordant explicit properties each) exceed their own
   180 mm calculation rule; authoring tools warn about, but do not enforce, such rules. With the rule binding, the
   method concluded "no violation" from indirect evidence; after the change it leaves those checks open.
2. **Residual-degree baseline** (`planner.choose`, policy `degree`): value-blind ordering by the number of unsettled
   element checks a request touches per unit effort (transplant of source-recovery ordering).
3. **Experiment 4** (`run_e4_validation.py`) and the audit category `intent` (design intent not met).
4. Corrected statement: a suspected export default has a zero-cost error reading and therefore never narrows the
   admissible set on its own (R09's manuscript text claimed otherwise).

## 4. Data

**Lineage rule.** A model is excluded if its IfcProject GlobalId, its raw SHA-256 or its SHA-256 after CRLF→LF
normalisation matches any IFC file in the companion project tree `2026-AIC-RuleBridge-BIM` (index:
`lineage/rulebridge_index.json`, 787 files), except copies that exist only in internal development rounds and were
never reported in any submitted manuscript (this exception applies to `city_house_munich` only and is disclosed).

**Development set D** (catalogue developed on these and on the excluded R09 models): `city_house_munich`, `duplex`,
`fantasy_office_building_1`, `wbdg_office` (IFC-Bench v2, unchanged files from R09).

**Held-out set H.** Candidates are all IFC-Bench v2 projects not used in R09 and not already known to be in the
companion corpus (Schependomlaan and Smiley West are excluded a priori): `ettenheim_gis`, `fantasy_hotel_1`,
`fantasy_hotel_2`, `fantasy_office_building_2`, `fantasy_office_building_3`, `fantasy_residential_building_1`, `hitos`,
`molio`, `samuel_macalister_sample_house`, `sixty5`, `west_riverside_hospital`. Rules, applied in this order:
1. Only the architectural model is used (`arc.ifc`). A project without an architectural model is excluded
   (expected: `ettenheim_gis`, which provides a city model only). If the architectural model is provided in several
   schema versions, the newest schema is used (`west_riverside_hospital`: `arc_ifc4.ifc`).
2. Lineage rule above; any match excludes the model.
3. Inclusion: the file opens in IfcOpenShell 0.8.5 and extraction completes, and the model yields at least one check
   in at least two of the four rule families.
No other filtering. Files are stored unmodified in `data/external/ifc-bench-v2-heldout/projects/<project>/`, with
licence text and model card; their hashes are recorded in `lineage/heldout_lineage.json`.

**Occupancy.** Decided from the model card before extraction: the IRC applies to detached one- and two-family
dwellings and townhouses; every other use (offices, hotels, multi-family residential buildings, hospitals,
universities, unknown) uses the IBC.

## 5. Experiments (unchanged parameters from R09 unless stated)

- **E1** delivered-evidence audit at evidence levels min/std/full, rulebooks US and DE_DOOR.
- **E2** acquisition simulation, 200 hidden-state draws per model, costs clarify 1 / value 3, ε = 0.1 mm. Policies:
  single-source (pending-aware face value), completeness-first, confidence-gated τ ∈ {0.8, 0.9, 0.95, 0.99},
  value-only, random, model order, residual degree, EC², stability VOI, hindsight reference.
- **E3** robustness, 100 draws: value cost 1.5 and 6; DIN 18040-1 doors; misspecified catalogue (truth from
  catalogue widened by λ = 0.5, 1.0); conservative catalogue (planner on widened catalogue, truth from the same, and
  λ = 0.5 with truth from the declared catalogue); no geometry.
- **E4** withheld explicit values (definitions in `run_e4_validation.py::is_explicit`): explicit clear-width
  properties of doors; riser/tread attributes and properties of flights; railing-height properties; explicit
  clear-height properties of spaces. Suspected defaults are never references.

## 6. Endpoints

Primary analysis set: **H** (out-of-sample). D is reported as in-sample development data; D∪H is reported for
completeness.
- P1 (E1, H, full level, US): share of checks with a stable conclusion; share decided by the single-source checker
  without sufficient evidence; share where it contradicts the stable conclusion.
- P2 (E4, D∪H and H): error rate of stable conclusions from indirect evidence against withheld explicit values
  (exact binomial 95% CI), coverage, and the face-value baseline on the same checks; every disagreement is inspected
  and classified (data defect vs. method error).
- P3 (E2, H, full level): effort of stability VOI relative to completeness-first, residual degree, EC² and model
  order (paired over draws; Wilcoxon signed-rank), gap to the hindsight reference, wrong conclusions.
- P4 (E3, H): wrong conclusions under λ = 0.5 and 1.0 for stability VOI, value-only and completeness-first; effort
  premium of the conservative catalogue.
Between-model variability is reported with a model-level bootstrap (resampling models, 10,000 replicates).

## 7. Deviations

Any change to frozen code after the first held-out model is downloaded is recorded in `DEVIATIONS.md` with date,
reason and effect. Robustness fixes that do not change readings (for example handling a parse exception) are
allowed and recorded. A change that alters readings is reported with results both before and after; the frozen
version stays primary.
