import React from 'react';
import { ExternalLink, Info, X } from 'lucide-react';
import AutomationGuideContent from './AutomationGuideContent.jsx';

export default function AutomationHelpModal({ open, onClose, onOpenInlineHelp, onOpenNewWindow }) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
      <div className="max-h-[96vh] w-full max-w-[min(96vw,1520px)] overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl">
        <div className="flex items-center justify-between gap-4 border-b border-slate-200 bg-slate-50 px-6 py-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.3em] text-primary">Automatitzacions</p>
            <h4 className="text-xl font-bold text-slate-950">Com funciona aquesta pàgina</h4>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={onOpenNewWindow} className="inline-flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/10 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-primary transition hover:bg-primary/20">
              <ExternalLink size={14} />
              Obre en nova finestra
            </button>
            <button type="button" onClick={onClose} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-700 transition hover:bg-slate-100">
              <X size={14} />
              Tanca
            </button>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            <button type="button" onClick={onOpenInlineHelp} className="inline-flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/10 px-4 py-2 text-sm font-semibold text-primary transition hover:bg-primary/20">
              <Info size={16} />
              Ajuda integrada
            </button>
            <button type="button" onClick={onOpenNewWindow} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-foreground transition hover:bg-white/10">
              <ExternalLink size={16} />
              Obre ajuda en una finestra nova
            </button>
          </div>
        </div>
        <div className="max-h-[calc(96vh-84px)] overflow-y-auto bg-white px-6 py-5 text-slate-900">
          <AutomationGuideContent />
        </div>
      </div>
    </div>
  );
}
