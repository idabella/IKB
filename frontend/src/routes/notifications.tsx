import { createFileRoute, Link } from "@tanstack/react-router";
import { useState, useMemo } from "react";
import {
  Bell, AlertTriangle, CheckCircle2, Info, Wrench,
  Clock, Filter, CheckCheck, Trash2, ChevronRight,
  RefreshCw, Loader2,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { api, type Alert } from "@/lib/api";
import { useQuery } from "@/hooks/useQuery";

export const Route = createFileRoute("/notifications")({
  head: () => ({
    meta: [
      { title: "Notifications — IKB" },
      { name: "description", content: "Real-time machine alerts and system notifications." },
    ],
  }),
  component: NotificationsPage,
});

type FilterTab = "all" | "active" | "acknowledged" | "resolved";
type SeverityFilter = "all" | "high" | "medium" | "low";

function severityIcon(severity: Alert["severity"]) {
  if (severity === "high") return <AlertTriangle className="h-4 w-4 text-destructive" />;
  if (severity === "medium") return <AlertTriangle className="h-4 w-4 text-warning" />;
  return <Info className="h-4 w-4 text-info" />;
}

function severityBadge(severity: Alert["severity"]) {
  const cls =
    severity === "high"
      ? "bg-destructive/10 text-destructive"
      : severity === "medium"
      ? "bg-warning/15 text-warning"
      : "bg-info/10 text-info";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${cls}`}>
      {severity}
    </span>
  );
}

function statusBadge(status: Alert["status"]) {
  const map: Record<Alert["status"], string> = {
    active: "bg-destructive/10 text-destructive",
    acknowledged: "bg-warning/15 text-warning",
    resolved: "bg-success/10 text-success",
  };
  const icons: Record<Alert["status"], React.ReactNode> = {
    active: <span className="h-1.5 w-1.5 rounded-full bg-destructive animate-pulse" />,
    acknowledged: <Clock className="h-3 w-3" />,
    resolved: <CheckCircle2 className="h-3 w-3" />,
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${map[status]}`}>
      {icons[status]} {status}
    </span>
  );
}

