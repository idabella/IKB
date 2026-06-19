"use client";

/**
 * PAGE DE STATUT DU SYSTÈME — /status
 * ====================================
*/

import { useEffect, useState } from "react";

// ── Configuration des services à surveiller ──────────────────────────────
// Si un camarade ajoute un nouveau service plus tard, il suffit d'ajouter
// une ligne ici, rien d'autre à modifier dans le fichier.
type ServiceConfig = {
  name: string;
  description: string;
  healthUrl: string;
  docsUrl: string;
};

const SERVICES: ServiceConfig[] = [
  {
    name: "API Gateway",
    description: "Authentification, RBAC, rate limiting, WebSocket",
    healthUrl:
      (process.env.NEXT_PUBLIC_API_GATEWAY_URL || "http://localhost:8000") +
      "/health",
    docsUrl:
      (process.env.NEXT_PUBLIC_API_GATEWAY_URL || "http://localhost:8000") +
      "/docs",
  },
  {
    name: "Knowledge Engine",
    description: "Agents IA, RAG, Knowledge Graph",
    healthUrl:
      (process.env.NEXT_PUBLIC_KNOWLEDGE_ENGINE_URL ||
        "http://localhost:8001") + "/health",
    docsUrl:
      (process.env.NEXT_PUBLIC_KNOWLEDGE_ENGINE_URL ||
        "http://localhost:8001") + "/docs",
  },
  {
    name: "Telemetry Aggregator",
    description: "Ingestion capteurs, détection d'anomalies",
    healthUrl:
      (process.env.NEXT_PUBLIC_TELEMETRY_URL || "http://localhost:8002") +
      "/health",
    docsUrl:
      (process.env.NEXT_PUBLIC_TELEMETRY_URL || "http://localhost:8002") +
      "/docs",
  },
];

// ── Forme des données qu'on va stocker pour chaque service ──────────────
type ServiceStatus = {
  name: string;
  description: string;
  docsUrl: string;
  state: "loading" | "healthy" | "down";
  detail?: string; // contenu brut renvoyé par /health (ex: singletons_ready)
  latencyMs?: number;
};

