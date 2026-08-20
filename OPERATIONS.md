# RiskRoute operations

RiskRoute deploys as a Next.js frontend, a FastAPI backend, and PostgreSQL 16 with PostGIS 3.4. The checked-in Compose stack is for local and single-host validation. Production should use managed PostGIS, a secret manager, independently scalable frontend/backend services, TLS at the edge, and a private data-import runner.

## Local deployment

1. Copy `.env.example` to `.env`. Keep the demo defaults for a local evaluation and add public Mapbox tokens if available.
2. Run `docker compose up --build --detach`. Compose waits for PostGIS, runs Alembic once, then starts the API and frontend. Use `docker compose ps` to confirm the backend and frontend are healthy.
3. Open `http://localhost:3000`. Liveness is `GET http://localhost:8000/health`; dependency and data readiness is `GET http://localhost:8000/ready`.
4. Stop services with `docker compose down`. Add `--volumes` only when deliberately discarding the local database.

For production set `APP_MODE=production`, `ENVIRONMENT=production`, `ALLOW_MOCK_MAPBOX=false`, `SEED_DEMO_DATA=false`, an exact HTTPS `CORS_ORIGINS` allowlist, a server-side `MAPBOX_ACCESS_TOKEN`, and a TLS-enabled managed PostGIS `DATABASE_URL`. `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_MAPBOX_TOKEN` are public build-time values and must be supplied while building the frontend image. Never put a secret Mapbox token in a `NEXT_PUBLIC_*` variable.

## Migrations and releases

Run migrations as a one-shot release job before shifting traffic:

```bash
docker compose run --rm migrate
```

In a managed environment, run the same backend image with `alembic upgrade head`. Permit only one migration job at a time, take a database snapshot first, and inspect the revision SQL in staging. Do not run `Base.metadata.create_all()` as a production migration mechanism.

Build each image once in CI, record its content digest, and promote that exact digest from staging to production; never rebuild during promotion. Staging and production must have separate databases, Mapbox tokens, CORS allowlists, object-storage prefixes, and secret-manager entries. Run migrations, readiness checks, a fixed Dallas route-analysis smoke test, and a report create/open/delete smoke test in staging before production approval.

A release is ready for traffic only when `/health` returns 200, `/ready` returns 200, the database reports PostGIS installed, and the data-status response names an active, in-policy Dallas crash snapshot. A model may remain a documented historical fallback, but a model promotion must pass its recorded calibration and baseline gates.

## Backups, restore, and rollback

- Enable managed point-in-time recovery and daily encrypted snapshots. Retain at least 35 days; test restoration quarterly in an isolated account/project.
- Before a migration or data promotion, record the application image digest, Alembic revision, dataset version/checksum, model version/checksum, and create an on-demand database snapshot.
- For a logical backup, use `pg_dump --format=custom --no-owner --no-acl "$DATABASE_URL" > riskroute.dump` from a restricted host. Store it encrypted outside the repository. Do not print the DSN or place dumps in CI artifacts.
- Restore into an empty database with PostGIS enabled, then run `pg_restore --clean --if-exists --no-owner --no-acl --dbname "$RESTORE_DATABASE_URL" riskroute.dump`. Validate row counts, dataset checksums, spatial indexes, `/ready`, and a fixed Dallas route-analysis smoke test before cutover.
- Roll back application code by redeploying the previous immutable image digest. Prefer a forward database fix. Use `alembic downgrade <revision>` only when the revision's downgrade was rehearsed and no newer writes would be lost; otherwise restore the pre-release snapshot and repoint traffic.

## Dallas data schedule and CRIS boundary

The `Sync Dallas public exposure data` workflow runs Mondays at 08:23 UTC and refreshes only the public FHWA HPMS exposure layer incrementally. Manual runs can request a full exposure refresh. It has no crash/all option: the public Dallas 2019 crash layer is stale bootstrap data and must never overwrite the canonical production `dallas_crashes` metadata. That bootstrap source may be loaded only into an isolated nonproduction database.

Current TxDOT CRIS acquisition is a human access boundary:

1. An individually authorized operator signs in to TxDOT CRIS, accepts the applicable terms, and exports only approved crash-level Dallas/North Dallas fields. Do not automate credentials, MFA, CAPTCHA, or browser download.
2. Place the extract in encrypted, access-logged production object storage with a short retention policy. Do not email it, add it to Git, upload it as a GitHub artifact, or place it in a container image.
3. From a private import runner, mount one read-only extract and run `python -m app.scripts.ingest_cris_extract --input <mounted.csv> --usage-approved --promote`. The approval flag is an operator assertion; retain the legal/data-owner approval separately.
4. Review rejection rate, coverage, freshness, checksum, and the candidate/active status in `dataset_metadata`. Delete the runner copy after the retention policy and preserve only approved normalized records and non-sensitive validation metadata.
5. Train a candidate with `python -m app.scripts.train_risk_model`. Promotion requires the explicit `--promote` flag and every evaluation gate; archive its immutable artifacts in protected model storage before deploying the corresponding image or artifact reference.

The workflow needs the `dallas-data` GitHub Environment and a masked `DALLAS_SYNC_DATABASE_URL` environment secret. The DSN should identify a least-privilege migration/import role, require TLS, and reach the database through an allowlisted or private-network runner. No CRIS file or credential belongs in GitHub Secrets because this workflow never downloads CRIS.

Schedule `python -m app.scripts.purge_expired_reports` as a daily one-shot production job (recommended 06:15 UTC, outside the ingestion window). Use the same immutable backend image, a least-privilege database role, no public ingress, and concurrency policy that prevents overlapping purges. Before first activation, confirm the approved policy for legacy rows whose `expires_at` is null. Run the job with `--dry-run` after every retention-policy change, compare its count with an independent query, alert on failures, and rely on database backups—not expired reports—for disaster recovery.

## Monitoring and incident response

Monitor `/health` for process liveness and `/ready` for database/PostGIS/data readiness. Alert on sustained 5xx rate, p95/p99 latency, Mapbox error/quota rate, connection-pool saturation, database CPU/storage/replica lag, ingestion failures, rejected-row ratio, dataset age, and model/data version drift. Logs should be structured, centralized, access-controlled, and searchable by `X-Request-ID`; never log route ownership tokens, database URLs, Mapbox tokens, or raw CRIS records.

When readiness fails, keep the instance out of service, inspect dependency details and the latest ingestion run, and avoid bypassing freshness or licensing gates. For a data incident, freeze sync/promotion, record dataset and model checksums, roll back to the last approved versions, and notify the data owner. For an application incident, roll back the image first and preserve database evidence.