function NotificationsPage() {
  const { data, loading, error, refetch } = useQuery<Alert[]>(() => api.alerts.list());
  const alerts = data ?? [];

  const [tab, setTab] = useState<FilterTab>("all");
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [busyId, setBusyId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    return alerts.filter((a) => {
      const matchTab = tab === "all" || a.status === tab;
      const matchSev = severity === "all" || a.severity === severity;
      return matchTab && matchSev;
    });
  }, [alerts, tab, severity]);

  const counts = useMemo(() => ({
    all: alerts.length,
    active: alerts.filter((a) => a.status === "active").length,
    acknowledged: alerts.filter((a) => a.status === "acknowledged").length,
    resolved: alerts.filter((a) => a.status === "resolved").length,
  }), [alerts]);

  const handleAcknowledge = async (id: string) => {
    setBusyId(id);
    try { await api.alerts.acknowledge(id); refetch(); } finally { setBusyId(null); }
  };

  const handleResolve = async (id: string) => {
    setBusyId(id);
    try { await api.alerts.resolve(id); refetch(); } finally { setBusyId(null); }
  };

  const tabs: { key: FilterTab; label: string }[] = [
    { key: "all", label: "All" },
    { key: "active", label: "Active" },
    { key: "acknowledged", label: "Acknowledged" },
    { key: "resolved", label: "Resolved" },
  ];

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-6 px-6 py-6">

        {/* Header */}
        <header className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight">Notifications</h1>
              {counts.active > 0 && (
                <span className="inline-flex items-center justify-center rounded-full bg-destructive px-2 py-0.5 text-xs font-bold text-destructive-foreground">
                  {counts.active} active
                </span>
              )}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Real-time machine alerts and system events
            </p>
          </div>
          <button
            onClick={refetch}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-muted-foreground hover:bg-secondary transition"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </header>

        {/* Summary cards */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Total", value: counts.all, color: "text-foreground", bg: "bg-card" },
            { label: "Active", value: counts.active, color: "text-destructive", bg: "bg-destructive/5" },
            { label: "Acknowledged", value: counts.acknowledged, color: "text-warning", bg: "bg-warning/5" },
            { label: "Resolved", value: counts.resolved, color: "text-success", bg: "bg-success/5" },
          ].map((s) => (
            <div key={s.label} className={`rounded-xl border border-border ${s.bg} p-4 shadow-[var(--shadow-card)]`}>
              <p className="text-xs text-muted-foreground">{s.label}</p>
              <p className={`mt-1 text-2xl font-bold ${s.color}`}>{s.value}</p>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Status tabs */}
          <div className="flex items-center gap-1 rounded-xl border border-border bg-card p-1">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  tab === t.key
                    ? "bg-primary text-primary-foreground shadow"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t.label}
                <span className={`ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                  tab === t.key ? "bg-white/20 text-white" : "bg-secondary"
                }`}>
                  {counts[t.key]}
                </span>
              </button>
            ))}
          </div>

          {/* Severity filter */}
          <div className="ml-auto flex items-center gap-1.5">
            <Filter className="h-3.5 w-3.5 text-muted-foreground" />
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value as SeverityFilter)}
              className="rounded-lg border border-border bg-card px-2 py-1.5 text-xs font-semibold text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            >
              <option value="all">All severities</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>

        {/* List */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : error ? (
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-6 text-center text-sm text-destructive">
            Failed to load notifications. <button onClick={refetch} className="underline">Retry</button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-card py-16 text-center">
            <CheckCheck className="h-10 w-10 text-success/50" />
            <p className="text-sm font-semibold text-muted-foreground">All clear — no notifications here</p>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((alert) => (
              <div
                key={alert.id}
                className={`group relative rounded-xl border bg-card p-4 shadow-[var(--shadow-card)] transition hover:shadow-md ${
                  alert.status === "active" ? "border-destructive/30" : "border-border"
                }`}
              >
                {/* Active pulse stripe */}
                {alert.status === "active" && (
                  <span className="absolute left-0 top-4 h-8 w-[3px] rounded-r bg-destructive" />
                )}

                <div className="flex items-start gap-3">
                  {/* Icon */}
                  <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
                    alert.severity === "high" ? "bg-destructive/10" :
                    alert.severity === "medium" ? "bg-warning/10" : "bg-info/10"
                  }`}>
                    {severityIcon(alert.severity)}
                  </div>

                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-bold">{alert.machine}</span>
                      {severityBadge(alert.severity)}
                      {statusBadge(alert.status)}
                    </div>
                    <p className="mt-0.5 text-sm font-semibold text-foreground">{alert.type}</p>
                    <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{alert.description}</p>

                    <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />{alert.time}
                      </span>
                      <span className="flex items-center gap-1">
                        <Wrench className="h-3 w-3" />
                        {alert.current} / threshold {alert.threshold}
                      </span>
                      <span>{alert.duration}</span>
                    </div>

                    {alert.tags?.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {alert.tags.map((tag) => (
                          <span key={tag} className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex shrink-0 flex-col items-end gap-2">
                    {alert.status === "active" && (
                      <button
                        onClick={() => handleAcknowledge(alert.id)}
                        disabled={busyId === alert.id}
                        className="inline-flex items-center gap-1 rounded-lg border border-warning/40 bg-warning/10 px-2.5 py-1.5 text-[11px] font-semibold text-warning hover:bg-warning/20 disabled:opacity-50 transition"
                      >
                        {busyId === alert.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Clock className="h-3 w-3" />}
                        Acknowledge
                      </button>
                    )}
                    {alert.status !== "resolved" && (
                      <button
                        onClick={() => handleResolve(alert.id)}
                        disabled={busyId === alert.id}
                        className="inline-flex items-center gap-1 rounded-lg border border-success/40 bg-success/10 px-2.5 py-1.5 text-[11px] font-semibold text-success hover:bg-success/20 disabled:opacity-50 transition"
                      >
                        {busyId === alert.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
                        Resolve
                      </button>
                    )}
                    <Link
                      to="/alerts"
                      className="inline-flex items-center gap-0.5 text-[11px] font-medium text-primary hover:underline"
                    >
                      Details <ChevronRight className="h-3 w-3" />
                    </Link>
                  </div>
                </div>

                {alert.notes && (
                  <div className="mt-3 rounded-lg bg-secondary/60 px-3 py-2 text-xs text-muted-foreground">
                    📝 {alert.notes}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
