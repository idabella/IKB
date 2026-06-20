/**
 * Minimal data-fetching hook.
 * Usage:
 *   const { data, loading, error, refetch } = useQuery(() => api.machines.list());
 *
 * On the very first network-level failure the hook waits 2 s and retries once
 * automatically — this covers the common race where the user opens the frontend
 * before uvicorn has fully started.
 */

import { useState, useEffect, useCallback, useRef } from "react";

export interface QueryResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Returns true when the error message indicates the backend server is down. */
export function isBackendError(msg: string | null): boolean {
  if (!msg) return false;
  const m = msg.toLowerCase();
  return (
    m.includes("backend is not running") ||
    m.includes("cannot connect to backend") ||
    m.includes("failed to fetch") ||
    m.includes("networkerror") ||
    m.includes("load failed")
  );
}

export function useQuery<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = []
): QueryResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  // Track whether we've already done the auto-retry for this tick
  const retriedRef = useRef(false);

  const refetch = useCallback(() => {
    retriedRef.current = false;
    setTick((n) => n + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    retriedRef.current = false;
    setLoading(true);
    setError(null);

    const attempt = () =>
      fetcher()
        .then((result) => {
          if (!cancelled) {
            setData(result);
            setLoading(false);
          }
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          const msg = err instanceof Error ? err.message : String(err);

          // Auto-retry once on network errors (backend may still be starting)
          if (isBackendError(msg) && !retriedRef.current) {
            retriedRef.current = true;
            setTimeout(() => {
              if (!cancelled) attempt();
            }, 2000);
            return;
          }

          setError(msg);
          setLoading(false);
        });

    attempt();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  return { data, loading, error, refetch };
}
