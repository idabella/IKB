/**
 * BackendError — displays a friendly error panel when an API call fails.
 * Detects the "backend not running" case and shows setup instructions.
 */

import { AlertTriangle, RefreshCw, Terminal } from "lucide-react";

interface BackendErrorProps {
  error: string;
  onRetry?: () => void;
  context?: string; // e.g. "documents", "machines", "alerts"
}

const isBackendDown = (msg: string) =>
  msg.toLowerCase().includes("backend is not running") ||
  msg.toLowerCase().includes("cannot connect to backend") ||
  msg.toLowerCase().includes("failed to fetch") ||
  msg.toLowerCase().includes("networkerror") ||
  msg.toLowerCase().includes("load failed");

export function BackendError({ error, onRetry, context = "data" }: BackendErrorProps) {
  const backendDown = isBackendDown(error);

  return (
    <div
      className="rounded-xl border p-6 space-y-4"
      style={{
        borderColor: backendDown ? "hsl(var(--warning) / 0.35)" : "hsl(var(--destructive) / 0.35)",
        background: backendDown ? "hsl(var(--warning) / 0.05)" : "hsl(var(--destructive) / 0.05)",
      }}
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        <AlertTriangle
          className="mt-0.5 h-5 w-5 shrink-0"
          style={{ color: backendDown ? "hsl(var(--warning))" : "hsl(var(--destructive))" }}
        />
        <div>
          <p
            className="font-semibold text-sm"
            style={{ color: backendDown ? "hsl(var(--warning))" : "hsl(var(--destructive))" }}
          >
            {backendDown
              ? "Backend server is not running"
              : `Failed to load ${context}`}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">
            {backendDown
              ? "The FastAPI backend must be started before the frontend can fetch data."
              : error}
          </p>
        </div>
      </div>

      {/* Setup instructions when backend is down */}
      {backendDown && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            How to start the backend
          </p>

          {/* Option 1 — start.ps1 */}
          <div className="space-y-1">
            <p className="text-xs font-medium text-foreground">
              Option 1 — one-command launcher (recommended)
            </p>
            <div className="flex items-center gap-2 rounded-md bg-secondary px-3 py-2">
              <Terminal className="h-3.5 w-3.5 shrink-0 text-primary" />
              <code className="text-xs font-mono text-foreground select-all">
                .\start.ps1
              </code>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Run from the project root — starts both backend and frontend.
            </p>
          </div>

          {/* Option 2 — manual */}
          <div className="space-y-1">
            <p className="text-xs font-medium text-foreground">
              Option 2 — manual (in a separate terminal)
            </p>
            <div className="flex items-center gap-2 rounded-md bg-secondary px-3 py-2">
              <Terminal className="h-3.5 w-3.5 shrink-0 text-primary" />
              <code className="text-xs font-mono text-foreground select-all">
                uvicorn backend.main:app --reload --port 3000
              </code>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Run from the project root (the folder containing the{" "}
              <code className="text-[11px]">backend/</code> directory).
            </p>
          </div>

          {/* First-time setup */}
          <div className="rounded-md border border-border/60 bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground">
            <span className="font-semibold text-foreground">First time?</span>{" "}
            Install dependencies first:{" "}
            <code className="font-mono">
              pip install -r backend/requirements.txt
            </code>
          </div>
        </div>
      )}

      {/* Retry button */}
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-xs font-semibold text-foreground shadow-sm transition hover:bg-secondary active:scale-95"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Retry
        </button>
      )}
    </div>
  );
}
