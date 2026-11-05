# Development

The frontend and backend have independent dependencies and lockfiles. Run Python
commands from `backend/` so settings load `backend/.env`; run npm commands from
`frontend/`. Keep both lockfiles in Git and use `uv sync --locked` and `npm ci`
for reproducible installations.

## Backend tests

```sh
cd backend
uv run pytest
uv run python -m unittest scripts.test_phase6_runner
uv run python -m scripts.validate_heldout_scenarios
```

The tests use the real MCP transport, workflow, and conflict handling with
substitutes for MongoDB persistence and model inference. To run without a local
`.env`, set these environment variables to local test values:

```dotenv
MONGODB_URI=mongodb://127.0.0.1:27017
OLLAMA_MODEL=test-model
```

Historical SQLite modules and their obsolete tests were retired during the
repository restructure. The current runtime uses MongoDB; the old repository
methods, configuration, and server factory no longer match that implementation.
Those historical files remain recoverable in Git history. Existing local copies
were preserved in the ignored `.local-archive/` directory during cleanup.

## Frontend tests

```sh
cd frontend
npm run typecheck
npm test
npm run build
npm run test:browser
```

Browser tests need installed Chrome, uv on PATH, and the backend dependencies.
The test API on port 8002 uses isolated fixtures and does not require external
services. It is intended for automated tests. Live demonstrations use the normal
API on port 8000 with MongoDB, Ollama, and the MCP server.

The GitHub Actions workflow runs backend tests and frontend type checks, unit
tests, and a build. Browser tests and live model benchmarks are run locally.

## Generated files

Keep environments, local data, logs, test screenshots, build outputs, and report
exports out of Git. New benchmark exports go to `backend/results/`. The curated
snapshot in `reports/benchmarks/` is retained because the research report depends
on it. Updating the snapshot requires reviewing and regenerating the report.
