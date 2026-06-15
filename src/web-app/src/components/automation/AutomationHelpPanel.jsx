import React from 'react';
import AutomationGuideContent from './AutomationGuideContent.jsx';

export default function AutomationHelpPanel() {
  return (
    <div className="glass-card overflow-hidden p-0">
      <div className="border-b border-white/10 bg-white/5 px-6 py-5">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-primary">Ajuda</p>
        <h4 className="mt-2 text-2xl font-extrabold tracking-tight text-foreground">Guia visual del mòdul</h4>
        <p className="mt-2 text-sm text-muted-foreground">
          Recorre el flux complet, mira les pantalles principals i obre la guia en una finestra nova si necessites treballar en paral·lel.
        </p>
      </div>
      <div className="bg-white px-6 py-6 text-slate-900">
        <AutomationGuideContent />
      </div>
    </div>
  );
}
