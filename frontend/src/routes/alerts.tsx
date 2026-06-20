import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { ChevronDown, AlertTriangle, MapPin, BrainCircuit, MessageSquare, Loader2, RefreshCw } from "lucide-react";
import { LineChart, Line, ReferenceLine, ResponsiveContainer, YAxis } from "recharts";
import { AppShell } from "@/components/AppShell";
import { SeverityBadge } from "@/components/StatusBadge";
import { BackendError } from "@/components/BackendError";
import { api, type Alert, type VibrationResponse } from "@/lib/api";
import { useQuery } from "@/hooks/useQuery";

export const Route = createFileRoute("/alerts")({
  head: () => ({
    meta: [
      { title: "Alerts — IKB" },
      { name: "description", content: "Real-time monitoring and alert management for industrial machines." },
    ],
  }),
  component: AlertsPage,
});

const tabs = ["All", "Active", "Acknowledged", "Resolved"] as const;

function AlertsPage() {
  const [tab, setTab] = useState<(typeof tabs)[number]>("All");
  const { data, loading, error, refetch } = useQuery<Alert[]>(() => api.alerts.list());
  const alerts = data ?? [];
  // Live vibration trend for the mini sparkline on each alert card
  const vibrationQuery = useQuery<VibrationResponse>(() => api.dashboard.vibration());

  const filtered =
    tab === "All"
      ? alerts
      : alerts.filter((a) =>
          tab === "Active"
            ? a.status === "active"
            : tab === "Acknowledged"
            ? a.status === "acknowledged"
            : a.status === "resolved"
        );

  const activeCount = alerts.filter((a) => a.status === "active").length;
  const ackCount = alerts.filter((a) => a.status === "acknowledged").length;
  const resolvedCount = alerts.filter((a) => a.status === "resolved").length;

  return (
    <AppShell>
      <div className="mx-auto max-w-[1500px] space-y-6 px-6 py-6">
        <header>
          <h1 className="text-2xl font-bold tracking-tight">System Alerts</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Real-time monitoring and alert management
          </p>
        </header>

        {/* Summary */}
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <SummaryCard tone="danger" value={activeCount} label="Active Alerts" />
          <SummaryCard tone="warn" value={ackCount} label="Acknowledged" />
          <SummaryCard tone="ok" value={resolvedCount} label="Resolved" />
          <SummaryCard tone="info" value={alerts.length} label="Total Alerts" />
        </div>

        {/* Filters */}
        <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3 shadow-[var(--shadow-card)] md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-1 rounded-lg bg-secondary p-1">
            {tabs.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-md px-3.5 py-1.5 text-xs font-semibold transition ${
                  tab === t
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <button
            onClick={refetch}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-2 text-xs font-semibold text-muted-foreground hover:bg-secondary"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>

        {/* Alert list */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-7 w-7 animate-spin text-primary" />
          </div>
        ) : error ? (
          <BackendError error={error} onRetry={refetch} context="alerts" />
        ) : filtered.length === 0 ? (
          <div className="rounded-xl border border-border bg-card p-10 text-center text-sm text-muted-foreground">
            No alerts in this category.
          </div>
        ) : (
          <div className="space-y-4">
            {filtered.map((a) => (
              <AlertCard key={a.id} alert={a} onUpdate={refetch} vibration={vibrationQuery.data} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}

function SummaryCard({ tone, value, label }: { tone: "danger" | "warn" | "ok" | "info"; value: number; label: string }) {
  const tones = {
    danger: "bg-destructive/8 border-destructive/30 text-destructive",
    warn: "bg-warning/15 border-warning/40 text-warning",
    ok: "bg-success/10 border-success/30 text-success",
    info: "bg-info/10 border-info/30 text-info",
  } as const;
  return (
    <div className={`rounded-xl border p-5 shadow-[var(--shadow-card)] ${tones[tone]}`}>
      <div className="flex items-center justify-between">
        <div className="text-3xl font-bold">{value}</div>
        <AlertTriangle className="h-5 w-5 opacity-70" />
      </div>
      <div className="mt-1 text-xs font-semibold uppercase tracking-wider opacity-90">{label}</div>
    </div>
  );
}

function AlertCard({ alert, onUpdate, vibration }: { alert: Alert; onUpdate: () => void; vibration?: VibrationResponse | null }) {
  const [expanded, setExpanded] = useState(false);
  const [note, setNote] = useState("");
  const [posting, setPosting] = useState(false);
  const [actioning, setActioning] = useState<"ack" | "resolve" | null>(null);

  const sevDot =
    alert.severity === "high" ? "bg-destructive" : alert.severity === "medium" ? "bg-warning" : "bg-success";

  const handleAcknowledge = async () => {
    setActioning("ack");
    try {
      await api.alerts.acknowledge(alert.id);
      onUpdate();
    } finally {
      setActioning(null);
    }
  };

  const handleResolve = async () => {
    setActioning("resolve");
    try {
      await api.alerts.resolve(alert.id);
      onUpdate();
    } finally {
      setActioning(null);
    }
  };

  const handlePostNote = async () => {
    if (!note.trim()) return;
    setPosting(true);
    try {
      await api.alerts.addNote(alert.id, note.trim());
      setNote("");
      onUpdate();
    } finally {
      setPosting(false);
    }
  };

  return (
    <article className="overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-card)]">
      <div className="grid grid-cols-1 gap-4 p-5 lg:grid-cols-12">
        {/* Left */}
        <div className="lg:col-span-5">
          <div className="flex items-start gap-3">
            <span className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${sevDot}/15`}>
              <span className={`h-2.5 w-2.5 rounded-full ${sevDot} ${alert.status === "active" ? "alert-pulse" : ""}`} />
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold">{alert.machine}</h3>
              </div>
              <div className="text-xs font-semibold text-muted-foreground">{alert.type}</div>
              <p className="mt-2 text-sm text-foreground/80">{alert.description}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {alert.tags.map((t, idx) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary px-2 py-0.5 text-[10px] font-semibold text-muted-foreground"
                  >
                    {idx === 2 && <MapPin className="h-2.5 w-2.5" />}
                    {t}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Center */}
        <div className="lg:col-span-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-border bg-secondary/30 p-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Current</div>
              <div className="text-lg font-bold text-destructive">{alert.current}</div>
            </div>
            <div className="rounded-lg border border-border bg-secondary/30 p-3">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Threshold</div>
              <div className="text-lg font-bold text-muted-foreground">{alert.threshold}</div>
            </div>
          </div>
          <div className="mt-2 text-[11px] font-semibold text-muted-foreground">{alert.duration}</div>
          <div className="mt-2 h-12">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={vibration?.data ?? []}>
                <YAxis hide domain={[0, 8]} />
                <ReferenceLine y={vibration?.threshold ?? 3.5} stroke="oklch(0.628 0.224 27.5)" strokeDasharray="3 3" />
                <Line type="monotone" dataKey="value" stroke="oklch(0.66 0.13 210)" strokeWidth={1.8} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right */}
        <div className="flex flex-col items-start gap-2 lg:col-span-3 lg:items-end">
          <SeverityBadge severity={alert.severity} />
          <div className="text-right">
            <div className="text-xs font-semibold">{alert.time}</div>
            <div className="text-[10px] text-muted-foreground">{alert.full_time}</div>
          </div>
          <div className="flex w-full flex-col gap-1.5 lg:items-end">
            {alert.status === "active" && (
              <button
                onClick={handleAcknowledge}
                disabled={actioning === "ack"}
                className="inline-flex items-center gap-1 rounded-md border border-warning/50 px-3 py-1.5 text-xs font-semibold text-warning hover:bg-warning/10 disabled:opacity-50"
              >
                {actioning === "ack" ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                Acknowledge
              </button>
            )}
            {alert.status !== "resolved" && (
              <button
                onClick={handleResolve}
                disabled={actioning === "resolve"}
                className="inline-flex items-center gap-1 rounded-md border border-success/50 px-3 py-1.5 text-xs font-semibold text-success hover:bg-success/10 disabled:opacity-50"
              >
                {actioning === "resolve" ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                Resolve
              </button>
            )}
            <button className="inline-flex items-center justify-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90">
              <BrainCircuit className="h-3.5 w-3.5" /> Diagnose with AI
            </button>
          </div>
          <div className="text-[11px] text-muted-foreground">
            Assigned: <span className="font-semibold text-foreground">{alert.assigned_to ?? "Unassigned"}</span>
          </div>
        </div>
      </div>

      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-center gap-1 border-t border-border bg-secondary/40 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground"
      >
        {expanded ? "Hide details" : "Show details"}
        <ChevronDown className={`h-3.5 w-3.5 transition ${expanded ? "rotate-180" : ""}`} />
      </button>

      {expanded && (
        <div className="grid grid-cols-1 gap-5 border-t border-border bg-secondary/20 p-5 lg:grid-cols-2">
          {/* Notes history */}
          <div>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Technician Notes
            </h4>
            {alert.notes ? (
              <pre className="whitespace-pre-wrap rounded-lg border border-border bg-card p-3 text-xs text-foreground/80">
                {alert.notes}
              </pre>
            ) : (
              <p className="text-xs text-muted-foreground">No notes yet.</p>
            )}
          </div>
          {/* Add note */}
          <div>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Add Note
            </h4>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="h-20 w-full rounded-lg border border-border bg-card p-2 text-xs focus:border-primary focus:outline-none"
              placeholder="Comment for technicians…"
            />
            <button
              onClick={handlePostNote}
              disabled={posting || !note.trim()}
              className="mt-2 inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {posting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MessageSquare className="h-3.5 w-3.5" />}
              Post note
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
