import React, { Suspense, lazy } from 'react';

const AutomationGuide = lazy(() => import('../AutomationGuide.jsx'));

export default function AutomationGuideContent() {
  return (
    <Suspense fallback={<div className="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">Carregant ajuda contextual...</div>}>
      <AutomationGuide />
    </Suspense>
  );
}
