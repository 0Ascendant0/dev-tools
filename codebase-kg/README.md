# Codebase Knowledge Graph

A local-first developer tool that statically analyses Python and JavaScript/TypeScript
projects and renders their file dependencies as an interactive graph. No code is
executed, and nothing leaves your machine.

## What it does

- Recursively discovers `.py`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts` and `.tsx` files,
  skipping `node_modules`, `.git`, virtualenvs, `__pycache__`, `dist`, `build`,
  `coverage` and `.next`.
- Parses Python with the `ast` module and JavaScript/TypeScript with purpose-built
  tokenising rules (ESM, CommonJS and JSX forms).
- Extracts imports, exports, functions and classes per file.
- Resolves local imports — dotted Python modules, extension-less JS paths and
  `index.*` files — and records imports it cannot resolve.
- Stores everything in SQLite and exposes it through a FastAPI REST API.
- Visualises the dependency graph with React Flow: layer-by-layer layout, zoom, pan,
  drag, search and a per-file inspector.

## Stack

| Layer    | Technology                                    |
| -------- | --------------------------------------------- |
| Backend  | Python 3.10+, FastAPI, NetworkX, SQLite       |
| Frontend | React 19, Vite, `@xyflow/react` (React Flow)  |
| Analysis | Python `ast`, custom JS/TS rules              |

## Getting started

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

The API is served at `http://127.0.0.1:8000` (interactive docs at `/docs`).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`). The dev server proxies
`/api` and `/health` to the backend on port 8000.

### 3. Analyse a project

In the sidebar, enter a display name and the absolute path of a local project, then
press **Analyse project**. Scanning happens in a background task; the project list
shows a status dot and the dashboard refreshes when the scan completes.

Select a project to see its graph. Click any node (or a search result) to inspect the
file's imports, dependents, functions and classes. `/` accepts a `?project=<id>`
query parameter for direct links.

## API

All project routes are under `/api/projects`.

| Method | Path                          | Purpose                                  |
| ------ | ----------------------------- | ---------------------------------------- |
| GET    | `/health`                     | Service health check                     |
| POST   | `/scan?project_name=&project_path=` | Start a background scan            |
| GET    | `""`                          | List analysed projects                   |
| GET    | `/{id}`                       | Project metadata and file list           |
| DELETE | `/{id}`                       | Remove a project and its data            |
| POST   | `/{id}/refresh`               | Re-run the analysis                      |
| GET    | `/{id}/graph`                 | Nodes, edges and counts                  |
| GET    | `/{id}/cycles`                | Import cycles (file paths)               |
| GET    | `/{id}/statistics`            | File, dependency, function and class counts |
| GET    | `/{id}/files`                 | Discovered source files                  |
| GET    | `/{id}/files/{file_id}`       | Imports, dependents, functions, classes  |
| GET    | `/{id}/search?query=`         | Search files, functions and classes      |

## Project layout

```
codebase-kg/
├── backend/
│   ├── main.py                     # FastAPI app, CORS and router wiring
│   ├── database.py                 # SQLite schema and ProjectDB access layer
│   ├── requirements.txt
│   ├── api/
│   │   ├── scan.py                 # discovery, analysis pipeline, import resolution
│   │   ├── projects.py             # project CRUD, files, refresh
│   │   ├── graph.py                # graph and cycle endpoints
│   │   ├── search.py               # file/function/class search
│   │   └── stats.py                # project statistics
│   ├── parsers/
│   │   ├── python_parser.py        # AST-based Python analysis
│   │   └── javascript_parser.py    # JS/JSX/TS analysis
│   └── graph/
│       └── graph_builder.py        # NetworkX dependency graph
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # app shell: projects, search, inspector
│   │   ├── GraphCanvas.jsx         # React Flow graph and layered layout
│   │   ├── api.js                  # typed-ish API client helpers
│   │   ├── App.css                 # dark theme
│   │   └── main.jsx
│   └── vite.config.js              # dev proxy to the backend
└── tests/                          # pytest suite for parsers, DB, graph, scanning
```

## Tests

```bash
cd codebase-kg
python -m pytest tests -q
```

Covers Python and JS/TS extraction (including comment handling and CommonJS), the
SQLite layer (per-project path uniqueness, idempotent writes, cascade delete), import
resolution and file discovery, and graph construction, cycles and degree queries.

## Limitations

- Analysis is static; dynamic imports, `eval`/`exec`, and computed `require()` calls
  are not followed.
- Import resolution covers same-project files only — installed packages and path
  aliases (`@/…`) that are not relative paths stay unresolved.
- The database is a single local SQLite file (`backend/codebase_kg.db`) — intended for
  single-user, local use.
- No file watching: rescan a project to pick up changes.

## Licence

MIT
