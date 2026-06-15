import React from 'react';
import PageHelpButton from '../PageHelpButton.jsx';

export default function AutomationScreenHeader({ screen, jobsCount, routesCount, retryCount }) {
  return (
    <div className="glass-card p-8">
      <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
        <div className="max-w-none xl:flex-1">
          <p className="text-xs font-bold uppercase tracking-[0.3em] text-primary">Pantalla activa</p>
          <div className="mt-2 flex items-start gap-3">
            <h4 className="text-3xl font-extrabold tracking-tight text-foreground">{screen.title}</h4>
            <PageHelpButton helpKey={screen.helpKey} className="shrink-0" />
          </div>
          <p className="mt-3 text-sm text-muted-foreground">{screen.description}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3 xl:min-w-[420px]">
          <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
            <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Jobs</p>
            <p className="mt-2 text-2xl font-bold text-foreground">{jobsCount}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
            <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Lots amb ruta</p>
            <p className="mt-2 text-2xl font-bold text-foreground">{routesCount}</p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
            <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Reintents pendents</p>
            <p className="mt-2 text-2xl font-bold text-foreground">{retryCount}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
