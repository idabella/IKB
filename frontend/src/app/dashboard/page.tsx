"use client";

/**
 * PAGE DASHBOARD — /dashboard
 * ============================
 */

import { useEffect, useState } from "react";

const TELEMETRY_URL =
  process.env.NEXT_PUBLIC_TELEMETRY_URL || "http://localhost:8002";

// ── Types (la "forme" des données qu'on reçoit du backend) ──────────────────

type Machine = {
  machine_id: string;
  name: string;
  type: string | null;
  location: string | null;
  factory_id: string;
  active: boolean;
  sensor_count: number;
};

type SensorReading = {
  sensor_id: string;
  value: number;
  unit: string;
  recorded_at?: string;
  ts?: number;
};

type Anomaly = {
  anomaly_id: string;
  sensor_id: string;
  severity: string;
  value: number;
  timestamp: number;
  detector_type: string;
  description?: string;
};

export default function DashboardPage() {
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedMachineId, setSelectedMachineId] = useState<string | null>(
    null
  );

  // Au chargement de la page : on va chercher la liste des machines
  useEffect(() => {
    async function fetchMachines() {
      try {
        const response = await fetch(`${TELEMETRY_URL}/api/v1/machines`, {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        setMachines(data.machines || []);
        // Sélectionne automatiquement la première machine pour que la
        // page ne soit pas vide au premier affichage
        if (data.machines?.length > 0) {
          setSelectedMachineId(data.machines[0].machine_id);
        }
      } catch (err) {
        setError(
          "Impossible de joindre le Telemetry Aggregator (vérifie que " +
            "le backend tourne sur le port 8002, ou que ta route /machines " +
            "a bien été ajoutée — voir le guide d'installation)."
        );
      } finally {
        setLoading(false);
      }
    }
    fetchMachines();
  }, []);

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950 px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <div className="mb-10">
          <h1 className="bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-4xl font-bold text-transparent">
            Dashboard Machines
          </h1>
          <p className="mt-3 text-slate-400">
            Vue d&apos;ensemble des machines, capteurs et anomalies en temps
            réel
          </p>
        </div>

        {loading && (
          <p className="text-slate-400">Chargement des machines...</p>
        )}

        {error && (
          <div className="rounded-lg border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">
            {error}
          </div>
        )}

        {!loading && !error && machines.length === 0 && (
          <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4 text-sm text-slate-400">
            Aucune machine trouvée. As-tu lancé{" "}
            <code className="rounded bg-slate-800 px-1.5 py-0.5">
              python scripts/seed_data.py
            </code>{" "}
            pour insérer des données de démo ?
          </div>
        )}

        {!loading && machines.length > 0 && (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-[280px_1fr]">
            {/* ── Liste des machines (colonne de gauche) ──────────────── */}
            <div className="space-y-2">
              {machines.map((machine) => (
                <button
                  key={machine.machine_id}
                  onClick={() => setSelectedMachineId(machine.machine_id)}
                  className={`w-full rounded-lg border p-3 text-left transition-colors ${
                    selectedMachineId === machine.machine_id
                      ? "border-blue-500 bg-blue-950/40"
                      : "border-slate-700 bg-slate-900/40 hover:border-slate-500"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-white">
                      {machine.name}
                    </span>
                    <span
                      className={`h-2 w-2 rounded-full ${
                        machine.active ? "bg-emerald-400" : "bg-slate-600"
                      }`}
                    />
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {machine.machine_id} · {machine.sensor_count} capteur(s)
                  </p>
                </button>
              ))}
            </div>

            {/* ── Détail de la machine sélectionnée (colonne de droite) ── */}
            <div>
              {selectedMachineId && (
                <MachineDetail machineId={selectedMachineId} />
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

// ── Composant : détail d'une machine (capteurs + anomalies) ────────────────
function MachineDetail({ machineId }: { machineId: string }) {
  const [readings, setReadings] = useState<SensorReading[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchDetail() {
      setLoading(true);
      try {
        const [readingsRes, anomaliesRes] = await Promise.all([
          fetch(
            `${TELEMETRY_URL}/api/v1/sensors/machines/${machineId}/latest`,
            { cache: "no-store" }
          ),
          fetch(`${TELEMETRY_URL}/api/v1/anomalies/machines/${machineId}`, {
            cache: "no-store",
          }),
        ]);

        const readingsData = readingsRes.ok
          ? await readingsRes.json()
          : { readings: [] };
        const anomaliesData = anomaliesRes.ok
          ? await anomaliesRes.json()
          : { anomalies: [] };

        if (!cancelled) {
          setReadings(readingsData.readings || []);
          setAnomalies(anomaliesData.anomalies || []);
        }
      } catch {
        if (!cancelled) {
          setReadings([]);
          setAnomalies([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchDetail();
    // Rafraîchit automatiquement toutes les 10 secondes
    const interval = setInterval(fetchDetail, 10000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [machineId]);

  if (loading) {
    return <p className="text-slate-400">Chargement des détails...</p>;
  }

  return (
    <div className="space-y-6">
      {/* ── Dernières valeurs de capteurs ──────────────────────────── */}
      <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
        <h2 className="mb-4 font-semibold text-white">
          Dernières valeurs des capteurs
        </h2>
        {readings.length === 0 ? (
          <p className="text-sm text-slate-500">
            Aucune lecture récente pour cette machine.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {readings.map((reading) => (
              <div
                key={reading.sensor_id}
                className="rounded-lg border border-slate-800 bg-slate-950/60 p-3"
              >
                <p className="text-xs text-slate-500">{reading.sensor_id}</p>
                <p className="mt-1 text-xl font-semibold text-cyan-300">
                  {reading.value}
                  <span className="ml-1 text-sm text-slate-500">
                    {reading.unit}
                  </span>
                </p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Anomalies récentes ──────────────────────────────────────── */}
      <section className="rounded-xl border border-slate-700 bg-slate-900/40 p-5">
        <h2 className="mb-4 font-semibold text-white">Anomalies récentes</h2>
        {anomalies.length === 0 ? (
          <p className="text-sm text-slate-500">
            Aucune anomalie détectée — tout va bien.
          </p>
        ) : (
          <div className="space-y-2">
            {anomalies.map((anomaly) => (
              <AnomalyRow key={anomaly.anomaly_id} anomaly={anomaly} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// ── Composant : une ligne d'anomalie avec une couleur selon la sévérité ────
function AnomalyRow({ anomaly }: { anomaly: Anomaly }) {
  const severityColors: Record<string, string> = {
    LOW: "text-blue-300 border-blue-900",
    MEDIUM: "text-amber-300 border-amber-900",
    HIGH: "text-orange-300 border-orange-900",
    CRITICAL: "text-red-300 border-red-900",
  };
  const colorClass =
    severityColors[anomaly.severity?.toUpperCase()] ||
    "text-slate-300 border-slate-700";

  return (
    <div
      className={`flex items-center justify-between rounded-lg border ${colorClass} bg-slate-950/40 px-3 py-2 text-sm`}
    >
      <div>
        <span className="font-medium">{anomaly.severity}</span>
        <span className="ml-2 text-slate-400">{anomaly.sensor_id}</span>
        {anomaly.description && (
          <p className="mt-0.5 text-xs text-slate-500">
            {anomaly.description}
          </p>
        )}
      </div>
      <span className="text-xs text-slate-500">valeur: {anomaly.value}</span>
    </div>
  );
}
