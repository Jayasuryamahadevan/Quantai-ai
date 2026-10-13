/**
 * components/layout/Sidebar.tsx — Left sidebar with sources, nav, and status.
 */
import React, { useEffect, useState } from 'react';
import {
  Database, MessageSquare, History, Settings, Upload,
  ChevronLeft, ChevronRight, Trash2, Plus,
  Wifi, WifiOff, Star, LayoutDashboard, Loader2
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { api } from '../../api/client';
import { DEMO_SOURCES } from '../../api/demo';

interface Props {
  onNavigate: (page: 'welcome' | 'chat') => void;
}

export const Sidebar: React.FC<Props> = ({ onNavigate }) => {
  const [deletingSourceId, setDeletingSourceId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const {
    sidebarOpen, setSidebarOpen,
    activePanel, setActivePanel,
    sources, setSources, sourcesLoaded, setSourcesLoaded,
    selectedSourceId, setSelectedSourceId,
    setUploadDialogOpen,
    demoMode, backendReachable, setBackendReachable, setDocumentMode,
  } = useAppStore();

  // Load sources on mount
  useEffect(() => {
    if (demoMode) {
      if (!sourcesLoaded) {
        setSources(DEMO_SOURCES);
        setSelectedSourceId(DEMO_SOURCES[0]?.id ?? null);
        setSourcesLoaded(true);
      }
      return;
    }
    if (sourcesLoaded || !backendReachable) return;
    api.sources.list()
      .then((loadedSources) => {
        setSources(loadedSources);
        setBackendReachable(true);
      })
      .catch(() => {
        setSources([]);
        setBackendReachable(false);
      })
      .finally(() => setSourcesLoaded(true));
  }, [demoMode, backendReachable, sourcesLoaded, setSources, setSourcesLoaded, setBackendReachable]);

  const handleDeleteSource = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this data source? This cannot be undone.')) return;
    setDeleteError(null);
    setDeletingSourceId(id);
    try {
      const state = useAppStore.getState();
      if (state.selectedSourceId === id) {
        state.activeStream?.cancel();
        state.setActiveStream(null);
      }
      if (!demoMode) await api.sources.delete(id);
      useAppStore.getState().removeSource(id);
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : 'Could not delete this data source. Please try again.');
    } finally {
      setDeletingSourceId(null);
    }
  };

  const navItems = [
    { id: 'chat' as const, icon: MessageSquare, label: 'Chat' },
    { id: 'data' as const, icon: LayoutDashboard, label: 'Data' },
    { id: 'history' as const, icon: History, label: 'History' },
    { id: 'settings' as const, icon: Settings, label: 'Settings' },
  ];

  return (
    <aside
      className={`relative flex flex-col shrink-0 border-r border-slate-800/60 bg-[#080817] transition-all duration-300 ease-in-out ${
        sidebarOpen ? 'w-64' : 'w-16'
      }`}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 h-16 border-b border-slate-800/60 shrink-0">
        <div
          className="w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center shrink-0 cursor-pointer shadow-lg shadow-indigo-600/30"
          onClick={() => onNavigate('welcome')}
        >
          <Database className="w-4.5 h-4.5 text-white w-[18px] h-[18px]" />
        </div>
        {sidebarOpen && (
          <span className="font-bold text-white text-lg tracking-tight truncate">Quantai AI</span>
        )}

        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="ml-auto p-1 rounded-lg text-slate-600 hover:text-slate-300 hover:bg-slate-800 transition-colors shrink-0"
        >
          {sidebarOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
      </div>

      {/* Demo / Status badge */}
      {sidebarOpen && (demoMode || !backendReachable) && (
        <div className="mx-3 mt-3 px-3 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center gap-2">
          <Star className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <span className="text-xs text-amber-300 font-medium">Demo Mode</span>
        </div>
      )}

      {/* Nav */}
      <nav className="flex flex-col gap-1 p-2 mt-2">
        {navItems.map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            onClick={() => { setActivePanel(id); onNavigate('chat'); }}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all text-sm font-medium
              ${activePanel === id
                ? 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/25'
                : 'text-slate-500 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            title={!sidebarOpen ? label : undefined}
          >
            <Icon className="w-4.5 h-4.5 w-[18px] h-[18px] shrink-0" />
            {sidebarOpen && <span>{label}</span>}
          </button>
        ))}
      </nav>

      {/* Divider */}
      <div className="h-px bg-slate-800/60 mx-3 my-2" />

      {deleteError && sidebarOpen && (
        <div role="alert" className="mx-3 mb-2 rounded-xl border border-red-400/15 bg-red-400/[0.06] px-3 py-2.5 text-[11px] leading-5 text-red-200">
          {deleteError}
        </div>
      )}

      {/* Sources */}
      {sidebarOpen && (
        <div className="flex flex-col flex-1 overflow-hidden px-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-semibold text-slate-600 uppercase tracking-wider">
              Data Sources
            </span>
            <button
              onClick={() => setUploadDialogOpen(true)}
              className="p-1 rounded-lg text-slate-600 hover:text-indigo-400 hover:bg-slate-800 transition-colors"
              title="Upload file"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto space-y-1 min-h-0">
            {sources.length === 0 ? (
              <button
                onClick={() => setUploadDialogOpen(true)}
                className="w-full flex flex-col items-center gap-2 p-4 rounded-xl border border-dashed border-slate-800 
                           text-slate-600 hover:text-slate-400 hover:border-slate-700 transition-colors"
              >
                <Upload className="w-5 h-5" />
                <span className="text-xs">Upload CSV or Excel</span>
              </button>
            ) : (
              sources.map((src) => (
                <div
                  key={src.id}
                  onClick={() => { setDocumentMode(false); setSelectedSourceId(src.id); }}
                  className={`group flex items-center gap-2.5 px-3 py-2.5 rounded-xl cursor-pointer transition-all
                    ${selectedSourceId === src.id
                      ? 'bg-indigo-500/12 border border-indigo-500/25 text-indigo-200'
                      : 'hover:bg-slate-800/60 text-slate-400 hover:text-slate-200'
                    }`}
                >
                  <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 text-xs font-bold
                    ${src.source_type === 'csv' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-blue-500/15 text-blue-400'}
                  `}>
                    {src.source_type === 'csv' ? 'CSV' : 'XLS'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{src.name.replace(/\.(csv|xlsx|xls)$/i, '')}</p>
                    <p className="text-[10px] text-slate-600">{src.row_count?.toLocaleString()} rows</p>
                  </div>
                  <button
                    onClick={(e) => handleDeleteSource(src.id, e)}
                    disabled={deletingSourceId === src.id}
                    aria-label={`Delete ${src.name}`}
                    title={deletingSourceId === src.id ? 'Deleting data source' : 'Delete data source'}
                    className="shrink-0 opacity-0 group-hover:opacity-100 p-1 rounded text-slate-600 hover:text-red-400 transition-all disabled:opacity-100 disabled:cursor-wait"
                  >
                    {deletingSourceId === src.id
                      ? <Loader2 className="w-3 h-3 animate-spin" />
                      : <Trash2 className="w-3 h-3" />}
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Collapsed: icon only sources indicator */}
      {!sidebarOpen && (
        <div className="flex-1 flex flex-col items-center gap-1 px-2 mt-1">
          <button
            onClick={() => setUploadDialogOpen(true)}
            className="w-full p-2 flex justify-center rounded-xl text-slate-600 hover:text-indigo-400 hover:bg-slate-800 transition-colors"
            title="Upload data"
          >
            <Upload className="w-4 h-4" />
          </button>
          {sources.map((src) => (
            <button
              key={src.id}
              onClick={() => { setDocumentMode(false); setSelectedSourceId(src.id); }}
              title={src.name}
              className={`w-9 h-9 rounded-xl flex items-center justify-center text-[10px] font-bold transition-all
                ${selectedSourceId === src.id
                  ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                  : 'text-slate-500 hover:bg-slate-800'
                }
                ${src.source_type === 'csv' ? 'text-emerald-400' : 'text-blue-400'}`}
            >
              {src.source_type === 'csv' ? 'C' : 'X'}
            </button>
          ))}
        </div>
      )}

      {/* Status footer */}
      <div className={`shrink-0 px-3 py-3 border-t border-slate-800/60 flex items-center gap-2 
                       ${!sidebarOpen ? 'justify-center' : ''}`}>
        {backendReachable && !demoMode ? (
          <Wifi className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
        ) : (
          <WifiOff className="w-3.5 h-3.5 text-amber-400 shrink-0" />
        )}
        {sidebarOpen && (
          <span className="text-[11px] text-slate-600">
            {backendReachable && !demoMode ? 'Connected to backend' : 'Demo mode'}
          </span>
        )}
      </div>
    </aside>
  );
};
