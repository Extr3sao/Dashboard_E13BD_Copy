import React from 'react';
import { Download, RefreshCcw } from 'lucide-react';

export default function AutomationDashboardPanel({
  analyticsMonth,
  onChangeMonth,
  onRefresh,
  onExportPdf,
  analyticsLoading,
  analyticsOverview,
  analyticsLots,
  analyticsSchemas,
  analyticsChecks,
  runs = [],
  retryQueue = [],
}) {
  const running = runs.filter((run) => run.status === 'running').length;
  const failed = runs.filter((run) => ['error', 'partial_error'].includes(run.status)).length;
  const retryPending = retryQueue.filter((item) => ['pending', 'failed'].includes(item.status)).length;
  const recentErrors = retryQueue.filter((item) => item.last_error || item.error_message).length;
  return (
    <div className="grid gap-6">
      <section className="glass-card p-6" aria-labelledby="operational-overview-title">
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-white/10 pb-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary">Ara mateix</p>
            <h4 id="operational-overview-title" className="mt-2 text-xl font-extrabold text-foreground">Seguiment operatiu</h4>
          </div>
          <p className="text-sm text-muted-foreground">Basat en les últimes execucions i la cua de reintents carregades.</p>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[['En execució', running, 'Revisa durades anòmales'], ['Error o parcial', failed, 'Requereix diagnòstic'], ['Reintents pendents', retryPending, 'Acció disponible si és segura'], ['Errors recents', recentErrors, 'Consulta la cua de reintents']].map(([label, value, help]) => (
            <div key={label} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
              <p className="mt-2 text-3xl font-extrabold text-foreground">{value}</p>
              <p className="mt-1 text-xs text-muted-foreground">{help}</p>
            </div>
          ))}
        </div>
      </section>
      <div className="glass-card p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.3em] text-primary">Dashboard</p>
            <h4 className="mt-2 text-2xl font-extrabold tracking-tight text-foreground">Històric analític mensual</h4>
            <p className="mt-2 text-sm text-muted-foreground">
              Dades agregades per lot, esquema i tipus de check. Aquest resum es nodreix automàticament de cada execució Post-CRQ desada.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-2 text-sm">
              <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Mes</span>
              <input
                type="month"
                value={analyticsMonth}
                onChange={(event) => onChangeMonth(event.target.value)}
                className="rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary"
              />
            </label>
            <button
              type="button"
              onClick={onRefresh}
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-foreground transition hover:bg-white/10"
            >
              <RefreshCcw size={16} />
              Refresca
            </button>
            <button
              type="button"
              onClick={onExportPdf}
              className="inline-flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/10 px-4 py-3 text-sm font-semibold text-primary transition hover:bg-primary/20"
            >
              <Download size={16} />
              PDF mensual
            </button>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
        <div className="glass-card p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Execucions</p>
          <p className="mt-3 text-3xl font-extrabold text-foreground">{analyticsLoading ? '...' : analyticsOverview?.runs ?? 0}</p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Troballes totals</p>
          <p className="mt-3 text-3xl font-extrabold text-foreground">{analyticsLoading ? '...' : analyticsOverview?.total_findings ?? 0}</p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Lots amb troballes</p>
          <p className="mt-3 text-3xl font-extrabold text-foreground">{analyticsLoading ? '...' : analyticsOverview?.lots_with_findings ?? 0}</p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Checks amb errors</p>
          <p className="mt-3 text-3xl font-extrabold text-foreground">{analyticsLoading ? '...' : analyticsOverview?.checks_with_errors ?? 0}</p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <section className="glass-card p-6">
          <div className="border-b border-white/10 pb-4">
            <h4 className="text-lg font-bold text-foreground">Lots</h4>
            <p className="text-sm text-muted-foreground">Quins lots acumulen més troballes durant el mes seleccionat.</p>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-3">Lot</th>
                  <th className="px-3 py-3">Exec.</th>
                  <th className="px-3 py-3">Troballes</th>
                </tr>
              </thead>
              <tbody>
                {analyticsLots.length === 0 ? (
                  <tr>
                    <td colSpan="3" className="px-3 py-6 text-sm text-muted-foreground">Sense dades per al mes seleccionat.</td>
                  </tr>
                ) : analyticsLots.map((item) => (
                  <tr key={item.lot} className="border-t border-white/10">
                    <td className="px-3 py-3 text-foreground">{item.lot}</td>
                    <td className="px-3 py-3 text-foreground">{item.runs}</td>
                    <td className="px-3 py-3 text-foreground">{item.total_findings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="glass-card p-6">
          <div className="border-b border-white/10 pb-4">
            <h4 className="text-lg font-bold text-foreground">Esquemes</h4>
            <p className="text-sm text-muted-foreground">Relació entre esquemes, lot i volum de troballes persistides.</p>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-3">Esquema</th>
                  <th className="px-3 py-3">Lot</th>
                  <th className="px-3 py-3">Troballes</th>
                </tr>
              </thead>
              <tbody>
                {analyticsSchemas.length === 0 ? (
                  <tr>
                    <td colSpan="3" className="px-3 py-6 text-sm text-muted-foreground">Sense dades per al mes seleccionat.</td>
                  </tr>
                ) : analyticsSchemas.map((item) => (
                  <tr key={`${item.schema_name}-${item.lot}`} className="border-t border-white/10">
                    <td className="px-3 py-3 text-foreground">{item.schema_name}</td>
                    <td className="px-3 py-3 text-foreground">{item.lot}</td>
                    <td className="px-3 py-3 text-foreground">{item.total_findings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="glass-card p-6">
          <div className="border-b border-white/10 pb-4">
            <h4 className="text-lg font-bold text-foreground">Checks</h4>
            <p className="text-sm text-muted-foreground">Tipus de check amb més impacte durant el mes seleccionat.</p>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-3">Check</th>
                  <th className="px-3 py-3">Severitat</th>
                  <th className="px-3 py-3">Troballes</th>
                </tr>
              </thead>
              <tbody>
                {analyticsChecks.length === 0 ? (
                  <tr>
                    <td colSpan="3" className="px-3 py-6 text-sm text-muted-foreground">Sense dades per al mes seleccionat.</td>
                  </tr>
                ) : analyticsChecks.map((item) => (
                  <tr key={item.check_id} className="border-t border-white/10">
                    <td className="px-3 py-3 text-foreground">
                      <div className="font-semibold">{item.check_id}</div>
                      <div className="text-xs text-muted-foreground">{item.title || '-'}</div>
                    </td>
                    <td className="px-3 py-3 text-foreground">{item.severity || '-'}</td>
                    <td className="px-3 py-3 text-foreground">{item.total_findings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
