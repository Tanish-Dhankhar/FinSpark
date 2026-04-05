"use client";
import { useEffect, useState, useRef } from "react";
import { listProjects, listAdapters, listHooks, getAdapter, getHook, uploadAdapter, uploadHook } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function DashboardPage() {
  const { role, clientId: boundClientId } = useAuth();
  const [projects, setProjects] = useState<any[]>([]);
  const [adapters, setAdapters] = useState<any[]>([]);
  const [hooks, setHooks] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [modal, setModal] = useState<{ type: "adapter" | "hook"; data: any } | null>(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [uploadModal, setUploadModal] = useState<"adapter" | "hook" | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    Promise.all([
      listProjects().then(setProjects).catch(() => {}),
      listAdapters().then((d: any) => setAdapters(d.adapters || [])).catch(() => {}),
      listHooks().then((d: any) => setHooks(d.hooks || [])).catch(() => {}),
    ]).finally(() => setLoaded(true));
  }, []);

  const openAdapter = async (id: string) => {
    setModalLoading(true);
    setModal({ type: "adapter", data: null });
    try {
      const data = await getAdapter(id);
      setModal({ type: "adapter", data });
    } catch { setModal(null); }
    finally { setModalLoading(false); }
  };

  const openHook = async (id: string) => {
    setModalLoading(true);
    setModal({ type: "hook", data: null });
    try {
      const data = await getHook(id);
      setModal({ type: "hook", data });
    } catch { setModal(null); }
    finally { setModalLoading(false); }
  };

  const refreshCatalogs = () => {
    listAdapters().then((d: any) => setAdapters(d.adapters || [])).catch(() => {});
    listHooks().then((d: any) => setHooks(d.hooks || [])).catch(() => {});
  };

  const handleUpload = async () => {
    if (!uploadFile || !uploadModal) return;
    setUploading(true);
    setUploadMsg(null);
    try {
      const fn = uploadModal === "adapter" ? uploadAdapter : uploadHook;
      const res = await fn(uploadFile);
      setUploadMsg({ ok: true, text: res.message || "Uploaded successfully!" });
      setUploadFile(null);
      refreshCatalogs();
      setTimeout(() => { setUploadModal(null); setUploadMsg(null); }, 1500);
    } catch (e: any) {
      setUploadMsg({ ok: false, text: e.message || "Upload failed" });
    } finally {
      setUploading(false);
    }
  };

  const STATUS_STYLE: Record<string, { bg: string; color: string; dot: string }> = {
    completed: { bg: "#ecfdf5", color: "#047857", dot: "#10b981" },
    "production-ready": { bg: "#ecfdf5", color: "#047857", dot: "#10b981" },
    approved: { bg: "#ecfdf5", color: "#047857", dot: "#10b981" },
    awaiting_review: { bg: "#fffbeb", color: "#b45309", dot: "#f59e0b" },
    pending: { bg: "#fffbeb", color: "#b45309", dot: "#f59e0b" },
    running: { bg: "#e8f0fe", color: "#0653c7", dot: "#3b82f6" },
    failed: { bg: "#fef2f2", color: "#b91c1c", dot: "#ef4444" },
  };

  const STATS = [
    { icon: "📁", label: "Active Projects", value: projects.length, color: "#0653c7", glowColor: "rgba(6, 83, 199, 0.06)" },
    { icon: "🔌", label: "Integration Adapters", value: adapters.length, color: "#0d9488", glowColor: "rgba(13, 148, 136, 0.06)" },
    { icon: "🪝", label: "Pipeline Hooks", value: hooks.length, color: "#7c3aed", glowColor: "rgba(124, 58, 237, 0.06)" },
  ];

  const CAT_BADGE: Record<string, string> = {
    bureau: "badge-blue", kyc: "badge-cyan", payment: "badge-emerald",
    banking: "badge-teal", gst: "badge-amber", document: "badge-violet",
    fraud: "badge-rose", messaging: "badge-rose",
  };

  const HOOK_TYPE_BADGE: Record<string, string> = {
    "pre-call": "badge-amber", "post-call": "badge-emerald", "post_call": "badge-emerald",
    retry: "badge-rose", audit: "badge-blue", validation: "badge-violet",
    "on-failure": "badge-rose",
  };

  // For client role, filter projects to only their bound project
  const visibleProjects = role === "client" && boundClientId
    ? projects.filter(p => p.client_id === boundClientId)
    : projects;

  // Client redirect: if client role lands on dashboard, send to their project
  useEffect(() => {
    if (role === "client" && boundClientId && loaded) {
      window.location.href = `/projects/${boundClientId}`;
    }
  }, [role, boundClientId, loaded]);

  return (
    <div>
      {/* Hero */}
      <div className={loaded ? "animate-in" : ""} style={{ marginBottom: 36 }}>
        <h1 style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-0.5px", lineHeight: 1.2, marginBottom: 8 }}>
          AI Integration <span className="gradient-text">Orchestrator</span>
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 15, maxWidth: 540, lineHeight: 1.6 }}>
          Transform requirement documents into production-ready integration configs — zero manual schema mapping.
        </p>
      </div>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 40 }}>
        {STATS.map((s, i) => (
          <div key={i} className="card stat-card"
            style={{
              padding: "22px 24px",
              animationDelay: `${i * 0.1}s`,
              // @ts-expect-error CSS custom property
              "--glow-color": s.glowColor,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                  <span style={{ fontSize: 18 }}>{s.icon}</span>
                  <span style={{ fontSize: 12.5, fontWeight: 500, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>{s.label}</span>
                </div>
                <div className={loaded ? "count-animate" : ""} style={{ fontSize: 36, fontWeight: 800, color: s.color, letterSpacing: "-1.5px", animationDelay: `${i * 0.15 + 0.2}s` }}>
                  {s.value}
                </div>
              </div>
              <div style={{ width: 48, height: 48, borderRadius: 12, background: s.glowColor, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22 }}>
                {s.icon}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Projects */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
        <h2 className="section-header">Projects</h2>
        <a href="/projects/new" className="btn-primary" style={{ fontSize: 13, padding: "8px 18px" }}>+ New Project</a>
      </div>

      {visibleProjects.length === 0 ? (
        <div className="card" style={{ padding: "56px 24px", textAlign: "center", marginBottom: 40 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📂</div>
          <p style={{ color: "var(--text-muted)", marginBottom: 16, fontSize: 14 }}>No projects yet. Create your first integration project.</p>
          <a href="/projects/new" className="btn-primary">Create Project</a>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 14, marginBottom: 40 }}>
          {visibleProjects.map((p, i) => {
            const st = STATUS_STYLE[p.status] || { bg: "#f1f5f9", color: "#475569", dot: "#94a3b8" };
            return (
              <a key={i} href={`/projects/${p.client_id}`} className="card card-interactive"
                style={{ padding: "20px 24px", textDecoration: "none", color: "inherit", display: "block" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                  <span style={{ fontSize: 15.5, fontWeight: 700, color: "var(--text-primary)" }}>{p.client_name}</span>
                  <span className="badge" style={{ background: st.bg, color: st.color, display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: st.dot, display: "inline-block" }} />
                    {p.status}
                  </span>
                </div>
                <div style={{ display: "flex", gap: 18, fontSize: 12.5, color: "var(--text-muted)", marginBottom: 6 }}>
                  <span>🆔 {p.client_id?.slice(0, 18)}</span>
                  <span>🔌 {p.integration_count} integrations</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-muted)", paddingTop: 8, borderTop: "1px solid var(--border-subtle)" }}>
                  <span>Config v{p.current_config_version}</span>
                  <span>{new Date(p.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</span>
                </div>
              </a>
            );
          })}
        </div>
      )}

      {/* Adapter Catalog — hidden for client role */}
      {role !== "client" && (<>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h2 className="section-header" style={{ marginBottom: 0 }}>Adapter Catalog</h2>
        <button className="btn-primary" style={{ fontSize: 13, padding: "8px 18px" }}
          onClick={() => { setUploadModal("adapter"); setUploadFile(null); setUploadMsg(null); }}>+ Add Adapter</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12, marginBottom: 40 }}>
        {adapters.map((a, i) => (
          <div key={i} className="card card-interactive" style={{ padding: "18px 22px" }}
            onClick={() => openAdapter(a.id)}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>{a.name}</span>
              <span className={`badge ${CAT_BADGE[a.category] || "badge-slate"}`}>{a.category}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-muted)" }}>
              <span>{(a.versions || []).length} version{(a.versions || []).length !== 1 ? "s" : ""}</span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ color: "#0653c7", fontWeight: 600 }}>{a.maturity_score}</span>/10 maturity
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Hook Library */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h2 className="section-header" style={{ marginBottom: 0 }}>Hook Library</h2>
        <button className="btn-primary" style={{ fontSize: 13, padding: "8px 18px" }}
          onClick={() => { setUploadModal("hook"); setUploadFile(null); setUploadMsg(null); }}>+ Add Hook</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(270px, 1fr))", gap: 12 }}>
        {hooks.map((h, i) => (
          <div key={i} className="card card-interactive" style={{ padding: "16px 22px", display: "flex", alignItems: "center", justifyContent: "space-between" }}
            onClick={() => openHook(h.id)}>
            <div>
              <span style={{ fontSize: 14, fontWeight: 600, display: "block" }}>{h.name}</span>
              <span style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 2, display: "block" }}>{h.id}</span>
            </div>
            <span className={`badge ${HOOK_TYPE_BADGE[h.type] || "badge-slate"}`}>{h.type}</span>
          </div>
        ))}
      </div>
      </>)}

      {/* ── Detail Modal ───────────────────────────── */}
      {modal && (
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 100,
            background: "rgba(0, 0, 0, 0.35)", backdropFilter: "blur(6px)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: 24,
          }}
          onClick={() => setModal(null)}
        >
          <div className="animate-in" onClick={e => e.stopPropagation()}
            style={{
              background: "white", borderRadius: 18,
              maxWidth: 740, width: "100%", maxHeight: "85vh",
              overflow: "hidden", display: "flex", flexDirection: "column",
              boxShadow: "0 24px 64px rgba(0, 0, 0, 0.18)",
            }}>
            {modalLoading || !modal.data ? (
              <div style={{ padding: 60, textAlign: "center" }}>
                <div className="spin-slow" style={{ width: 40, height: 40, borderRadius: 10, background: "var(--gradient-primary)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 20, color: "white", marginBottom: 12 }}>⚡</div>
                <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading details…</p>
              </div>
            ) : modal.type === "adapter" ? (
              <AdapterDetail data={modal.data} onClose={() => setModal(null)} />
            ) : (
              <HookDetail data={modal.data} onClose={() => setModal(null)} />
            )}
          </div>
        </div>
      )}

      {/* ── Upload Modal ────────────────────────────── */}
      {uploadModal && (
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 100,
            background: "rgba(0, 0, 0, 0.35)", backdropFilter: "blur(6px)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: 24,
          }}
          onClick={() => { if (!uploading) { setUploadModal(null); setUploadFile(null); setUploadMsg(null); } }}
        >
          <div className="animate-in" onClick={e => e.stopPropagation()}
            style={{
              background: "white", borderRadius: 18,
              maxWidth: 520, width: "100%",
              boxShadow: "0 24px 64px rgba(0, 0, 0, 0.18)",
              overflow: "hidden",
            }}>
            {/* Header */}
            <div style={{ padding: "24px 28px 0", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h2 style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.3px" }}>
                {uploadModal === "adapter" ? "Upload Adapter" : "Upload Hook"}
              </h2>
              <button onClick={() => { if (!uploading) { setUploadModal(null); setUploadFile(null); setUploadMsg(null); } }}
                style={{ background: "none", border: "none", fontSize: 22, color: "var(--text-muted)", cursor: "pointer", padding: "4px 8px", borderRadius: 8, transition: "background 0.15s" }}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-surface)")}
                onMouseLeave={e => (e.currentTarget.style.background = "none")}>✕</button>
            </div>
            <p style={{ padding: "6px 28px 0", color: "var(--text-secondary)", fontSize: 13.5, lineHeight: 1.5 }}>
              {uploadModal === "adapter"
                ? "Upload a .json file containing the adapter definition. The file should have an \"adapter_name\" field."
                : "Upload a .json file containing the hook definition. The file should have a \"hook_name\" field."}
            </p>

            {/* Body */}
            <div style={{ padding: "20px 28px 28px" }}>
              {/* Drop Zone */}
              <div
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={e => {
                  e.preventDefault(); setDragOver(false);
                  const f = e.dataTransfer.files[0];
                  if (f && f.name.endsWith(".json")) { setUploadFile(f); setUploadMsg(null); }
                  else setUploadMsg({ ok: false, text: "Please drop a .json file" });
                }}
                onClick={() => fileRef.current?.click()}
                style={{
                  border: `2px dashed ${dragOver ? "#0653c7" : "var(--border-subtle)"}`,
                  borderRadius: 14, padding: "36px 20px", textAlign: "center",
                  cursor: "pointer", transition: "all 0.2s",
                  background: dragOver ? "rgba(6, 83, 199, 0.04)" : "var(--bg-surface)",
                  marginBottom: 18,
                }}>
                <input ref={fileRef} type="file" accept=".json" style={{ display: "none" }}
                  onChange={e => {
                    const f = e.target.files?.[0];
                    if (f) { setUploadFile(f); setUploadMsg(null); }
                    e.target.value = "";
                  }} />
                {uploadFile ? (
                  <div>
                    <div style={{ fontSize: 32, marginBottom: 8 }}>📄</div>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>{uploadFile.name}</span>
                    <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginTop: 4 }}>
                      {(uploadFile.size / 1024).toFixed(1)} KB — Click or drop to replace
                    </span>
                  </div>
                ) : (
                  <div>
                    <div style={{ fontSize: 32, marginBottom: 8 }}>📁</div>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>Drop .json file here or click to browse</span>
                    <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginTop: 4 }}>Only .json files accepted</span>
                  </div>
                )}
              </div>

              {/* Feedback message */}
              {uploadMsg && (
                <div style={{
                  padding: "10px 14px", borderRadius: 10, marginBottom: 14, fontSize: 13, fontWeight: 500,
                  background: uploadMsg.ok ? "#ecfdf5" : "#fef2f2",
                  color: uploadMsg.ok ? "#047857" : "#b91c1c",
                  border: `1px solid ${uploadMsg.ok ? "rgba(5,150,105,0.15)" : "rgba(220,38,38,0.12)"}`,
                }}>
                  {uploadMsg.ok ? "✓ " : "✗ "}{uploadMsg.text}
                </div>
              )}

              {/* Actions */}
              <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
                <button
                  onClick={() => { setUploadModal(null); setUploadFile(null); setUploadMsg(null); }}
                  disabled={uploading}
                  style={{
                    padding: "10px 20px", borderRadius: 10, border: "1px solid var(--border-subtle)",
                    background: "white", fontSize: 13, fontWeight: 600, cursor: "pointer",
                    color: "var(--text-secondary)", transition: "all 0.15s",
                  }}>Cancel</button>
                <button
                  onClick={handleUpload}
                  disabled={!uploadFile || uploading}
                  className="btn-primary"
                  style={{
                    padding: "10px 24px", fontSize: 13,
                    opacity: (!uploadFile || uploading) ? 0.5 : 1,
                    cursor: (!uploadFile || uploading) ? "not-allowed" : "pointer",
                  }}>
                  {uploading ? "Uploading…" : "Upload"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


/* ── Adapter Detail Modal ───────────────────────── */

function AdapterDetail({ data, onClose }: { data: any; onClose: () => void }) {
  const CAT_BADGE: Record<string, string> = {
    bureau: "badge-blue", kyc: "badge-cyan", payment: "badge-emerald",
    banking: "badge-teal", gst: "badge-amber", document: "badge-violet",
    fraud: "badge-rose", messaging: "badge-rose",
  };

  return (
    <>
      {/* Header */}
      <div style={{ padding: "24px 28px 0", display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <h2 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.3px" }}>{data.adapter_name}</h2>
            <span className={`badge ${CAT_BADGE[data.category] || "badge-slate"}`}>{data.category}</span>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: 13.5, lineHeight: 1.5 }}>{data.description}</p>
        </div>
        <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 22, color: "var(--text-muted)", cursor: "pointer", padding: "4px 8px", borderRadius: 8, transition: "background 0.15s" }}
          onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-surface)")}
          onMouseLeave={e => (e.currentTarget.style.background = "none")}>✕</button>
      </div>

      {/* Body */}
      <div style={{ padding: "20px 28px 28px", overflowY: "auto", flex: 1 }}>
        {/* Connection Info */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 22 }}>
          <InfoCard label="Provider" value={data.provider} />
          <InfoCard label="Auth Type" value={data.auth_type} />
          <InfoCard label="Base URL" value={data.base_url} mono />
          <InfoCard label="Sandbox" value={data.sandbox_base_url} mono />
          <InfoCard label="Timeout" value={`${data.timeout_ms} ms`} />
          <InfoCard label="Fallback" value={data.fallback_adapter || "—"} />
        </div>

        {/* Credentials */}
        {(data.credential_env_vars || []).length > 0 && (
          <div style={{ marginBottom: 22 }}>
            <SectionLabel>Credential Env Vars</SectionLabel>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {data.credential_env_vars.map((v: string, i: number) => (
                <span key={i} style={{ padding: "4px 10px", background: "var(--bg-surface)", border: "1px solid var(--border-subtle)", borderRadius: 6, fontSize: 12, fontFamily: "monospace", color: "var(--accent-blue)" }}>{v}</span>
              ))}
            </div>
          </div>
        )}

        {/* Versions */}
        <SectionLabel>Versions ({(data.versions || []).length})</SectionLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 22 }}>
          {(data.versions || []).map((v: any, i: number) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", background: "var(--bg-surface)", borderRadius: 10, border: "1px solid var(--border-subtle)" }}>
              <span className="badge badge-blue" style={{ minWidth: 32, justifyContent: "center" }}>{v.version}</span>
              <span style={{ fontSize: 12, fontFamily: "monospace", color: "var(--text-secondary)", flex: 1 }}>{v.endpoint}</span>
              <span className={`badge ${v.status === "stable" ? "badge-emerald" : v.status === "deprecated" ? "badge-rose" : "badge-amber"}`}>
                {v.status}
              </span>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>maturity: <b style={{ color: "#0653c7" }}>{v.maturity_score}</b></span>
            </div>
          ))}
        </div>

        {/* Required Fields */}
        {(data.required_fields || []).length > 0 && (
          <>
            <SectionLabel>Required Fields ({data.required_fields.length})</SectionLabel>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 22 }}>
              {data.required_fields.map((f: any, i: number) => (
                <div key={i} style={{ padding: "10px 14px", background: "var(--bg-surface)", borderRadius: 10, border: "1px solid var(--border-subtle)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "#0653c7", fontFamily: "monospace" }}>{f.field_name}</span>
                    <span className="badge badge-slate">{f.type}</span>
                  </div>
                  <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{f.description}</span>
                  {f.validation && <span style={{ fontSize: 10.5, color: "var(--accent-amber)", display: "block", marginTop: 2 }}>⚡ {f.validation}</span>}
                </div>
              ))}
            </div>
          </>
        )}

        {/* Optional Fields */}
        {(data.optional_fields || []).length > 0 && (
          <>
            <SectionLabel>Optional Fields ({data.optional_fields.length})</SectionLabel>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 22 }}>
              {data.optional_fields.map((f: any, i: number) => (
                <div key={i} style={{ padding: "10px 14px", background: "var(--bg-surface)", borderRadius: 10, border: "1px solid var(--border-subtle)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", fontFamily: "monospace" }}>{f.field_name}</span>
                    <span className="badge badge-slate">{f.type}</span>
                  </div>
                  <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{f.description}</span>
                  {f.default_value && <span style={{ fontSize: 10.5, color: "var(--accent-teal)", display: "block", marginTop: 2 }}>default: {f.default_value}</span>}
                </div>
              ))}
            </div>
          </>
        )}

        {/* Response Schema */}
        {data.response_schema && (
          <>
            <SectionLabel>Response Schema</SectionLabel>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 22 }}>
              {Object.entries(data.response_schema).map(([key, val]: [string, any], i: number) => (
                <div key={i} style={{ padding: "10px 14px", background: "var(--bg-surface)", borderRadius: 10, border: "1px solid var(--border-subtle)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "#059669", fontFamily: "monospace" }}>{key}</span>
                    <span className="badge badge-slate">{val.type}</span>
                  </div>
                  <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{val.description}</span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Error Codes */}
        {data.error_codes && (
          <>
            <SectionLabel>Error Codes</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 22 }}>
              {Object.entries(data.error_codes).map(([code, msg]: [string, any], i: number) => (
                <div key={i} style={{ display: "flex", gap: 12, padding: "8px 14px", background: "var(--bg-surface)", borderRadius: 8, border: "1px solid var(--border-subtle)", fontSize: 12.5 }}>
                  <span style={{ fontWeight: 700, color: "#dc2626", fontFamily: "monospace", minWidth: 36 }}>{code}</span>
                  <span style={{ color: "var(--text-secondary)" }}>{msg}</span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Retry Policy */}
        {data.retry_policy && (
          <div style={{ display: "flex", gap: 12 }}>
            <InfoCard label="Max Retries" value={data.retry_policy.max_retries} />
            <InfoCard label="Backoff" value={data.retry_policy.backoff_strategy} />
          </div>
        )}
      </div>
    </>
  );
}


/* ── Hook Detail Modal ──────────────────────────── */

function HookDetail({ data, onClose }: { data: any; onClose: () => void }) {
  const HOOK_TYPE_BADGE: Record<string, string> = {
    "pre-call": "badge-amber", "post-call": "badge-emerald", "post_call": "badge-emerald",
    retry: "badge-rose", audit: "badge-blue", validation: "badge-violet",
    "on-failure": "badge-rose",
  };

  return (
    <>
      {/* Header */}
      <div style={{ padding: "24px 28px 0", display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <h2 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.3px" }}>{data.hook_name}</h2>
            <span className={`badge ${HOOK_TYPE_BADGE[data.hook_type] || "badge-slate"}`}>{data.hook_type}</span>
            {data.is_blocking && <span className="badge badge-rose">blocking</span>}
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: 13.5, lineHeight: 1.5 }}>{data.description}</p>
        </div>
        <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 22, color: "var(--text-muted)", cursor: "pointer", padding: "4px 8px", borderRadius: 8, transition: "background 0.15s" }}
          onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-surface)")}
          onMouseLeave={e => (e.currentTarget.style.background = "none")}>✕</button>
      </div>

      {/* Body */}
      <div style={{ padding: "20px 28px 28px", overflowY: "auto", flex: 1 }}>
        {/* Core Info */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 22 }}>
          <InfoCard label="Lifecycle" value={data.lifecycle_state} />
          <InfoCard label="Execution Order" value={data.execution_order} />
          <InfoCard label="Timeout" value={`${data.timeout_ms} ms`} />
          <InfoCard label="Audit On Trigger" value={data.audit_on_trigger ? "Yes" : "No"} />
          <InfoCard label="Blocking" value={data.is_blocking ? "Yes" : "No"} />
        </div>

        {/* Trigger Condition */}
        {data.trigger_condition && (
          <div style={{ marginBottom: 22 }}>
            <SectionLabel>Trigger Condition</SectionLabel>
            <div style={{ padding: "12px 16px", background: "var(--accent-blue-pale)", borderRadius: 10, border: "1px solid rgba(6, 83, 199, 0.12)", fontSize: 13, color: "var(--accent-blue)", fontWeight: 500 }}>
              {data.trigger_condition}
            </div>
          </div>
        )}

        {/* Applicable Adapters */}
        {(data.applicable_adapters || []).length > 0 && (
          <div style={{ marginBottom: 22 }}>
            <SectionLabel>Applicable Adapters</SectionLabel>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {data.applicable_adapters.map((a: string, i: number) => (
                <span key={i} className="badge badge-blue">{a === "*" ? "All Adapters" : a}</span>
              ))}
            </div>
          </div>
        )}

        {/* Input Parameters */}
        {(data.input_parameters || []).length > 0 && (
          <>
            <SectionLabel>Input Parameters ({data.input_parameters.length})</SectionLabel>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 22 }}>
              {data.input_parameters.map((p: any, i: number) => (
                <div key={i} style={{ padding: "10px 14px", background: "var(--bg-surface)", borderRadius: 10, border: "1px solid var(--border-subtle)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "#0653c7", fontFamily: "monospace" }}>{p.param_name}</span>
                    <span className="badge badge-slate">{p.type}</span>
                    {p.required && <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#dc2626", display: "inline-block" }} title="Required" />}
                  </div>
                  <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{p.description}</span>
                  {p.default_value && <span style={{ fontSize: 10.5, color: "var(--accent-teal)", display: "block", marginTop: 2 }}>default: {p.default_value}</span>}
                </div>
              ))}
            </div>
          </>
        )}

        {/* Output */}
        {data.output && (
          <div style={{ marginBottom: 22 }}>
            <SectionLabel>Output</SectionLabel>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div style={{ padding: "12px 14px", background: "#ecfdf5", borderRadius: 10, border: "1px solid rgba(5, 150, 105, 0.15)" }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#047857", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: 4 }}>On Success</span>
                <span style={{ fontSize: 12.5, color: "#065f46" }}>{data.output.on_success}</span>
              </div>
              <div style={{ padding: "12px 14px", background: "#fef2f2", borderRadius: 10, border: "1px solid rgba(220, 38, 38, 0.12)" }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#b91c1c", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: 4 }}>On Failure</span>
                <span style={{ fontSize: 12.5, color: "#991b1b" }}>{data.output.on_failure}</span>
              </div>
            </div>
          </div>
        )}

        {/* Payload Template */}
        {data.payload_template && (
          <div style={{ marginBottom: 22 }}>
            <SectionLabel>Payload Template</SectionLabel>
            <div className="json-viewer" style={{ padding: 14, fontSize: 12 }}>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                {JSON.stringify(data.payload_template, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {/* Credentials */}
        {(data.credential_env_vars || []).length > 0 && (
          <div style={{ marginBottom: 22 }}>
            <SectionLabel>Credential Env Vars</SectionLabel>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {data.credential_env_vars.map((v: string, i: number) => (
                <span key={i} style={{ padding: "4px 10px", background: "var(--bg-surface)", border: "1px solid var(--border-subtle)", borderRadius: 6, fontSize: 12, fontFamily: "monospace", color: "var(--accent-blue)" }}>{v}</span>
              ))}
            </div>
          </div>
        )}

        {/* Error Codes */}
        {data.error_codes && (
          <>
            <SectionLabel>Error Codes</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 22 }}>
              {Object.entries(data.error_codes).map(([code, msg]: [string, any], i: number) => (
                <div key={i} style={{ display: "flex", gap: 12, padding: "8px 14px", background: "var(--bg-surface)", borderRadius: 8, border: "1px solid var(--border-subtle)", fontSize: 12.5 }}>
                  <span style={{ fontWeight: 700, color: "#dc2626", fontFamily: "monospace", minWidth: 70 }}>{code}</span>
                  <span style={{ color: "var(--text-secondary)" }}>{msg}</span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Example Log */}
        {data.example_log_entry && (
          <div>
            <SectionLabel>Example Log Entry</SectionLabel>
            <div className="json-viewer" style={{ padding: 14, fontSize: 12 }}>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                {JSON.stringify(data.example_log_entry, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {/* Retry Policy */}
        {data.retry_policy && (
          <div style={{ display: "flex", gap: 12, marginTop: 22 }}>
            <InfoCard label="Max Retries" value={data.retry_policy.max_retries} />
            <InfoCard label="Backoff" value={data.retry_policy.backoff_strategy} />
            <InfoCard label="Initial Delay" value={`${data.retry_policy.initial_delay_ms} ms`} />
          </div>
        )}
      </div>
    </>
  );
}


/* ── Shared Helpers ─────────────────────────────── */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h4 style={{ fontSize: 11.5, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginBottom: 10 }}>
      {children}
    </h4>
  );
}

function InfoCard({ label, value, mono }: { label: string; value: any; mono?: boolean }) {
  return (
    <div style={{ flex: 1, padding: "10px 14px", background: "var(--bg-surface)", borderRadius: 10, border: "1px solid var(--border-subtle)" }}>
      <span style={{ fontSize: 10.5, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: 3 }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", fontFamily: mono ? "monospace" : "inherit", wordBreak: "break-all" }}>{value || "—"}</span>
    </div>
  );
}
