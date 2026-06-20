import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  Bot, User, Mic, Send, Loader2, Wrench, AlertTriangle,
  Plus, Trash2, MessageSquare, Pencil, Check, X,
  ChevronLeft, ChevronRight,
} from "lucide-react";
import { LineChart, Line, ReferenceLine, ResponsiveContainer, YAxis } from "recharts";
import ReactMarkdown from "react-markdown";
import { AppShell } from "@/components/AppShell";
import { StatusBadge } from "@/components/StatusBadge";
import { api, type Alert, type Machine, type VibrationResponse } from "@/lib/api";
import { useQuery } from "@/hooks/useQuery";
import { useConversations, type Msg } from "@/hooks/useConversations";

export const Route = createFileRoute("/chat")({
  head: () => ({
    meta: [
      { title: "AI Chat Assistant — IKB" },
      { name: "description", content: "Diagnose machine issues and analyze sensor data with the IKB AI assistant." },
    ],
  }),
  component: ChatPage,
});

function now() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

const WELCOME: Msg = {
  id: "welcome",
  role: "ai",
  content:
    "Hello! I'm your Industrial Knowledge Brain assistant. I can help diagnose machine issues, analyze sensor data, and recommend solutions based on our knowledge base. How can I assist you today?",
  time: now(),
};

const suggestedChips = [
  "Analyze current machine alerts",
  "Find similar past incidents",
  "Recommend maintenance actions",
  "Explain vibration threshold exceedance",
];

