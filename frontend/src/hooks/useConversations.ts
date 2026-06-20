/**
 * Persists chat conversations in localStorage.
 * Each conversation stores display messages + ChatTurn history for the API.
 */
import { useCallback, useState } from "react";
import type { ChatTurn } from "@/lib/api";

export interface Msg {
  id: string;
  role: "ai" | "user";
  content: string;
  time: string;
  sources?: string[];
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: string; // ISO string
  messages: Msg[];
  history: ChatTurn[];
}

const STORAGE_KEY = "ikb_chat_conversations";

function load(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Conversation[]) : [];
  } catch {
    return [];
  }
}

function save(convos: Conversation[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(convos));
}

function makeId() {
  return `conv-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function makeTitle(messages: Msg[]): string {
  const firstUser = messages.find((m) => m.role === "user");
  if (!firstUser) return "New conversation";
  const text = firstUser.content.trim();
  return text.length > 40 ? text.slice(0, 40) + "…" : text;
}

export function useConversations(welcomeMsg: Msg) {
  const [conversations, setConversations] = useState<Conversation[]>(load);
  const [activeId, setActiveId] = useState<string | null>(
    () => load()[0]?.id ?? null
  );

  const persist = useCallback((next: Conversation[]) => {
    setConversations(next);
    save(next);
  }, []);

  // Current active conversation (or a fresh empty shell)
  const active: Conversation | null =
    conversations.find((c) => c.id === activeId) ?? null;

  // ── Create a brand-new conversation ──────────────────────────────────────
  const createConversation = useCallback((): Conversation => {
    const c: Conversation = {
      id: makeId(),
      title: "New conversation",
      createdAt: new Date().toISOString(),
      messages: [welcomeMsg],
      history: [],
    };
    persist([c, ...conversations]);
    setActiveId(c.id);
    return c;
  }, [conversations, persist, welcomeMsg]);

  // ── Update messages + history of the active conversation ─────────────────
  const updateActive = useCallback(
    (messages: Msg[], history: ChatTurn[]) => {
      if (!activeId) return;
      const next = conversations.map((c) =>
        c.id === activeId
          ? { ...c, messages, history, title: makeTitle(messages) }
          : c
      );
      persist(next);
    },
    [activeId, conversations, persist]
  );

  // ── Rename a conversation ─────────────────────────────────────────────────
  const renameConversation = useCallback(
    (id: string, title: string) => {
      persist(conversations.map((c) => (c.id === id ? { ...c, title } : c)));
    },
    [conversations, persist]
  );

  // ── Delete a conversation ─────────────────────────────────────────────────
  const deleteConversation = useCallback(
    (id: string) => {
      const next = conversations.filter((c) => c.id !== id);
      persist(next);
      if (activeId === id) setActiveId(next[0]?.id ?? null);
    },
    [activeId, conversations, persist]
  );

  return {
    conversations,
    active,
    activeId,
    setActiveId,
    createConversation,
    updateActive,
    renameConversation,
    deleteConversation,
  };
}
