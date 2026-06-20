import { createFileRoute, Link } from "@tanstack/react-router";
import {
  CheckCircle2,
  AlertTriangle,
  Activity,
  Sparkles,
  ArrowUpRight,
  TrendingUp,
  BrainCircuit,
  Loader2,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  CartesianGrid,
} from "recharts";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";
import { BackendError } from "@/components/BackendError";
import { api, type Machine, type KpiResponse, type VibrationResponse, type Insight, type ActivityEvent } from "@/lib/api";
import { useQuery } from "@/hooks/useQuery";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Dashboard — IKB" },
      { name: "description", content: "Real-time industrial operations monitoring across all machines." },
    ],
  }),
  component: DashboardPage,
});

// ---------------------------------------------------------------------------
// KPI Card
// ---------------------------------------------------------------------------
function KpiCard({
  label,
  value,
  trend,
  trendColor = "text-success",
  sub,
  icon: Icon,
  iconBg,
  iconColor,
}: {
  label: string;
  value: string;
  trend?: string;
  trendColor?: string;
  sub?: { text: string; color: string };
  icon: React.ElementType;
  iconBg: string;
  iconColor: string;
}) {
  return (
    <div className="card-hover rounded-xl border border-border bg-card p-5 shadow-[var(--shadow-card)]">
      <div className="flex items-start justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${iconBg}`}>
          <Icon className={`h-4.5 w-4.5 ${iconColor}`} />
        </div>
      </div>
      <div className="mt-3 text-[34px] font-bold leading-none tracking-tight text-foreground">
        {value}
      </div>
      <div className="mt-2 flex items-center gap-1 text-xs">
        {trend && (
          <span className={`inline-flex items-center gap-1 font-semibold ${trendColor}`}>
            <TrendingUp className="h-3 w-3" />
            {trend}
          </span>
        )}
        {sub && <span className={`font-medium ${sub.color}`}>{sub.text}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading / Error helpers
// ---------------------------------------------------------------------------
function LoadingCard({ cols = 1 }: { cols?: number }) {
  return (
    <div className={`col-span-${cols} flex items-center justify-center rounded-xl border border-border bg-card p-10`}>
      <Loader2 className="h-6 w-6 animate-spin text-primary" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard Page
// ---------------------------------------------------------------------------
function DashboardPage() {
  const kpis = useQuery<KpiResponse>(() => api.dashboard.kpis());
  const vibration = useQuery<VibrationResponse>(() => api.dashboard.vibration("m2"));
  const activity = useQuery<ActivityEvent[]>(() => api.dashboard.activity());
  const insights = useQuery<Insight[]>(() => api.dashboard.insights());
  const machines = useQuery<Machine[]>(() => api.machines.list());

  return (
    <AppShell>
      <div className="mx-auto max-w-[1500px] space-y-6 px-6 py-6">
        <header>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard Overview</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Real-time industrial operations monitoring
          </p>
        </header>

        {/* KPI cards */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {kpis.loading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-[112px] animate-pulse rounded-xl border border-border bg-card" />
            ))
          ) : kpis.error ? (
            <div className="col-span-4"><BackendError error={kpis.error} onRetry={kpis.refetch} context="dashboard KPIs" /></div>
          ) : (
            <>
              <KpiCard
                label="Active Machines"
                value={String(kpis.data!.active_machines)}
                icon={CheckCircle2}
                iconBg="bg-success/15"
                iconColor="text-success"
              />
              <KpiCard
                label="Active Alerts"
                value={String(kpis.data!.active_alerts)}
                sub={
                  kpis.data!.active_alerts > 0
                    ? { text: `${kpis.data!.active_alerts} requiring attention`, color: "text-destructive" }
                    : { text: "All clear", color: "text-success" }
                }
                icon={AlertTriangle}
                iconBg="bg-warning/20"
                iconColor="text-warning"
              />
              <KpiCard
                label="Efficiency Rate"
                value={`${kpis.data!.efficiency_rate}%`}
                icon={Activity}
                iconBg="bg-primary/15"
                iconColor="text-primary"
              />
              <KpiCard
                label="AI Insights"
                value={String(kpis.data!.insight_count)}
                sub={{ text: "In knowledge base", color: "text-muted-foreground" }}
                icon={Sparkles}
                iconBg="bg-primary/15"
                iconColor="text-primary"
              />
            </>
          )}
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
          {/* Vibration trend */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-[var(--shadow-card)] lg:col-span-3">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-base font-semibold">Vibration Trend</h2>
                <p className="text-xs text-muted-foreground">
                  {vibration.data?.machine_name ?? "CNC Mill #3"} — Last 60 minutes
                </p>
              </div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-destructive/10 px-2.5 py-1 text-[11px] font-semibold text-destructive">
                <span className="h-1.5 w-1.5 rounded-full bg-destructive alert-pulse" />
                Above threshold
              </span>
            </div>
            <div className="mt-4 h-[260px]">
              {vibration.loading ? (
                <div className="flex h-full items-center justify-center">
                  <Loader2 className="h-6 w-6 animate-spin text-primary" />
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={vibration.data?.data ?? []} margin={{ top: 10, right: 12, left: -10, bottom: 0 }}>
                    <defs>
                      <linearGradient id="vibFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="oklch(0.66 0.13 210)" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="oklch(0.66 0.13 210)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.92 0.01 256)" vertical={false} />
                    <XAxis dataKey="time" tick={{ fontSize: 11, fill: "#94a3b8" }} stroke="#e2e8f0" />
                    <YAxis
                      domain={[0, 8]}
                      ticks={[0, 2, 4, 6, 8]}
                      tick={{ fontSize: 11, fill: "#94a3b8" }}
                      stroke="#e2e8f0"
                    />
                    <Tooltip
                      contentStyle={{
                        borderRadius: 8,
                        border: "1px solid #e2e8f0",
                        fontSize: 12,
                        boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                      }}
                      formatter={(v: number) => [`${v} mm/s`, "Vibration"]}
                    />
                    <ReferenceLine
                      y={vibration.data?.threshold ?? 3.5}
                      stroke="oklch(0.628 0.224 27.5)"
                      strokeDasharray="4 4"
                      label={{ value: "Threshold", position: "right", fill: "#ef4444", fontSize: 11 }}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="oklch(0.66 0.13 210)"
                      strokeWidth={2.5}
                      fill="url(#vibFill)"
                      activeDot={{ r: 5, fill: "#ef4444", stroke: "#fff", strokeWidth: 2 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Recent Activity */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-[var(--shadow-card)] lg:col-span-2">
            <h2 className="text-base font-semibold">Recent Activity</h2>

            {activity.loading ? (
              <div className="mt-6 flex justify-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>
            ) : activity.error ? (
              <BackendError error={activity.error} onRetry={activity.refetch} context="activity" />
            ) : (
              <ul className="mt-4 space-y-3">
                {(activity.data ?? []).map((a) => (
                  <li key={a.id} className="flex items-start gap-2.5 text-xs">
                    <span
                      className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                        a.kind === "ok"
                          ? "bg-success"
                          : a.kind === "warn"
                          ? "bg-warning"
                          : "bg-destructive"
                      }`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="font-semibold text-foreground">{a.machine}</div>
                      <div className="text-muted-foreground">{a.desc}</div>
                    </div>
                    <span className="shrink-0 text-muted-foreground">{a.time}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Bottom row */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
          {/* Machine table */}
          <div className="rounded-xl border border-border bg-card shadow-[var(--shadow-card)] lg:col-span-3">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h2 className="text-base font-semibold">Machine Status Overview</h2>
              <Link to="/machines" className="text-xs font-semibold text-primary hover:underline">
                View all →
              </Link>
            </div>
            {machines.loading ? (
              <div className="flex items-center justify-center p-10">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
              </div>
            ) : machines.error ? (
              <div className="p-5"><BackendError error={machines.error} onRetry={machines.refetch} context="machines" /></div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-secondary/60 text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                      <th className="px-5 py-3 font-semibold">Machine</th>
                      <th className="px-3 py-3 font-semibold">Type</th>
                      <th className="px-3 py-3 font-semibold">Status</th>
                      <th className="px-3 py-3 font-semibold">Last Check</th>
                      <th className="px-3 py-3 font-semibold">Efficiency</th>
                      <th className="px-5 py-3 font-semibold text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(machines.data ?? []).slice(0, 6).map((m, i) => (
                      <tr
                        key={m.id}
                        className={`border-t border-border ${i % 2 === 1 ? "bg-secondary/30" : ""}`}
                      >
                        <td className="px-5 py-3 font-semibold">{m.name}</td>
                        <td className="px-3 py-3 text-muted-foreground">{m.type.split(" ")[0]}</td>
                        <td className="px-3 py-3">
                          <StatusBadge status={m.status} pulse={m.status === "alert"} />
                        </td>
                        <td className="px-3 py-3 text-muted-foreground">{m.last_check}</td>
                        <td className="px-3 py-3">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-16 overflow-hidden rounded-full bg-secondary">
                              <div
                                className={`h-full ${
                                  m.efficiency >= 85
                                    ? "bg-success"
                                    : m.efficiency >= 75
                                    ? "bg-warning"
                                    : "bg-destructive"
                                }`}
                                style={{ width: `${m.efficiency}%` }}
                              />
                            </div>
                            <span className="text-xs font-semibold">{m.efficiency}%</span>
                          </div>
                        </td>
                        <td className="px-5 py-3 text-right">
                          <Link
                            to="/machines"
                            className="inline-flex items-center rounded-md border border-primary/30 px-2.5 py-1 text-xs font-semibold text-primary hover:bg-primary/10"
                          >
                            View
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* AI insights feed */}
          <div className="rounded-xl border border-border bg-card shadow-[var(--shadow-card)] lg:col-span-2">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h2 className="text-base font-semibold">AI Insights</h2>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-primary">
                Live
              </span>
            </div>
            {insights.loading ? (
              <div className="flex items-center justify-center p-10">
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
              </div>
            ) : insights.error ? (
              <div className="p-5"><BackendError error={insights.error} onRetry={insights.refetch} context="insights" /></div>
            ) : (
              <ul className="divide-y divide-border">
                {(insights.data ?? []).map((ins) => (
                  <li key={ins.id} className="px-5 py-4">
                    <div className="flex items-start gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/15">
                        <BrainCircuit className="h-4 w-4 text-primary" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-semibold">{ins.title}</div>
                        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{ins.desc}</p>
                        <div className="mt-2 flex items-center justify-between text-[11px]">
                          <span className="text-muted-foreground">{ins.time}</span>
                          <Link to="/chat" className="inline-flex items-center gap-0.5 font-semibold text-primary hover:underline">
                            View Details <ArrowUpRight className="h-3 w-3" />
                          </Link>
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