// ---------------------------------------------------------------------------
// Sidebar — conversation history list
// ---------------------------------------------------------------------------
function ConversationSidebar({
  conversations,
  activeId,
  collapsed,
  onToggleCollapse,
  onSelect,
  onCreate,
  onDelete,
  onRename,
}: {
  conversations: ReturnType<typeof useConversations>["conversations"];
  activeId: string | null;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const startEdit = (id: string, title: string) => {
    setEditingId(id);
    setEditValue(title);
  };

  const commitEdit = (id: string) => {
    if (editValue.trim()) onRename(id, editValue.trim());
    setEditingId(null);
  };

  // ── Collapsed rail ────────────────────────────────────────────────────────
  if (collapsed) {
    return (
      <div className="flex h-full w-[52px] shrink-0 flex-col items-center border-r border-border bg-card py-3 gap-2 transition-all duration-200">
        {/* Toggle */}
        <button
          id="sidebar-expand-btn"
          onClick={onToggleCollapse}
          title="Expand sidebar"
          className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition"
        >
          <ChevronRight className="h-4 w-4" />
        </button>

        {/* New chat */}
        <button
          onClick={onCreate}
          title="New conversation"
          className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition"
        >
          <Plus className="h-4 w-4" />
        </button>

        <div className="mt-1 w-full border-t border-border" />

        {/* Conversation dots */}
        <div className="flex flex-1 flex-col items-center gap-1.5 overflow-y-auto pt-1 w-full px-2">
          {conversations.map((c) => (
            <button
              key={c.id}
              onClick={() => onSelect(c.id)}
              title={c.title}
              className={`flex h-8 w-8 items-center justify-center rounded-lg transition ${
                c.id === activeId
                  ? "bg-primary/20 text-primary"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground"
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5" />
            </button>
          ))}
        </div>
      </div>
    );
  }

  // ── Expanded ──────────────────────────────────────────────────────────────
  return (
    <div className="flex h-full w-[240px] shrink-0 flex-col border-r border-border bg-card transition-all duration-200">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-3">
        <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Conversations
        </span>
        <div className="flex items-center gap-1">
          <button
            id="new-conversation-btn"
            onClick={onCreate}
            title="New conversation"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition"
          >
            <Plus className="h-4 w-4" />
          </button>
          <button
            id="sidebar-collapse-btn"
            onClick={onToggleCollapse}
            title="Collapse sidebar"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto py-2">
        {conversations.length === 0 && (
          <p className="px-4 py-6 text-center text-xs text-muted-foreground">
            No conversations yet.<br />Start a new one above.
          </p>
        )}
        {conversations.map((c) => (
          <div
            key={c.id}
            onClick={() => onSelect(c.id)}
            className={`group relative flex cursor-pointer items-start gap-2 px-4 py-3 transition ${
              c.id === activeId
                ? "bg-primary/10 text-foreground"
                : "hover:bg-secondary text-muted-foreground hover:text-foreground"
            }`}
          >
            <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-60" />

            {editingId === c.id ? (
              <div className="flex flex-1 items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <input
                  autoFocus
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitEdit(c.id);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  className="w-full rounded bg-background px-1 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <button onClick={() => commitEdit(c.id)} className="text-success"><Check className="h-3 w-3" /></button>
                <button onClick={() => setEditingId(null)} className="text-muted-foreground"><X className="h-3 w-3" /></button>
              </div>
            ) : (
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold leading-snug">{c.title}</p>
                <p className="mt-0.5 text-[10px] opacity-50">
                  {new Date(c.createdAt).toLocaleDateString()} · {c.messages.filter(m => m.role === "user").length} msgs
                </p>
              </div>
            )}

            {editingId !== c.id && (
              <div className="invisible absolute right-2 top-2.5 flex gap-1 group-hover:visible">
                <button
                  onClick={(e) => { e.stopPropagation(); startEdit(c.id, c.title); }}
                  className="rounded p-0.5 hover:text-primary"
                  title="Rename"
                >
                  <Pencil className="h-3 w-3" />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onDelete(c.id); }}
                  className="rounded p-0.5 hover:text-destructive"
                  title="Delete"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
function ChatPage() {
  const {
    conversations,
    active,
    activeId,
    setActiveId,
    createConversation,
    updateActive,
    renameConversation,
    deleteConversation,
  } = useConversations(WELCOME);

  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [selectedMachineId, setSelectedMachineId] = useState<string | undefined>(undefined);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [contextCollapsed, setContextCollapsed] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const messages: Msg[] = active?.messages ?? [WELCOME];

  const alertsQuery = useQuery<Alert[]>(() => api.alerts.list({ status: "active" }));
  const machinesQuery = useQuery<Machine[]>(() => api.machines.list());
  const vibrationQuery = useQuery<VibrationResponse>(
    () => api.dashboard.vibration(selectedMachineId ?? "m2"),
    [selectedMachineId]
  );

  useEffect(() => {
    const firstAlert = alertsQuery.data?.[0];
    if (firstAlert && machinesQuery.data) {
      const m = machinesQuery.data.find((m) => m.name === firstAlert.machine);
      if (m) setSelectedMachineId(m.id);
    }
  }, [alertsQuery.data, machinesQuery.data]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typing]);

  const contextMachine = machinesQuery.data?.find((m) => m.id === selectedMachineId);

  // Ensure there's always an active conversation
  const ensureActive = (): { msgs: Msg[]; hist: ReturnType<typeof useConversations>["active"]["history"] } => {
    if (active) return { msgs: active.messages, hist: active.history };
    const c = createConversation();
    return { msgs: c.messages, hist: c.history };
  };

  const send = async (text?: string) => {
    const value = (text ?? input).trim();
    if (!value || typing) return;

    const { msgs, hist } = ensureActive();

    const userMsg: Msg = { id: Date.now().toString(), role: "user", content: value, time: now() };
    const nextMsgs = [...msgs, userMsg];
    const nextHist = [...hist, { role: "user" as const, content: value }];
    updateActive(nextMsgs, nextHist);
    setInput("");
    setTyping(true);

    try {
      const res = await api.chat.send({ message: value, machine_id: selectedMachineId, history: hist });
      const aiMsg: Msg = {
        id: Date.now().toString() + "-r",
        role: "ai",
        content: res.reply,
        time: now(),
        sources: res.sources,
      };
      updateActive([...nextMsgs, aiMsg], [...nextHist, { role: "assistant", content: res.reply }]);
    } catch (err) {
      const errMsg: Msg = {
        id: Date.now().toString() + "-err",
        role: "ai",
        content: `⚠️ Error: ${err instanceof Error ? err.message : "Failed to reach AI service."}`,
        time: now(),
      };
      updateActive([...nextMsgs, errMsg], nextHist);
    } finally {
      setTyping(false);
    }
  };

  const handleNewChat = () => {
    createConversation();
    setInput("");
  };

  return (
    <AppShell>
      <div className="flex h-[calc(100vh-60px)] overflow-hidden">

        {/* ── History sidebar ───────────────────────────────────────────────── */}
        <ConversationSidebar
          conversations={conversations}
          activeId={activeId}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
          onSelect={setActiveId}
          onCreate={handleNewChat}
          onDelete={deleteConversation}
          onRename={renameConversation}
        />

        {/* ── Chat column ──────────────────────────────────────────────────── */}
        <section className="flex flex-1 flex-col border-r border-border bg-background min-w-0">
          <div className="flex items-center justify-between border-b border-border bg-card px-6 py-4">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold">AI Chat Assistant</h1>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-success/15 px-2 py-0.5 text-[11px] font-semibold text-success">
                  <span className="h-1.5 w-1.5 rounded-full bg-success" />
                  Online
                </span>
              </div>
              <p className="text-xs text-muted-foreground">Powered by IKB knowledge graph · Gemini AI</p>
            </div>
            <button
              onClick={handleNewChat}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:bg-secondary"
            >
              <Plus className="h-3.5 w-3.5" /> New chat
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-6">
            <div className="mx-auto max-w-3xl space-y-6">
              {messages.map((m) => (
                <MessageBubble key={m.id} msg={m} />
              ))}
              {typing && (
                <div className="flex items-end gap-2">
                  <Avatar role="ai" />
                  <div className="rounded-2xl rounded-bl-sm bg-secondary px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <span className="typing-dot h-2 w-2 rounded-full bg-muted-foreground" />
                      <span className="typing-dot h-2 w-2 rounded-full bg-muted-foreground" />
                      <span className="typing-dot h-2 w-2 rounded-full bg-muted-foreground" />
                    </div>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          </div>

          {/* Suggested chips */}
          <div className="border-t border-border bg-card px-6 pt-3">
            <div className="mx-auto max-w-3xl flex flex-wrap gap-2">
              {suggestedChips.map((c) => (
                <button
                  key={c}
                  onClick={() => send(c)}
                  disabled={typing}
                  className="rounded-full border border-border bg-secondary px-3 py-1 text-xs font-medium text-foreground transition hover:border-primary hover:text-primary disabled:opacity-50"
                >
                  {c}
                </button>
              ))}
            </div>
          </div>

          {/* Input bar */}
          <div className="border-t border-border bg-card px-6 py-4">
            <div className="mx-auto flex max-w-3xl items-center gap-2">
              <div className="flex flex-1 items-center gap-2 rounded-full border border-border bg-secondary px-4 py-2 focus-within:border-primary focus-within:bg-card focus-within:ring-2 focus-within:ring-primary/20">
                <button className="text-muted-foreground hover:text-foreground" aria-label="Voice input">
                  <Mic className="h-4 w-4" />
                </button>
                <input
                  id="chat-input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && send()}
                  type="text"
                  placeholder="Ask about machine issues, diagnostics, solutions…"
                  className="h-8 flex-1 bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none"
                  disabled={typing}
                />
              </div>
              <button
                id="chat-send-btn"
                onClick={() => send()}
                disabled={typing || !input.trim()}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground shadow transition hover:opacity-90 disabled:opacity-50"
                aria-label="Send"
              >
                {typing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </button>
            </div>
            <div className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted-foreground">
              Press Enter to send · History saved across sessions
            </div>
          </div>
        </section>

        {/* ── Context panel ─────────────────────────────────────────────────── */}
        {contextCollapsed ? (
          /* ── Collapsed icon rail ──────────────────────────────────────────── */
          <div className="hidden xl:flex h-full w-[52px] shrink-0 flex-col items-center border-l border-border bg-card py-3 gap-3 transition-all duration-200">
            <button
              id="context-expand-btn"
              onClick={() => setContextCollapsed(false)}
              title="Expand context panel"
              className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <div className="w-full border-t border-border" />
            <button
              title={contextMachine ? contextMachine.name : "No machine"}
              className={`flex h-8 w-8 items-center justify-center rounded-lg transition ${
                contextMachine ? "text-primary bg-primary/10" : "text-muted-foreground"
              }`}
            >
              <Wrench className="h-3.5 w-3.5" />
            </button>
            <button
              title="Active alerts"
              className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground transition"
            >
              <AlertTriangle className="h-3.5 w-3.5" />
            </button>
          </div>
        ) : (
          /* ── Expanded ─────────────────────────────────────────────────── */
          <aside className="hidden w-[320px] shrink-0 overflow-y-auto bg-card xl:block transition-all duration-200">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Context Panel</h2>
              <button
                id="context-collapse-btn"
                onClick={() => setContextCollapsed(true)}
                title="Collapse context panel"
                className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-5 px-5 py-5">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Machine Context</div>
                <select
                  value={selectedMachineId ?? ""}
                  onChange={(e) => setSelectedMachineId(e.target.value || undefined)}
                  className="mt-2 h-9 w-full rounded-lg border border-border bg-secondary px-2 text-xs focus:border-primary focus:outline-none"
                >
                  <option value="">No machine selected</option>
                  {(machinesQuery.data ?? []).map((m) => (
                    <option key={m.id} value={m.id}>{m.name} ({m.status})</option>
                  ))}
                </select>
              </div>

              {contextMachine && (
                <>
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Current Machine</div>
                    <div className="mt-2 flex items-center gap-3 rounded-lg border border-border bg-secondary/40 p-3">
                      <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${contextMachine.status === "alert" ? "bg-destructive/10" : "bg-primary/10"}`}>
                        <Wrench className={`h-5 w-5 ${contextMachine.status === "alert" ? "text-destructive" : "text-primary"}`} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="font-bold">{contextMachine.name}</div>
                        <StatusBadge status={contextMachine.status} pulse={contextMachine.status === "alert"} />
                      </div>
                    </div>
                  </div>

                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Live Sensor Data</div>
                    <ul className="mt-2 space-y-2 text-sm">
                      <SensorRow label="Vibration" value={`${contextMachine.vibration} mm/s`} status={contextMachine.vibration > 3.5 ? "alert" : "ok"} />
                      <SensorRow label="Temperature" value={`${contextMachine.temp}°C`} status={contextMachine.temp > 70 ? "warn" : "ok"} />
                      <SensorRow label="RPM" value={`${contextMachine.rpm}`} status="ok" />
                      <SensorRow label="Pressure" value={`${contextMachine.pressure} bar`} status="ok" />
                      <SensorRow label="Efficiency" value={`${contextMachine.efficiency}%`} status={contextMachine.efficiency >= 85 ? "ok" : contextMachine.efficiency >= 75 ? "warn" : "alert"} />
                    </ul>
                  </div>

                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Vibration (trend)</div>
                    <div className="mt-2 h-[80px] rounded-lg border border-border bg-secondary/30 p-2">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={vibrationQuery.data?.data ?? []}>
                          <YAxis hide domain={[0, 8]} />
                          <ReferenceLine y={vibrationQuery.data?.threshold ?? 3.5} stroke="oklch(0.628 0.224 27.5)" strokeDasharray="3 3" />
                          <Line type="monotone" dataKey="value" stroke="oklch(0.66 0.13 210)" strokeWidth={2} dot={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </>
              )}

              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Active Alerts</div>
                {alertsQuery.loading ? (
                  <div className="mt-2 flex justify-center"><Loader2 className="h-4 w-4 animate-spin text-primary" /></div>
                ) : (alertsQuery.data ?? []).filter((a) => a.status === "active").length === 0 ? (
                  <p className="mt-2 text-xs text-success">No active alerts 🎉</p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {(alertsQuery.data ?? [])
                      .filter((a) => a.status === "active")
                      .slice(0, 3)
                      .map((a) => (
                        <li key={a.id} className="flex items-start gap-2 rounded-md border border-border bg-secondary/30 px-3 py-2 text-xs">
                          <AlertTriangle className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${a.severity === "high" ? "text-destructive" : "text-warning"}`} />
                          <div>
                            <div className="font-semibold">{a.machine}</div>
                            <div className="text-muted-foreground">{a.type}</div>
                          </div>
                        </li>
                      ))}
                  </ul>
                )}
              </div>

              <div className="border-t border-border pt-4">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Session Stats</div>
                <div className="mt-2 space-y-1.5">
                  <StatRow label="Total conversations" value={conversations.length} />
                  <StatRow label="Messages this chat" value={messages.filter(m => m.role === "user").length} />
                </div>
              </div>
            </div>
          </aside>
        )}

      </div>
    </AppShell>
  );
}


// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function Avatar({ role }: { role: "ai" | "user" }) {
  return role === "ai" ? (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
      <Bot className="h-4 w-4" />
    </div>
  ) : (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-foreground">
      <User className="h-4 w-4" />
    </div>
  );
}

function MessageBubble({ msg }: { msg: Msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex items-end gap-2 ${isUser ? "justify-end" : ""}`}>
      {!isUser && <Avatar role="ai" />}
      <div className={`flex max-w-[78%] flex-col ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser ? "rounded-br-sm bg-primary text-primary-foreground" : "rounded-bl-sm bg-secondary text-foreground"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{msg.content}</p>
          ) : (
            <div className="prose-chat">
              <ReactMarkdown
                components={{
                  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                  strong: ({ children }) => <strong className="font-bold text-foreground">{children}</strong>,
                  em: ({ children }) => <em className="italic">{children}</em>,
                  ul: ({ children }) => <ul className="my-2 ml-4 list-disc space-y-1">{children}</ul>,
                  ol: ({ children }) => <ol className="my-2 ml-4 list-decimal space-y-1">{children}</ol>,
                  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                  code: ({ inline, children }: { inline?: boolean; children?: React.ReactNode }) =>
                    inline ? (
                      <code className="rounded bg-muted/60 px-1 py-0.5 font-mono text-[12px] text-primary">{children}</code>
                    ) : (
                      <pre className="my-2 overflow-x-auto rounded-lg bg-muted/60 p-3">
                        <code className="font-mono text-[12px]">{children}</code>
                      </pre>
                    ),
                  a: ({ href, children }) => (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:opacity-80">
                      {children}
                    </a>
                  ),
                  h1: ({ children }) => <h1 className="mb-1 text-base font-bold">{children}</h1>,
                  h2: ({ children }) => <h2 className="mb-1 text-sm font-bold">{children}</h2>,
                  h3: ({ children }) => <h3 className="mb-1 text-sm font-semibold">{children}</h3>,
                  blockquote: ({ children }) => (
                    <blockquote className="my-2 border-l-2 border-primary/40 pl-3 text-muted-foreground italic">{children}</blockquote>
                  ),
                }}
              >
                {msg.content}
              </ReactMarkdown>
            </div>
          )}
          {msg.sources && msg.sources.length > 0 && (
            <div className="mt-2 border-t border-border/50 pt-2">
              <div className="text-[10px] font-semibold uppercase tracking-wider opacity-70">Sources</div>
              <ul className="mt-1 space-y-0.5">
                {msg.sources.map((s) => (
                  <li key={s} className="text-[11px] font-medium text-primary/80">📄 {s}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <span className="mt-1 text-[10px] text-muted-foreground">{msg.time}</span>
      </div>
      {isUser && <Avatar role="user" />}
    </div>
  );
}

function SensorRow({ label, value, status }: { label: string; value: string; status: "ok" | "warn" | "alert" }) {
  const dot = status === "ok" ? "bg-success" : status === "warn" ? "bg-warning" : "bg-destructive";
  return (
    <li className="flex items-center justify-between rounded-md border border-border bg-secondary/30 px-3 py-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="flex items-center gap-2 text-sm font-semibold">
        {value}
        <span className={`h-2 w-2 rounded-full ${dot} ${status === "alert" ? "alert-pulse" : ""}`} />
      </span>
    </li>
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
