# Import Provenance

## john-deere-ingestion

- source_repo: N/A (local creation)
- source_local_path: N/A
- source_ref: feat/john-deere-ingestion
- source_commit: N/A
- source_status: clean local creation
- source_path: my-farm-advisor/data-sources/john-deere-ingestion/
- destination_path: my-farm-advisor/data-sources/john-deere-ingestion/
- import_date: 2026-04-28
- exclusions: `.runtime/`, `node_modules/`, `dist/`, token stores, generated data exports, live sandbox evidence files
- local_modifications: New subskill created to ingest John Deere Operations Center data into the My Farm Advisor canonical farm tree. TypeScript tooling isolated to this directory only. Raw exports and normalized projections follow the grower/farm/field/asset conventions documented in `my-farm-advisor/README.md`. No upstream source was imported; all files are original.
- update_procedure: When updating, increment the version in `PLAYBOOK.md`, refresh the operation registry against the installed `deere-sdk`, rerun `npm run build && npm test`, run `./scripts/validate.sh` from the repo root, and update this provenance file with the new date and any new exclusions.
