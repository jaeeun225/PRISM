# Private recommendation artifacts

Run these commands from the PRISM project directory with its existing `.venv`.
No package, data-version, or Secrets changes are required.

## 1. Map artifact hash and Cloud diagnostics

`ast.dump()` output changes between Python 3.12 and 3.13/3.14. Fingerprints now
use selected function source text with normalized line endings instead. The
source paths, operating system, and Python version are not hashed.

Rebuild and upload the map after updating `src/map_artifact.py`:

```powershell
.\.venv\Scripts\python.exe scripts\build_map_artifact.py
.\.venv\Scripts\python.exe scripts\upload_map_artifact.py "data\artifacts\scent-map-all-notes-2026-10-23-v7-1-1e0f69f1-logic-6f57ab80568c9447.parquet"
```

The filename printed by the builder is authoritative if calculation code or the
configured data version changes later. Existing private CSV and old artifacts
are retained. Reboot Cloud after pushing code and uploading the matching file,
since a failed artifact lookup may already be cached in the running app.

Server logs show `map artifact: loaded (file=..., N rows)` or
`map artifact: fallback (reason=missing|download_error|read_error|version_mismatch, ...)`.
They contain filenames and exception types, never keys, tokens, response bodies,
or signed URLs. A missing/invalid artifact uses the original CSV pipeline.

PyArrow 24.0 officially supports Python 3.14 and Linux; no requirements pin is
introduced here. Check the installed Cloud version and these logs before
attributing a failure to Parquet compatibility.

## 2. Recommendation artifact

Build from the same local processed CSV that was uploaded to Supabase:

```powershell
.\.venv\Scripts\python.exe scripts\build_recommendation_artifact.py
.\.venv\Scripts\python.exe scripts\upload_recommendation_artifact.py "data\artifacts\recommendation-all-notes-2026-10-23-v7-1-1e0f69f1-logic-3ff959de148b6dd0.zip"
```

The upload uses the existing URL/key/bucket from `.streamlit/secrets.toml` and
upserts into private `prism-data/map-artifacts/`, then downloads and compares
SHA-256. It refuses a public bucket or mismatched artifact. Keys are never printed.

For local-CSV mode, build a separate file with `--source local` (optionally
`--csv PATH`). Local mode's existing CSV-mtime version is preserved; its artifact
is read from `data/artifacts/` and is not uploaded by the Supabase upload command.

One ZIP contains only data, with no pickle/executable serialization:

- `manifest.json`: schema, data version, source, CSV object path/hash, logic hash,
  row/note counts and member SHA-256 checksums.
- `catalog.parquet`: `_id`, `Name`, `Brand`, sanitized `Image URL`. Its row order
  is the ID-to-matrix-row mapping.
- `accord.npy`: original float32 `(N, 14)` accord matrix.
- `notes.npz`: original float32 CSR matrix over all dataset notes, including
  original indices/indptr/data and the Top/Middle/Base weights.

This is separate from the map because recommendations retain every catalog row,
including rows with no valid map coordinates. The existing shared
`@st.cache_resource` stores the loaded catalog/matrices once per settings/logic
key. There is no CSV download, string parsing, or matrix construction on a hit.
Missing, corrupted or mismatched files log a safe reason and use the unchanged
`get_catalog()` / matrix builders. Ranking and deduplication are unchanged.

Both artifacts contain licensed data and must never be committed. `/data/artifacts/`,
`**/scent-map-*.parquet` and `**/recommendation-*.zip` are ignored.

## 3. Recommendation figure

The recommendation background has hover disabled. Only its unused hover payload
is omitted when creating a recommendation figure; full map hover and all
recommendation detail tooltips are retained. Coordinates, marker colors, highlight
sizes, ranks, jitter, zoom and trace order must remain identical. Standard
`st.plotly_chart` still sends a complete figure specification on each update.
