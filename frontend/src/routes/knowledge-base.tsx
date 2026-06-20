import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useRef, useState } from "react";
import {
  Search, FileText, Eye, Download, Bot, Loader2, RefreshCw,
  Upload, X, CheckCircle2, AlertCircle, CloudUpload,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { BackendError } from "@/components/BackendError";
import { api, type Document } from "@/lib/api";
import { useQuery } from "@/hooks/useQuery";

export const Route = createFileRoute("/knowledge-base")({
  head: () => ({
    meta: [
      { title: "Knowledge Base — IKB" },
      { name: "description", content: "Industrial documentation, procedures, FMEA reports, and SOPs." },
    ],
  }),
  component: KnowledgeBasePage,
});

const categories = ["All", "FMEA", "Procedure", "Incident Report", "SOP", "Training"];
const uploadCategories = ["Documents", "FMEA", "Procedure", "Incident Report", "SOP", "Training"];

// ---------------------------------------------------------------------------
// Upload Modal
// ---------------------------------------------------------------------------
type UploadStatus = "idle" | "uploading" | "success" | "error";

function UploadModal({ onClose, onUploaded }: { onClose: () => void; onUploaded: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("Documents");
  const [author, setAuthor] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const pickFile = (f: File) => {
    setFile(f);
    setStatus("idle");
    setErrorMsg("");
    if (!title) setTitle(f.name.replace(/\.[^.]+$/, "").replace(/[_-]/g, " "));
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) pickFile(f);
  };

  const handleSubmit = async () => {
    if (!file) return;
    setStatus("uploading");
    setErrorMsg("");
    try {
      await api.documents.upload(file, { title, category, author, excerpt });
      setStatus("success");
      setTimeout(() => { onUploaded(); onClose(); }, 1200);
    } catch (err: unknown) {
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : String(err));
    }
  };

  const handleBackdrop = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={handleBackdrop}
    >
      <div className="relative w-full max-w-lg rounded-2xl border border-border bg-card shadow-2xl mx-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="text-base font-bold">Upload Document</h2>
            <p className="text-xs text-muted-foreground mt-0.5">PDF, DOCX, or TXT</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 hover:bg-secondary text-muted-foreground hover:text-foreground transition"
            aria-label="Close upload dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-6">
          {/* Drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition ${
              dragging
                ? "border-primary bg-primary/10"
                : file
                ? "border-primary/40 bg-primary/5"
                : "border-border hover:border-primary/50 hover:bg-secondary/50"
            }`}
          >
            <input
              ref={fileRef}
              id="kb-file-input"
              type="file"
              accept=".pdf,.docx,.doc,.txt"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) pickFile(f); }}
            />
            {file ? (
              <>
                <FileText className="h-8 w-8 text-primary" />
                <p className="text-sm font-semibold text-foreground">{file.name}</p>
                <p className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(0)} KB · click to change</p>
              </>
            ) : (
              <>
                <CloudUpload className="h-8 w-8 text-muted-foreground" />
                <p className="text-sm font-semibold">Drop a file here or click to browse</p>
                <p className="text-xs text-muted-foreground">PDF, DOCX, TXT</p>
              </>
            )}
          </div>

          {/* Metadata */}
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label htmlFor="kb-upload-title" className="mb-1 block text-xs font-semibold text-muted-foreground">Title</label>
              <input
                id="kb-upload-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Auto-filled from filename"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
            <div>
              <label htmlFor="kb-upload-category" className="mb-1 block text-xs font-semibold text-muted-foreground">Category</label>
              <select
                id="kb-upload-category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              >
                {uploadCategories.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="kb-upload-author" className="mb-1 block text-xs font-semibold text-muted-foreground">Author</label>
              <input
                id="kb-upload-author"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                placeholder="Your name"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
            <div className="col-span-2">
              <label htmlFor="kb-upload-excerpt" className="mb-1 block text-xs font-semibold text-muted-foreground">
                Description <span className="font-normal opacity-60">(optional)</span>
              </label>
              <textarea
                id="kb-upload-excerpt"
                value={excerpt}
                onChange={(e) => setExcerpt(e.target.value)}
                rows={2}
                placeholder="Brief summary of the document…"
                className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
          </div>

          {/* Status */}
          {status === "error" && (
            <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}
          {status === "success" && (
            <div className="flex items-center gap-2 rounded-lg bg-emerald-500/10 px-3 py-2 text-xs text-emerald-500">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>Document uploaded successfully!</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-1">
            <button
              id="kb-upload-cancel"
              onClick={onClose}
              className="rounded-lg border border-border px-4 py-2 text-sm font-semibold hover:bg-secondary transition"
            >
              Cancel
            </button>
            <button
              id="kb-upload-submit"
              onClick={handleSubmit}
              disabled={!file || status === "uploading" || status === "success"}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground shadow hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              {status === "uploading" ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Uploading…</>
              ) : status === "success" ? (
                <><CheckCircle2 className="h-4 w-4" /> Done</>
              ) : (
                <><Upload className="h-4 w-4" /> Upload</>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
function KnowledgeBasePage() {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState("All");
  const [showUpload, setShowUpload] = useState(false);
  const { data, loading, error, refetch } = useQuery<Document[]>(() => api.documents.list());
  const documents = data ?? [];

  const filtered = useMemo(() => {
    return documents.filter((d) => {
      const q = query.toLowerCase();
      const matchQ =
        !q ||
        d.title.toLowerCase().includes(q) ||
        d.excerpt.toLowerCase().includes(q) ||
        d.machines.join(" ").toLowerCase().includes(q);
      const matchC = active === "All" || d.category === active;
      return matchQ && matchC;
    });
  }, [query, active, documents]);

  const recent = [...documents].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 4);

  return (
    <AppShell>
      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onUploaded={() => { refetch(); }}
        />
      )}

      <div className="mx-auto max-w-[1500px] space-y-6 px-6 py-6">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Knowledge Base</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Industrial documentation, procedures, and expertise
            </p>
          </div>
          <button
            id="upload-document-btn"
            onClick={() => setShowUpload(true)}
            className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow hover:brightness-110 transition"
          >
            <Upload className="h-4 w-4" />
            Upload Document
          </button>
        </header>

        {/* Big search */}
        <div className="rounded-xl border border-border bg-card p-2 shadow-[var(--shadow-card)]">
          <div className="relative">
            <Search className="pointer-events-none absolute left-5 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search documents, procedures, FMEA reports, solutions…"
              className="h-14 w-full rounded-lg bg-transparent pl-14 pr-5 text-base placeholder:text-muted-foreground focus:outline-none"
            />
          </div>
        </div>

        {/* Category chips + refresh */}
        <div className="flex flex-wrap items-center gap-2">
          {categories.map((c) => (
            <button
              key={c}
              onClick={() => setActive(c)}
              className={`rounded-full px-4 py-1.5 text-xs font-semibold transition ${
                active === c
                  ? "bg-primary text-primary-foreground shadow"
                  : "border border-border bg-card text-muted-foreground hover:text-foreground"
              }`}
            >
              {c}
            </button>
          ))}
          <button
            onClick={refetch}
            className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:bg-secondary"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : error ? (
          <BackendError error={error} onRetry={refetch} context="documents" />
        ) : (
          <>
            {/* Recently added */}
            {recent.length > 0 && (
              <section>
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                  Recently Added
                </h2>
                <div className="flex gap-4 overflow-x-auto pb-2">
                  {recent.map((d) => (
                    <div
                      key={d.id}
                      className="card-hover w-[280px] shrink-0 rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)]"
                    >
                      <div className="mb-2 inline-flex items-center gap-1.5 rounded bg-primary/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary">
                        {d.type}
                      </div>
                      <h3 className="line-clamp-2 text-sm font-bold">{d.title}</h3>
                      <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{d.excerpt}</p>
                      <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground">
                        <span>{d.date}</span>
                        <button className="font-semibold text-primary hover:underline">View</button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Main grid + sidebar */}
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:col-span-3">
                {filtered.length === 0 ? (
                  <div className="col-span-2 flex flex-col items-center gap-4 rounded-xl border border-dashed border-border bg-card p-12 text-center">
                    <CloudUpload className="h-10 w-10 text-muted-foreground/40" />
                    <div>
                      <p className="text-sm font-semibold text-muted-foreground">No documents found</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {query ? "Try a different search term." : "Upload your first document to get started."}
                      </p>
                    </div>
                    {!query && (
                      <button
                        onClick={() => setShowUpload(true)}
                        className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:brightness-110 transition"
                      >
                        <Upload className="h-3.5 w-3.5" /> Upload Document
                      </button>
                    )}
                  </div>
                ) : (
                  filtered.map((d) => (
                    <article
                      key={d.id}
                      className="card-hover flex flex-col rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-card)]"
                    >
                      <div className="flex items-start gap-3">
                        <div
                          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-white ${
                            d.type === "PDF" ? "bg-destructive" : "bg-info"
                          }`}
                        >
                          <FileText className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <h3 className="line-clamp-2 text-sm font-bold leading-snug">{d.title}</h3>
                          <span className="mt-1 inline-block rounded bg-secondary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                            {d.category}
                          </span>
                        </div>
                      </div>

                      <p className="mt-3 line-clamp-2 text-xs text-muted-foreground">{d.excerpt}</p>

                      <div className="mt-3 flex flex-wrap gap-1">
                        {d.machines.slice(0, 3).map((m) => (
                          <span
                            key={m}
                            className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary"
                          >
                            {m}
                          </span>
                        ))}
                      </div>

                      <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-[11px]">
                        <span className="text-muted-foreground">
                          {d.date} · {d.author}
                        </span>
                        <div className="flex items-center gap-1.5 text-muted-foreground">
                          <button className="rounded p-1 hover:bg-secondary hover:text-foreground" aria-label="View">
                            <Eye className="h-4 w-4" />
                          </button>
                          <button className="rounded p-1 hover:bg-secondary hover:text-foreground" aria-label="Download">
                            <Download className="h-4 w-4" />
                          </button>
                          <button className="rounded p-1 hover:bg-secondary hover:text-primary" aria-label="Ask AI">
                            <Bot className="h-4 w-4" />
                          </button>
                        </div>
                      </div>
                    </article>
                  ))
                )}
              </div>

              {/* Stats sidebar */}
              <aside className="rounded-xl border border-border bg-card p-5 shadow-[var(--shadow-card)] lg:col-span-1">
                <h3 className="text-sm font-semibold">Document Statistics</h3>
                <div className="mt-4 space-y-3">
                  <StatRow label="Total Documents" value={documents.length} />
                  {categories.slice(1).map((cat) => (
                    <StatRow
                      key={cat}
                      label={cat}
                      value={documents.filter((d) => d.category === cat).length}
                    />
                  ))}
                </div>

                <div className="mt-6 border-t border-border pt-4">
                  <h3 className="text-sm font-semibold">Authors</h3>
                  <div className="mt-3 space-y-1.5">
                    {[...new Set(documents.map((d) => d.author))].slice(0, 5).map((author) => (
                      <div key={author} className="flex items-center justify-between text-[11px]">
                        <span className="text-muted-foreground">{author}</span>
                        <span className="font-semibold text-foreground">
                          {documents.filter((d) => d.author === author).length}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="mt-6 border-t border-border pt-4">
                  <button
                    onClick={() => setShowUpload(true)}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-primary/40 bg-primary/5 px-3 py-3 text-xs font-semibold text-primary hover:bg-primary/10 transition"
                  >
                    <Upload className="h-3.5 w-3.5" />
                    Upload Document
                  </button>
                </div>
              </aside>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}

function StatRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-bold text-foreground">{value}</span>
    </div>
  );
}
