import React from 'react';
import { CalendarClock, ChevronDown, ChevronUp, RefreshCcw } from 'lucide-react';

export default function AutomationSidebar({ screens, activeScreen, onSelectScreen, onExpandAll, onCollapseAll, onRefresh }) {
  return (
    <aside className="xl:sticky xl:top-6 xl:self-start">
      <div className="glass-card flex flex-col gap-5 p-5">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-bold uppercase tracking-widest text-primary">
            <CalendarClock size={14} />
            Automatitzacions
          </div>
          <h3 className="text-2xl font-extrabold tracking-tight text-primary">Programació d'auditories</h3>
          <p className="mt-3 text-sm text-muted-foreground">
            Configura els jobs, organitza lots i plantilles, i revisa el seguiment operatiu de cada execució.
          </p>
        </div>

        <div className="grid gap-2">
          <button type="button" onClick={onExpandAll} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-foreground transition hover:bg-white/10">
            <ChevronDown size={16} />
            Desplega-ho tot
          </button>
          <button type="button" onClick={onCollapseAll} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-foreground transition hover:bg-white/10">
            <ChevronUp size={16} />
            Encongeix-ho tot
          </button>
          <button type="button" onClick={onRefresh} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-foreground transition hover:bg-white/10">
            <RefreshCcw size={16} />
            Refresca
          </button>
        </div>

        <nav className="flex flex-col gap-2 border-t border-white/10 pt-5">
          {screens.map((screen) => {
            const selected = activeScreen === screen.id;
            return (
              <button
                key={screen.id}
                type="button"
                onClick={() => onSelectScreen(screen.id)}
                className={`rounded-2xl border px-4 py-3 text-left transition ${
                  selected
                    ? 'border-primary/30 bg-primary text-primary-foreground shadow-lg shadow-primary/20'
                    : 'border-white/10 bg-white/5 text-foreground hover:bg-white/10'
                }`}
              >
                <p className="text-sm font-bold">{screen.label}</p>
                <p className={`mt-1 text-xs ${selected ? 'text-primary-foreground/80' : 'text-muted-foreground'}`}>
                  {screen.description}
                </p>
              </button>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}
