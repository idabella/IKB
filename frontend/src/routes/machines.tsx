import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  Search,
  Plus,
  Wrench,
  Thermometer,
  Activity,
  Zap,
  X,
  MessageSquare,
  Loader2,
  RefreshCw,
  Save,
  Trash2,
  AlertTriangle,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";
import { BackendError } from "@/components/BackendError";
import { api, type Machine } from "@/lib/api";
import { useQuery } from "@/hooks/useQuery";

export const Route = createFileRoute("/machines")({
  head: () => ({
    meta: [
      { title: "Machines — IKB" },
      { name: "description", content: "Monitor and manage all industrial equipment in real time." },
    ],
  }),
  component: MachinesPage,
});

function MachinesPage() {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selected, setSelected] = useState<Machine | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const { data, loading, error, refetch } = useQuery<Machine[]>(() => api.machines.list());

  const handleDelete = async (id: string) => {
    setDeleting(id);
    try {
      await api.machines.delete(id);
      if (selected?.id === id) setSelected(null);
      refetch();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete machine.");
    } finally {
      setDeleting(null);
    }
  };

  const machines = data ?? [];

  const filtered = useMemo(() => {
    return machines.filter((m) => {
      const q = query.toLowerCase();
      const matchQ =
        !q ||
        m.name.toLowerCase().includes(q) ||
        m.type.toLowerCase().includes(q) ||
        m.status.includes(q);
      const matchS = statusFilter === "all" || m.status === statusFilter;
      return matchQ && matchS;
    });
  }, [query, statusFilter, machines]);

  const total = machines.length;
  const online = machines.filter((m) => m.status === "online").length;
  const inAlert = machines.filter((m) => m.status === "alert").length;

  return (
    <AppShell>
      <div className="mx-auto max-w-[1500px] space-y-6 px-6 py-6">
        <header>
          <h1 className="text-2xl font-bold tracking-tight">Machine Management</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Monitor and manage all industrial equipment
          </p>
        </header>

        {/* Action bar */}
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="relative w-full md:max-w-md">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search machines by name, type, status…"
              className="h-10 w-full rounded-lg border border-border bg-card pl-10 pr-4 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
          <div className="flex items-center gap-2">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-10 rounded-lg border border-border bg-card px-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              <option value="all">All Status</option>
              <option value="online">Online</option>
              <option value="alert">Alert</option>
              <option value="warning">Warning</option>
              <option value="maintenance">Maintenance</option>
            </select>
            <button
              onClick={refetch}
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:bg-secondary"
              title="Refresh"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
            <button
              onClick={() => setShowAdd(true)}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground shadow hover:opacity-90"
            >
              <Plus className="h-4 w-4" /> Add Machine
            </button>
          </div>
        </div>

        {/* Summary stats */}
        <div className="grid grid-cols-3 gap-4">
          <SmallStat label="Total Machines" value={total} color="text-foreground" />
          <SmallStat label="Online" value={online} color="text-success" />
          <SmallStat label="In Alert" value={inAlert} color="text-destructive" />
        </div>

        {/* Grid */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : error ? (
          <BackendError error={error} onRetry={refetch} context="machines" />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filtered.length === 0 ? (
              <div className="col-span-3 rounded-xl border border-border bg-card p-10 text-center text-sm text-muted-foreground">
                No machines match the current filters.
              </div>
            ) : (
              filtered.map((m) => (
                <MachineCard
                  key={m.id}
                  machine={m}
                  onView={() => setSelected(m)}
                  onDelete={handleDelete}
                  isDeleting={deleting === m.id}
                />
              ))
            )}
          </div>
        )}
      </div>

      {/* Drawer */}
      {selected && (
        <MachineDrawer
          machine={selected}
          onClose={() => setSelected(null)}
          onDelete={handleDelete}
          isDeleting={deleting === selected.id}
        />
      )}

      {/* Add Machine Modal */}
      {showAdd && (
        <AddMachineModal
          onClose={() => setShowAdd(false)}
          onCreated={() => { setShowAdd(false); refetch(); }}
        />
      )}
    </AppShell>
  );
}

function SmallStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${color}`}>{value}</div>
    </div>
  );
}

function MachineCard({
  machine,
  onView,
  onDelete,
  isDeleting,
}: {
  machine: Machine;
  onView: () => void;
  onDelete: (id: string) => void;
  isDeleting: boolean;
}) {
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const isAlert = machine.status === "alert";

  return (
    <div
      className={`card-hover overflow-hidden rounded-xl border bg-card shadow-[var(--shadow-card)] ${
        isAlert ? "border-destructive/40 border-t-2 border-t-destructive" : "border-border"
      }`}
    >
      <div className="relative flex h-32 items-center justify-center bg-gradient-to-br from-secondary to-card">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <Wrench className="h-8 w-8" strokeWidth={1.6} />
        </div>
        <div className="absolute right-3 top-3 flex items-center gap-1.5">
          <StatusBadge status={machine.status} pulse={isAlert} />
          {/* Delete trigger */}
          {!confirmDelete && (
            <button
              onClick={(e) => { e.stopPropagation(); setConfirmDelete(true); }}
              className="flex h-6 w-6 items-center justify-center rounded-md bg-card/80 text-muted-foreground backdrop-blur hover:bg-destructive/10 hover:text-destructive transition-colors"
              title="Delete machine"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Inline delete confirmation banner */}
      {confirmDelete && (
        <div className="flex items-center gap-2 border-b border-destructive/30 bg-destructive/5 px-4 py-2.5">
          <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />
          <span className="flex-1 text-[11px] font-semibold text-destructive">Delete this machine?</span>
          <button
            onClick={() => setConfirmDelete(false)}
            className="rounded px-2 py-1 text-[11px] font-semibold text-muted-foreground hover:bg-secondary"
          >
            Cancel
          </button>
          <button
            disabled={isDeleting}
            onClick={() => { setConfirmDelete(false); onDelete(machine.id); }}
            className="inline-flex items-center gap-1 rounded bg-destructive px-2.5 py-1 text-[11px] font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            {isDeleting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
            Delete
          </button>
        </div>
      )}

      <div className="p-4">
        <h3 className="text-base font-bold">{machine.name}</h3>
        <p className="text-xs text-muted-foreground">{machine.type}</p>

        <div className="mt-3 grid grid-cols-3 gap-2 border-y border-border py-3 text-center">
          <Reading icon={Thermometer} value={`${machine.temp}°C`} label="Temp" />
          <Reading icon={Activity} value={`${machine.vibration}`} label="Vib mm/s" />
          <Reading icon={Zap} value={`${machine.efficiency}%`} label="Eff" />
        </div>

        <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground">
          Last checked {machine.last_check}
        </div>

        <div className="mt-3 flex items-center gap-2">
          <button
            onClick={onView}
            className="flex-1 rounded-md border border-primary/40 px-3 py-2 text-xs font-semibold text-primary hover:bg-primary/10"
          >
            View Details
          </button>
          <button
            onClick={() => navigate({ to: "/chat", search: { machine_id: machine.id } as never })}
            className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90"
          >
            <MessageSquare className="h-3.5 w-3.5" /> Chat AI
          </button>
        </div>
      </div>
    </div>
  );
}

function Reading({ icon: Icon, value, label }: { icon: React.ElementType; value: string; label: string }) {
  return (
    <div className="flex flex-col items-center">
      <Icon className="h-4 w-4 text-muted-foreground" />
      <div className="mt-1 text-sm font-bold">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
    </div>
  );
}

function MachineDrawer({
  machine,
  onClose,
  onDelete,
  isDeleting,
}: {
  machine: Machine;
  onClose: () => void;
  onDelete: (id: string) => void;
  isDeleting: boolean;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [tab, setTab] = useState<"overview" | "sensors" | "docs">("overview");
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-foreground/30 backdrop-blur-sm" onClick={onClose} />
      <div className="relative h-full w-full max-w-[480px] overflow-y-auto bg-card shadow-2xl">
        <div className="flex items-start justify-between border-b border-border px-6 py-5">
          <div>
            <h2 className="text-lg font-bold">{machine.name}</h2>
            <div className="mt-1 flex items-center gap-2">
              <StatusBadge status={machine.status} pulse={machine.status === "alert"} />
              <span className="text-xs text-muted-foreground">{machine.type}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!confirmDelete ? (
              <button
                onClick={() => setConfirmDelete(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-destructive/40 px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/10 transition-colors"
              >
                <Trash2 className="h-3.5 w-3.5" /> Delete
              </button>
            ) : (
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-semibold text-destructive">Sure?</span>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="rounded-md px-2 py-1 text-xs font-semibold text-muted-foreground hover:bg-secondary"
                >
                  Cancel
                </button>
                <button
                  disabled={isDeleting}
                  onClick={() => { setConfirmDelete(false); onDelete(machine.id); onClose(); }}
                  className="inline-flex items-center gap-1 rounded-md bg-destructive px-3 py-1 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
                >
                  {isDeleting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                  Delete
                </button>
              </div>
            )}
            <button onClick={onClose} className="rounded-md p-1 hover:bg-secondary" aria-label="Close">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="flex border-b border-border px-3 text-sm">
          {(
            [
              ["overview", "Overview"],
              ["sensors", "Sensors"],
              ["docs", "Documents"],
            ] as const
          ).map(([k, l]) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`relative px-3 py-3 text-xs font-semibold ${
                tab === k ? "text-primary" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {l}
              {tab === k && <span className="absolute inset-x-2 bottom-0 h-[2px] rounded-t bg-primary" />}
            </button>
          ))}
        </div>

        <div className="px-6 py-5">
          {tab === "overview" && (
            <div className="grid grid-cols-2 gap-5">
              <div className="space-y-2 text-sm">
                <Spec label="Type" value={machine.type} />
                <Spec label="Serial" value={machine.serial} />
                <Spec label="Installed" value={machine.installed} />
                <Spec label="Location" value={machine.location} />
                <Spec label="Department" value={machine.department} />
              </div>
              <div className="space-y-3">
                <Gauge label="Temperature" value={machine.temp} max={100} unit="°C" zone={machine.temp > 70 ? "warn" : "ok"} />
                <Gauge label="Vibration" value={machine.vibration} max={6} unit="mm/s" zone={machine.vibration > 3.5 ? "alert" : "ok"} />
                <Gauge label="Efficiency" value={machine.efficiency} max={100} unit="%" zone={machine.efficiency >= 85 ? "ok" : machine.efficiency >= 75 ? "warn" : "alert"} />
              </div>
            </div>
          )}
          {tab === "sensors" && (
            <ul className="space-y-2 text-sm">
              <SensorListRow label="Temperature" value={`${machine.temp}°C`} />
              <SensorListRow label="Vibration" value={`${machine.vibration} mm/s`} />
              <SensorListRow label="RPM" value={`${machine.rpm}`} />
              <SensorListRow label="Pressure" value={`${machine.pressure} bar`} />
              <SensorListRow label="Efficiency" value={`${machine.efficiency}%`} />
            </ul>
          )}
          {tab === "docs" && <DocsTab machineName={machine.name} />}
        </div>
      </div>
    </div>
  );
}

