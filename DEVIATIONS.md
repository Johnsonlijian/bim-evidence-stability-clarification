# Deviations from PREREGISTRATION.md

## D1 — lineage rule: ArchiCAD template project identifiers (2026-10-11, before any analysis of the models concerned)

**Pre-registered rule.** Exclude a model if its IfcProject GlobalId, raw SHA-256 or line-ending-normalised SHA-256
matches any IFC file of the companion project tree.

**Observation.** The held-out models `molio` (*Molio Demo-hus*) and `sixty5` (*Blok S1 Strijp S*) have no byte or
content match. Their only match is the IfcProject GlobalId `344O7vICcwH8qAEnwJDjSU`, which 156 files of the companion
tree also carry under four unrelated project names (*Projekt* ×151, *Smiley West* ×2, *Geldropseweg 47* ×2,
*10 Appartementen Schependomlaan* ×1). Two of the 787 indexed GlobalIds are shared by more than one project name.
The identifier is the project object of the ArchiCAD template, not a project identity; none of the 156 files carries
the name Molio or Strijp S.

**Change.** An IfcProject GlobalId match counts as same-project evidence only if the identifier is not a template
identifier, i.e. it is not shared by two or more distinct project names in the reference index. Byte and content
matches are unaffected. `molio` and `sixty5` are therefore retained; `samuel_macalister_sample_house` remains excluded
(byte-identical to `data_v2/realworld_multitool/revit_ifc4_rac_sample.ifc` of the companion corpus).

**Timing and safeguard.** Decided from lineage metadata only, before extraction or any result for these models.
All primary held-out results are additionally reported without `molio` and `sixty5` (strict pre-registered rule).

## Occupancy (pre-registered rule applied to model cards, no deviation)

All held-out models use the IBC: `fantasy_hotel_1`, `fantasy_hotel_2` (hospitality), `fantasy_office_building_2`,
`fantasy_office_building_3`, `hitos`, `molio` (office), `fantasy_residential_building_1` ("living", dwelling count not
stated, hence IBC by the default clause), `sixty5` (residential complex with 105 apartments), `west_riverside_hospital`.
