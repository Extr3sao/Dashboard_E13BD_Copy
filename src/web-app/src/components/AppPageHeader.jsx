import React from 'react';
import { RefreshCcw } from 'lucide-react';

import PageHelpButton from './PageHelpButton.jsx';

export default function AppPageHeader({
  activeTab,
  subtabLabel,
  helpKey,
  showGlobalReportControls,
  loading,
  onRefresh,
  onGenerateReport,
}) {
  return (
    <header className="mb-10 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="flex items-start gap-3">
        <div>
          <h2 className="text-4xl font-extrabold tracking-tight mb-2">{activeTab}</h2>
          {subtabLabel ? (
            <p className="text-sm font-semibold text-primary">{subtabLabel}</p>
          ) : null}
          <p className="text-lg text-muted-foreground font-medium">Arquitectura d'auditoria governada per Agents IA.</p>
        </div>
        <PageHelpButton helpKey={helpKey} className="mt-1 shrink-0" />
      </div>

      {showGlobalReportControls && (
        <div className="flex flex-wrap gap-3">
          <button
            onClick={onRefresh}
            className="flex h-10 items-center gap-2 rounded-lg border border-border bg-background px-4 font-semibold transition-all hover:bg-secondary"
          >
            <RefreshCcw size={16} /> Refresca
          </button>
          <div className="flex flex-col gap-2">
            <button
              onClick={onGenerateReport}
              disabled={loading}
              className={`flex h-10 items-center gap-2 rounded-lg bg-primary px-4 font-bold text-primary-foreground transition-all ${loading ? 'opacity-50 cursor-not-allowed' : 'hover:brightness-110'}`}
            >
              {loading ? <RefreshCcw size={16} className="animate-spin" /> : null}
              {loading ? 'Generant...' : 'Generar Informe'}
            </button>
          </div>
        </div>
      )}
    </header>
  );
}
