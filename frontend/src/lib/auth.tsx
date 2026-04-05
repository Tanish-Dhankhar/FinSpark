"use client";
import { createContext, useContext, useState, useEffect, ReactNode } from "react";

export type Role = "admin" | "standard" | "client";

interface AuthCtx {
  role: Role;
  setRole: (r: Role) => void;
  clientId: string | null;       // only relevant for client role
  setClientId: (id: string | null) => void;
}

const AuthContext = createContext<AuthCtx>({
  role: "admin",
  setRole: () => {},
  clientId: null,
  setClientId: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [role, _setRole] = useState<Role>("admin");
  const [clientId, _setClientId] = useState<string | null>(null);

  // Hydrate from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem("finspark_role");
    if (saved === "admin" || saved === "standard" || saved === "client") _setRole(saved);
    const savedCid = localStorage.getItem("finspark_client_id");
    if (savedCid) _setClientId(savedCid);
  }, []);

  const setRole = (r: Role) => {
    _setRole(r);
    localStorage.setItem("finspark_role", r);
  };
  const setClientId = (id: string | null) => {
    _setClientId(id);
    if (id) localStorage.setItem("finspark_client_id", id);
    else localStorage.removeItem("finspark_client_id");
  };

  return (
    <AuthContext.Provider value={{ role, setRole, clientId, setClientId }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

/* ── Role Metadata ─────────────────────────────── */
export const ROLE_META: Record<Role, { label: string; icon: ReactNode; color: string; bg: string; desc: string }> = {
  admin: { 
    label: "Admin", 
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>, 
    color: "#7c3aed", bg: "#f5f3ff", desc: "Full access to all sections" 
  },
  standard: { 
    label: "Standard", 
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>, 
    color: "#0653c7", bg: "#eff6ff", desc: "No credentials access" 
  },
  client: { 
    label: "Client", 
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z"/></svg>, 
    color: "#059669", bg: "#ecfdf5", desc: "Own project only" 
  },
};
