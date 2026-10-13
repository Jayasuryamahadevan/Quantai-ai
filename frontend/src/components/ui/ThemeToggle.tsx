import React from 'react';
import { Moon, Sun } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';

export const ThemeToggle: React.FC = () => {
  const theme = useAppStore((state) => state.theme);
  const setTheme = useAppStore((state) => state.setTheme);
  const nextTheme = theme === 'dark' ? 'light' : 'dark';

  return (
    <button
      type="button"
      onClick={() => setTheme(nextTheme)}
      aria-label={`Switch to ${nextTheme} mode`}
      title={`Switch to ${nextTheme} mode`}
      className="theme-toggle inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.035] px-3 py-2 text-sm text-slate-300 transition hover:bg-white/[0.08] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/70"
    >
      {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      <span className="hidden sm:inline">{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
    </button>
  );
};
