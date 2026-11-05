const BASE = "/api/projects";

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body && body.detail) detail = body.detail;
    } catch {
      // response had no JSON body; keep the status message
    }
    throw new Error(detail);
  }
  return response.json();
}

export const listProjects = () => request(BASE);

export const getProject = (projectId) => request(`${BASE}/${projectId}`);

export const getGraph = (projectId) => request(`${BASE}/${projectId}/graph`);

export const getStatistics = (projectId) =>
  request(`${BASE}/${projectId}/statistics`);

export const getFileDetails = (projectId, fileId) =>
  request(`${BASE}/${projectId}/files/${fileId}`);

export const searchProject = (projectId, query) =>
  request(`${BASE}/${projectId}/search?query=${encodeURIComponent(query)}`);

export const scanProject = (name, path) =>
  request(
    `${BASE}/scan?project_name=${encodeURIComponent(name)}&project_path=${encodeURIComponent(path)}`,
    { method: "POST" }
  );

export const refreshProject = (projectId) =>
  request(`${BASE}/${projectId}/refresh`, { method: "POST" });

export const deleteProject = (projectId) =>
  request(`${BASE}/${projectId}`, { method: "DELETE" });