export default function StatusPage() {
  // statuses : la liste de l'état de chaque service. On démarre avec
  // tout en "loading" (en cours de vérification).
  const [statuses, setStatuses] = useState<ServiceStatus[]>(
    SERVICES.map((s) => ({
      name: s.name,
      description: s.description,
      docsUrl: s.docsUrl,
      state: "loading",
    }))
  );

  // lastChecked : la dernière fois qu'on a rafraîchi (juste pour affichage)
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  // checkAllServices : fonction qui interroge les 3 services en parallèle
  async function checkAllServices() {
    const results = await Promise.all(
      SERVICES.map(async (service) => {
        const startedAt = performance.now();
        try {
          // On donne 5 secondes max à chaque service pour répondre,
          // sinon on considère qu'il est down.
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 5000);

          const response = await fetch(service.healthUrl, {
            signal: controller.signal,
            cache: "no-store",
          });
          clearTimeout(timeout);

          const latencyMs = Math.round(performance.now() - startedAt);

          if (!response.ok) {
            return {
              name: service.name,
              description: service.description,
              docsUrl: service.docsUrl,
              state: "down" as const,
              detail: `HTTP ${response.status}`,
              latencyMs,
            };
          }

          const data = await response.json();
          return {
            name: service.name,
            description: service.description,
            docsUrl: service.docsUrl,
            state: "healthy" as const,
            detail: JSON.stringify(data),
            latencyMs,
          };
        } catch (error) {
          // fetch() lève une erreur si le service ne répond pas du tout
          // (service éteint, mauvais port, CORS, etc.)
          return {
            name: service.name,
            description: service.description,
            docsUrl: service.docsUrl,
            state: "down" as const,
            detail: "Aucune réponse (service éteint ou injoignable)",
          };
        }
      })
    );

    setStatuses(results);
    setLastChecked(new Date());
  }

  // useEffect avec [] : s'exécute une seule fois au chargement de la page,
  // puis on programme un rafraîchissement automatique toutes les 10s.
  useEffect(() => {
    checkAllServices();
    const interval = setInterval(checkAllServices, 10000);
    // "cleanup" : si on quitte la page, on arrête le minuteur
    return () => clearInterval(interval);
  }, []);

  const healthyCount = statuses.filter((s) => s.state === "healthy").length;

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950 px-6 py-12">
      <div className="mx-auto max-w-3xl">
        {/* ── En-tête ───────────────────────────────────────────── */}
        <div className="mb-10 text-center">
          <h1 className="bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-4xl font-bold text-transparent">
            Statut du Système
          </h1>
          <p className="mt-3 text-slate-400">
            Surveillance en direct des 3 services backend (rafraîchi toutes
            les 10 secondes)
          </p>

          {/* Résumé global : X / 3 services en ligne */}
          <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/50 px-4 py-2">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                healthyCount === SERVICES.length
                  ? "bg-emerald-400"
                  : healthyCount === 0
                  ? "bg-red-500"
                  : "bg-amber-400"
              }`}
            />
            <span className="text-sm text-slate-300">
              {healthyCount} / {SERVICES.length} services en ligne
            </span>
          </div>
        </div>

        {/* ── Liste des services ───────────────────────────────────── */}
        <div className="space-y-4">
          {statuses.map((service) => (
            <ServiceCard key={service.name} service={service} />
          ))}
        </div>

        {/* ── Pied de page ─────────────────────────────────────────── */}
        <div className="mt-8 flex items-center justify-between text-xs text-slate-500">
          <span>
            {lastChecked
              ? `Dernière vérification : ${lastChecked.toLocaleTimeString(
                  "fr-FR"
                )}`
              : "Vérification en cours..."}
          </span>
          <button
            onClick={checkAllServices}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
          >
            Rafraîchir maintenant
          </button>
        </div>
      </div>
    </main>
  );
}

// ── Petit composant séparé pour afficher une "carte" de service ─────────
// (Le séparer en sous-composant rend le code plus lisible — c'est une
// bonne pratique React, pas obligatoire pour un fichier aussi court,
// mais utile dès que le fichier grossit.)
function ServiceCard({ service }: { service: ServiceStatus }) {
  const stateStyles = {
    loading: {
      dot: "bg-slate-500 animate-pulse",
      label: "Vérification...",
      labelColor: "text-slate-400",
      border: "border-slate-700",
    },
    healthy: {
      dot: "bg-emerald-400",
      label: "En ligne",
      labelColor: "text-emerald-400",
      border: "border-emerald-900",
    },
    down: {
      dot: "bg-red-500",
      label: "Hors ligne",
      labelColor: "text-red-400",
      border: "border-red-900",
    },
  }[service.state];

  return (
    <div
      className={`rounded-xl border ${stateStyles.border} bg-slate-900/40 p-5 backdrop-blur-sm`}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${stateStyles.dot}`} />
            <h2 className="font-semibold text-white">{service.name}</h2>
          </div>
          <p className="mt-1 text-sm text-slate-400">{service.description}</p>
        </div>

        <div className="text-right">
          <span className={`text-sm font-medium ${stateStyles.labelColor}`}>
            {stateStyles.label}
          </span>
          {service.latencyMs !== undefined && (
            <p className="mt-1 text-xs text-slate-500">
              {service.latencyMs} ms
            </p>
          )}
        </div>
      </div>

      {/* Détail technique renvoyé par /health (utile pour déboguer) */}
      {service.detail && (
        <p className="mt-3 truncate rounded-md bg-slate-950/60 px-3 py-2 font-mono text-xs text-slate-500">
          {service.detail}
        </p>
      )}

      <a
        href={service.docsUrl}
        target="_blank"
        rel="noreferrer"
        className="mt-3 inline-block text-xs text-blue-400 hover:text-blue-300 hover:underline"
      >
        Voir la documentation API →
      </a>
    </div>
  );
}
