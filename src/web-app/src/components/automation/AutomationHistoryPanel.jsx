import React from 'react';
import { ChevronDown, ChevronUp, Download, Filter, RefreshCcw, Trash2 } from 'lucide-react';
import { DELIVERY_AUDIENCES, DELIVERY_RESULTS, LOT_STATES } from '../../config/automationViewConfig.js';
import { SectionToggleButton } from './AutomationSection.jsx';

function formatTimestamp(value) {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('ca-ES');
}

export default function AutomationHistoryPanel({
  isVisible,
  registerSection,
  auditOpen,
  historyOpen,
  toggleSection,
  changeEvents,
  retentionDays,
  setRetentionDays,
  handlePurgeHistory,
  maintenanceSummary,
  runLotFilter,
  setRunLotFilter,
  expandedRunId,
  refreshRunLots,
  runs,
  toggleRunLots,
  getAutomationRunReportUrl,
  handleOpenRunSnapshot,
  handleRerunLiveFromHistory,
  handleExportRunCsv,
  loadingRunLotsId,
  runLotsById,
  lotStatusLabel,
  lotStatusClass,
  runStatusLabel,
  runStatusClass,
  runLotSummary,
  deliveryAudienceLabel,
  deliveryResultLabel,
  yesNo,
  handleEnqueueRetry,
}) {
  return (
    <>
      <div id="audit" ref={registerSection('audit')} className={isVisible ? '' : 'hidden'}>
        <section className="glass-card p-6">
          <div className="flex items-center justify-between gap-4 border-b border-white/10 pb-4">
            <div>
              <h4 className="text-lg font-bold text-foreground">Auditoria de canvis</h4>
              <p className="text-sm text-muted-foreground">Traça funcional dels canvis a lots, rutes, plantilles i previsualitzacions de backfill.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-muted-foreground">{changeEvents.length} esdeveniments</span>
              <SectionToggleButton open={auditOpen} onClick={() => toggleSection('audit')} />
            </div>
          </div>
          {auditOpen ? (
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-3 py-3">Quan</th>
                    <th className="px-3 py-3">Entitat</th>
                    <th className="px-3 py-3">Acció</th>
                    <th className="px-3 py-3">Actor</th>
                    <th className="px-3 py-3">Motiu</th>
                  </tr>
                </thead>
                <tbody>
                  {changeEvents.length === 0 ? (
                    <tr><td colSpan="5" className="px-3 py-6 text-sm text-muted-foreground">No hi ha canvis auditats encara.</td></tr>
                  ) : changeEvents.map((event) => (
                    <tr key={event.id} className="border-t border-white/10">
                      <td className="px-3 py-3 text-muted-foreground">{formatTimestamp(event.created_at)}</td>
                      <td className="px-3 py-3 text-foreground">{event.entity_type} · {event.entity_key}</td>
                      <td className="px-3 py-3 text-foreground">{event.action}</td>
                      <td className="px-3 py-3 text-foreground">{event.actor || '-'}</td>
                      <td className="px-3 py-3 text-muted-foreground">{event.reason || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </div>

      <div id="history" ref={registerSection('history')} className={isVisible ? '' : 'hidden'}>
        <section className="glass-card p-6">
          <div className="flex flex-col gap-4 border-b border-white/10 pb-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h4 className="text-lg font-bold text-foreground">Històric d'execucions</h4>
              <p className="text-sm text-muted-foreground">Detall per execució amb filtre per estat, exportació CSV i reintents manuals.</p>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <label className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold text-muted-foreground">
                Mantén últims
                <input
                  type="number"
                  min="1"
                  value={retentionDays}
                  onChange={(event) => setRetentionDays(Number(event.target.value || 30))}
                  className="w-20 rounded-lg border border-white/10 bg-transparent px-2 py-1 text-sm text-foreground outline-none"
                />
                dies
              </label>
              <button type="button" onClick={handlePurgeHistory} className="inline-flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-amber-100 transition hover:bg-amber-500/20">
                <Trash2 size={14} />
                Neteja històric antic
              </button>
              <SectionToggleButton open={historyOpen} onClick={() => toggleSection('history')} />
            </div>
          </div>

          {historyOpen ? (
            <>
              <div className="mb-4 grid gap-3 sm:grid-cols-4">
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                  <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Runs antics</p>
                  <p className="mt-2 text-2xl font-bold text-foreground">{maintenanceSummary?.old_runs ?? '-'}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                  <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Lots antics</p>
                  <p className="mt-2 text-2xl font-bold text-foreground">{maintenanceSummary?.old_lot_statuses ?? '-'}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                  <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Intents antics</p>
                  <p className="mt-2 text-2xl font-bold text-foreground">{maintenanceSummary?.old_delivery_attempts ?? '-'}</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                  <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Cua vinculada</p>
                  <p className="mt-2 text-2xl font-bold text-foreground">{maintenanceSummary?.old_retry_items ?? '-'}</p>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-5">
                <label className="flex flex-col gap-2 text-sm">
                  <span className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-muted-foreground"><Filter size={13} />Estat</span>
                  <select value={runLotFilter.status} onChange={(event) => setRunLotFilter((current) => ({ ...current, status: event.target.value }))} className="rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary">
                    <option value="">Tots</option>
                    {LOT_STATES.map((state) => <option key={state} value={state}>{lotStatusLabel(state)}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-2 text-sm">
                  <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Audiència</span>
                  <select value={runLotFilter.audience} onChange={(event) => setRunLotFilter((current) => ({ ...current, audience: event.target.value }))} className="rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary">
                    <option value="">Totes</option>
                    {DELIVERY_AUDIENCES.map((state) => <option key={state} value={state}>{deliveryAudienceLabel(state)}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-2 text-sm">
                  <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Resultat d'enviament</span>
                  <select value={runLotFilter.delivery_result} onChange={(event) => setRunLotFilter((current) => ({ ...current, delivery_result: event.target.value }))} className="rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary">
                    <option value="">Tots</option>
                    {DELIVERY_RESULTS.map((state) => <option key={state} value={state}>{deliveryResultLabel(state)}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-2 text-sm">
                  <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Text lot</span>
                  <input value={runLotFilter.search} onChange={(event) => setRunLotFilter((current) => ({ ...current, search: event.target.value }))} placeholder="AM10" className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
                </label>
                <button type="button" onClick={() => { if (expandedRunId) refreshRunLots(expandedRunId); }} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-foreground transition hover:bg-white/10">
                  <RefreshCcw size={16} />
                  Aplica
                </button>
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-3 py-3">Job</th>
                      <th className="px-3 py-3">Inici</th>
                      <th className="px-3 py-3">Estat</th>
                      <th className="px-3 py-3">Lots</th>
                      <th className="px-3 py-3">Accions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.length === 0 ? (
                      <tr><td colSpan="5" className="px-3 py-6 text-sm text-muted-foreground">No hi ha execucions registrades.</td></tr>
                    ) : runs.map((run) => (
                      <React.Fragment key={run.id}>
                        <tr className="border-t border-white/10 align-top">
                          <td className="px-3 py-4 text-foreground">{run.job_name || run.job_id}</td>
                          <td className="px-3 py-4 text-muted-foreground">{formatTimestamp(run.started_at)}</td>
                          <td className="px-3 py-4"><span className={`rounded-full border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${runStatusClass(run.status)}`}>{runStatusLabel(run.status)}</span></td>
                          <td className="px-3 py-4 text-muted-foreground">{runLotSummary(run.summary)}</td>
                          <td className="px-3 py-4">
                            <div className="flex flex-wrap gap-2">
                              <button type="button" onClick={() => toggleRunLots(run.id)} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10">
                                {expandedRunId === run.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                                Lots
                              </button>
                              {(!run.audit_type || String(run.audit_type).startsWith('post_crq')) ? (
                                <>
                                  <button type="button" onClick={() => handleOpenRunSnapshot(run)} className="inline-flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-emerald-100 transition hover:bg-emerald-500/20">
                                    <Download size={14} />
                                    Obrir snapshot
                                  </button>
                                  <button type="button" onClick={() => handleRerunLiveFromHistory(run)} className="inline-flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-amber-100 transition hover:bg-amber-500/20">
                                    <RefreshCcw size={14} />
                                    Reexecutar en viu
                                  </button>
                                </>
                              ) : null}
                              <a href={getAutomationRunReportUrl(run.id)} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10">
                                <Download size={14} />
                                Informe
                              </a>
                              <button type="button" onClick={() => handleExportRunCsv(run.id)} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10">
                                <Download size={14} />
                                CSV
                              </button>
                            </div>
                          </td>
                        </tr>
                        {expandedRunId === run.id ? (
                          <tr className="border-t border-white/5 bg-white/5">
                            <td colSpan="5" className="px-3 py-4">
                              {loadingRunLotsId === run.id ? (
                                <div className="flex items-center gap-2 text-sm text-muted-foreground"><RefreshCcw className="animate-spin" size={15} />Carregant detall per lots...</div>
                              ) : (
                                <div className="overflow-x-auto">
                                  <table className="min-w-full text-left text-sm">
                                    <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                                      <tr>
                                        <th className="px-3 py-3">Lot</th>
                                        <th className="px-3 py-3">Estat</th>
                                        <th className="px-3 py-3">Troballes</th>
                                        <th className="px-3 py-3">Audiència</th>
                                        <th className="px-3 py-3">Resultat d'enviament</th>
                                        <th className="px-3 py-3">Report</th>
                                        <th className="px-3 py-3">Enviament</th>
                                        <th className="px-3 py-3">Observacio</th>
                                        <th className="px-3 py-3">Acció</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {(runLotsById[run.id] || []).map((item, index) => (
                                        <tr key={`${run.id}-${item.lot || 'item'}-${index}`} className="border-t border-white/10">
                                          <td className="px-3 py-3 text-foreground">{item.lot || '-'}</td>
                                          <td className="px-3 py-3"><span className={`rounded-full border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${lotStatusClass(item.detection_status)}`}>{lotStatusLabel(item.detection_status)}</span></td>
                                          <td className="px-3 py-3 text-foreground">{item.num_findings ?? '-'}</td>
                                          <td className="px-3 py-3 text-foreground">{deliveryAudienceLabel(item.delivery_audience)}</td>
                                          <td className="px-3 py-3 text-foreground">{deliveryResultLabel(item.delivery_result)}</td>
                                          <td className="px-3 py-3 text-foreground">{yesNo(item.report_generated)}</td>
                                          <td className="px-3 py-3 text-foreground">{yesNo(item.email_sent)}</td>
                                          <td className="px-3 py-3 text-muted-foreground">{item.observaciones || item.motivo_sin_envio || '-'}</td>
                                          <td className="px-3 py-3">
                                            {!item.email_sent ? (
                                              <button type="button" onClick={() => handleEnqueueRetry(run.id, item.lot, item.lot === 'TIC' ? 'tic' : 'provider')} className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-amber-100 transition hover:bg-amber-500/20">
                                                Envia a reintents
                                              </button>
                                            ) : <span className="text-xs text-muted-foreground">-</span>}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </td>
                          </tr>
                        ) : null}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </section>
      </div>
    </>
  );
}
