"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  getProject, getLatestConfig, getPipelineStatus,
  approveConfig, requestChanges,
  listSimReports, getSimReport, getAuditLog,
  listConfigs, getConfigFile, diffConfigs, saveConfigFile,
  getCredentials, saveCredentials, runDetailedSimulation,
  migrateVersion, getReasoningReport, rerunPipeline,
} from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const ALL_TABS = ["Overview", "Config", "Diff", "Integrations", "Simulation", "Credentials", "Audit"];

const STATUS_STYLE: Record<string, { bg: string; color: string; dot: string }> = {
  completed: { bg: "#ecfdf5", color: "#047857", dot: "#10b981" },
  approved: { bg: "#ecfdf5", color: "#047857", dot: "#10b981" },
  "production-ready": { bg: "#ecfdf5", color: "#047857", dot: "#10b981" },
  awaiting_review: { bg: "#fffbeb", color: "#b45309", dot: "#f59e0b" },
  pending: { bg: "#fffbeb", color: "#b45309", dot: "#f59e0b" },
  running: { bg: "#e8f0fe", color: "#0653c7", dot: "#3b82f6" },
  failed: { bg: "#fef2f2", color: "#b91c1c", dot: "#ef4444" },
  escalated: { bg: "#fef2f2", color: "#b91c1c", dot: "#ef4444" },
};

