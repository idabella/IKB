import { type MachineStatus } from "@/lib/api";

const map: Record<MachineStatus, { label: string; cls: string; dot: string }> = {
  online: { label: "Online", cls: "bg-success/15 text-success", dot: "bg-success" },
  alert: { label: "Alert", cls: "bg-destructive/15 text-destructive", dot: "bg-destructive" },
  warning: { label: "Warning", cls: "bg-warning/20 text-warning-foreground", dot: "bg-warning" },
  maintenance: { label: "Maintenance", cls: "bg-info/15 text-info", dot: "bg-info" },
};

export function StatusBadge({ status, pulse = false }: { status: MachineStatus; pulse?: boolean }) {
  const s = map[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${s.cls}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot} ${pulse ? "alert-pulse" : ""}`} />
      {s.label}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: "high" | "medium" | "low" }) {
  const map = {
    high: "bg-destructive text-destructive-foreground",
    medium: "bg-warning text-warning-foreground",
    low: "bg-success text-success-foreground",
  } as const;
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${map[severity]}`}
    >
      {severity}
    </span>
  );
}
