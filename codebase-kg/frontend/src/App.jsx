import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import GraphCanvas from "./GraphCanvas";
import {
  deleteProject,
  getFileDetails,
  getGraph,
  getProject,
  getStatistics,
  listProjects,
  refreshProject,
  scanProject,
  searchProject,
} from "./api";
import "./App.css";

const EMPTY_STATS = {
  total_source_files: 0,
  total_python_files: 0,
  total_javascript_files: 0,
  total_internal_dependencies: 0,
  total_unresolved_imports: 0,
  total_detected_functions: 0,
  total_detected_classes: 0,
};

function StatusDot({ status }) {
  return <span className={`status-dot status-${status}`} title={status} />;
}

export default function App() {
  const [projects, setProjects] = useState([]);
  const [activeProjectId, setActiveProjectId] = useState(null);
  const [project, setProject] = useState(null);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [stats, setStats] = useState(EMPTY_STATS);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [fileDetails, setFileDetails] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState({ files: [], functions: [], classes: [] });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [scanForm, setScanForm] = useState({ name: "", path: "" });
  const pollRef = useRef(null);

  const activeProject = useMemo(
    () => projects.find((p) => p.id === activeProjectId) ?? project,
    [projects, activeProjectId, project]
  );

  const loadProjects = useCallback(async () => {
    try {
      const data = await listProjects();
      setProjects(data.projects ?? []);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const loadProjectData = useCallback(async (projectId) => {
    try {
      const [projectData, graphData, statsData] = await Promise.all([
        getProject(projectId),
        getGraph(projectId),
        getStatistics(projectId),
      ]);
      setProject(projectData.project);
      setGraph({ nodes: graphData.nodes ?? [], edges: graphData.edges ?? [] });
      setStats(statsData);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  // Allow deep links such as /?project=3
  const [initialProjectId] = useState(() => {
    const value = new URLSearchParams(window.location.search).get("project");
    return value && /^\d+$/.test(value) ? Number(value) : null;
  });

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    if (!initialProjectId) return;
    selectProject(initialProjectId);
    // Only auto-select the project encoded in the URL, once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialProjectId]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (activeProjectId) url.searchParams.set("project", String(activeProjectId));
    else url.searchParams.delete("project");
    window.history.replaceState({}, "", url);
  }, [activeProjectId]);

  // Clear the polling timer when the component unmounts.
  useEffect(() => () => clearInterval(pollRef.current), []);

  const startPolling = (projectId) => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const data = await getProject(projectId);
        if (data.project.status !== "scanning") {
          clearInterval(pollRef.current);
          await loadProjects();
          await loadProjectData(projectId);
        }
      } catch {
        clearInterval(pollRef.current);
      }
    }, 1200);
  };

  const selectProject = async (projectId) => {
    setActiveProjectId(projectId);
    setSelectedNodeId(null);
    setFileDetails(null);
    setQuery("");
    setResults({ files: [], functions: [], classes: [] });
    setError("");
    setNotice("");
    await loadProjectData(projectId);
  };

  const handleScan = async (event) => {
    event.preventDefault();
    if (!scanForm.name.trim() || !scanForm.path.trim()) {
      setError("Both a project name and a folder path are required.");
      return;
    }
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const response = await scanProject(scanForm.name.trim(), scanForm.path.trim());
      setNotice(response.message ?? "Scan started");
      setScanForm({ name: "", path: "" });
      await loadProjects();
      await selectProject(response.project_id);
      startPolling(response.project_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRescan = async () => {
    if (!activeProjectId) return;
    setError("");
    try {
      await refreshProject(activeProjectId);
      setNotice("Rescan started");
      await loadProjects();
      startPolling(activeProjectId);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async (event, projectId) => {
    event.stopPropagation();
    setError("");
    try {
      await deleteProject(projectId);
      if (projectId === activeProjectId) {
        setActiveProjectId(null);
        setProject(null);
        setGraph({ nodes: [], edges: [] });
        setStats(EMPTY_STATS);
        setSelectedNodeId(null);
        setFileDetails(null);
      }
      await loadProjects();
    } catch (err) {
      setError(err.message);
    }
  };

  // Search (debounced)
  useEffect(() => {
    if (!activeProjectId) return;
    const trimmed = query.trim();
    if (!trimmed) {
      setResults({ files: [], functions: [], classes: [] });
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const data = await searchProject(activeProjectId, trimmed);
        setResults({
          files: data.files ?? [],
          functions: data.functions ?? [],
          classes: data.classes ?? [],
        });
      } catch (err) {
        setError(err.message);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [query, activeProjectId]);

  // Load details for the selected node.
  useEffect(() => {
    if (!activeProjectId || selectedNodeId == null) {
      setFileDetails(null);
      return;
    }
    let cancelled = false;
    getFileDetails(activeProjectId, selectedNodeId)
      .then((data) => {
        if (!cancelled) setFileDetails(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [activeProjectId, selectedNodeId]);

  const focusSearchResult = (result) => {
    const fileId = result.file_id ?? result.id;
    if (fileId != null) setSelectedNodeId(fileId);
  };

  const scanning = activeProject?.status === "scanning";
  const resultCount =
    results.files.length + results.functions.length + results.classes.length;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">◈</span>
          <div>
            <div className="brand-title">Codebase KG</div>
            <div className="brand-sub">dependency explorer</div>
          </div>
        </div>

        <form className="scan-form" onSubmit={handleScan}>
          <h2>Scan a project</h2>
          <input
            type="text"
            placeholder="Project name"
            value={scanForm.name}
            onChange={(e) => setScanForm({ ...scanForm, name: e.target.value })}
          />
          <input
            type="text"
            placeholder="C:\path\to\project"
            value={scanForm.path}
            onChange={(e) => setScanForm({ ...scanForm, path: e.target.value })}
          />
          <button type="submit" disabled={busy}>
            {busy ? "Starting…" : "Analyse project"}
          </button>
        </form>

        <div className="sidebar-section">
          <h2>Projects</h2>
          {projects.length === 0 && <p className="muted">No projects yet.</p>}
          <ul className="project-list">
            {projects.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={`project-item ${item.id === activeProjectId ? "active" : ""}`}
                  onClick={() => selectProject(item.id)}
                >
                  <StatusDot status={item.status} />
                  <span className="project-name">{item.name}</span>
                  <span
                    className="project-remove"
                    role="button"
                    tabIndex={0}
                    title="Remove project"
                    onClick={(event) => handleDelete(event, item.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") handleDelete(event, item.id);
                    }}
                  >
                    ×
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        {activeProjectId && (
          <div className="sidebar-section">
            <h2>Search</h2>
            <input
              className="search-input"
              type="search"
              placeholder="Files, functions, classes…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {query.trim() && (
              <div className="search-results">
                {resultCount === 0 && <p className="muted">No matches.</p>}
                {results.files.map((file) => (
                  <button
                    key={`f-${file.id}`}
                    type="button"
                    className="search-result"
                    onClick={() => focusSearchResult(file)}
                  >
                    <span className="tag">{file.extension}</span>
                    {file.path}
                  </button>
                ))}
                {results.functions.map((fn) => (
                  <button
                    key={`fn-${fn.file_id}-${fn.name}`}
                    type="button"
                    className="search-result"
                    onClick={() => focusSearchResult(fn)}
                  >
                    <span className="tag tag-fn">fn</span>
                    {fn.name} <span className="muted">{fn.file}</span>
                  </button>
                ))}
                {results.classes.map((cls) => (
                  <button
                    key={`cls-${cls.file_id}-${cls.name}`}
                    type="button"
                    className="search-result"
                    onClick={() => focusSearchResult(cls)}
                  >
                    <span className="tag tag-cls">cls</span>
                    {cls.name} <span className="muted">{cls.file}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </aside>

      <main className="content">
        {error && (
          <div className="banner banner-error">
            {error}
            <button type="button" onClick={() => setError("")}>
              ×
            </button>
          </div>
        )}
        {notice && (
          <div className="banner banner-info">
            {notice}
            <button type="button" onClick={() => setNotice("")}>
              ×
            </button>
          </div>
        )}

        {!activeProjectId && (
          <section className="welcome">
            <h1>Understand a codebase at a glance</h1>
            <p>
              Point the analyser at a local Python or JavaScript project to map every
              file, its imports, functions and classes. Everything stays on this machine.
            </p>
            <ul>
              <li>Recursive discovery of .py, .js, .jsx, .mjs, .cjs, .ts and .tsx files</li>
              <li>Static analysis — no code is executed</li>
              <li>Interactive dependency graph with search and file inspection</li>
            </ul>
          </section>
        )}

        {activeProjectId && (
          <>
            <header className="project-header">
              <div>
                <h1>{activeProject?.name ?? "Project"}</h1>
                <p className="muted mono">{activeProject?.root_path}</p>
              </div>
              <div className="header-actions">
                <span className={`badge badge-${activeProject?.status ?? "unknown"}`}>
                  {scanning ? "scanning…" : activeProject?.status ?? "unknown"}
                </span>
                <button type="button" onClick={handleRescan} disabled={scanning}>
                  Rescan
                </button>
              </div>
            </header>

            <section className="stat-grid">
              <div className="stat-card">
                <span>Files</span>
                <strong>{stats.total_source_files}</strong>
              </div>
              <div className="stat-card">
                <span>Python</span>
                <strong>{stats.total_python_files}</strong>
              </div>
              <div className="stat-card">
                <span>JS / TS</span>
                <strong>{stats.total_javascript_files}</strong>
              </div>
              <div className="stat-card">
                <span>Internal links</span>
                <strong>{stats.total_internal_dependencies}</strong>
              </div>
              <div className="stat-card">
                <span>Unresolved</span>
                <strong>{stats.total_unresolved_imports}</strong>
              </div>
              <div className="stat-card">
                <span>Functions</span>
                <strong>{stats.total_detected_functions}</strong>
              </div>
              <div className="stat-card">
                <span>Classes</span>
                <strong>{stats.total_detected_classes}</strong>
              </div>
            </section>

            <section className="workspace">
              <div className="graph-panel">
                {scanning ? (
                  <div className="graph-empty">Scanning project files…</div>
                ) : (
                  <GraphCanvas
                    apiNodes={graph.nodes}
                    apiEdges={graph.edges}
                    selectedNodeId={selectedNodeId}
                    onSelectNode={setSelectedNodeId}
                  />
                )}
              </div>

              <aside className="inspector">
                {!selectedNodeId && (
                  <div className="inspector-empty">
                    <h2>File inspector</h2>
                    <p className="muted">
                      Select a node in the graph, or use search, to see its imports,
                      dependents, functions and classes.
                    </p>
                  </div>
                )}

                {selectedNodeId && !fileDetails && (
                  <div className="inspector-empty">
                    <p className="muted">Loading file details…</p>
                  </div>
                )}

                {fileDetails && (
                  <>
                    <h2 className="mono">{fileDetails.file.relative_path}</h2>
                    <p className="muted">
                      {fileDetails.file.file_extension} ·{" "}
                      {fileDetails.import_count} imports ·{" "}
                      {fileDetails.dependents_count} dependents
                    </p>

                    <h3>Imports ({fileDetails.import_count})</h3>
                    {fileDetails.imports.length === 0 && (
                      <p className="muted">No imports detected.</p>
                    )}
                    <ul className="link-list">
                      {fileDetails.imports.map((dep, index) => (
                        <li key={`imp-${index}`}>
                          {dep.target_file_id ? (
                            <button
                              type="button"
                              className="link-button mono"
                              onClick={() => setSelectedNodeId(dep.target_file_id)}
                            >
                              {dep.target_path}
                            </button>
                          ) : (
                            <span className={`muted mono`}>
                              {dep.import_statement}{" "}
                              <span className="tag">{dep.import_type}</span>
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>

                    <h3>Imported by ({fileDetails.dependents_count})</h3>
                    {fileDetails.imports_to.length === 0 && (
                      <p className="muted">Nothing imports this file.</p>
                    )}
                    <ul className="link-list">
                      {fileDetails.imports_to.map((dep, index) => (
                        <li key={`dep-${index}`}>
                          <button
                            type="button"
                            className="link-button mono"
                            onClick={() => setSelectedNodeId(dep.source_file_id)}
                          >
                            {dep.source_path}
                          </button>
                        </li>
                      ))}
                    </ul>

                    <h3>Functions ({fileDetails.functions.length})</h3>
                    {fileDetails.functions.length === 0 && (
                      <p className="muted">No functions detected.</p>
                    )}
                    <ul className="symbol-list">
                      {fileDetails.functions.map((fn) => (
                        <li key={`fn-${fn.name}-${fn.line_number}`}>
                          <span className="mono">{fn.name}</span>
                          <span className="muted"> line {fn.line_number}</span>
                        </li>
                      ))}
                    </ul>

                    <h3>Classes ({fileDetails.classes.length})</h3>
                    {fileDetails.classes.length === 0 && (
                      <p className="muted">No classes detected.</p>
                    )}
                    <ul className="symbol-list">
                      {fileDetails.classes.map((cls) => (
                        <li key={`cls-${cls.name}-${cls.line_number}`}>
                          <span className="mono">{cls.name}</span>
                          <span className="muted"> line {cls.line_number}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </aside>
            </section>
          </>
        )}
      </main>
    </div>
  );
}