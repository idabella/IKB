import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  Cog,
  Plug,
  BrainCircuit,
  Bell,
  Users,
  Database,
  Shield,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Settings — IKB" },
      { name: "description", content: "Configure IKB integrations, AI behaviour, notifications and access." },
    ],
  }),
  component: SettingsPage,
});

const sections = [
  { id: "general", label: "General", icon: Cog },
  { id: "integrations", label: "Integrations", icon: Plug },
  { id: "ai", label: "AI Configuration", icon: BrainCircuit },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "users", label: "Users & Roles", icon: Users },
  { id: "data", label: "Data Sources", icon: Database },
  { id: "security", label: "Security", icon: Shield },
] as const;

function SettingsPage() {
  const [active, setActive] = useState<(typeof sections)[number]["id"]>("general");

  return (
    <AppShell>
      <div className="mx-auto max-w-[1500px] px-6 py-6">
        <header className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">Settings &amp; Configuration</h1>
          <p className="mt-1 text-sm text-muted-foreground">Manage your IKB workspace</p>
        </header>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr]">
          <nav className="rounded-xl border border-border bg-card p-2 shadow-[var(--shadow-card)] h-fit">
            {sections.map((s) => {
              const Icon = s.icon;
              return (
                <button
                  key={s.id}
                  onClick={() => setActive(s.id)}
                  className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2.5 text-left text-sm font-medium transition ${
                    active === s.id
                      ? "bg-primary/10 text-primary"
                      : "text-foreground/70 hover:bg-secondary"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {s.label}
                </button>
              );
            })}
          </nav>

          <section className="rounded-xl border border-border bg-card p-6 shadow-[var(--shadow-card)]">
            {active === "general" && <GeneralTab />}
            {active === "integrations" && <IntegrationsTab />}
            {active === "ai" && <AITab />}
            {active === "notifications" && <NotificationsTab />}
            {active === "users" && <Placeholder title="Users & Roles" />}
            {active === "data" && <Placeholder title="Data Sources" />}
            {active === "security" && <Placeholder title="Security" />}
          </section>
        </div>
      </div>
    </AppShell>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

const inputCls =
  "h-10 w-full rounded-md border border-border bg-card px-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (b: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-center justify-between rounded-lg border border-border bg-card px-3 py-2.5 text-sm">
      <span className="font-medium">{label}</span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`relative h-5 w-9 rounded-full transition ${
          checked ? "bg-primary" : "bg-muted"
        }`}
        aria-pressed={checked}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition ${
            checked ? "left-[18px]" : "left-0.5"
          }`}
        />
      </button>
    </label>
  );
}

function GeneralTab() {
  return (
    <div className="space-y-5">
      <h2 className="text-lg font-semibold">General</h2>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <Field label="App Name">
          <input className={inputCls} defaultValue="IKB Industrial" />
        </Field>
        <Field label="Timezone">
          <select className={inputCls} defaultValue="europe-paris">
            <option value="europe-paris">Europe / Paris (UTC+1)</option>
            <option value="utc">UTC</option>
            <option value="us-east">US Eastern</option>
          </select>
        </Field>
        <Field label="Language">
          <select className={inputCls} defaultValue="en">
            <option value="en">English</option>
            <option value="fr">Français</option>
            <option value="de">Deutsch</option>
          </select>
        </Field>
        <Field label="Theme">
          <select className={inputCls} defaultValue="light">
            <option value="light">Light</option>
            <option value="dark">Dark</option>
            <option value="auto">Auto</option>
          </select>
        </Field>
      </div>
      <div className="flex justify-end gap-2 border-t border-border pt-4">
        <button className="rounded-md border border-border px-4 py-2 text-sm font-semibold hover:bg-secondary">
          Cancel
        </button>
        <button className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90">
          Save changes
        </button>
      </div>
    </div>
  );
}

function IntegrationsTab() {
  const items = [
    { name: "SCADA System", status: "connected", sync: "2 min ago" },
    { name: "ERP / SAP", status: "disconnected", sync: "—" },
    { name: "CMMS", status: "partial", sync: "1 hr ago" },
    { name: "Historian DB", status: "connected", sync: "5 min ago" },
    { name: "Email", status: "connected", sync: "Live" },
    { name: "Slack", status: "disconnected", sync: "—" },
  ];
  return (
    <div className="space-y-5">
      <h2 className="text-lg font-semibold">Integrations</h2>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {items.map((it) => (
          <div key={it.name} className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                  <Plug className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-sm font-bold">{it.name}</div>
                  <div className="text-[11px] text-muted-foreground">Last sync: {it.sync}</div>
                </div>
              </div>
              <StatusPill status={it.status} />
            </div>
            <div className="mt-3 flex justify-end">
              <button
                className={`rounded-md px-3 py-1.5 text-xs font-semibold ${
                  it.status === "disconnected"
                    ? "bg-primary text-primary-foreground"
                    : "border border-border text-foreground hover:bg-secondary"
                }`}
              >
                {it.status === "disconnected" ? "Connect" : "Configure"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  if (status === "connected")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-success">
        <CheckCircle2 className="h-3 w-3" /> Connected
      </span>
    );
  if (status === "partial")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-warning/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-warning">
        <AlertCircle className="h-3 w-3" /> Partial
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-destructive">
      <XCircle className="h-3 w-3" /> Disconnected
    </span>
  );
}

function AITab() {
  const [refs, setRefs] = useState(true);
  const [voice, setVoice] = useState(false);
  const [indexing, setIndexing] = useState(true);
  const [chunk, setChunk] = useState(512);
  const [sim, setSim] = useState(0.78);
  const [maxLen, setMaxLen] = useState(1200);
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">AI Configuration</h2>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <Field label="LLM Model">
          <select className={inputCls} defaultValue="ikb-pro">
            <option value="ikb-pro">IKB Pro (recommended)</option>
            <option value="ikb-fast">IKB Fast</option>
            <option value="ikb-reason">IKB Reasoning</option>
          </select>
        </Field>
        <Field label="Response Language">
          <select className={inputCls} defaultValue="auto">
            <option value="auto">Auto-detect</option>
            <option value="en">English</option>
            <option value="fr">Français</option>
          </select>
        </Field>
        <SliderField label={`Chunk Size — ${chunk} tokens`} value={chunk} min={128} max={2048} step={64} onChange={setChunk} />
        <SliderField label={`Similarity Threshold — ${sim.toFixed(2)}`} value={sim} min={0.3} max={0.99} step={0.01} onChange={setSim} />
        <SliderField label={`Max Response Length — ${maxLen} chars`} value={maxLen} min={200} max={4000} step={100} onChange={setMaxLen} />
      </div>

      <div className="space-y-2">
        <Toggle checked={indexing} onChange={setIndexing} label="Knowledge base indexing" />
        <Toggle checked={refs} onChange={setRefs} label="Include source references in responses" />
        <Toggle checked={voice} onChange={setVoice} label="Enable voice input" />
      </div>
    </div>
  );
}

function SliderField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (n: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[oklch(0.66_0.13_210)]"
      />
    </Field>
  );
}

function NotificationsTab() {
  const [email, setEmail] = useState(true);
  const [inApp, setInApp] = useState(true);
  const [sms, setSms] = useState(false);
  const [webhook, setWebhook] = useState(false);
  return (
    <div className="space-y-5">
      <h2 className="text-lg font-semibold">Notifications</h2>
      <div className="space-y-2">
        <Toggle checked={email} onChange={setEmail} label="Email alerts" />
        <Toggle checked={inApp} onChange={setInApp} label="In-app notifications" />
        <Toggle checked={sms} onChange={setSms} label="SMS alerts" />
        <Toggle checked={webhook} onChange={setWebhook} label="Webhook" />
      </div>
      <Field label="Notification Frequency">
        <select className={inputCls} defaultValue="immediate">
          <option value="immediate">Immediate</option>
          <option value="batched">Batched (15 min)</option>
          <option value="digest">Daily digest</option>
        </select>
      </Field>
    </div>
  );
}

function Placeholder({ title }: { title: string }) {
  return (
    <div className="space-y-2">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="text-sm text-muted-foreground">
        This section is part of the configuration shell. Detailed settings can be wired up here.
      </p>
    </div>
  );
}
