# Main FastAPI application
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Codebase Knowledge Graph API",
    description="A local-first developer tool for analyzing project dependencies and generating interactive graphs",
    version="0.1.0",
)

# CORS - allow the Vite dev server for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers already carry the /api/projects prefix, so include them as-is.
from api.scan import router as scan_router
from api.projects import router as projects_router
from api.graph import router as graph_router
from api.search import router as search_router
from api.stats import router as stats_router
from api.extensions import router as extensions_router

# Register the more specific routers first so their paths win over
# the /{project_id} catch-all in projects_router.
app.include_router(scan_router)
app.include_router(extensions_router)
app.include_router(graph_router)
app.include_router(search_router)
app.include_router(stats_router)
app.include_router(projects_router)


@app.get("/")
async def root():
    return {"message": "Codebase Knowledge Graph API", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}