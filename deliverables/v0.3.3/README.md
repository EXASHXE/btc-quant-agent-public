# v0.3.3 Delivery Bundle

Classification: `GEOMETRY_AUDIT_COMPLETE`

Strategy status: `EXPERIMENTAL` · execution disabled · Holdout sealed / not accessed

This folder contains copies of the v0.3.3 human-readable delivery documents:

- `V0.3.3_GEOMETRY_EXCURSION_REPORT.md` — primary report with all numeric answers
- `V0.3.3_NUMERIC_ANSWERS.json` — the 13 mandated numeric answers in machine-readable form

Machine-readable outputs live under `artifacts/research/v0.3.3_geometry_20260827T120000Z/`
(protocol, data manifest, tp_geometry.parquet, br_geometry_reference.parquet,
excursion/reachability/barrier parquet files, and all JSON summaries). The report records
their provenance: git commit `fc001d783d4e10bf855096faee5ec24b70d84db9`, config hash
`52e176c8bdcfce94` (frozen research config), dataset checksum
`82d058b2e9e5bfbd20bf36026abec045fb778ddb72582277e0dac00846ae9901`, protocol checksum
`035aa3c492450c8fe33dce68131086c2e432b2887438b99caeb3ed8e24b0e003`, random seed 33.

Key verdicts: H6 SUPPORTED (stop too wide, insufficient alone), H7 SUPPORTED (entry too late,
binding single fix), H8 SUPPORTED (target too close). Next: v0.3.4 `E-GEO-ENTRY` minimal arm.
