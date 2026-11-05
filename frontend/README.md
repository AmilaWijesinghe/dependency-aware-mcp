# Frontend

Next.js dashboard for observing the backend's dependency-aware MCP workflows.
It consumes the FastAPI demo endpoints and server-sent events.

Use Node.js 24 and npm. From this directory:

```sh
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://127.0.0.1:3000`. The API defaults to `http://127.0.0.1:8000`;
set `NEXT_PUBLIC_API_URL` in `.env.local` to change it. This variable is public
browser configuration. Backend credentials belong in `../backend/.env`.

```sh
npm run typecheck
npm test
npm run build
npm run start
```

Run `npm run start` after a successful build for a production frontend preview.
Changes to `NEXT_PUBLIC_API_URL` require a rebuild for production.

For browser tests, install Google Chrome and ensure uv is on PATH and the backend
dependencies are installed. Run `npm run test:browser`. Playwright starts
`../backend/scripts/serve_demo_test_api.py` on port 8002 and the frontend on
port 3000; keep both ports free. Screenshots and test results are ignored by Git.

See [the demo guide](../docs/demo.md) for the real MongoDB/Ollama workflow.
