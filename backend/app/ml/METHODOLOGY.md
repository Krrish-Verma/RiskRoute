# RiskRoute Dallas ML lifecycle

## Estimand and score semantics

The model estimates the calibrated probability that an exposure-covered
`0.01`-degree Dallas-area road cell has at least one **reported crash** during
the documented target window (365 days by default). It does not estimate that
a route is safe, prevent crashes, or establish causation.

The runtime exposes two related values:

- `calibrated_probability` (`0..1`): the forecast event probability.
- `risk_percentile` (`0..100`): the midrank of that probability against the
  non-test training/calibration road-cell cohort. The legacy route scorer uses
  this percentile, not an uncalibrated classifier output.

Confidence bounds are Wilson 95% intervals for the observed event rate in the
corresponding calibration bin. They describe cohort calibration uncertainty,
not an individualized guarantee.

## Point-in-time feature contract

Only crashes in `history_start..history_end` are features. Target crashes in
`target_start..target_end` only define labels, and the windows cannot overlap.
AADT records must have `data_year <= history_end.year` by default. Demo rows are
excluded. The command refuses to run if the database cannot distinguish demo
and source provenance.

Exposure is calculated explicitly as:

```text
million VMT = AADT vehicles/day * road miles * calendar days / 1,000,000
```

Historical crash, severe-crash, and weighted-severity counts are divided by
historical million VMT and transformed with `log1p`. Other allowed features are
historical severity/context fractions, average AADT, covered road mileage,
arterial-road fraction, and AADT coverage. The same versioned function builds
training and prediction vectors. Missing exposure fails closed; the former
nearby-crash-count payload is not silently adapted.

## Validation design

Cells are grouped into coarse `4 x 4` cell spatial blocks. SHA-256 of the block,
plus the fixed seed, assigns the entire block to fit (60%), probability
calibration (20%), or final test (20%). This prevents the same or immediately
adjacent cells from crossing splits and makes membership stable across runs.

The primary random forest is fit only on the fit partition. A logistic Platt
map is learned only on the calibration partition. Final ROC AUC, PR AUC, Brier
score, ten-bin expected calibration error, risk-band event rates, and 0.1-degree
geographic subgroup results use the untouched test partition.

Two predeclared calibrated logistic baselines use the same partitions:

- Exposure only: AADT, road miles, road class, and exposure coverage.
- Historical rate only: crash, severe-crash, and severity rates per million
  VMT.

No demographic fields are present or used. The evaluation report records that
demographic bias could not be assessed and reports geographic performance
instead.

## Training gates

Production defaults reject training when any of these conditions fail:

- fewer than 200 eligible road cells;
- fewer than 20 target events or 20 target non-events;
- fewer than 20 rows, or fewer than three examples of either class, in any
  fit/calibration/test partition;
- less than 80% mapped-road-mile AADT coverage;
- less than 70% crash-to-eligible-exposure-cell coverage;
- absent Dallas road geometry, invalid/non-point-in-time AADT, missing dates,
  or an incomplete database model contract.

Lower thresholds exist as explicit CLI/test parameters, but should not be used
to publish a production model without a documented scientific review.

## Database assumptions

Training consumes these SQLAlchemy fields:

- `Crash(latitude, longitude, crash_date, crash_time, severity_score,
  intersection_related, is_demo, data_source)` and preferably `source_id` for
  deterministic deduplication.
- `RoadSegment(source_id, geometry_json, aadt, functional_class,
  length_meters, data_year)`, where geometry is GeoJSON `LineString` or
  `MultiLineString` in longitude/latitude order.

If `RiskCell` exists, the script upserts compatible fields including the cell
location, percentile, calibration interval, crash/exposure summaries, exact
features, and model/data versions. It never creates schema or migrations.

## Run and outputs

After authoritative crash and road/exposure ingestion and migrations:

```powershell
cd backend
$env:PYTHONPATH = "."
python -m app.scripts.train_risk_model
```

For a predeclared evaluation window, supply all four of `--history-start`,
`--history-end`, `--target-start`, and `--target-end`. If omitted, the latest
dated real crash anchors a three-year history followed by a one-year target.

The command writes atomically only after all data/training gates and evaluation
succeed. By default it writes a versioned candidate under
`models/candidates/<model_version>/` and registers it as `candidate`; it does
not replace the active runtime files.

- `risk_model.pkl`: versioned calibrated estimator bundle;
- `model_metrics.json`: evaluation, coverage, splits, baselines, calibration,
  geographic audit, and limitations;
- `model_manifest.json`: artifact/data/model versions, feature/training-source
  and runtime versions, SHA-256 checksums, geography, windows, and seed.

Use `--promote` to request activation. Promotion occurs only when ROC AUC, PR
AUC, Brier score, ECE, and comparisons with both declared baselines pass the
explicit policy. The registry archives the prior active version, marks the new
one active, copies its checksum-verified files to the canonical runtime paths,
and refreshes `RiskCell`. A failed promotion request remains a candidate and
returns an error. `ModelVersion` stores the full metrics, feature schema,
training/promotion thresholds, checksum, and training/promotion timestamps.

The runtime verifies artifact and evaluation checksums before loading. The old
unversioned pickle is intentionally rejected. Use `--dry-run` to evaluate
without writing artifacts or database state. A one-year 2019 bootstrap paired
with 2024 AADT fails point-in-time coverage and can never create or promote an
artifact; historical road vintages or later crash years are required.
