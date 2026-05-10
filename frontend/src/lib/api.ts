const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") ? "http://localhost:8001" : "");

export async function api(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", "Bypass-Tunnel-Reminder": "*", ...options?.headers },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${res.status}: ${err}`);
  }
  return res.json();
}

export async function apiUpload(path: string, files: File[]) {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", body: formData, headers: { "Bypass-Tunnel-Reminder": "*" } });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

// ── Project APIs ───────────────────────────────────
export const listProjects = () => api("/api/projects");
export const createProject = (name: string) =>
  api("/api/projects", { method: "POST", body: JSON.stringify({ client_name: name }) });
export const getProject = (id: string) => api(`/api/projects/${id}`);
export const getLatestConfig = (id: string) => api(`/api/projects/${id}/configs/latest`);
export const listConfigs = (id: string) => api(`/api/projects/${id}/configs`);
export const getConfigFile = (id: string, filename: string) =>
  api(`/api/projects/${id}/configs/${filename}`);
export const saveConfigFile = (id: string, filename: string, content: any) =>
  api(`/api/projects/${id}/configs/${filename}`, { method: "PUT", body: JSON.stringify(content) });
export const getCredentials = (id: string) =>
  api(`/api/projects/${id}/credentials`);
export const saveCredentials = (id: string, credentials: any[]) =>
  api(`/api/projects/${id}/credentials`, { method: "PUT", body: JSON.stringify({ credentials }) });

// ── Pipeline APIs ──────────────────────────────────
export const uploadDocs = (id: string, files: File[]) =>
  apiUpload(`/api/projects/${id}/upload`, files);
export const runPipeline = (id: string) =>
  api(`/api/projects/${id}/run-pipeline`, { method: "POST" });
export const getPipelineStatus = (id: string) => api(`/api/projects/${id}/status`);
export const runDetailedSimulation = (id: string) =>
  api(`/api/projects/${id}/simulate-detailed`, { method: "POST" });
export async function rerunPipeline(id: string, files: File[]) {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  const res = await fetch(`${API_BASE}/api/projects/${id}/rerun-pipeline`, { method: "POST", body: formData, headers: { "Bypass-Tunnel-Reminder": "*" } });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Rerun failed: ${res.status} — ${err}`);
  }
  return res.json();
}
export const migrateVersion = (id: string, integrationId: string, targetVersion?: string) =>
  api(`/api/projects/${id}/migrate-version`, {
    method: "POST",
    body: JSON.stringify({ integration_id: integrationId, target_version: targetVersion || null }),
  });

// ── Review APIs ────────────────────────────────────
export const approveConfig = (id: string) =>
  api(`/api/projects/${id}/review`, {
    method: "POST",
    body: JSON.stringify({ action: "approve" }),
  });
export const requestChanges = (id: string, feedback: string) =>
  api(`/api/projects/${id}/review`, {
    method: "POST",
    body: JSON.stringify({ action: "request_changes", feedback_text: feedback }),
  });

// ── Artifact APIs ──────────────────────────────────
export const diffConfigs = (id: string, v1: string, v2: string) =>
  api(`/api/projects/${id}/configs/diff?v1=${encodeURIComponent(v1)}&v2=${encodeURIComponent(v2)}`);
export const listSimReports = (id: string) => api(`/api/projects/${id}/simulation-reports`);
export const getSimReport = (id: string, filename: string) =>
  api(`/api/projects/${id}/simulation-reports/${filename}`);
export const getAuditLog = (id: string) => api(`/api/projects/${id}/audit`);
export const getReasoningReport = (id: string) => api(`/api/projects/${id}/reasoning-report`);

// ── Catalog APIs ───────────────────────────────────
export const listAdapters = () => api("/api/catalogs/adapters");
export const getAdapter = (id: string) => api(`/api/catalogs/adapters/${id}`);
export const listHooks = () => api("/api/catalogs/hooks");
export const getHook = (id: string) => api(`/api/catalogs/hooks/${id}`);

export async function uploadAdapter(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/catalogs/adapters/upload`, { method: "POST", body: formData, headers: { "Bypass-Tunnel-Reminder": "*" } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function uploadHook(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/catalogs/hooks/upload`, { method: "POST", body: formData, headers: { "Bypass-Tunnel-Reminder": "*" } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}
