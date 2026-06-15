import React, { Suspense, lazy } from 'react';
import { ExternalLink, Info, X } from 'lucide-react';

const AutomationGuide = lazy(() => import('../components/AutomationGuide.jsx'));

export default function AutomationHelpView() {
  const handleOpenApp = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete('automation-help');
    window.open(url.toString(), '_blank', 'noopener,noreferrer');
  };

  const handleClose = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete('automation-help');
    window.location.href = url.toString();
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(192,0,0,0.16),transparent_38%),linear-gradient(180deg,#f8fafc,#eef2f7)] px-4 py-6 md:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="rounded-[28px] border border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.12)]">
          <div className="flex flex-col gap-4 border-b border-slate-200 bg-slate-50 px-6 py-5 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[0.3em] text-primary">
                <Info size={14} />
                Automatitzacions
              </p>
              <h1 className="mt-2 text-2xl font-black tracking-tight text-slate-950">Guia visual d&apos;Automatitzacions</h1>
              <p className="mt-2 text-sm text-slate-600">Vista dedicada per entendre el flux, les pantalles internes i la traçabilitat operativa.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={handleOpenApp} className="inline-flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/10 px-4 py-2 text-sm font-semibold text-primary transition hover:bg-primary/20">
                <ExternalLink size={15} />
                Obre l&apos;aplicació
              </button>
              <button type="button" onClick={handleClose} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100">
                <X size={15} />
                Tanca ajuda
              </button>
            </div>
          </div>
          <div className="px-6 py-6 md:px-8">
            <Suspense fallback={<div className="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">Carregant ajuda contextual...</div>}>
              <AutomationGuide />
            </Suspense>
          </div>
        </div>
      </div>
    </div>
  );
}