function DocsTab({ machineName }: { machineName: string }) {
  const { data, loading, error } = useQuery(
    () => api.documents.list({ q: machineName }),
    [machineName]
  );
  if (loading) return <div className="flex justify-center pt-6"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>;
  if (error) return <BackendError error={error} context="documents" />;
  if (!data?.length) return <p className="text-sm text-muted-foreground">No documents found for this machine.</p>;
  return (
    <ul className="space-y-2 text-sm">
      {data.map((d) => (
        <li key={d.id} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
          <div>
            <div className="font-semibold">{d.title}</div>
            <div className="text-[10px] text-muted-foreground">{d.category} · {d.date}</div>
          </div>
          <span className="ml-2 inline-flex items-center rounded bg-secondary px-2 py-0.5 text-[10px] font-bold uppercase text-muted-foreground">
            {d.type}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Spec({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}

function SensorListRow({ label, value }: { label: string; value: string }) {
  return (
    <li className="flex items-center justify-between rounded-md border border-border px-3 py-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold">{value}</span>
    </li>
  );
}

function Gauge({ label, value, max, unit, zone }: { label: string; value: number; max: number; unit: string; zone: "ok" | "warn" | "alert" }) {
  const pct = Math.min(100, (value / max) * 100);
  const color = zone === "ok" ? "stroke-success" : zone === "warn" ? "stroke-warning" : "stroke-destructive";
  const r = 28;
  const c = 2 * Math.PI * r;
  return (
    <div className="flex items-center gap-3">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r={r} className="stroke-secondary" strokeWidth="6" fill="none" />
        <circle
          cx="36" cy="36" r={r}
          className={color}
          strokeWidth="6" fill="none"
          strokeDasharray={`${(pct / 100) * c} ${c}`}
          strokeLinecap="round"
          transform="rotate(-90 36 36)"
        />
        <text x="36" y="40" textAnchor="middle" className="fill-foreground text-[11px] font-bold">{value}</text>
      </svg>
      <div>
        <div className="text-xs font-semibold">{label}</div>
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{unit}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add Machine Modal
// ---------------------------------------------------------------------------

const MACHINE_TYPES = [
  "CNC Milling Machine",
  "CNC Lathe",
  "Hydraulic Press",
  "Air Compressor",
  "Robotic Welder",
  "Conveyor Belt",
  "Injection Molder",
  "Industrial Robot",
  "Other",
];

function AddMachineModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    type: MACHINE_TYPES[0],
    status: "online" as Machine["status"],
    serial: "",
    installed: "",
    location: "",
    department: "",
    temp: 50,
    vibration: 1.0,
    rpm: 0,
    pressure: 1.0,
    efficiency: 90,
  });

  const set = (field: string, value: string | number) =>
    setForm((f) => ({ ...f, [field]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) { setFormError("Machine name is required."); return; }
    setSaving(true);
    setFormError(null);
    try {
      await api.machines.create({
        id: `m-${Date.now()}`,
        last_check: "just now",
        ...form,
      } as Machine);
      onCreated();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to create machine.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-foreground/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-[560px] max-h-[90vh] overflow-y-auto rounded-2xl border border-border bg-card shadow-2xl mx-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-5">
          <div>
            <h2 className="text-lg font-bold">Add New Machine</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Register a new machine in the system</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 hover:bg-secondary" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-5">
          {/* Identity */}
          <fieldset className="space-y-3">
            <legend className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2 block">Identity</legend>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="mb-1 block text-xs font-semibold">Machine Name *</label>
                <input
                  value={form.name}
                  onChange={(e) => set("name", e.target.value)}
                  placeholder="e.g. CNC Mill #7"
                  className="h-9 w-full rounded-lg border border-border bg-secondary/50 px-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold">Type</label>
                <select
                  value={form.type}
                  onChange={(e) => set("type", e.target.value)}
                  className="h-9 w-full rounded-lg border border-border bg-secondary/50 px-3 text-sm focus:border-primary focus:outline-none"
                >
                  {MACHINE_TYPES.map((t) => <option key={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold">Status</label>
                <select
                  value={form.status}
                  onChange={(e) => set("status", e.target.value)}
                  className="h-9 w-full rounded-lg border border-border bg-secondary/50 px-3 text-sm focus:border-primary focus:outline-none"
                >
                  <option value="online">Online</option>
                  <option value="warning">Warning</option>
                  <option value="alert">Alert</option>
                  <option value="maintenance">Maintenance</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold">Serial Number</label>
                <input
                  value={form.serial}
                  onChange={(e) => set("serial", e.target.value)}
                  placeholder="e.g. CNCM-2024-007"
                  className="h-9 w-full rounded-lg border border-border bg-secondary/50 px-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold">Install Date</label>
                <input
                  type="date"
                  value={form.installed}
                  onChange={(e) => set("installed", e.target.value)}
                  className="h-9 w-full rounded-lg border border-border bg-secondary/50 px-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold">Location</label>
                <input
                  value={form.location}
                  onChange={(e) => set("location", e.target.value)}
                  placeholder="e.g. Hall A"
                  className="h-9 w-full rounded-lg border border-border bg-secondary/50 px-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold">Department</label>
                <input
                  value={form.department}
                  onChange={(e) => set("department", e.target.value)}
                  placeholder="e.g. Production"
                  className="h-9 w-full rounded-lg border border-border bg-secondary/50 px-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </div>
            </div>
          </fieldset>

          {/* Sensors */}
          <fieldset className="space-y-3">
            <legend className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2 block">Initial Sensor Values</legend>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <NumericField label="Temperature (°C)" value={form.temp} min={0} max={200} step={0.5} onChange={(v) => set("temp", v)} />
              <NumericField label="Vibration (mm/s)" value={form.vibration} min={0} max={20} step={0.1} onChange={(v) => set("vibration", v)} />
              <NumericField label="RPM" value={form.rpm} min={0} max={10000} step={10} onChange={(v) => set("rpm", v)} />
              <NumericField label="Pressure (bar)" value={form.pressure} min={0} max={500} step={0.1} onChange={(v) => set("pressure", v)} />
              <NumericField label="Efficiency (%)" value={form.efficiency} min={0} max={100} step={1} onChange={(v) => set("efficiency", v)} />
            </div>
          </fieldset>

          {/* Error */}
          {formError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              ⚠️ {formError}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2 border-t border-border pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-muted-foreground hover:bg-secondary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground shadow hover:opacity-90 disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {saving ? "Saving…" : "Save Machine"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function NumericField({
  label, value, min, max, step, onChange,
}: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-semibold">{label}</label>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        className="h-9 w-full rounded-lg border border-border bg-secondary/50 px-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
      />
    </div>
  );
}
