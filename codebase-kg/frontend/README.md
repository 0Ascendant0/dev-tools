# Frontend

React + Vite client for Codebase Knowledge Graph.

```bash
npm install
npm run dev     # dev server on :5173, proxies /api and /health to :8000
npm run build   # production build in dist/
npm run lint    # oxlint
```

Start the backend first (`uvicorn main:app --port 8000` inside `../backend`), otherwise
API calls will fail with a proxy/connection error.

- `src/App.jsx` — app shell: project scanning, project list, search, inspector.
- `src/GraphCanvas.jsx` — React Flow graph, layered layout, selection panning.
- `src/api.js` — fetch helpers for the backend endpoints.
