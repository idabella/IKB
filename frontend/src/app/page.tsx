export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950">
      <div className="text-center space-y-6">
        <h1 className="text-5xl font-bold bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">
          Factory AI Brain
        </h1>
        <p className="text-lg text-slate-400 max-w-md">
          Industrial Knowledge System — Real-time monitoring, diagnostics, and
          AI-powered insights.
        </p>
        <div className="flex gap-4 justify-center">
          <a
            href="/dashboard"
            className="px-6 py-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors"
          >
            Dashboard
          </a>
          <a
            href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/docs`}
            className="px-6 py-3 rounded-lg border border-slate-700 hover:border-slate-500 text-slate-300 font-medium transition-colors"
          >
            API Docs
          </a>
        </div>
      </div>
    </main>
  );
}
