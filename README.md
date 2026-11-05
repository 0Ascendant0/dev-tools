# Codebase Knowledge Graph

A local-first developer tool that statically analyses Python and JavaScript/TypeScript
projects and renders their import dependencies as an interactive graph. Nothing is
executed and nothing leaves your machine.

The application lives in [`codebase-kg/`](codebase-kg); see
[`codebase-kg/README.md`](codebase-kg/README.md) for the full reference — every API
route, the database schema and the known limitations.

## Features

- Discovers `.py`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts` and `.tsx` files, skipping
  `node_modules`, `.git`, virtualenvs, `__pycache__`, `dist`, `build`, `coverage`,
  `.next`, `.tox` and `site-packages`.
- Parses Python with its `ast` module and JS/TS with purpose-built tokenising rules
  (ESM, CommonJS and JSX), extracting imports, exports, functions and classes.
- Resolves local imports — dotted Python modules, extension-less JS paths and
  `index.*` files — and reports the ones it cannot resolve.
- Stores results in SQLite behind a FastAPI REST API.
- Draws the graph with React Flow: layered layout, zoom, pan, drag, search and a
  per-file inspector. The API also reports import cycles.

## Stack

| Layer    | Technology                                    |
| -------- | --------------------------------------------- |
| Backend  | Python 3.10+, FastAPI, NetworkX, SQLite       |
| Frontend | React 19, Vite, `@xyflow/react` (React Flow)  |
| Analysis | Python `ast`, custom JS/TS rules               |

## Quickstart

Backend (port 8000):

```bash
cd codebase-kg/backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

Frontend (port 5173, proxies `/api` and `/health` to the backend):

```bash
cd codebase-kg/frontend
npm install
npm run dev
```

Then in the sidebar enter a display name and the absolute path of a local project
and press **Analyse project**. Scans run in the background; pick a project to walk
its graph and click any node to inspect that file.

## Layout

```
.
├── README.md
└── codebase-kg/
    ├── backend/       FastAPI app, parsers, graph builder, SQLite layer
    ├── frontend/      React + Vite UI
    ├── tests/         pytest suite for parsers, database, graph and scanning
    └── README.md      full project documentation
```

## Tests

```bash
cd codebase-kg
python -m pytest tests -q
```
