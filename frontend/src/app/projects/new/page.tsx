"use client";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { createProject, uploadDocs, runPipeline } from "@/lib/api";

const STEPS = ["Client Info", "Upload Documents", "Launch Pipeline"];

export default function NewProjectPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [clientName, setClientName] = useState("");
  const [clientId, setClientId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleCreate = async () => {
    if (!clientName.trim()) return setError("Client name is required");
    setLoading(true); setError("");
    try {
      const r = await createProject(clientName.trim());
      setClientId(r.client_id);
      setStep(1);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleUpload = async () => {
    if (files.length === 0) return setError("Upload at least one document");
    setLoading(true); setError("");
    try {
      await uploadDocs(clientId, files);
      setStep(2);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleLaunch = async () => {
    setLoading(true); setError("");
    try {
      await runPipeline(clientId);
      router.push(`/projects/${clientId}`);
    } catch (e: any) { setError(e.message); setLoading(false); }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files).filter(
      f => f.name.endsWith(".pdf") || f.name.endsWith(".docx") || f.name.endsWith(".txt") || f.name.endsWith(".json")
    );
    setFiles(prev => [...prev, ...dropped]);
  };

  return (
    <div style={{ maxWidth: 560, margin: "0 auto", paddingTop: 16 }}>
      <a href="/" style={{ color: "var(--text-muted)", textDecoration: "none", fontSize: 13, marginBottom: 20, display: "inline-flex", alignItems: "center", gap: 4 }}>← Back to Dashboard</a>

      <h1 style={{ fontSize: 26, fontWeight: 800, marginBottom: 6, letterSpacing: "-0.5px" }}>New Project</h1>
      <p style={{ color: "var(--text-secondary)", fontSize: 14, marginBottom: 32, lineHeight: 1.5 }}>
        Set up a new integration pipeline in three simple steps.
      </p>

      {/* Stepper */}
      <div style={{ display: "flex", alignItems: "center", gap: 0, marginBottom: 36 }}>
        {STEPS.map((s, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{
                width: 30, height: 30, borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 12, fontWeight: 700,
                background: i < step ? "var(--gradient-success)" : i === step ? "var(--gradient-primary)" : "var(--bg-surface)",
                color: i <= step ? "white" : "var(--text-muted)",
                border: i <= step ? "none" : "1px solid var(--border-subtle)",
                transition: "all 0.3s ease",
                boxShadow: i === step ? "0 2px 8px rgba(6, 83, 199, 0.25)" : "none",
              }}>
                {i < step ? "✓" : i + 1}
              </div>
              <span style={{
                fontSize: 12.5, fontWeight: i === step ? 600 : 400,
                color: i === step ? "var(--text-primary)" : "var(--text-muted)",
                whiteSpace: "nowrap",
              }}>{s}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div style={{
                flex: 1, height: 2, margin: "0 12px", borderRadius: 1,
                background: i < step ? "var(--accent-emerald)" : "var(--border-subtle)",
                transition: "background 0.3s ease",
              }} />
            )}
          </div>
        ))}
      </div>

      {/* Step Content */}
      <div className="card animate-in" key={step} style={{ padding: 36 }}>
        {step === 0 && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 22 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: "var(--accent-blue-pale)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0653c7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
              </div>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700 }}>Client Information</h3>
                <p style={{ color: "var(--text-muted)", fontSize: 12.5 }}>Enter the enterprise client name to begin.</p>
              </div>
            </div>
            <label style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 6, display: "block" }}>Client Name *</label>
            <input
              value={clientName} onChange={e => setClientName(e.target.value)}
              placeholder="e.g. FinNova Technologies"
              onKeyDown={e => e.key === "Enter" && handleCreate()}
              style={{
                width: "100%", padding: "11px 14px", borderRadius: 10, fontSize: 14,
                background: "var(--bg-input)", border: "1px solid var(--border-subtle)",
                color: "var(--text-primary)", outline: "none", marginBottom: 22,
                transition: "border-color 0.15s ease",
              }}
              onFocus={e => e.target.style.borderColor = "#0653c7"}
              onBlur={e => e.target.style.borderColor = "var(--border-subtle)"}
            />
            <button className="btn-primary" onClick={handleCreate} disabled={loading} style={{ width: "100%" }}>
              {loading ? "Creating…" : "Create Project"}
            </button>
          </>
        )}

        {step === 1 && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 22 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: "var(--accent-blue-pale)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0653c7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              </div>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 700 }}>Upload Documents</h3>
                <p style={{ color: "var(--text-muted)", fontSize: 12.5 }}>BRDs, SOWs, or API specs — .pdf, .docx, .txt, .json</p>
              </div>
            </div>
            <div
              className={`upload-zone ${dragOver ? "drag-over" : ""}`}
              onClick={() => fileRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
            >
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginBottom: 8, opacity: 0.6 }}>
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <p style={{ color: "var(--text-secondary)", fontSize: 14, fontWeight: 500 }}>Drag & drop files here</p>
              <p style={{ color: "var(--text-muted)", fontSize: 12.5, marginTop: 4 }}>or click to browse</p>
            </div>
            <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.txt,.json"
              style={{ display: "none" }}
              onChange={e => setFiles(prev => [...prev, ...Array.from(e.target.files || [])])}
            />
            {files.length > 0 && (
              <div style={{ marginTop: 16 }}>
                {files.map((f, i) => (
                  <div key={i} className="animate-in" style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "10px 14px", borderRadius: 8,
                    background: "var(--bg-surface)", marginBottom: 6,
                    border: "1px solid var(--border-subtle)",
                    animationDelay: `${i * 0.05}s`,
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                      <span style={{ fontSize: 13, fontWeight: 500 }}>{f.name}</span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>({(f.size / 1024).toFixed(0)} KB)</span>
                    </div>
                    <button onClick={() => setFiles(files.filter((_, j) => j !== i))}
                      style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 16, transition: "color 0.15s" }}
                      onMouseEnter={e => (e.currentTarget.style.color = "#dc2626")}
                      onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}>×</button>
                  </div>
                ))}
              </div>
            )}
            <button className="btn-primary" onClick={handleUpload} disabled={loading} style={{ width: "100%", marginTop: 20 }}>
              {loading ? "Uploading…" : `Upload ${files.length} file${files.length !== 1 ? "s" : ""}`}
            </button>
          </>
        )}

        {step === 2 && (
          <div style={{ padding: "8px 0" }}>
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: "linear-gradient(135deg, #0653c7 0%, #3b82f6 100%)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              </div>
              <div>
                <h3 style={{ fontSize: 18, fontWeight: 700, letterSpacing: "-0.3px" }}>Pipeline Ready</h3>
                <p style={{ color: "var(--text-muted)", fontSize: 12.5 }}>Documents uploaded successfully. Ready to begin processing.</p>
              </div>
            </div>

            <div style={{ borderTop: "1px solid var(--border-subtle)", margin: "18px 0 20px" }} />

            {/* Pipeline Stages */}
            <p style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 14 }}>7-Stage Automated Pipeline</p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0px 24px" }}>
              {[
               { n: 1, name: "Ingestion", desc: "Document intake" },
                { n: 2, name: "Parsing", desc: "Entity extraction" },
                { n: 3, name: "Matching", desc: "Adapter & version matching" },
                { n: 4, name: "Reasoning", desc: "Decision report" },
                { n: 5, name: "Cleaning", desc: "Production sanitization" },
                { n: 6, name: "Review", desc: "Human-in-the-loop" },
                { n: 7, name: "Simulation", desc: "Dry run validation" },
              ].map((s, i) => (
                <div key={i} className="animate-in" style={{
                  display: "flex", alignItems: "center", gap: 12,
                  padding: "10px 0",
                  borderBottom: (i < 5) ? "1px solid var(--border-subtle)" : (i === 5 ? "1px solid var(--border-subtle)" : "none"),
                  animationDelay: `${i * 0.04}s`,
                }}>
                  <div style={{
                    width: 26, height: 26, borderRadius: 7, flexShrink: 0,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 11, fontWeight: 700, letterSpacing: "-0.3px",
                    background: "var(--bg-surface)", border: "1px solid var(--border-subtle)",
                    color: "var(--text-secondary)",
                  }}>{s.n}</div>
                  <div>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", display: "block", lineHeight: 1.2 }}>{s.name}</span>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{s.desc}</span>
                  </div>
                </div>
              ))}
            </div>

            <div style={{ borderTop: "1px solid var(--border-subtle)", margin: "18px 0 22px" }} />

            <button className="btn-primary" onClick={handleLaunch} disabled={loading}
              style={{ width: "100%", padding: "12px 36px", fontSize: 14, fontWeight: 700, letterSpacing: "-0.2px" }}>
              {loading ? "Launching Pipeline…" : "Launch Pipeline"}
            </button>
          </div>
        )}

        {error && <p style={{ color: "#dc2626", fontSize: 13, marginTop: 14, textAlign: "center", padding: "8px 12px", background: "#fef2f2", borderRadius: 8 }}>{error}</p>}
      </div>
    </div>
  );
}
