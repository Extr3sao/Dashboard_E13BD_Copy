import React from 'react';
import { Play, Trash2 } from 'lucide-react';
import { SectionToggleButton } from './AutomationSection.jsx';

export default function AutomationRetryPanel({
  isVisible,
  registerSection,
  retryOpen,
  toggleSection,
  retryQueue,
  handlePurgeRetryQueue,
  maintenanceSummary,
  handleRunRetryNow,
}) {
  return (
    <div id="retry" ref={registerSection('retry')} className={isVisible ? '' : 'hidden'}>
      <section className="glass-card p-6">
        <div className="flex items-center justify-between gap-4 border-b border-white/10 pb-4">
          <div>
            <h4 className="text-lg font-bold text-foreground">Cua de reintents</h4>
            <p className="text-sm text-muted-foreground">Elements pendents o fallits que es poden reexecutar des de la interfície.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-muted-foreground">{retryQueue.length} elements</span>
            <button type="button" onClick={handlePurgeRetryQueue} className="inline-flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-amber-100 transition hover:bg-amber-500/20">
              <Trash2 size={14} />
              Buida cua
            </button>
            <SectionToggleButton open={retryOpen} onClick={() => toggleSection('retry')} />
          </div>
        </div>
        {retryOpen ? (
          <div className="mt-4 space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Elements a la cua</p>
                <p className="mt-2 text-2xl font-bold text-foreground">{maintenanceSummary?.retry_queue_total ?? retryQueue.length}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Pendents</p>
                <p className="mt-2 text-2xl font-bold text-foreground">{maintenanceSummary?.retry_queue_pending ?? '-'}</p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-3 py-3">Run</th>
                    <th className="px-3 py-3">Lot</th>
                    <th className="px-3 py-3">Audiència</th>
                    <th className="px-3 py-3">Intent</th>
                    <th className="px-3 py-3">Mode</th>
                    <th className="px-3 py-3">Estat</th>
                    <th className="px-3 py-3">Error</th>
                    <th className="px-3 py-3">Acció</th>
                  </tr>
                </thead>
                <tbody>
                  {retryQueue.length === 0 ? (
                    <tr><td colSpan="8" className="px-3 py-6 text-sm text-muted-foreground">No hi ha reintents pendents.</td></tr>
                  ) : retryQueue.map((item) => (
                    <tr key={item.id} className="border-t border-white/10">
                      <td className="px-3 py-3 text-muted-foreground">{item.run_id}</td>
                      <td className="px-3 py-3 text-foreground">{item.lot || 'TIC'}</td>
                      <td className="px-3 py-3 text-foreground">{item.audience}</td>
                      <td className="px-3 py-3 text-foreground">{item.attempt_number}</td>
                      <td className="px-3 py-3 text-foreground">{item.retry_mode === 'auto' ? 'Automàtic' : item.retry_mode === 'manual' ? 'Manual' : '-'}</td>
                      <td className="px-3 py-3 text-foreground">{item.status === 'pending' ? 'Pendent' : item.status === 'done' ? 'Fet' : item.status === 'failed' ? 'Fallit' : item.status || '-'}</td>
                      <td className="px-3 py-3 text-muted-foreground">{item.last_error || '-'}</td>
                      <td className="px-3 py-3">
                        <button type="button" onClick={() => handleRunRetryNow(item.id)} className="inline-flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/10 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-primary transition hover:bg-primary/20">
                          <Play size={14} />
                          Executa
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
