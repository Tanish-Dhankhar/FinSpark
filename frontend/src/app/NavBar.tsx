"use client";
import { AuthProvider, useAuth } from "@/lib/auth";
import RoleSwitcher from "@/components/RoleSwitcher";
import { ReactNode } from "react";

function NavContent({ children }: { children: ReactNode }) {
  const { role } = useAuth();
  return (
    <>
      <nav style={{
        position: 'sticky', top: 0, zIndex: 50,
        background: 'rgba(255, 255, 255, 0.92)',
        backdropFilter: 'blur(16px)',
        borderBottom: '1px solid var(--border-subtle)',
        transition: 'box-shadow 0.2s ease',
      }}>
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '10px 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <a href="/" style={{ display: 'flex', alignItems: 'center', gap: 0, textDecoration: 'none' }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo_dark.svg" alt="Logo" style={{ height: 30 }} />
          </a>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {role !== "client" && (
              <a href="/" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: 13.5, fontWeight: 500, transition: 'color 0.15s' }}>Dashboard</a>
            )}
            {role !== "client" && (
              <a href="/projects/new" className="btn-primary" style={{ padding: '8px 18px', fontSize: 13 }}>
                + New Project
              </a>
            )}
            <RoleSwitcher />
          </div>
        </div>
      </nav>
      <main style={{ maxWidth: 1280, margin: '0 auto', padding: '32px 28px' }}>
        {children}
      </main>
    </>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <NavContent>{children}</NavContent>
    </AuthProvider>
  );
}
