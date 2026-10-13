/**
 * store/useAppStore.ts — Zustand global state store.
 * Manages sources, chat messages, query state, and UI.
 */
import { create } from 'zustand';
import type { Source, SourceOverview } from '../api/client';

export type AppTheme = 'dark' | 'light';

const initialTheme: AppTheme = (() => {
  try {
    return window.localStorage.getItem('quantai.theme') === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
})();
document.documentElement.dataset.theme = initialTheme;
document.documentElement.style.colorScheme = initialTheme;

const savedDocuments = (() => {
  try {
    return JSON.parse(window.sessionStorage.getItem('quantai.documents') || '[]') as string[];
  } catch {
    return [];
  }
})();
const savedDocumentMode = window.sessionStorage.getItem('quantai.documentMode') === 'true';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  run_id?: string;
  session_id?: string;
  sql?: string;
  chart?: Record<string, any>;
  chart_type?: string;
  rows?: Record<string, any>[];
  columns?: string[];
  total_rows?: number;
  confidence?: string;
  verified?: boolean;
  warnings?: string[];
  trace?: any[];
  is_fallback_sql?: boolean;
  is_document_answer?: boolean;
  errors?: string[];
  step?: string;
  status: 'streaming' | 'done' | 'error';
  timestamp: number;
}

export interface ActiveStream {
  run_id: string;
  current_step: string;
  completed_steps: string[];
  cancel: () => void;
}

interface AppStore {
  // Sources
  sources: Source[];
  selectedSourceId: string | null;
  sourceOverview: SourceOverview | null;
  sourcesLoaded: boolean;
  setSources: (sources: Source[]) => void;
  setSelectedSourceId: (id: string | null) => void;
  setSourceOverview: (ov: SourceOverview | null) => void;
  setSourcesLoaded: (v: boolean) => void;
  removeSource: (id: string) => void;
  addSource: (s: Source) => void;

  // Chat
  sessionId: string | null;
  messages: ChatMessage[];
  setSessionId: (id: string) => void;
  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (msg: ChatMessage) => void;
  updateMessage: (id: string, patch: Partial<ChatMessage> | ((prev: ChatMessage) => Partial<ChatMessage>)) => void;
  clearMessages: () => void;

  // Streaming
  activeStream: ActiveStream | null;
  setActiveStream: (s: ActiveStream | null | ((prev: ActiveStream | null) => ActiveStream | null)) => void;

  // UI
  sidebarOpen: boolean;
  activePanel: 'chat' | 'data' | 'history' | 'settings';
  uploadDialogOpen: boolean;
  setSidebarOpen: (v: boolean) => void;
  setActivePanel: (p: 'chat' | 'data' | 'history' | 'settings') => void;
  setUploadDialogOpen: (v: boolean) => void;

  // Local document RAG
  documents: string[];
  documentMode: boolean;
  addDocument: (name: string) => void;
  setDocumentMode: (v: boolean) => void;

  // Settings
  demoMode: boolean;
  backendReachable: boolean;
  theme: AppTheme;
  setDemoMode: (v: boolean) => void;
  setBackendReachable: (v: boolean) => void;
  setTheme: (theme: AppTheme) => void;
}

export const useAppStore = create<AppStore>((set) => ({
  // Sources
  sources: [],
  selectedSourceId: null,
  sourceOverview: null,
  sourcesLoaded: false,
  setSources: (sources) => set({ sources }),
  setSelectedSourceId: (id) => set({ selectedSourceId: id }),
  setSourceOverview: (ov) => set({ sourceOverview: ov }),
  setSourcesLoaded: (v) => set({ sourcesLoaded: v }),
  removeSource: (id) =>
    set((s) => {
      const sources = s.sources.filter((src) => src.id !== id);
      const removedSelectedSource = s.selectedSourceId === id;
      return {
        sources,
        selectedSourceId: removedSelectedSource ? (sources[0]?.id ?? null) : s.selectedSourceId,
        sourceOverview: removedSelectedSource ? null : s.sourceOverview,
        messages: removedSelectedSource ? [] : s.messages,
        sessionId: removedSelectedSource ? null : s.sessionId,
      };
    }),
  addSource: (src) => set((s) => ({ sources: [src, ...s.sources] })),

  // Chat
  sessionId: null,
  messages: [],
  setSessionId: (id) => set({ sessionId: id }),
  setMessages: (messages) => set({ messages }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  updateMessage: (id, patch) =>
    set((s) => ({
      messages: s.messages.map((m) => {
        if (m.id !== id) return m;
        const resolved = typeof patch === 'function' ? patch(m) : patch;
        return { ...m, ...resolved };
      }),
    })),
  clearMessages: () => set({ messages: [], sessionId: null }),

  // Streaming
  activeStream: null,
  setActiveStream: (s) =>
    set((state) => ({
      activeStream: typeof s === 'function' ? s(state.activeStream) : s,
    })),

  // UI
  sidebarOpen: true,
  activePanel: 'chat',
  uploadDialogOpen: false,
  setSidebarOpen: (v) => set({ sidebarOpen: v }),
  setActivePanel: (p) => set({ activePanel: p }),
  setUploadDialogOpen: (v) => set({ uploadDialogOpen: v }),

  documents: savedDocuments,
  documentMode: savedDocumentMode,
  addDocument: (name) => set((s) => {
    const documents = s.documents.includes(name) ? s.documents : [...s.documents, name];
    window.sessionStorage.setItem('quantai.documents', JSON.stringify(documents));
    window.sessionStorage.setItem('quantai.documentMode', 'true');
    return { documents, documentMode: true, activePanel: 'chat' };
  }),
  setDocumentMode: (v) => {
    window.sessionStorage.setItem('quantai.documentMode', String(v));
    set({ documentMode: v });
  },

  // Settings
  demoMode: false,
  backendReachable: true,
  theme: initialTheme,
  setDemoMode: (v) => set({ demoMode: v, sourcesLoaded: false }),
  setBackendReachable: (v) => set({ backendReachable: v }),
  setTheme: (theme) => {
    try {
      window.localStorage.setItem('quantai.theme', theme);
    } catch {
      // The active theme still applies when persistent storage is unavailable.
    }
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    set({ theme });
  },
}));
