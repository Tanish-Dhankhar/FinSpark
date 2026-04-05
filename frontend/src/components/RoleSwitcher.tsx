"use client";
import { useAuth, ROLE_META, Role } from "@/lib/auth";
import { useState, useRef, useEffect } from "react";

const ROLES: Role[] = ["admin", "standard", "client"];

export default function RoleSwitcher() {
  const { role, setRole, clientId, setClientId } = useAuth();
  const [open, setOpen] = useState(false);
  const [showClientInput, setShowClientInput] = useState(false);
  const [tempCid, setTempCid] = useState(clientId || "");
  const ref = useRef<HTMLDivElement>(null);
  const meta = ROLE_META[role];

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const pickRole = (r: Role) => {
    if (r === "client") {
      setShowClientInput(true);
    } else {
      setRole(r);
      setShowClientInput(false);
      setOpen(false);
    }
  };

  const confirmClient = () => {
    if (tempCid.trim()) {
      setClientId(tempCid.trim());
      setRole("client");
      setShowClientInput(false);
      setOpen(false);
      // redirect to their project
      window.location.href = `/projects/${tempCid.trim()}`;
    }
  };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      {/* Current Role Badge */}
      <button
        onClick={() => setOpen(!open)}
        style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "6px 14px 6px 10px", borderRadius: 10,
          border: `1.5px solid ${meta.color}30`, background: meta.bg,
          cursor: "pointer", fontSize: 12.5, fontWeight: 600,
          color: meta.color, transition: "all 0.15s",
          boxShadow: open ? `0 0 0 3px ${meta.color}18` : "none",
        }}
      >
        <span style={{ fontSize: 14 }}>{meta.icon}</span>
        {meta.label} View
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
          style={{ transition: "transform 0.2s", transform: open ? "rotate(180deg)" : "rotate(0)" }}>
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 6px)", right: 0,
          width: 280, background: "white", borderRadius: 14,
          border: "1px solid var(--border-subtle)",
          boxShadow: "0 12px 40px rgba(0,0,0,0.12), 0 4px 12px rgba(0,0,0,0.06)",
          padding: 6, zIndex: 100,
          animation: "fadeIn 0.15s ease",
        }}>
          <div style={{ padding: "10px 14px 8px", fontSize: 10.5, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.8px" }}>
            Switch Access Level
          </div>

          {ROLES.map(r => {
            const m = ROLE_META[r];
            const isActive = r === role;
            return (
              <button
                key={r}
                onClick={() => pickRole(r)}
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 12,
                  padding: "10px 14px", borderRadius: 10,
                  border: "none", background: isActive ? m.bg : "transparent",
                  cursor: "pointer", textAlign: "left",
                  transition: "all 0.12s",
                }}
                onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = "#f8fafc"; }}
                onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
              >
                <div style={{
                  width: 34, height: 34, borderRadius: 9,
                  background: isActive ? `${m.color}14` : "#f1f5f9",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 16, flexShrink: 0,
                  border: isActive ? `1.5px solid ${m.color}40` : "1px solid transparent",
                  transition: "all 0.12s",
                }}>
                  {m.icon}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: isActive ? m.color : "var(--text-primary)" }}>
                    {m.label}
                    {isActive && <span style={{ fontSize: 10, marginLeft: 6, fontWeight: 700, opacity: 0.7 }}>ACTIVE</span>}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>{m.desc}</div>
                </div>
                {isActive && (
                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: m.color, flexShrink: 0 }} />
                )}
              </button>
            );
          })}

          {/* Client ID Input */}
          {showClientInput && (
            <div style={{
              margin: "6px 8px 8px", padding: 12, borderRadius: 10,
              background: "#ecfdf5", border: "1px solid #a7f3d0",
            }}>
              <label style={{ fontSize: 11, fontWeight: 600, color: "#065f46", marginBottom: 6, display: "block" }}>
                Enter Client ID
              </label>
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  value={tempCid}
                  onChange={e => setTempCid(e.target.value)}
                  placeholder="e.g. client_101960f3"
                  onKeyDown={e => e.key === "Enter" && confirmClient()}
                  style={{
                    flex: 1, padding: "7px 10px", borderRadius: 7,
                    fontSize: 12.5, border: "1px solid #a7f3d0",
                    background: "white", outline: "none",
                    fontFamily: "'SF Mono', 'Consolas', monospace",
                  }}
                  autoFocus
                />
                <button onClick={confirmClient} style={{
                  padding: "7px 14px", borderRadius: 7, fontSize: 12, fontWeight: 700,
                  border: "none", background: "#059669", color: "white", cursor: "pointer",
                }}>
                  Go
                </button>
              </div>
            </div>
          )}

          {/* Current Role Info */}
          {role === "client" && clientId && (
            <div style={{
              margin: "2px 8px 8px", padding: "8px 12px", borderRadius: 8,
              background: "#f0fdf4", fontSize: 11, color: "#065f46",
            }}>
              Bound to: <code style={{ fontWeight: 700 }}>{clientId}</code>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
