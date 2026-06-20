import { ReactNode, useState } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  LayoutGrid, MessageSquare, Settings2, Database,
  AlertTriangle, Settings, Search, Bell, BrainCircuit,
  ChevronLeft, ChevronRight,
} from "lucide-react";
import { useQuery } from "@/hooks/useQuery";
import { api } from "@/lib/api";

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutGrid },
  { to: "/chat", label: "Chat Assistant", icon: MessageSquare },
  { to: "/machines", label: "Machines", icon: Settings2 },
  { to: "/knowledge-base", label: "Knowledge Base", icon: Database },
  { to: "/alerts", label: "Alerts", icon: AlertTriangle },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

function loadCollapsed(): boolean {
  try { return localStorage.getItem("ikb_sidebar_collapsed") === "true"; } catch { return false; }
}

export function AppShell({ children }: { children: ReactNode }) {
  const { location } = useRouterState();
  const path = location.pathname;
  const { data: activeAlerts } = useQuery(() => api.alerts.list({ status: "active" }));
  const alertCount = activeAlerts?.length ?? 0;

  const [collapsed, setCollapsed] = useState<boolean>(loadCollapsed);

  const toggle = () => {
    setCollapsed((v) => {
      const next = !v;
      try { localStorage.setItem("ikb_sidebar_collapsed", String(next)); } catch { /* noop */ }
      return next;
    });
  };

  const sidebarW = collapsed ? "w-[64px]" : "w-60";
  const mainPl   = collapsed ? "lg:pl-[64px]" : "lg:pl-60";

  return (
    <div className="flex min-h-screen w-full bg-background">

      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <aside
        className={`fixed inset-y-0 left-0 z-30 hidden flex-col bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-in-out lg:flex ${sidebarW}`}
      >
        {/* Logo row */}
        <div className={`flex items-center border-b border-sidebar-border ${collapsed ? "justify-center px-0 py-5" : "gap-3 px-4 py-5"}`}>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/15 ring-1 ring-primary/40">
            <BrainCircuit className="h-5 w-5 text-primary" strokeWidth={2.2} />
          </div>
          {!collapsed && (
            <div className="flex flex-1 items-center justify-between overflow-hidden">
              <div className="leading-tight">
                <div className="text-base font-bold tracking-tight whitespace-nowrap">IKB</div>
                <div className="text-[11px] text-sidebar-muted whitespace-nowrap">Knowledge Brain</div>
              </div>
              <button
                id="sidebar-toggle-btn"
                onClick={toggle}
                title="Collapse sidebar"
                className="ml-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-sidebar-muted hover:bg-sidebar-active/60 hover:text-sidebar-foreground transition"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
            </div>
          )}
          {collapsed && (
            <button
              id="sidebar-toggle-btn"
              onClick={toggle}
              title="Expand sidebar"
              className="absolute right-0 top-[18px] flex h-7 w-7 items-center justify-center rounded-md text-sidebar-muted hover:bg-sidebar-active/60 hover:text-sidebar-foreground transition"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Nav links */}
        <nav className={`flex-1 py-4 space-y-1 ${collapsed ? "px-2" : "px-3"}`}>
          {nav.map((item) => {
            const active = item.to === "/" ? path === "/" : path.startsWith(item.to);
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                title={collapsed ? item.label : undefined}
                className={`group relative flex items-center rounded-md py-2.5 text-sm transition-colors ${
                  collapsed ? "justify-center px-0" : "gap-3 px-3"
                } ${
                  active
                    ? "bg-sidebar-active text-sidebar-active-foreground"
                    : "text-sidebar-muted hover:bg-sidebar-active/60 hover:text-sidebar-foreground"
                }`}
              >
                {active && (
                  <span className="absolute left-0 top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-r bg-primary" />
                )}
                <Icon className="h-[18px] w-[18px] shrink-0" strokeWidth={2} />
                {!collapsed && <span className="font-medium">{item.label}</span>}

                {/* Tooltip when collapsed */}
                {collapsed && (
                  <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs font-semibold text-background opacity-0 shadow-lg transition-opacity group-hover:opacity-100 z-50">
                    {item.label}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="border-t border-sidebar-border py-3 px-3">
          {!collapsed && (
            <p className="px-2 text-[11px] text-sidebar-muted">Industrial AI Assistant v2.0</p>
          )}
        </div>
      </aside>

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <div className={`flex flex-1 flex-col transition-[padding] duration-200 ease-in-out ${mainPl}`}>
        <header className="sticky top-0 z-20 flex h-[60px] items-center justify-between gap-4 border-b border-border bg-card/95 px-6 backdrop-blur">
          <div className="relative w-full max-w-[420px]">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search machines, issues, solutions…"
              className="h-10 w-full rounded-full border border-border bg-secondary pl-11 pr-4 text-sm placeholder:text-muted-foreground focus:border-primary focus:bg-card focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          <div className="flex items-center gap-4">
            <Link
              to="/notifications"
              id="notifications-btn"
              className={`relative inline-flex h-10 w-10 items-center justify-center rounded-full transition hover:bg-secondary ${
                path === "/notifications" ? "text-primary bg-primary/10" : "text-foreground/70"
              }`}
              title="Notifications"
            >
              <Bell className="h-5 w-5" />
              {alertCount > 0 && (
                <span className="absolute right-1.5 top-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground animate-pulse">
                  {alertCount > 9 ? "9+" : alertCount}
                </span>
              )}
            </Link>
            <div className="flex items-center gap-3">
              <div className="hidden text-right text-xs leading-tight md:block">
                <div className="font-semibold text-foreground">Marc Laurent</div>
                <div className="text-muted-foreground">Maintenance Lead</div>
              </div>
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                ML
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