export default function ProjectDetailPage() {
  const { clientId: rawClientId } = useParams<{ clientId: string }>();
  const clientId = rawClientId as string;
  const { role, clientId: boundClientId } = useAuth();

  // Role-based tab filtering
  const TABS = role === "standard"
    ? ALL_TABS.filter(t => t !== "Credentials")
    : ALL_TABS;

  const [project, setProject] = useState<any>(null);
  const [config, setConfig] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [simReport, setSimReport] = useState<any>(null);
  const [auditLog, setAuditLog] = useState<any>(null);
  const [configFiles, setConfigFiles] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState("Overview");
  const [feedback, setFeedback] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewMsg, setReviewMsg] = useState("");
  const [loading, setLoading] = useState(true);
  const [showReasoning, setShowReasoning] = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [p, c, s] = await Promise.all([
        getProject(clientId), getLatestConfig(clientId), getPipelineStatus(clientId),
      ]);
      setProject(p); setConfig(c); setStatus(s);
      const reports = await listSimReports(clientId);
      if (reports.length > 0) {
        const r = await getSimReport(clientId, reports[reports.length - 1].filename);
        setSimReport(r);
      }
      const a = await getAuditLog(clientId);
      setAuditLog(a);
      const cfgFiles = await listConfigs(clientId).catch(() => []);
      setConfigFiles(cfgFiles);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [clientId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  useEffect(() => {
    if (!status) return;
    const isRunning = ["running", "stage_1", "stage_2", "stage_3", "stage_4", "stage_5", "stage_7"].some(
      s => status.stage?.includes(s) || status.status === "running"
    );
    if (!isRunning) return;
    const iv = setInterval(async () => {
      const s = await getPipelineStatus(clientId);
      setStatus(s);
      if (s.status === "awaiting_review" || s.status === "completed" || s.status === "failed") {
        clearInterval(iv); fetchAll();
      }
    }, 3000);
    return () => clearInterval(iv);
  }, [status, clientId, fetchAll]);

  const handleApprove = async () => {
    setReviewLoading(true); setReviewMsg("");
    try {
      const r = await approveConfig(clientId);
      setReviewMsg(r.message || "Approved!"); setTimeout(() => fetchAll(), 2000);
    } catch (e: any) { setReviewMsg(e.message); }
    finally { setReviewLoading(false); }
  };

  const handleRequestChanges = async () => {
    if (!feedback.trim()) return;
    setReviewLoading(true); setReviewMsg("");
    try {
      const r = await requestChanges(clientId, feedback);
      setReviewMsg(r.message || "Changes applied!"); setFeedback(""); setTimeout(() => fetchAll(), 1000);
    } catch (e: any) { setReviewMsg(e.message); }
    finally { setReviewLoading(false); }
  };

  if (loading) return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "60vh", gap: 16 }}>
      <div className="spin-slow" style={{ width: 40, height: 40, borderRadius: 10, background: "var(--gradient-primary)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, color: "white" }}>⚡</div>
      <span style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading project…</span>
    </div>
  );

  // Client role access gate
  if (role === "client" && boundClientId && boundClientId !== clientId) return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "60vh", gap: 16, textAlign: "center" }}>
      <div style={{ width: 56, height: 56, borderRadius: 14, background: "#fef2f2", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28 }}>🔒</div>
      <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>Access Restricted</h2>
      <p style={{ color: "var(--text-muted)", fontSize: 13, maxWidth: 360, lineHeight: 1.5 }}>
        Your client account (<code style={{ fontWeight: 600 }}>{boundClientId}</code>) does not have permission to access this project.
      </p>
      <a href={`/projects/${boundClientId}`} className="btn-primary" style={{ marginTop: 8, padding: "10px 24px", fontSize: 13 }}>
        Go to My Project →
      </a>
    </div>
  );

  if (!project) return <div style={{ textAlign: "center", padding: 48, color: "var(--text-muted)" }}>Project not found.</div>;

  const pipelineStatus = config?.metadata?.pipeline_run?.overall_status || status?.status || "unknown";
  const stStyle = STATUS_STYLE[pipelineStatus] || { bg: "#f1f5f9", color: "#475569", dot: "#94a3b8" };
  const isReview = pipelineStatus === "awaiting_review";
  const isRunning = status?.status === "running" || (status?.progress_percent > 0 && status?.progress_percent < 90);
  const integrations = config?.integrations || [];

  return (
    <div className="animate-in">
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 28 }}>
        <div>
          <a href="/" style={{ color: "var(--text-muted)", textDecoration: "none", fontSize: 13, display: "inline-flex", alignItems: "center", gap: 4, marginBottom: 8, transition: "color 0.15s" }}>
            ← Dashboard
          </a>
          <h1 style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-0.5px", marginBottom: 4 }}>{project.client_name}</h1>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            {clientId} • Config v{project.current_config_version} • {integrations.length} integrations
          </p>
        </div>
        <div className="badge" style={{
          background: stStyle.bg, color: stStyle.color,
          padding: "7px 16px", fontSize: 11.5,
          display: "flex", alignItems: "center", gap: 6,
          borderRadius: 8,
        }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: stStyle.dot, display: "inline-block" }}
            className={isRunning ? "status-dot-pulse" : ""} />
          {pipelineStatus.toUpperCase().replace("_", " ")}
        </div>
      </div>

      {/* Pipeline Progress */}
      {isRunning && status && (
        <div className="card" style={{ padding: 22, marginBottom: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
            <span style={{ fontSize: 13.5, fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
              <span className="spin-slow" style={{ fontSize: 14 }}>⚙️</span> Pipeline Running
            </span>
            <span style={{ fontSize: 14, fontWeight: 700, color: "var(--accent-blue)" }}>{status.progress_percent}%</span>
          </div>
          <div style={{ width: "100%", height: 5, background: "var(--bg-surface)", borderRadius: 99, overflow: "hidden" }}>
            <div className="progress-bar" style={{ width: `${status.progress_percent}%`, transition: "width 0.5s ease" }} />
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: 12.5, marginTop: 8 }}>{status.message}</p>
        </div>
      )}

      {/* Review Panel */}
      {isReview && (
        <div className="card" style={{ padding: 24, marginBottom: 20, borderLeft: "3px solid #f59e0b" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: "#fffbeb", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>👁️</div>
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 700 }}>Human Review Required</h3>
              <p style={{ color: "var(--text-muted)", fontSize: 12.5 }}>
                {integrations.length} integrations generated • Corrections: {config?.metadata?.pipeline_run?.correction_iterations || 0}/3
              </p>
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
            <button className="btn-success" onClick={handleApprove} disabled={reviewLoading}>
              {reviewLoading ? "Processing…" : "✓ Approve & Simulate"}
            </button>
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <input value={feedback} onChange={e => setFeedback(e.target.value)}
              placeholder='e.g. "Change Experian timeout to 20s"'
              onKeyDown={e => e.key === "Enter" && handleRequestChanges()}
              style={{
                flex: 1, padding: "10px 14px", borderRadius: 10, fontSize: 13.5,
                background: "var(--bg-input)", border: "1px solid var(--border-subtle)",
                color: "var(--text-primary)", outline: "none",
              }}
            />
            <button className="btn-secondary" onClick={handleRequestChanges} disabled={reviewLoading || !feedback.trim()}>
              Request Changes
            </button>
          </div>
          {reviewMsg && <p style={{ color: "var(--accent-emerald)", fontSize: 13, marginTop: 10 }}>{reviewMsg}</p>}
        </div>
      )}

      {/* Tabs */}
      <div className="tab-bar" style={{ marginBottom: 22 }}>
        {TABS.map(t => (
          <button key={t} className={`tab-item ${activeTab === t ? "active" : ""}`} onClick={() => setActiveTab(t)}>{t}</button>
        ))}
      </div>

      {/* Tab Content */}
      <div key={activeTab} className="animate-in">
        {activeTab === "Overview" && <OverviewTab project={project} config={config} simReport={simReport} configFiles={configFiles} clientId={clientId} onRerun={fetchAll} />}
        {activeTab === "Config" && (
          <div style={{ display: "flex", gap: 18, alignItems: "stretch", height: 750 }}>
            {/* Toggle Button */}
            <button
              onClick={() => setShowReasoning(!showReasoning)}
              title={showReasoning ? "Hide Reasoning Report" : "Show Reasoning Report"}
              style={{
                position: "sticky", top: 20, flexShrink: 0,
                width: 36, height: 36, borderRadius: 9,
                background: showReasoning ? "linear-gradient(135deg, #0653c7, #3b82f6)" : "white",
                border: showReasoning ? "none" : "1px solid var(--border-subtle)",
                color: showReasoning ? "white" : "var(--text-muted)",
                cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.25s cubic-bezier(0.4,0,0.2,1)",
                boxShadow: showReasoning ? "0 4px 14px rgba(6,83,199,0.3)" : "var(--shadow-sm)",
                zIndex: 10,
              }}
              onMouseEnter={e => { if (!showReasoning) { e.currentTarget.style.borderColor = "#0653c7"; e.currentTarget.style.color = "#0653c7"; }}}
              onMouseLeave={e => { if (!showReasoning) { e.currentTarget.style.borderColor = "var(--border-subtle)"; e.currentTarget.style.color = "var(--text-muted)"; }}}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
              </svg>
            </button>

            {/* Reasoning Panel (Left) */}
            <div style={{
              width: showReasoning ? 480 : 0,
              minWidth: showReasoning ? 480 : 0,
              opacity: showReasoning ? 1 : 0,
              overflow: "hidden",
              transition: "all 0.35s cubic-bezier(0.4,0,0.2,1)",
              flexShrink: 0,
              display: "flex", flexDirection: "column",
            }}>
              {showReasoning && <ReasoningTab clientId={clientId} />}
            </div>

            {/* Config (takes remaining space) */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <ConfigTab config={config} configFiles={configFiles} clientId={clientId} onConfigSaved={fetchAll} />
            </div>
          </div>
        )}
        {activeTab === "Credentials" && <CredentialsTab clientId={clientId} />}
        {activeTab === "Diff" && <DiffTab configFiles={configFiles} clientId={clientId} />}
        {activeTab === "Integrations" && <IntegrationsTab integrations={integrations} clientId={clientId} onMigrated={fetchAll} />}
        {activeTab === "Simulation" && <SimulationTab report={simReport} clientId={clientId} />}
        {activeTab === "Audit" && <AuditTab auditLog={auditLog} clientId={clientId} />}
      </div>
    </div>
  );
}

/* ── Tab Components ─────────────────────────────── */

function OverviewTab({ project, config, simReport, configFiles, clientId, onRerun }: any) {
  const meta = config?.metadata || {};
  const pr = meta.pipeline_run || {};

  // Upload Updated Documents state
  const [showUpload, setShowUpload] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files).filter(
      f => f.name.endsWith(".pdf") || f.name.endsWith(".docx") || f.name.endsWith(".txt") || f.name.endsWith(".json")
    );
    setUploadFiles(prev => [...prev, ...dropped]);
  };

  const handleRerun = async () => {
    if (uploadFiles.length === 0) return;
    setUploading(true); setUploadMsg("");
    try {
      const r = await rerunPipeline(clientId, uploadFiles);
      setUploadMsg(r.message || "Pipeline re-run started!");
      setUploadFiles([]); setShowUpload(false);
      if (onRerun) setTimeout(() => onRerun(), 1500);
    } catch (e: any) { setUploadMsg(e.message || "Failed to start re-run"); }
    finally { setUploading(false); }
  };

  return (
    <div>
      {/* Top row: Client Details + Pipeline Run + Simulation */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 16 }}>
        <div className="card" style={{ padding: 24 }}>
          <h3 style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.6px" }}>Client Details</h3>
          <InfoRow label="Name" value={meta.client?.client_name} />
          <InfoRow label="ID" value={meta.client?.client_id} />
          <InfoRow label="Industry" value={meta.client?.industry_vertical} />
          <InfoRow label="Region" value={meta.client?.region} />
        </div>
        <div className="card" style={{ padding: 24 }}>
          <h3 style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.6px" }}>Pipeline Run</h3>
          <InfoRow label="Run ID" value={pr.run_id} />
          <InfoRow label="Status" value={pr.overall_status} />
          <InfoRow label="Triggered" value={pr.triggered_at ? new Date(pr.triggered_at).toLocaleString() : "—"} />
          <InfoRow label="Completed" value={pr.completed_at ? new Date(pr.completed_at).toLocaleString() : "—"} />
          <InfoRow label="Corrections" value={`${pr.correction_iterations || 0}/${pr.max_correction_iterations || 3}`} />
        </div>
        <div className="card" style={{ padding: 24 }}>
          <h3 style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.6px" }}>Simulation</h3>
          {simReport ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 14 }}>
                <ConfidenceGauge score={simReport.overall_confidence_score || 0} />
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 2 }}>Overall Confidence</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: "#0653c7", letterSpacing: "-1px" }}>
                    {simReport.overall_confidence_score}%
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <span className="badge badge-emerald">✓ {simReport.passed_count} passed</span>
                <span className="badge badge-rose">✕ {simReport.failed_count} failed</span>
              </div>
            </div>
          ) : (
            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No simulation report yet.</p>
          )}
        </div>
      </div>

      {/* Bottom row: Documents + Config Files */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="card" style={{ padding: 24 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <h3 style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", margin: 0 }}>Documents</h3>
            <button
              onClick={() => { setShowUpload(!showUpload); setUploadMsg(""); }}
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600,
                border: showUpload ? "1.5px solid #0653c7" : "1px solid var(--border-subtle)",
                background: showUpload ? "#e8f0fe" : "white",
                color: showUpload ? "#0653c7" : "var(--text-secondary)",
                cursor: "pointer", transition: "all 0.15s",
              }}
              onMouseEnter={e => { if (!showUpload) { e.currentTarget.style.borderColor = "#0653c7"; e.currentTarget.style.color = "#0653c7"; }}}
              onMouseLeave={e => { if (!showUpload) { e.currentTarget.style.borderColor = "var(--border-subtle)"; e.currentTarget.style.color = "var(--text-secondary)"; }}}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              Upload Updated Docs
            </button>
          </div>

          {/* Existing documents list */}
          {(meta.uploaded_documents || []).length === 0 && !showUpload && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No documents uploaded.</p>}
          {(meta.uploaded_documents || []).map((d: any, i: number) => (
            <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, padding: "8px 12px", background: "var(--bg-surface)", borderRadius: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 16 }}>📄</span>
                <div>
                  <span style={{ fontSize: 13, fontWeight: 500, display: "block" }}>{d.filename}</span>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{d.type}</span>
                </div>
              </div>
              <a href={`http://localhost:8000/api/projects/${clientId}/documents/${d.filename}/download`}
                download style={{
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  width: 30, height: 30, borderRadius: 7,
                  background: "white", border: "1px solid var(--border-subtle)",
                  color: "var(--text-secondary)", textDecoration: "none", fontSize: 14,
                  cursor: "pointer", transition: "all 0.15s", flexShrink: 0,
                }} title="Download">
                ⬇
              </a>
            </div>
          ))}

          {/* Upload Updated Documents panel */}
          {showUpload && (
            <div className="animate-in" style={{ marginTop: 12, padding: 16, borderRadius: 12, border: "1.5px dashed #0653c7", background: "#f8faff" }}>
              {/* Drop zone */}
              <div
                onClick={() => fileInputRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                style={{
                  padding: "20px 16px", borderRadius: 10, textAlign: "center", cursor: "pointer",
                  background: dragOver ? "#e8f0fe" : "white",
                  border: dragOver ? "2px solid #0653c7" : "1.5px dashed var(--border-subtle)",
                  transition: "all 0.15s",
                }}
              >
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={dragOver ? "#0653c7" : "var(--text-muted)"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginBottom: 6, opacity: 0.7 }}>
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                <p style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)", margin: 0 }}>Drag & drop updated documents</p>
                <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 3 }}>.pdf, .docx, .txt, .json</p>
              </div>
              <input ref={fileInputRef} type="file" multiple accept=".pdf,.docx,.txt,.json" style={{ display: "none" }}
                onChange={e => setUploadFiles(prev => [...prev, ...Array.from(e.target.files || [])])}
              />

              {/* Selected files */}
              {uploadFiles.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  {uploadFiles.map((f, i) => (
                    <div key={i} className="animate-in" style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "8px 12px", borderRadius: 8, background: "white",
                      border: "1px solid var(--border-subtle)", marginBottom: 6,
                      animationDelay: `${i * 0.04}s`,
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0653c7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                        </svg>
                        <span style={{ fontSize: 12.5, fontWeight: 500 }}>{f.name}</span>
                        <span style={{ fontSize: 10.5, color: "var(--text-muted)" }}>({(f.size / 1024).toFixed(0)} KB)</span>
                      </div>
                      <button onClick={() => setUploadFiles(uploadFiles.filter((_, j) => j !== i))}
                        style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 15, lineHeight: 1, padding: "2px 4px", transition: "color 0.15s" }}
                        onMouseEnter={e => (e.currentTarget.style.color = "#dc2626")}
                        onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
                      >×</button>
                    </div>
                  ))}
                </div>
              )}

              {/* Re-Run Pipeline button */}
              <button
                onClick={handleRerun}
                disabled={uploading || uploadFiles.length === 0}
                style={{
                  width: "100%", marginTop: 12, padding: "10px 20px", borderRadius: 10,
                  fontSize: 13, fontWeight: 700, border: "none", cursor: "pointer",
                  background: uploadFiles.length === 0 ? "var(--bg-surface)" : "linear-gradient(135deg, #0653c7 0%, #3b82f6 100%)",
                  color: uploadFiles.length === 0 ? "var(--text-muted)" : "white",
                  transition: "all 0.2s",
                  boxShadow: uploadFiles.length > 0 ? "0 4px 14px rgba(6,83,199,0.25)" : "none",
                  opacity: uploading ? 0.7 : 1,
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                }}
              >
                {uploading ? (
                  <><span className="spin-slow" style={{ display: "inline-block", width: 14, height: 14, border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "white", borderRadius: "50%" }} /> Re-Running Pipeline…</>
                ) : (
                  <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Upload & Re-Run Pipeline ({uploadFiles.length} file{uploadFiles.length !== 1 ? "s" : ""})</>
                )}
              </button>

              {uploadMsg && (
                <p style={{
                  fontSize: 12.5, marginTop: 10, textAlign: "center", padding: "8px 12px",
                  borderRadius: 8,
                  background: uploadMsg.includes("fail") || uploadMsg.includes("Failed") ? "#fef2f2" : "#ecfdf5",
                  color: uploadMsg.includes("fail") || uploadMsg.includes("Failed") ? "#dc2626" : "#047857",
                }}>{uploadMsg}</p>
              )}
            </div>
          )}
        </div>
        <div className="card" style={{ padding: 24 }}>
          <h3 style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.6px" }}>Config Files ({configFiles.length})</h3>
          {configFiles.length === 0 && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No configs generated yet.</p>}
          {configFiles.map((cf: any, i: number) => {
            const vMatch = cf.filename.match(/config_v(\d+)\.json/);
            const vNum = vMatch ? vMatch[1] : "?";
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8, padding: "10px 14px", background: "var(--bg-surface)", borderRadius: 8, border: "1px solid var(--border-subtle)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontSize: 16 }}>⚙️</span>
                  <div>
                    <span style={{ fontSize: 13, fontWeight: 600, display: "block", color: "var(--text-primary)" }}>{cf.filename}</span>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{(cf.size_bytes / 1024).toFixed(1)} KB</span>
                  </div>
                </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className={`badge ${i === configFiles.length - 1 ? "badge-emerald" : "badge-slate"}`}>v{vNum}{i === configFiles.length - 1 ? " (latest)" : ""}</span>
                <a href={`http://localhost:8000/api/projects/${clientId}/configs/${cf.filename}/download`}
                  download style={{
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                    width: 28, height: 28, borderRadius: 7,
                    background: "white", border: "1px solid var(--border-subtle)",
                    color: "var(--text-secondary)", textDecoration: "none", fontSize: 13,
                    cursor: "pointer", transition: "all 0.15s", flexShrink: 0,
                  }} title="Download">
                  ⬇
                </a>
              </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ConfigTab({ config, configFiles, clientId, onConfigSaved }: any) {
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [versionData, setVersionData] = useState<any>(null);
  const [versionLoading, setVersionLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [saveStatus, setSaveStatus] = useState<"" | "saving" | "saved" | "error">("");
  const [saveError, setSaveError] = useState("");

  const loadVersion = async (filename: string) => {
    setSelectedVersion(filename);
    setVersionLoading(true);
    setEditing(false); setSaveStatus("");
    try {
      const data = await getConfigFile(clientId, filename);
      setVersionData(data);
    } catch { setVersionData(null); }
    finally { setVersionLoading(false); }
  };

  const displayData = selectedVersion ? versionData : config;
  const displayName = selectedVersion || (configFiles.length > 0 ? configFiles[configFiles.length - 1]?.filename : "latest");
  const currentFilename = selectedVersion || (configFiles.length > 0 ? configFiles[configFiles.length - 1]?.filename : null);

  const startEditing = () => {
    setEditText(JSON.stringify(displayData, null, 2));
    setEditing(true);
    setSaveStatus("");
    setSaveError("");
  };

  const cancelEditing = () => {
    setEditing(false);
    setSaveStatus("");
    setSaveError("");
  };

  const handleSave = async () => {
    if (!currentFilename) return;
    // Validate JSON
    let parsed: any;
    try {
      parsed = JSON.parse(editText);
    } catch (e: any) {
      setSaveError("Invalid JSON: " + e.message);
      setSaveStatus("error");
      return;
    }
    setSaveStatus("saving"); setSaveError("");
    try {
      await saveConfigFile(clientId, currentFilename, parsed);
      setVersionData(parsed);
      setSaveStatus("saved");
      setEditing(false);
      if (onConfigSaved) onConfigSaved();
      setTimeout(() => setSaveStatus(""), 3000);
    } catch (e: any) {
      setSaveError(e.message || "Save failed");
      setSaveStatus("error");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* Version Selector */}
      {configFiles.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", marginRight: 4 }}>Version:</span>
          {configFiles.map((cf: any, i: number) => {
            const vMatch = cf.filename.match(/config_v(\d+)\.json/);
            const vNum = vMatch ? vMatch[1] : "?";
            const isActive = selectedVersion === cf.filename || (!selectedVersion && i === configFiles.length - 1);
            return (
              <button key={cf.filename} onClick={() => loadVersion(cf.filename)}
                style={{
                  padding: "6px 14px", borderRadius: 8, fontSize: 12.5, fontWeight: 600,
                  border: isActive ? "2px solid #0653c7" : "1px solid var(--border-subtle)",
                  background: isActive ? "#e8f0fe" : "white",
                  color: isActive ? "#0653c7" : "var(--text-secondary)",
                  cursor: "pointer", transition: "all 0.15s",
                }}>
                v{vNum}{i === configFiles.length - 1 ? " (latest)" : ""}
              </button>
            );
          })}
        </div>
      )}

      {/* Header with Edit/Save buttons */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>📄 {displayName}</span>
          {displayData && (
            <span className="badge badge-slate" style={{ fontSize: 10.5 }}>
              {(JSON.stringify(displayData, null, 2).length / 1024).toFixed(1)} KB
            </span>
          )}
          {saveStatus === "saved" && (
            <span style={{ fontSize: 12, color: "#047857", fontWeight: 600, display: "flex", alignItems: "center", gap: 4 }}>✓ Saved</span>
          )}
        </div>
        {displayData && !versionLoading && (
          <div style={{ display: "flex", gap: 8 }}>
            {editing ? (
              <>
                <button onClick={cancelEditing}
                  style={{
                    padding: "7px 16px", borderRadius: 8, fontSize: 12.5, fontWeight: 600,
                    border: "1px solid var(--border-subtle)", background: "white",
                    color: "var(--text-secondary)", cursor: "pointer",
                  }}>Cancel</button>
                <button onClick={handleSave}
                  disabled={saveStatus === "saving"}
                  style={{
                    padding: "7px 18px", borderRadius: 8, fontSize: 12.5, fontWeight: 600,
                    border: "none", background: "#0653c7", color: "white",
                    cursor: saveStatus === "saving" ? "wait" : "pointer",
                    opacity: saveStatus === "saving" ? 0.7 : 1,
                  }}>
                  {saveStatus === "saving" ? "Saving…" : "💾 Save"}
                </button>
              </>
            ) : (
              <button onClick={startEditing}
                style={{
                  padding: "7px 16px", borderRadius: 8, fontSize: 12.5, fontWeight: 600,
                  border: "1px solid #0653c7", background: "#e8f0fe",
                  color: "#0653c7", cursor: "pointer", transition: "all 0.15s",
                }}>✏️ Edit</button>
            )}
          </div>
        )}
      </div>

      {/* Error message */}
      {saveStatus === "error" && (
        <div style={{ padding: "10px 14px", marginBottom: 10, borderRadius: 8, background: "#fef2f2", border: "1px solid #fecaca", color: "#b91c1c", fontSize: 12.5 }}>
          ✗ {saveError}
        </div>
      )}

      {/* JSON Viewer / Editor */}
      {versionLoading ? (
        <div className="card" style={{ padding: 48, textAlign: "center" }}>
          <div className="spin-slow" style={{ width: 36, height: 36, borderRadius: 10, background: "var(--gradient-primary)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 18, color: "white", marginBottom: 10 }}>⚡</div>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading config…</p>
        </div>
      ) : editing ? (
        <textarea
          value={editText}
          onChange={e => setEditText(e.target.value)}
          spellCheck={false}
          style={{
            width: "100%", minHeight: 500, padding: 18,
            fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
            fontSize: 13, lineHeight: 1.6, borderRadius: 12,
            border: "2px solid #0653c7", background: "#f8fafc",
            color: "var(--text-primary)", resize: "vertical",
            outline: "none", boxSizing: "border-box",
          }}
        />
      ) : displayData ? (
        <div className="json-viewer" style={{ flex: 1, overflowY: "auto", minHeight: 0, maxHeight: "none", margin: 0 }}>
          <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
            {JSON.stringify(displayData, null, 2)}
          </pre>
        </div>
      ) : (
        <div className="card" style={{ padding: 48, textAlign: "center", flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <p style={{ color: "var(--text-muted)", fontSize: 14 }}>No config data available.</p>
        </div>
      )}
    </div>
  );
}

function DiffTab({ configFiles, clientId }: any) {
  const [v1, setV1] = useState("");
  const [v2, setV2] = useState("");
  const [diff, setDiff] = useState<any>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState("");
  const [filter, setFilter] = useState<"all" | "changed" | "added" | "removed">("all");

  const runDiff = async () => {
    if (!v1 || !v2 || v1 === v2) return;
    setDiffLoading(true); setDiffError(""); setDiff(null);
    try {
      const d = await diffConfigs(clientId, v1, v2);
      setDiff(d);
    } catch (e: any) { setDiffError(e.message || "Diff failed"); }
    finally { setDiffLoading(false); }
  };

  const TYPE_STYLE: Record<string, { bg: string; color: string; label: string }> = {
    changed: { bg: "#fffbeb", color: "#b45309", label: "CHANGED" },
    added: { bg: "#ecfdf5", color: "#047857", label: "ADDED" },
    removed: { bg: "#fef2f2", color: "#b91c1c", label: "REMOVED" },
  };

  const filteredChanges = diff?.changes?.filter((c: any) => filter === "all" || c.type === filter) || [];

  if (configFiles.length < 2) {
    return (
      <div className="card" style={{ padding: 56, textAlign: "center" }}>
        <div style={{ fontSize: 36, marginBottom: 12, opacity: 0.5 }}>📊</div>
        <p style={{ color: "var(--text-muted)", fontSize: 14 }}>Need at least 2 config versions to compare.</p>
      </div>
    );
  }

  return (
    <div>
      {/* Version Pickers */}
      <div className="card" style={{ padding: 22, marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 180 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: 6 }}>Base Version</label>
            <select value={v1} onChange={e => setV1(e.target.value)}
              style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid var(--border-subtle)", fontSize: 13, background: "var(--bg-surface)", color: "var(--text-primary)", cursor: "pointer" }}>
              <option value="">Select version…</option>
              {configFiles.map((cf: any) => {
                const m = cf.filename.match(/config_v(\d+)\.json/);
                return <option key={cf.filename} value={cf.filename}>v{m ? m[1] : "?"} — {cf.filename}</option>;
              })}
            </select>
          </div>
          <div style={{ fontSize: 20, color: "var(--text-muted)", paddingTop: 20 }}>→</div>
          <div style={{ flex: 1, minWidth: 180 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: 6 }}>Compare Version</label>
            <select value={v2} onChange={e => setV2(e.target.value)}
              style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid var(--border-subtle)", fontSize: 13, background: "var(--bg-surface)", color: "var(--text-primary)", cursor: "pointer" }}>
              <option value="">Select version…</option>
              {configFiles.map((cf: any) => {
                const m = cf.filename.match(/config_v(\d+)\.json/);
                return <option key={cf.filename} value={cf.filename}>v{m ? m[1] : "?"} — {cf.filename}</option>;
              })}
            </select>
          </div>
          <button className="btn-primary" onClick={runDiff}
            disabled={!v1 || !v2 || v1 === v2 || diffLoading}
            style={{ padding: "10px 24px", marginTop: 18, opacity: (!v1 || !v2 || v1 === v2) ? 0.5 : 1, cursor: (!v1 || !v2 || v1 === v2) ? "not-allowed" : "pointer" }}>
            {diffLoading ? "Comparing…" : "Compare"}
          </button>
        </div>
        {v1 && v2 && v1 === v2 && <p style={{ color: "#b45309", fontSize: 12, marginTop: 8 }}>⚠ Select two different versions to compare.</p>}
      </div>

      {diffError && <div className="card" style={{ padding: 16, marginBottom: 16, borderLeft: "3px solid #dc2626", color: "#b91c1c", fontSize: 13 }}>✗ {diffError}</div>}

      {diffLoading && (
        <div className="card" style={{ padding: 48, textAlign: "center" }}>
          <div className="spin-slow" style={{ width: 36, height: 36, borderRadius: 10, background: "var(--gradient-primary)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 18, color: "white", marginBottom: 10 }}>⚡</div>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Computing diff…</p>
        </div>
      )}

      {diff && !diffLoading && (
        <>
          {/* Stats Bar */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
            <span style={{ fontSize: 14, fontWeight: 700 }}>{diff.total_changes} changes</span>
            <span style={{ color: "var(--text-muted)", fontSize: 13 }}>between {diff.v1} and {diff.v2}</span>
            <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
              {(["all", "changed", "added", "removed"] as const).map(f => (
                <button key={f} onClick={() => setFilter(f)} style={{
                  padding: "5px 12px", borderRadius: 7, fontSize: 11.5, fontWeight: 600,
                  border: filter === f ? "2px solid #0653c7" : "1px solid var(--border-subtle)",
                  background: filter === f ? "#e8f0fe" : "white",
                  color: filter === f ? "#0653c7" : "var(--text-secondary)",
                  cursor: "pointer", textTransform: "capitalize",
                }}>{f} {f !== "all" ? `(${diff.changes.filter((c: any) => c.type === f).length})` : `(${diff.total_changes})`}</button>
              ))}
            </div>
          </div>

          {/* Changes List */}
          {filteredChanges.length === 0 ? (
            <div className="card" style={{ padding: 36, textAlign: "center" }}>
              <p style={{ color: "var(--text-muted)", fontSize: 13 }}>{diff.total_changes === 0 ? "The two versions are identical." : "No changes match the selected filter."}</p>
            </div>
          ) : (
            <div className="card" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                  <thead>
                    <tr style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-subtle)" }}>
                      {["Type", "Key", "Old Value", "New Value"].map(h => (
                        <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontWeight: 600, color: "var(--text-muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.5px" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredChanges.map((c: any, i: number) => {
                      const ts = TYPE_STYLE[c.type] || TYPE_STYLE.changed;
                      return (
                        <tr key={i} style={{ borderBottom: "1px solid var(--border-subtle)", transition: "background 0.15s" }}
                          onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-surface)")}
                          onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                          <td style={{ padding: "10px 16px" }}>
                            <span style={{ display: "inline-block", padding: "3px 8px", borderRadius: 6, fontSize: 10, fontWeight: 700, background: ts.bg, color: ts.color }}>{ts.label}</span>
                          </td>
                          <td style={{ padding: "10px 16px", fontFamily: "monospace", color: "var(--text-primary)", fontWeight: 500, maxWidth: 280, wordBreak: "break-all" }}>{c.key}</td>
                          <td style={{ padding: "10px 16px", fontFamily: "monospace", color: c.type === "removed" ? "#b91c1c" : "var(--text-secondary)", maxWidth: 220, wordBreak: "break-all", background: c.type === "removed" ? "rgba(220,38,38,0.04)" : c.type === "changed" ? "rgba(220,38,38,0.04)" : "transparent" }}>
                            {c.old !== null && c.old !== undefined ? String(c.old) : "—"}
                          </td>
                          <td style={{ padding: "10px 16px", fontFamily: "monospace", color: c.type === "added" ? "#047857" : "var(--text-secondary)", maxWidth: 220, wordBreak: "break-all", background: c.type === "added" ? "rgba(5,150,105,0.04)" : c.type === "changed" ? "rgba(5,150,105,0.04)" : "transparent" }}>
                            {c.new !== null && c.new !== undefined ? String(c.new) : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function IntegrationsTab({ integrations, clientId, onMigrated }: any) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [migrating, setMigrating] = useState<string | null>(null);
  const [migrateMsg, setMigrateMsg] = useState<{ id: string; ok: boolean; text: string } | null>(null);
  const CAT_BADGE: Record<string, string> = {
    bureau: "badge-blue", kyc: "badge-cyan", payment: "badge-emerald",
    banking: "badge-teal", gst: "badge-amber", document: "badge-violet",
    fraud: "badge-rose", messaging: "badge-cyan",
  };

  const isSunsetPassed = (sunsetDate: string | null) => {
    if (!sunsetDate) return false;
    return new Date(sunsetDate) < new Date();
  };

  const isDeprecatedOrSunset = (integ: any) => {
    return integ.deprecated === true || isSunsetPassed(integ.sunset_date);
  };

  const handleMigrate = async (integrationId: string) => {
    setMigrating(integrationId);
    setMigrateMsg(null);
    try {
      const result = await migrateVersion(clientId, integrationId);
      setMigrateMsg({ id: integrationId, ok: true, text: `Migrated to ${result.new_version}. New config: ${result.new_config_version}. Running simulation…` });
      // Run simulation on the new config
      try { await runDetailedSimulation(clientId); } catch {}
      if (onMigrated) onMigrated();
      setMigrateMsg({ id: integrationId, ok: true, text: `Migrated to ${result.new_version}. Config ${result.new_config_version} saved. Simulation complete.` });
    } catch (e: any) {
      const msg = e?.message || "Migration failed";
      setMigrateMsg({ id: integrationId, ok: false, text: msg });
    } finally {
      setMigrating(null);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {integrations.map((integ: any, idx: number) => {
        const deprecated = isDeprecatedOrSunset(integ);
        const sunsetPassed = isSunsetPassed(integ.sunset_date);
        return (
        <div key={idx} className="card" style={{ padding: 0, overflow: "hidden", border: deprecated ? "2px solid #f59e0b" : undefined }}>
          <div onClick={() => setExpanded(expanded === idx ? null : idx)}
            style={{ padding: "18px 22px", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", transition: "background 0.15s" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 15, fontWeight: 700 }}>{integ.service_name || integ.integration_id || "Unknown"}</span>
              <span className={`badge ${CAT_BADGE[integ.category] || "badge-slate"}`}>{integ.category || "General"}</span>
              {integ.is_mandatory && <span className="badge badge-rose">required</span>}
              {deprecated && <span className="badge badge-amber" style={{ fontWeight: 700 }}>DEPRECATED</span>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 16, color: "var(--text-muted)", fontSize: 12.5 }}>
              <span>{integ.adapter_id || "Unknown Adapter"}</span>
              <span className={`badge ${deprecated ? "badge-amber" : "badge-slate"}`}>{integ.selected_version || "v1"}</span>
              {integ.sunset_date && (
                <span style={{ fontSize: 11, color: sunsetPassed ? "#dc2626" : "var(--text-muted)" }}>
                  {sunsetPassed ? "Sunset: " : "Sunset: "}{integ.sunset_date}
                </span>
              )}
              <span style={{ fontSize: 16, transition: "transform 0.2s", transform: expanded === idx ? "rotate(180deg)" : "rotate(0)" }}>▾</span>
            </div>
          </div>

          {/* Deprecation Warning Banner */}
          {deprecated && (
            <div style={{
              display: "flex", alignItems: "center", gap: 12, padding: "12px 22px",
              background: "#fffbeb", borderTop: "1px solid #fcd34d", borderBottom: "1px solid #fcd34d",
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#d97706" strokeWidth="2" style={{ flexShrink: 0 }}>
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <div style={{ flex: 1, fontSize: 12.5, color: "#92400e" }}>
                <strong>Version {integ.selected_version} is deprecated.</strong>
                {sunsetPassed
                  ? ` Sunset date (${integ.sunset_date}) has passed. This version may stop working.`
                  : integ.sunset_date
                    ? ` Scheduled for sunset on ${integ.sunset_date}.`
                    : " Consider migrating to a supported version."
                }
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); handleMigrate(integ.integration_id); }}
                disabled={migrating === integ.integration_id}
                style={{
                  padding: "8px 18px", borderRadius: 8, fontSize: 12, fontWeight: 700,
                  border: "none", background: migrating === integ.integration_id ? "#d97706" : "#b45309",
                  color: "white", cursor: migrating === integ.integration_id ? "wait" : "pointer",
                  whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 6,
                  transition: "all 0.15s",
                }}>
                {migrating === integ.integration_id ? (
                  <><span className="spin-slow" style={{ display: "inline-block", width: 12, height: 12, border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "white", borderRadius: "50%" }}/> Migrating…</>
                ) : (
                  <>↑ Migrate to Latest</>
                )}
              </button>
            </div>
          )}

          {/* Migration result message */}
          {migrateMsg && migrateMsg.id === integ.integration_id && (
            <div style={{
              padding: "10px 22px", fontSize: 12.5, fontWeight: 600,
              background: migrateMsg.ok ? "#ecfdf5" : "#fef2f2",
              color: migrateMsg.ok ? "#047857" : "#b91c1c",
              borderBottom: `1px solid ${migrateMsg.ok ? "#a7f3d0" : "#fecaca"}`,
            }}>
              {migrateMsg.ok ? "✓" : "✕"} {migrateMsg.text}
            </div>
          )}

          {expanded === idx && (
            <div className="animate-in" style={{ padding: "0 22px 22px", borderTop: "1px solid var(--border-subtle)" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginTop: 18 }}>
                <div>
                  <h4 style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.6px" }}>Connection</h4>
                  <InfoRow label="Endpoint" value={integ.endpoint_url} />
                  <InfoRow label="Auth" value={integ.auth_type} />
                  <InfoRow label="Timeout" value={integ.timeout_ms ? `${integ.timeout_ms}ms` : undefined} />
                  <InfoRow label="Sandbox" value={integ.sandbox_url} />
                  <InfoRow label="Credentials" value={(integ.credential_env_vars || []).join(", ")} />
                  <InfoRow label="Deprecated" value={integ.deprecated ? "Yes" : "No"} />
                  <InfoRow label="Sunset Date" value={integ.sunset_date || "None"} />
                </div>
                <div>
                  <h4 style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.6px" }}>
                    Field Mappings ({(integ.field_mapping || []).length})
                  </h4>
                  {(integ.field_mapping || []).map((fm: any, i: number) => (
                    <div key={i} style={{ fontSize: 12.5, marginBottom: 5, padding: "6px 10px", background: "var(--bg-surface)", borderRadius: 7, border: "1px solid var(--border-subtle)" }}>
                      <span style={{ color: "#0653c7", fontWeight: 600 }}>{fm.user_field}</span>
                      <span style={{ color: "var(--text-muted)", margin: "0 6px" }}>→</span>
                      <span style={{ color: "#059669", fontWeight: 600 }}>{fm.api_field}</span>
                      <span style={{ color: "var(--text-muted)", fontSize: 11, marginLeft: 6 }}>({fm.mapping_type})</span>
                    </div>
                  ))}
                </div>
              </div>
              {(integ.transformation_rules || []).length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <h4 style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.6px" }}>
                    Transformation Rules ({integ.transformation_rules.length})
                  </h4>
                  {integ.transformation_rules.map((tr: any, i: number) => (
                    <div key={i} style={{ fontSize: 12.5, marginBottom: 5, padding: "6px 10px", background: "var(--bg-surface)", borderRadius: 7, border: "1px solid var(--border-subtle)" }}>
                      <span className="badge badge-violet" style={{ marginRight: 8, fontSize: 10 }}>{tr.rule_type}</span>
                      {tr.source_field} → {tr.target_field}: {tr.rule}
                    </div>
                  ))}
                </div>
              )}
              {(integ.hooks || []).length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <h4 style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.6px" }}>
                    Hooks ({integ.hooks.length})
                  </h4>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {integ.hooks.map((h: any, i: number) => (
                      <span key={i} className="badge badge-cyan">{h.hook_name || h.hook_id}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        );
      })}
    </div>
  );
}

function SimulationTab({ report, clientId }: any) {
  const [detailedResults, setDetailedResults] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [expandedInteg, setExpandedInteg] = useState<string | null>(null);
  const [expandedScenario, setExpandedScenario] = useState<string | null>(null);

  const handleRunDetailed = async () => {
    setRunning(true);
    try {
      const data = await runDetailedSimulation(clientId);
      setDetailedResults(data);
    } catch (e) { console.error(e); }
    finally { setRunning(false); }
  };

  const SCENARIO_STYLES: Record<string, { icon: string; color: string; bg: string }> = {
    success: { icon: "✓", color: "#059669", bg: "#ecfdf5" },
    failure: { icon: "✕", color: "#dc2626", bg: "#fef2f2" },
    timeout: { icon: "⏱", color: "#d97706", bg: "#fffbeb" },
    missing_fields: { icon: "⚠", color: "#ea580c", bg: "#fff7ed" },
    fallback: { icon: "↩", color: "#7c3aed", bg: "#f5f3ff" },
    version_comparison: { icon: "⇆", color: "#0653c7", bg: "#eff6ff" },
  };

  if (!report) return (
    <div className="card" style={{ padding: 56, textAlign: "center" }}>
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" style={{ marginBottom: 12, opacity: 0.5 }}>
        <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
      </svg>
      <p style={{ color: "var(--text-muted)", fontSize: 14 }}>No simulation report yet. Approve the config to run simulation.</p>
    </div>
  );

  const results = report.integration_results || [];

  return (
    <div>
      {/* ── Pipeline Summary ─────────────────────── */}
      <div className="card" style={{ padding: 28, marginBottom: 18, display: "flex", alignItems: "center", gap: 32 }}>
        <ConfidenceGauge score={report.overall_confidence_score || 0} size={110} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 40, fontWeight: 800, color: "#0653c7", letterSpacing: "-1.5px" }}>{report.overall_confidence_score}%</div>
          <p style={{ color: "var(--text-secondary)", fontSize: 14, marginTop: 4, lineHeight: 1.5 }}>{report.human_readable_summary}</p>
          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <span className="badge badge-emerald">✓ {report.passed_count} passed</span>
            <span className="badge badge-rose">✕ {report.failed_count} failed</span>
            <span className="badge badge-blue">{report.total_integrations_tested} tested</span>
          </div>
        </div>
      </div>

      {/* Recommended Actions */}
      {(report.recommended_actions || []).length > 0 && (
        <div className="card" style={{ padding: 22, marginBottom: 18 }}>
          <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Recommended Actions</h4>
          {report.recommended_actions.map((a: string, i: number) => (
            <div key={i} style={{ display: "flex", gap: 8, marginBottom: 6, fontSize: 13, color: "var(--text-secondary)", alignItems: "flex-start" }}>
              <span style={{ color: "#0653c7", fontWeight: 600 }}>→</span><span>{a}</span>
            </div>
          ))}
        </div>
      )}

      {/* Integration result cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12, marginBottom: 24 }}>
        {results.map((r: any, i: number) => (
          <div key={i} className="card" style={{ padding: 20 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <span style={{ fontWeight: 700, fontSize: 14 }}>{r.adapter_id}</span>
              <span className={`badge ${r.status === "passed" ? "badge-emerald" : "badge-rose"}`}>{r.status}</span>
            </div>
            <InfoRow label="Version" value={r.version_tested} />
            <InfoRow label="Score" value={`${r.confidence_score}%`} />
            <InfoRow label="Fields OK" value={`${r.fields_mapped_correctly}/${r.total_required_fields}`} />
            {r.notes && <p style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 6, padding: "6px 10px", background: "var(--bg-surface)", borderRadius: 6 }}>{r.notes}</p>}
          </div>
        ))}
      </div>

      {/* ── Detailed Testing Section ─────────────── */}
      <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 24 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
          <div>
            <h3 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>Detailed Scenario Testing</h3>
            <p style={{ fontSize: 12.5, color: "var(--text-muted)", margin: "4px 0 0" }}>
              Run comprehensive tests: success, failure, timeout, missing fields, fallback, and version comparison.
            </p>
          </div>
          <button onClick={handleRunDetailed} disabled={running}
            style={{
              padding: "10px 22px", borderRadius: 9, fontSize: 13, fontWeight: 700,
              border: "none", background: running ? "#94a3b8" : "#0653c7", color: "white",
              cursor: running ? "wait" : "pointer", transition: "all 0.2s",
              display: "flex", alignItems: "center", gap: 8,
            }}>
            {running ? (
              <><span className="spin-slow" style={{ display: "inline-block", width: 14, height: 14, border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "white", borderRadius: "50%" }}/> Running Tests…</>
            ) : (
              <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Detailed Tests</>
            )}
          </button>
        </div>

        {/* Detailed Results */}
        {detailedResults && (
          <div>
            {/* Summary bar */}
            <div className="card" style={{ padding: 20, marginBottom: 16, display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 28, fontWeight: 800, color: "#059669" }}>{detailedResults.fidelity_score}%</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600 }}>FIDELITY</div>
              </div>
              <div style={{ width: 1, height: 40, background: "var(--border-subtle)" }} />
              <div style={{ display: "flex", gap: 14 }}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 20, fontWeight: 700 }}>{detailedResults.total_scenarios}</div>
                  <div style={{ fontSize: 10.5, color: "var(--text-muted)", fontWeight: 600 }}>SCENARIOS</div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "#059669" }}>{detailedResults.positive_passed}/{detailedResults.positive_total}</div>
                  <div style={{ fontSize: 10.5, color: "var(--text-muted)", fontWeight: 600 }}>POSITIVE</div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "#7c3aed" }}>{detailedResults.faults_handled}/{detailedResults.faults_total}</div>
                  <div style={{ fontSize: 10.5, color: "var(--text-muted)", fontWeight: 600 }}>FAULTS HANDLED</div>
                </div>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 20, fontWeight: 700 }}>{detailedResults.total_integrations}</div>
                  <div style={{ fontSize: 10.5, color: "var(--text-muted)", fontWeight: 600 }}>INTEGRATIONS</div>
                </div>
              </div>
              <div style={{ flex: 1 }} />
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                {new Date(detailedResults.timestamp).toLocaleString()}
              </div>
            </div>

            {/* Per-integration accordion */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {detailedResults.integrations.map((integ: any) => {
                const isExpanded = expandedInteg === integ.integration_id;
                return (
                  <div key={integ.integration_id} className="card" style={{ padding: 0, overflow: "hidden" }}>
                    {/* Integration header bar */}
                    <div
                      onClick={() => setExpandedInteg(isExpanded ? null : integ.integration_id)}
                      style={{
                        padding: "16px 20px", cursor: "pointer", display: "flex", alignItems: "center", gap: 14,
                        background: isExpanded ? "var(--bg-surface)" : "white", transition: "background 0.15s",
                      }}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2.5"
                        style={{ transition: "transform 0.2s", transform: isExpanded ? "rotate(90deg)" : "none", flexShrink: 0 }}>
                        <polyline points="9 18 15 12 9 6"/>
                      </svg>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontWeight: 700, fontSize: 14 }}>{integ.service_name}</span>
                        <span style={{ fontSize: 11.5, color: "var(--text-muted)", marginLeft: 8 }}>{integ.adapter_id} ({integ.selected_version})</span>
                      </div>
                      <span className="badge badge-blue" style={{ fontSize: 10 }}>{integ.category}</span>
                      {integ.fallback_adapter && (
                        <span className="badge badge-violet" style={{ fontSize: 10 }}>fallback: {integ.fallback_adapter}</span>
                      )}
                      <span className="badge badge-emerald" style={{ fontSize: 10 }}>{integ.positive_passed}/{integ.positive_total} positive</span>
                      <span className="badge badge-violet" style={{ fontSize: 10 }}>{integ.faults_handled}/{integ.faults_total} faults handled</span>
                      {integ.all_matched && <span className="badge badge-emerald" style={{ fontSize: 10 }}>all matched</span>}
                    </div>

                    {/* Expanded scenario list */}
                    {isExpanded && (
                      <div style={{ padding: "0 20px 20px" }}>
                        {integ.scenarios.map((sc: any, si: number) => {
                          const sty = SCENARIO_STYLES[sc.scenario] || SCENARIO_STYLES.success;
                          const scKey = `${integ.integration_id}_${sc.scenario}`;
                          const scExpanded = expandedScenario === scKey;
                          return (
                            <div key={si} style={{ marginTop: si > 0 ? 8 : 12 }}>
                              <div
                                onClick={() => setExpandedScenario(scExpanded ? null : scKey)}
                                style={{
                                  display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
                                  borderRadius: 9, background: sty.bg, cursor: "pointer", transition: "all 0.15s",
                                  border: `1px solid ${scExpanded ? sty.color + "44" : "transparent"}`,
                                }}
                              >
                                <span style={{ fontSize: 14, width: 22, textAlign: "center", flexShrink: 0 }}>{sty.icon}</span>
                                <span style={{ fontWeight: 600, fontSize: 13, color: sty.color, flex: 1 }}>{sc.label}</span>
                                <span style={{
                                  fontSize: 9.5, padding: "2px 7px", borderRadius: 4, fontWeight: 700, letterSpacing: "0.3px",
                                  background: sc.category === "positive" ? "#dcfce7" : sc.category === "fault_injection" ? "#f3e8ff" : "#dbeafe",
                                  color: sc.category === "positive" ? "#166534" : sc.category === "fault_injection" ? "#6b21a8" : "#1e40af",
                                }}>{sc.category === "positive" ? "POSITIVE" : sc.category === "fault_injection" ? "FAULT INJECTION" : "INFO"}</span>
                                {sc.response_code && (
                                  <code style={{ fontSize: 11, padding: "2px 8px", borderRadius: 5, background: "rgba(0,0,0,0.06)", color: sty.color, fontWeight: 700 }}>
                                    {sc.response_code}
                                  </code>
                                )}
                                {sc.response_time_ms != null && (
                                  <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600, minWidth: 60, textAlign: "right" }}>
                                    {sc.response_time_ms}ms
                                  </span>
                                )}
                                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={sty.color} strokeWidth="2.5"
                                  style={{ transition: "transform 0.2s", transform: scExpanded ? "rotate(90deg)" : "none", flexShrink: 0 }}>
                                  <polyline points="9 18 15 12 9 6"/>
                                </svg>
                              </div>

                              {/* Scenario details */}
                              {scExpanded && (
                                <div style={{ padding: "12px 14px 14px 46px", fontSize: 12.5 }}>
                                  {/* Expected vs actual outcome */}
                                  <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 10, padding: "8px 12px", background: sc.outcome_matched ? "#f0fdf4" : "#fef2f2", borderRadius: 8, border: `1px solid ${sc.outcome_matched ? "#bbf7d0" : "#fecaca"}` }}>
                                    <span style={{ fontSize: 14, flexShrink: 0, marginTop: 1 }}>{sc.outcome_matched ? "✓" : "✕"}</span>
                                    <div style={{ flex: 1 }}>
                                      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 2 }}>EXPECTED OUTCOME</div>
                                      <div style={{ fontSize: 12.5, fontWeight: 600, color: sc.outcome_matched ? "#059669" : "#dc2626" }}>{sc.expected_outcome}</div>
                                    </div>
                                    <span className={`badge ${sc.outcome_matched ? "badge-emerald" : "badge-rose"}`} style={{ fontSize: 10 }}>
                                      {sc.outcome_matched ? "matched" : "mismatch"}
                                    </span>
                                  </div>
                                  <p style={{ color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 10 }}>{sc.details}</p>

                                  {/* Response time bar */}
                                  {sc.response_time_ms != null && sc.scenario !== "version_comparison" && (
                                    <div style={{ marginBottom: 12 }}>
                                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
                                        <span>Response Time</span>
                                        <span>{sc.response_time_ms}ms / {integ.timeout_ms}ms timeout</span>
                                      </div>
                                      <div style={{ height: 6, borderRadius: 3, background: "#e5e7eb", overflow: "hidden" }}>
                                        <div style={{
                                          height: "100%", borderRadius: 3, transition: "width 0.5s ease",
                                          width: `${Math.min(100, (sc.response_time_ms / integ.timeout_ms) * 100)}%`,
                                          background: sc.response_time_ms >= integ.timeout_ms ? "#dc2626"
                                            : sc.response_time_ms > integ.timeout_ms * 0.7 ? "#d97706" : "#059669",
                                        }} />
                                      </div>
                                    </div>
                                  )}

                                  {/* Missing fields list */}
                                  {sc.missing_fields && (
                                    <div style={{ marginBottom: 10 }}>
                                      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)" }}>Missing Fields:</span>
                                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                                        {sc.missing_fields.map((f: string, fi: number) => (
                                          <code key={fi} style={{ padding: "2px 8px", borderRadius: 5, background: "#fef2f2", color: "#dc2626", fontSize: 11, fontWeight: 600 }}>{f}</code>
                                        ))}
                                      </div>
                                    </div>
                                  )}

                                  {/* Retry info */}
                                  {sc.retry_attempted != null && (
                                    <div style={{ marginBottom: 10 }}>
                                      <InfoRow label="Retry" value={sc.retry_attempted ? `${sc.retries_used} retries (${integ.retry_policy?.backoff_strategy})` : "No retry policy"} />
                                    </div>
                                  )}

                                  {/* Fallback chain */}
                                  {sc.scenario === "fallback" && (
                                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, padding: "8px 12px", background: "#f5f3ff", borderRadius: 8 }}>
                                      <code style={{ fontSize: 12, fontWeight: 700, color: "#dc2626" }}>{sc.primary_adapter} ({sc.primary_version})</code>
                                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#7c3aed" strokeWidth="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
                                      <code style={{ fontSize: 12, fontWeight: 700, color: "#059669" }}>{sc.fallback_adapter} ({sc.fallback_version})</code>
                                      <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>{sc.response_time_ms}ms</span>
                                    </div>
                                  )}

                                  {/* Version comparison table */}
                                  {sc.scenario === "version_comparison" && sc.versions && (
                                    <div style={{ marginBottom: 10 }}>
                                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                                        <thead>
                                          <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                                            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600, color: "var(--text-muted)", fontSize: 10.5 }}>VERSION</th>
                                            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600, color: "var(--text-muted)", fontSize: 10.5 }}>MOCK</th>
                                            <th style={{ textAlign: "left", padding: "6px 10px", fontWeight: 600, color: "var(--text-muted)", fontSize: 10.5 }}>RESPONSE</th>
                                            <th style={{ textAlign: "right", padding: "6px 10px", fontWeight: 600, color: "var(--text-muted)", fontSize: 10.5 }}>STATUS</th>
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {sc.versions.map((v: any, vi: number) => (
                                            <tr key={vi} style={{ borderBottom: "1px solid var(--border-subtle)", background: v.version === sc.selected_version ? "#eff6ff" : "transparent" }}>
                                              <td style={{ padding: "8px 10px", fontWeight: v.version === sc.selected_version ? 700 : 500 }}>
                                                {v.version} {v.version === sc.selected_version && <span style={{ fontSize: 9, color: "#0653c7", marginLeft: 4 }}>SELECTED</span>}
                                              </td>
                                              <td style={{ padding: "8px 10px" }}>
                                                <span className={`badge ${v.mock_available ? "badge-emerald" : "badge-amber"}`}>{v.mock_available ? "available" : "generic"}</span>
                                              </td>
                                              <td style={{ padding: "8px 10px", fontFamily: "monospace" }}>{v.response_time_ms}ms</td>
                                              <td style={{ padding: "8px 10px", textAlign: "right" }}>
                                                <span className={`badge ${v.status === "passed" ? "badge-emerald" : "badge-amber"}`}>{v.status}</span>
                                              </td>
                                            </tr>
                                          ))}
                                        </tbody>
                                      </table>
                                    </div>
                                  )}

                                  {/* Mock response viewer */}
                                  {sc.mock_response && (
                                    <details style={{ marginTop: 6 }}>
                                      <summary style={{ cursor: "pointer", fontSize: 11.5, fontWeight: 600, color: "var(--text-muted)", padding: "4px 0" }}>
                                        View Mock Response
                                      </summary>
                                      <pre style={{
                                        marginTop: 6, padding: 14, borderRadius: 8, fontSize: 11.5,
                                        background: "#1e293b", color: "#e2e8f0", overflow: "auto", maxHeight: 200, lineHeight: 1.5,
                                      }}>
                                        {JSON.stringify(sc.mock_response, null, 2)}
                                      </pre>
                                    </details>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function ReasoningTab({ clientId }: { clientId: string }) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getReasoningReport(clientId)
      .then((data: any) => setContent(data.content || ""))
      .catch((e: any) => {
        if (e?.message?.includes("404")) {
          setError("not_found");
        } else {
          setError(e?.message || "Failed to load reasoning report");
        }
      })
      .finally(() => setLoading(false));
  }, [clientId]);

  if (loading) return (
    <div className="card" style={{ padding: 56, textAlign: "center" }}>
      <div className="spin-slow" style={{ width: 36, height: 36, borderRadius: 10, background: "var(--gradient-primary)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 18, color: "white", marginBottom: 10 }}>📋</div>
      <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading reasoning report…</p>
    </div>
  );

  if (error === "not_found") return (
    <div className="card" style={{ padding: 56, textAlign: "center" }}>
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" style={{ marginBottom: 12, opacity: 0.5 }}>
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
      </svg>
      <p style={{ color: "var(--text-muted)", fontSize: 14, fontWeight: 500 }}>No reasoning report yet</p>
      <p style={{ color: "var(--text-muted)", fontSize: 12.5, marginTop: 4 }}>Run the pipeline to generate a reasoning report explaining adapter and version selections.</p>
    </div>
  );

  if (error) return (
    <div className="card" style={{ padding: 32, textAlign: "center" }}>
      <p style={{ color: "#dc2626", fontSize: 14 }}>Error: {error}</p>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexShrink: 0 }}>
        <div style={{ width: 30, height: 30, borderRadius: 8, background: "linear-gradient(135deg, #0653c7, #3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
          </svg>
        </div>
        <div>
          <span style={{ fontSize: 14, fontWeight: 700 }}>Reasoning Report</span>
          <p style={{ fontSize: 11, color: "var(--text-muted)", margin: 0 }}>Pipeline decision rationale</p>
        </div>
      </div>

      {/* Markdown Content */}
      <div className="card" style={{ padding: "20px 24px", flex: 1, overflowY: "auto", minHeight: 0 }}>
        <div className="reasoning-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || ""}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}


function AuditTab({ auditLog: initialAuditLog, clientId }: any) {
  const [auditLog, setAuditLog] = useState<any>(initialAuditLog);
  const [refreshing, setRefreshing] = useState(false);

  // Sync with parent prop when it changes (e.g. after migration triggers fetchAll)
  useEffect(() => { setAuditLog(initialAuditLog); }, [initialAuditLog]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const data = await getAuditLog(clientId);
      setAuditLog(data);
    } catch (e) { console.error(e); }
    finally { setRefreshing(false); }
  };

  const entries = auditLog?.entries || [];
  return (
    <div>
      {/* Header with refresh */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 15, fontWeight: 700 }}>Audit Trail</span>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{entries.length} event{entries.length !== 1 ? "s" : ""}</span>
        </div>
        <button onClick={handleRefresh} disabled={refreshing}
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "7px 14px", borderRadius: 8, fontSize: 12.5, fontWeight: 600,
            border: "1px solid var(--border-subtle)", background: "white",
            color: "var(--text-secondary)", cursor: refreshing ? "wait" : "pointer",
            transition: "all 0.15s",
          }}
          onMouseEnter={e => { if (!refreshing) { e.currentTarget.style.borderColor = "#0653c7"; e.currentTarget.style.color = "#0653c7"; } }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border-subtle)"; e.currentTarget.style.color = "var(--text-secondary)"; }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            style={{ transition: "transform 0.3s", transform: refreshing ? "rotate(360deg)" : "none" }}>
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-subtle)" }}>
                {["Date / Time", "Stage", "Action", "Agent"].map(h => (
                  <th key={h} style={{ padding: "12px 18px", textAlign: "left", fontWeight: 600, color: "var(--text-muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.5px" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 ? (
                <tr><td colSpan={4} style={{ padding: 36, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>No audit events yet.</td></tr>
              ) : entries.map((e: any, i: number) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--border-subtle)", transition: "background 0.15s" }}
                  onMouseEnter={ev => (ev.currentTarget.style.background = "var(--bg-surface)")}
                  onMouseLeave={ev => (ev.currentTarget.style.background = "transparent")}>
                  <td style={{ padding: "10px 18px", color: "var(--text-muted)", whiteSpace: "nowrap", fontSize: 12 }}>
                    {e.timestamp ? (
                      <span title={new Date(e.timestamp).toISOString()}>
                        {new Date(e.timestamp).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" })}
                        {" "}
                        <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>
                          {new Date(e.timestamp).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                        </span>
                      </span>
                    ) : "—"}
                  </td>
                  <td style={{ padding: "10px 18px" }}><span className="badge badge-blue">{e.stage}</span></td>
                  <td style={{ padding: "10px 18px", color: "var(--text-primary)", maxWidth: 420, fontSize: 12.5 }}>{e.action}</td>
                  <td style={{ padding: "10px 18px", color: "var(--text-muted)", fontSize: 12.5 }}>
                    {e.agent === "gemini_flash_lite" ? "Local LLM" : (e.agent || "—")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/* ── Helpers ─────────────────────────────────────── */

function InfoRow({ label, value }: { label: string; value: any }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 7 }}>
      <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{label}</span>
      <span style={{ color: "var(--text-primary)", fontSize: 13, fontWeight: 500, textAlign: "right", maxWidth: "60%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {value || "—"}
      </span>
    </div>
  );
}

function ConfidenceGauge({ score, size = 72 }: { score: number; size?: number }) {
  const strokeW = 6;
  const r = (size - strokeW) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = score >= 80 ? "#059669" : score >= 50 ? "#d97706" : "#dc2626";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef1f8" strokeWidth={strokeW} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={strokeW}
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" className="gauge-ring"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" style={{ fontSize: size * 0.22, fontWeight: 800, fill: color }}>
        {score}
      </text>
    </svg>
  );
}

function CredentialsTab({ clientId }: { clientId: string }) {
  const [credentials, setCredentials] = useState<{ key: string; value: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [showValues, setShowValues] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setLoading(true);
    getCredentials(clientId)
      .then((data: any) => setCredentials(data.credentials || []))
      .catch(() => setCredentials([]))
      .finally(() => setLoading(false));
  }, [clientId]);

  const updateValue = (index: number, value: string) => {
    setCredentials(prev => prev.map((c, i) => i === index ? { ...c, value } : c));
    setSaveMsg("");
  };

  const toggleShow = (key: string) => {
    setShowValues(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSave = async () => {
    setSaving(true); setSaveMsg("");
    try {
      const res = await saveCredentials(clientId, credentials);
      setSaveMsg(res.message || "Saved!");
      setTimeout(() => setSaveMsg(""), 4000);
    } catch (e: any) {
      setSaveMsg("Error: " + (e.message || "Save failed"));
    } finally {
      setSaving(false);
    }
  };

  const filledCount = credentials.filter(c => c.value.trim() !== "").length;
  const totalCount = credentials.length;

  if (loading) return (
    <div className="card" style={{ padding: 48, textAlign: "center" }}>
      <div className="spin-slow" style={{ width: 36, height: 36, borderRadius: 10, background: "var(--gradient-primary)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 18, color: "white", marginBottom: 10 }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading credentials…</p>
    </div>
  );

  if (credentials.length === 0) return (
    <div className="card" style={{ padding: 48, textAlign: "center" }}>
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" style={{ marginBottom: 12 }}><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
      <p style={{ color: "var(--text-muted)", fontSize: 14, fontWeight: 500 }}>No credentials required</p>
      <p style={{ color: "var(--text-muted)", fontSize: 12.5, marginTop: 4 }}>Run the pipeline first to generate integration configs with credential references.</p>
    </div>
  );

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 9, background: "var(--accent-blue-pale)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#0653c7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
          </div>
          <div>
            <span style={{ fontSize: 15, fontWeight: 700 }}>API Credentials</span>
            <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 8 }}>{filledCount}/{totalCount} configured</span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {saveMsg && (
            <span style={{ fontSize: 12, fontWeight: 600, color: saveMsg.startsWith("Error") ? "#dc2626" : "#047857" }}>{saveMsg}</span>
          )}
          <button onClick={handleSave} disabled={saving}
            style={{
              padding: "8px 20px", borderRadius: 8, fontSize: 13, fontWeight: 600,
              border: "none", background: "#0653c7", color: "white",
              cursor: saving ? "wait" : "pointer", opacity: saving ? 0.7 : 1,
              transition: "all 0.15s",
            }}>
            {saving ? "Saving…" : "Save Credentials"}
          </button>
        </div>
      </div>

      {/* Info banner */}
      <div style={{ padding: "10px 14px", marginBottom: 16, borderRadius: 8, background: "#eff6ff", border: "1px solid #bfdbfe", fontSize: 12.5, color: "#1e40af", lineHeight: 1.5 }}>
        These credentials are referenced as environment variables in your integration config. Values are stored locally in the project’s .env file and are never committed to version control.
      </div>

      {/* Credential rows */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {credentials.map((cred, i) => {
          const isSet = cred.value.trim() !== "";
          const visible = showValues[cred.key] || false;
          // Extract prefix for grouping label
          const prefix = cred.key.split("_")[0];
          const showGroupLabel = i === 0 || credentials[i - 1].key.split("_")[0] !== prefix;

          return (
            <div key={cred.key}>
              {showGroupLabel && (
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.6px", marginTop: i > 0 ? 12 : 0, marginBottom: 6 }}>{prefix}</div>
              )}
              <div style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "12px 16px", borderRadius: 10,
                background: "white", border: "1px solid var(--border-subtle)",
                transition: "border-color 0.15s",
              }}>
                {/* Key label */}
                <div style={{ minWidth: 220, flexShrink: 0 }}>
                  <code style={{
                    fontSize: 12.5, fontWeight: 600, color: "var(--text-primary)",
                    fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
                  }}>${cred.key}</code>
                </div>

                {/* Input */}
                <div style={{ flex: 1, position: "relative" }}>
                  <input
                    type={visible ? "text" : "password"}
                    value={cred.value}
                    onChange={e => updateValue(i, e.target.value)}
                    placeholder="Enter value…"
                    style={{
                      width: "100%", padding: "8px 36px 8px 12px", borderRadius: 7,
                      fontSize: 13, border: "1px solid var(--border-subtle)",
                      background: "var(--bg-surface)", color: "var(--text-primary)",
                      fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
                      outline: "none", transition: "border-color 0.15s",
                    }}
                    onFocus={e => e.target.style.borderColor = "#0653c7"}
                    onBlur={e => e.target.style.borderColor = "var(--border-subtle)"}
                  />
                  <button
                    onClick={() => toggleShow(cred.key)}
                    style={{
                      position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)",
                      background: "none", border: "none", cursor: "pointer",
                      color: "var(--text-muted)", fontSize: 13, padding: 2,
                    }}
                    title={visible ? "Hide" : "Show"}
                  >
                    {visible ? (
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                    ) : (
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    )}
                  </button>
                </div>

                {/* Status indicator */}
                <div style={{
                  width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                  background: isSet ? "#10b981" : "#d1d5db",
                  transition: "background 0.2s",
                }} title={isSet ? "Configured" : "Empty"} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
