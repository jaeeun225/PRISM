# Private map artifacts

Never commit artifacts, CSVs or secrets. `data/artifacts/` and `scent-map-*.parquet` are ignored.
Run from the PRISM project root, using the existing private Supabase secrets.

```powershell
.\.venv\Scripts\python.exe scripts/build_map_artifact.py --source supabase
$artifact = Get-ChildItem -LiteralPath data/artifacts -Filter '*.parquet' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
.\.venv\Scripts\python.exe scripts/upload_map_artifact.py $artifact.FullName
```

The build uses the local processed CSV but labels the artifact for current Supabase app settings. Upload the matching CSV first using `scripts/upload_data.py` when the underlying dataset changes. Keep data versions synchronized. Build again after changing calculation/preparation logic; the filename automatically includes the data version and logic fingerprint.

Current artifact: `scent-map-all-notes-2026-10-23-v7-1-1e0f69f1-logic-94a29a26179116ce.parquet` (10,002,928 bytes).
It has already been uploaded to private `prism-data/map-artifacts/` and download-hash verified during implementation. No additional upload is needed for this version. Restart/reboot an existing app after upload so any prior missing-artifact fallback/resource cache is cleared.

For local-CSV mode, build with `--source local --csv data/processed/fragella_processed.csv`. This generates a separate filename including the local CSV mtime-based version. The app in `SCENT_DATA_SOURCE=local` reads that local file; it does not access Supabase for artifacts.

Missing, corrupt, wrong-schema, wrong-data-version or wrong-logic artifacts fall back to the original pipeline. CSV and map calculations are still available. Recommendation vectors continue to use the original complete catalog (including the one non-placeable row); the artifact supplies the shared map and recommendation highlight lookup only.

Parquet stores numeric/string/list columns; JSON schema metadata stores section angles, source version, logic fingerprint and source CSV SHA-256. No credentials or executable pickles are stored. Generation/import algorithms and recommendations remain unchanged. Lazy sklearn/scipy imports delay their cost until recommendation is used.

If Streamlit Secrets' SCENT_DATA_VERSION changes, rebuild and upload to the newly computed name. No new secret keys or packages are required. Artifacts exist only in private storage/local ignored paths.
