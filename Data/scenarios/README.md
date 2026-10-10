# Scenarios S01–S20 (SIMULATED)

Defined in `backend/app/simulation/scenarios.py` (single source). Each `SXX_slug/` holds `scenario.json` (bilingual metadata: observable behavior, ground truth, expected health response, abstention cases, limitations), the exact `config.json` with its seed, and the dataset files (`*.csv.gz` raw and normalized, ground truth, topology, faults).

```bash
cd backend
python -m app.simulation.scenarios           # regenerate scenarios, golden cases, fixtures, checksums
python -m app.simulation.scenarios --verify  # regenerate in a temp dir and compare with checksums.json
```

`checksums.json` stores SHA-256 of the uncompressed content of every generated file, so verification does not depend on the zlib build.
