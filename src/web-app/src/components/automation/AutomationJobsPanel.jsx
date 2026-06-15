import React from 'react';
import { Info, Mail, Play, Plus, RefreshCcw, Save, Trash2, Wand2, X } from 'lucide-react';
import AutomationSection from './AutomationSection.jsx';

export default function AutomationJobsPanel({
  isVisible,
  registerSection,
  openSections,
  toggleSection,
  editingJobId,
  resetForm,
  form,
  setForm,
  profiles,
  checks,
  saving,
  handleSaveJob,
  deliveryRoutes,
  masterLots,
  jobs,
  setEditingJobId,
  formFromJob,
  handleRunNow,
  handleToggleJob,
  handleDeleteJob,
}) {
  const rawTicRecipients = (deliveryRoutes.tic_summary_recipients || [])
    .map((item) => {
      if (typeof item === 'object' && item !== null) {
        return {
          email: String(item.email || '').trim(),
          enabled: item.enabled !== false,
        };
      }
      return {
        email: String(item || '').trim(),
        enabled: true,
      };
    })
    .filter((item) => item.email && item.enabled);

  const knownLotCodes = new Set(
    (masterLots || [])
      .filter((item) => item?.enabled !== false)
      .map((item) => String(item.code || '').trim().toUpperCase())
      .filter(Boolean),
  );

  const enabledProviderRoutes = (deliveryRoutes.providers || []).filter((item) => item?.enabled !== false);
  const areaTicRoute = enabledProviderRoutes.find((item) => String(item.provider_code || '').trim().toUpperCase() === 'TIC') || null;
  const ticRecipientMap = new Map();
  rawTicRecipients.forEach((item) => {
    ticRecipientMap.set(item.email.toLowerCase(), item);
  });
  (areaTicRoute?.emails || []).forEach((email) => {
    const cleaned = String(email || '').trim();
    if (cleaned) {
      ticRecipientMap.set(cleaned.toLowerCase(), { email: cleaned, enabled: true });
    }
  });
  const ticRecipients = Array.from(ticRecipientMap.values());

  const specialContextRoutes = enabledProviderRoutes.filter((item) => {
    const code = String(item.provider_code || '').trim().toUpperCase();
    return code && code !== 'TIC' && !knownLotCodes.has(code);
  });
  const lotRoutes = enabledProviderRoutes.filter((item) => {
    const code = String(item.provider_code || '').trim().toUpperCase();
    return code && knownLotCodes.has(code);
  });

  const renderEmailList = (emails, accentClass = 'border-white/10 bg-white/5') => {
    const normalized = (emails || []).map((item) => String(item || '').trim()).filter(Boolean);
    if (normalized.length === 0) {
      return <span className="text-[11px] text-muted-foreground italic">Sense destinataris</span>;
    }
    return (
      <div className="mt-3 grid gap-2">
        {normalized.map((email, index) => (
          <div
            key={`${email}-${index}`}
            className={`rounded-lg border px-3 py-2 text-[11px] text-foreground break-all ${accentClass}`}
          >
            {email}
          </div>
        ))}
      </div>
    );
  };

  const deliveryTargetOptions = [
    { value: 'lots', label: 'Correus als lots', description: "Envia els informes individuals o els avisos per lot segons la configuració del job." },
    { value: 'tic', label: "Resum a l'àrea TIC", description: "Envia el resum general consolidat quan el job genera resum." },
    { value: 'proves', label: 'Proves', description: 'Simula l\'enviament complet: resum general i correus per lot es redirigeixen als destinataris de prova.' },
  ];
  const testModeEnabled = (form.delivery_targets || []).includes('proves');

  return (
    <div className={`grid gap-8 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.8fr)] ${isVisible ? '' : 'hidden'}`}>
      <div className="flex flex-col gap-8">
        <div id="job_form" ref={registerSection('job_form')}>
        <AutomationSection
          title="Job d'automatització"
          description="Configura el job principal i el comportament de distribució per lots."
          open={openSections.job_form}
          onToggle={() => toggleSection('job_form')}
          actions={editingJobId ? (
            <button type="button" onClick={resetForm} className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10">
              Nou job
            </button>
          ) : null}
        >
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm">
              <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Nom del job</span>
              <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
            </label>
            <label className="flex flex-col gap-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Tipus d auditoria</span>
                <div className="group relative">
                  <Info size={12} className="cursor-help text-muted-foreground transition-colors hover:text-primary" />
                  <div className="invisible absolute bottom-full left-1/2 mb-2 w-64 -translate-x-1/2 rounded-lg border border-white/10 bg-slate-900 p-2 text-[10px] leading-relaxed text-foreground opacity-0 shadow-xl transition-all group-hover:visible group-hover:opacity-100">
                    <p className="font-bold text-primary">Auditoria de canvis:</p>
                    <p>Analitza l historial de canvis (checks SQL) en un rang de dates.</p>
                    <hr className="my-1 border-white/5" />
                    <p className="font-bold text-primary">Distribució per lots:</p>
                    <p>Genera informes individuals per lot, basats en l'última execució de l'Audit Engine.</p>
                  </div>
                </div>
              </div>
              <select value={form.audit_type} onChange={(event) => setForm((current) => ({ ...current, audit_type: event.target.value }))} className="rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary">
                <option value="post_crq">Auditoria de canvis</option>
                <option value="post_crq_distribution">Distribució per lots Post-CRQ</option>
              </select>
            </label>
            <label className="flex flex-col gap-2 text-sm">
              <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Perfil</span>
              <select value={form.profile} onChange={(event) => setForm((current) => ({ ...current, profile: event.target.value }))} className="rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary">
                {profiles.map((profile) => <option key={profile} value={profile}>{profile}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-2 text-sm">
              <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Hora inici</span>
              <input type="datetime-local" value={form.start_at} onChange={(event) => setForm((current) => ({ ...current, start_at: event.target.value }))} className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
            </label>
            <label className="flex flex-col gap-2 text-sm">
              <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Planificació</span>
              <select value={form.schedule_type} onChange={(event) => setForm((current) => ({ ...current, schedule_type: event.target.value }))} className="rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary">
                <option value="manual">Manual</option>
                <option value="once">Una vegada</option>
                <option value="daily">Diari</option>
                <option value="weekly">Setmanal</option>
                <option value="monthly">Mensual</option>
              </select>
            </label>
            <label className="flex flex-col gap-2 text-sm">
              <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Timeout segons</span>
              <input type="number" min="30" value={form.timeout_seconds} onChange={(event) => setForm((current) => ({ ...current, timeout_seconds: event.target.value }))} className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
            </label>
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-foreground">
              <input type="checkbox" checked={form.enabled} onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))} />
              Job actiu
            </label>
            <label className="flex flex-col gap-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Checks inclosos</span>
                <div className="group relative">
                  <Info size={12} className="cursor-help text-muted-foreground transition-colors hover:text-primary" />
                  <div className="invisible absolute bottom-full left-1/2 mb-2 w-64 -translate-x-1/2 rounded-lg border border-white/10 bg-slate-900 p-2 text-[10px] leading-relaxed text-foreground opacity-0 shadow-xl transition-all group-hover:visible group-hover:opacity-100">
                    Selecciona els controls SQL que vols executar. Mantén premuda la tecla Ctrl (o Cmd) per fer una selecció múltiple.
                  </div>
                </div>
              </div>
              <select multiple value={form.selected_checks} onChange={(event) => setForm((current) => ({ ...current, selected_checks: Array.from(event.target.selectedOptions).map((option) => option.value) }))} className="min-h-[120px] rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary">
                {checks.map((check) => <option key={check.check_id} value={check.check_id}>{check.title || check.check_id}</option>)}
              </select>
            </label>
          </div>

          {['post_crq', 'post_crq_distribution'].includes(form.audit_type) ? (
            <div className="mt-6 grid gap-4">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Planificador efectiu</p>
                    <p className="mt-1 text-sm text-muted-foreground">Aquesta configuració també s'aplicarà al run automàtic i quedarà guardada al snapshot.</p>
                  </div>
                  <span className="rounded-full border border-white/10 bg-black/10 px-2.5 py-1 text-[10px] font-bold uppercase text-foreground">
                    Global {form.scheduler_options?.max_concurrency ?? 2}
                  </span>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  {[
                    ['max_concurrency', 'Concurrència global'],
                    ['max_concurrency_upper_bound', 'Límit superior'],
                    ['max_heavy_concurrency', 'Pesades'],
                    ['max_medium_concurrency', 'Mitjanes'],
                    ['max_light_concurrency', 'Lleugeres'],
                    ['max_retries', 'Reintents'],
                  ].map(([key, label]) => (
                    <label key={key} className="flex flex-col gap-2 text-sm">
                      <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">{label}</span>
                      <input
                        type="number"
                        min="0"
                        value={form.scheduler_options?.[key] ?? ''}
                        onChange={(event) => setForm((current) => ({
                          ...current,
                          scheduler_options: {
                            ...(current.scheduler_options || {}),
                            [key]: Number(event.target.value || 0),
                          },
                        }))}
                        className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary"
                      />
                    </label>
                  ))}
                </div>
                <label className="mt-4 flex items-center gap-3 rounded-xl border border-white/10 bg-black/10 p-3 text-sm text-foreground">
                  <input
                    type="checkbox"
                    checked={form.scheduler_options?.enable_auto_throttle !== false}
                    onChange={(event) => setForm((current) => ({
                      ...current,
                      scheduler_options: {
                        ...(current.scheduler_options || {}),
                        enable_auto_throttle: event.target.checked,
                      },
                    }))}
                  />
                  Auto-throttle activat
                </label>
                <div className="mt-4 rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-sm text-muted-foreground">
                  La criticitat dels jobs d'automatització sempre es resol amb la configuració base del backend.
                  Els overrides manuals només estan disponibles a l'execució interactiva.
                </div>
              </div>
            </div>
          ) : null}

          {form.audit_type === 'post_crq_distribution' ? (
            <div className="mt-6 rounded-2xl border border-primary/20 bg-primary/10 p-5">
              <div className="flex items-center gap-3">
                <Wand2 size={18} className="text-primary" />
                <div>
                  <p className="text-sm font-semibold text-primary">Aquest job et deixa triar l'audiencia real dels correus i, si actives Proves, simular l'enviament complet contra un sol destinatari.</p>
                  <p className="mt-1 text-xs text-muted-foreground">La decisió d'enviament es basa en una matriu d'estat per lot i no en la presència visual del lot al PDF.</p>
                </div>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div className="col-span-full mt-4 space-y-6">
                  <div className="flex items-center justify-between border-b border-white/10 pb-2">
                    <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Personalització de lots i destinataris</span>
                    <button
                      type="button"
                      disabled={form.lot_scope_mode !== 'selected'}
                      onClick={() => {
                        setForm(prev => ({
                          ...prev,
                          selected_lots: [...(prev.selected_lots || []), { code: '', emails: [{ email: '', enabled: true }] }]
                        }));
                      }}
                      className="inline-flex items-center gap-2 rounded-lg bg-primary/20 px-3 py-1.5 text-[11px] font-bold uppercase tracking-tight text-primary transition hover:bg-primary/30 disabled:opacity-30"
                    >
                      <Plus size={14} />
                      Afegir lot
                    </button>
                  </div>

                  {form.lot_scope_mode === 'selected' ? (
                    <div className="grid gap-4 sm:grid-cols-2">
                      {(form.selected_lots || []).map((lot, lotIdx) => (
                        <div key={lotIdx} className="group relative flex flex-col gap-4 rounded-xl border border-white/10 bg-white/5 p-4 transition-all hover:border-primary/30">
                          <button
                            type="button"
                            onClick={() => {
                              setForm(prev => ({
                                ...prev,
                                selected_lots: prev.selected_lots.filter((_, i) => i !== lotIdx)
                              }));
                            }}
                            className="absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full bg-red-500/80 text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100 hover:bg-red-600"
                          >
                            <X size={14} />
                          </button>

                          <div className="flex flex-col gap-2">
                            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Codi del Lot</span>
                            <input
                              value={lot.code}
                              onChange={(e) => {
                                const val = e.target.value.toUpperCase();
                                setForm(prev => {
                                  const next = [...prev.selected_lots];
                                  next[lotIdx] = { ...next[lotIdx], code: val };
                                  return { ...prev, selected_lots: next };
                                });
                              }}
                              placeholder="AM05, BQ22..."
                              className="rounded-lg border border-white/10 bg-slate-900/50 p-2 text-xs font-mono font-bold text-primary outline-none focus:ring-1 focus:ring-primary"
                            />
                          </div>

                          <div className="flex flex-col gap-3">
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Destinataris de correu</span>
                              <button
                                type="button"
                                onClick={() => {
                                  setForm(prev => {
                                    const next = [...prev.selected_lots];
                                    next[lotIdx] = {
                                      ...next[lotIdx],
                                      emails: [...(next[lotIdx].emails || []), { email: '', enabled: true }]
                                    };
                                    return { ...prev, selected_lots: next };
                                  });
                                }}
                                className="text-[10px] font-bold text-primary hover:underline"
                              >
                                + Afegir correu
                              </button>
                            </div>
                            
                            <div className="space-y-2">
                              {(lot.emails || []).map((emailObj, emailIdx) => (
                                <div key={emailIdx} className="flex items-center gap-2">
                                  <input
                                    type="checkbox"
                                    checked={emailObj.enabled}
                                    onChange={(e) => {
                                      setForm(prev => {
                                        const next = [...prev.selected_lots];
                                        const nextEmails = [...next[lotIdx].emails];
                                        nextEmails[emailIdx] = { ...nextEmails[emailIdx], enabled: e.target.checked };
                                        next[lotIdx] = { ...next[lotIdx], emails: nextEmails };
                                        return { ...prev, selected_lots: next };
                                      });
                                    }}
                                    className="h-3 w-3 accent-primary"
                                  />
                                  <input
                                    value={emailObj.email}
                                    onChange={(e) => {
                                      setForm(prev => {
                                        const next = [...prev.selected_lots];
                                        const nextEmails = [...next[lotIdx].emails];
                                        nextEmails[emailIdx] = { ...nextEmails[emailIdx], email: e.target.value };
                                        next[lotIdx] = { ...next[lotIdx], emails: nextEmails };
                                        return { ...prev, selected_lots: next };
                                      });
                                    }}
                                    placeholder="correu@exemple.com"
                                    className="flex-1 rounded border border-white/5 bg-transparent p-1.5 text-[11px] outline-none focus:border-primary/50"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setForm(prev => {
                                        const next = [...prev.selected_lots];
                                        next[lotIdx] = {
                                          ...next[lotIdx],
                                          emails: next[lotIdx].emails.filter((_, i) => i !== emailIdx)
                                        };
                                        return { ...prev, selected_lots: next };
                                      });
                                    }}
                                    className="text-muted-foreground hover:text-red-400"
                                  >
                                    <X size={12} />
                                  </button>
                                </div>
                              ))}
                              {(!lot.emails || lot.emails.length === 0) && (
                                <p className="text-[10px] italic text-muted-foreground py-1">Es faran servir les rutes per defecte.</p>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                      {(form.selected_lots || []).length === 0 && (
                        <div className="col-span-full rounded-xl border border-dashed border-white/10 p-8 text-center">
                          <p className="text-sm text-muted-foreground">No hi ha cap lot seleccionat.</p>
                          <p className="mt-1 text-xs text-muted-foreground">Fes clic a "Afegir lot" per començar la configuració manual.</p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-xl border border-white/10 bg-white/5 p-6 text-center">
                      <p className="text-sm text-muted-foreground">S'inclouran tots els lots detectats per l'Audit Engine.</p>
                      <p className="mt-1 text-xs text-muted-foreground">Es faran servir les rutes de distribució configurades a la pestanya "Destinataris".</p>
                    </div>
                  )}
                </div>
                <label className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-foreground">
                  <input type="checkbox" checked={form.include_summary} onChange={(event) => setForm((current) => ({ ...current, include_summary: event.target.checked }))} />
                  Genera resum general
                </label>
                <label className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-foreground">
                  <input type="checkbox" checked={form.include_lot_reports} onChange={(event) => setForm((current) => ({ ...current, include_lot_reports: event.target.checked }))} />
                  Informe individual per lot amb troballes
                </label>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-foreground">
                  <input type="checkbox" checked={form.send_without_findings} onChange={(event) => setForm((current) => ({ ...current, send_without_findings: event.target.checked }))} />
                  Envia correu també als lots sense troballes
                </label>
                <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-muted-foreground">
                  Si l'actives, s'enviarà la plantilla <span className="font-semibold text-foreground">Lot sense troballes</span> sense adjunt individual.
                </div>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="flex flex-col gap-2 text-sm">
                  <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Envia correus a</span>
                  <select
                    multiple
                    value={form.delivery_targets || []}
                    onChange={(event) => setForm((current) => ({
                      ...current,
                      delivery_targets: Array.from(event.target.selectedOptions).map((option) => option.value),
                    }))}
                    className="min-h-[116px] rounded-xl border border-border bg-white p-3 text-sm text-slate-900 outline-none focus:ring-1 focus:ring-primary"
                  >
                    {deliveryTargetOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-muted-foreground">
                    <p className="font-semibold text-foreground">Pots seleccionar múltiples opcions</p>
                    <div className="mt-2 grid gap-2">
                      {deliveryTargetOptions.map((option) => (
                        <p key={option.value}>
                          <span className="font-semibold text-foreground">{option.label}:</span> {option.description}
                        </p>
                      ))}
                    </div>
                  </div>
                </label>
                <label className="flex flex-col gap-2 text-sm">
                  <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Destinataris de prova</span>
                  <textarea
                    value={form.delivery_override_recipients}
                    onChange={(event) => setForm((current) => ({ ...current, delivery_override_recipients: event.target.value }))}
                    placeholder="franciscovalladares@gencat.cat, suport@example.com"
                    disabled={!testModeEnabled}
                    className="min-h-[116px] rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <p className="text-xs text-muted-foreground">
                    Activa l'opció <span className="font-semibold text-foreground">Proves</span> per enviar a aquesta llista tant el resum general com tots els correus per lot. Per defecte es carrega <span className="font-semibold text-foreground">franciscovalladares@gencat.cat</span>.
                  </p>
                </label>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="flex flex-col gap-2 text-sm">
                  <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Assumpte del correu</span>
                  <input value={form.email_subject} onChange={(event) => setForm((current) => ({ ...current, email_subject: event.target.value }))} className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
                </label>
                <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-muted-foreground">
                  <p className="font-semibold text-foreground">Variables</p>
                  <p className="mt-1">{'{job_name} {profile} {lot} {status} {findings} {execution_id} {observations} {summary} {technical_legend} {affected_queries} {affected_schemas}'}</p>
                </div>
              </div>
              <label className="mt-4 flex flex-col gap-2 text-sm">
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Plantilla de correu del lot</span>
                <textarea value={form.email_body} onChange={(event) => setForm((current) => ({ ...current, email_body: event.target.value }))} className="min-h-[140px] rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
              </label>
            </div>
          ) : (
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <label className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-foreground">
                <input type="checkbox" checked={form.email_enabled} onChange={(event) => setForm((current) => ({ ...current, email_enabled: event.target.checked }))} />
                Activa enviament per correu
              </label>
              <label className="flex flex-col gap-2 text-sm">
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Destinataris correu</span>
                <input value={form.email_recipients} onChange={(event) => setForm((current) => ({ ...current, email_recipients: event.target.value }))} className="rounded-xl border border-border bg-white/5 p-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-primary" />
              </label>
            </div>
          )}

          <div className="mt-6 flex flex-wrap gap-3">
            <button type="button" onClick={handleSaveJob} disabled={saving} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60">
              <Save size={16} />
              {saving ? 'Desant...' : editingJobId ? 'Actualitza job' : 'Crea job'}
            </button>
            <button type="button" onClick={resetForm} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-foreground transition hover:bg-white/10">
              <RefreshCcw size={16} />
              Neteja formulari
            </button>
          </div>
        </AutomationSection>
        </div>
        <div id="context" ref={registerSection('context')}>
          <AutomationSection
            title="Context de distribució"
            description="Consulta ràpidament qui rep el resum TIC, els contextos especials i totes les rutes per lot sense sortir del formulari."
            open={openSections.context}
            onToggle={() => toggleSection('context')}
            actions={<Mail size={18} className="text-primary" />}
            className="overflow-hidden"
          >
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-primary/20 bg-primary/10 px-4 py-3">
                <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-primary">Àrea TIC</p>
                <p className="mt-2 text-2xl font-black text-foreground">{ticRecipients.length}</p>
                <p className="mt-1 text-xs text-muted-foreground">{areaTicRoute ? `Ruta ${areaTicRoute.label || areaTicRoute.provider_code}` : 'Sense ruta TIC específica'}</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-muted-foreground">Contextos</p>
                <p className="mt-2 text-2xl font-black text-foreground">{specialContextRoutes.length}</p>
                <p className="mt-1 text-xs text-muted-foreground">Rutes especials fora del catàleg mestre de lots.</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-muted-foreground">Lots amb ruta</p>
                <p className="mt-2 text-2xl font-black text-foreground">{lotRoutes.length}</p>
                <p className="mt-1 text-xs text-muted-foreground">Tots els lots coneguts amb correus visibles a sota.</p>
              </div>
            </div>

            <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(280px,0.75fr)_minmax(0,1.25fr)]">
              <div className="grid gap-4">
                <div className="rounded-2xl border border-primary/20 bg-primary/10 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-primary">Àrea TIC</p>
                      <p className="mt-1 text-sm text-muted-foreground">Destinataris consolidats del resum general i de la ruta `ATIC`.</p>
                    </div>
                    <span className="rounded-full border border-primary/20 bg-primary/15 px-2.5 py-1 text-[10px] font-bold uppercase text-primary">
                      {ticRecipients.length} correus
                    </span>
                  </div>
                  {areaTicRoute ? (
                    <div className="mt-3 inline-flex rounded-full border border-primary/20 bg-black/10 px-3 py-1 text-[10px] font-bold uppercase tracking-wide text-primary">
                      Ruta activa: {areaTicRoute.label || areaTicRoute.provider_code}
                    </div>
                  ) : null}
                  {renderEmailList(ticRecipients.map((item) => item.email), 'border-primary/20 bg-white/10')}
                </div>

                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-muted-foreground">Contextos especials</p>
                      <p className="mt-1 text-sm text-muted-foreground">Caixes de distribució que no formen part dels lots mestres, com `PROVES`.</p>
                    </div>
                    <span className="rounded-full border border-white/10 bg-black/10 px-2.5 py-1 text-[10px] font-bold uppercase text-foreground">
                      {specialContextRoutes.length}
                    </span>
                  </div>
                  <div className="mt-4 grid gap-3">
                    {specialContextRoutes.length > 0 ? specialContextRoutes.map((route, idx) => (
                      <div key={`special-route-${idx}`} className="rounded-xl border border-white/10 bg-black/10 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-semibold text-foreground">{route.label || route.provider_code}</span>
                          <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-bold uppercase text-muted-foreground">
                            {route.provider_code}
                          </span>
                        </div>
                        {renderEmailList(route.emails, 'border-white/10 bg-white/5')}
                      </div>
                    )) : (
                      <div className="rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-sm text-muted-foreground">
                        Sense contextos especials.
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-muted-foreground">Lots amb ruta</p>
                    <p className="mt-1 text-sm text-muted-foreground">Totes les rutes per lot disponibles al backend, amb el detall complet dels correus.</p>
                  </div>
                  <span className="rounded-full border border-white/10 bg-black/10 px-3 py-1 text-[10px] font-bold uppercase text-foreground">
                    {lotRoutes.length} lots
                  </span>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {lotRoutes.length > 0 ? lotRoutes.map((route, idx) => (
                    <div key={`lot-route-${idx}`} className="rounded-xl border border-white/10 bg-black/10 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <p className="text-sm font-semibold text-foreground">{route.provider_code}</p>
                          <p className="text-[11px] text-muted-foreground">{route.label || route.provider_code}</p>
                        </div>
                        <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-bold uppercase text-muted-foreground">
                          {(route.emails || []).length} correus
                        </span>
                      </div>
                      {renderEmailList(route.emails, 'border-white/10 bg-white/5')}
                    </div>
                  )) : (
                    <div className="rounded-xl border border-dashed border-white/10 bg-black/10 p-4 text-sm text-muted-foreground">
                      Sense lots amb ruta.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </AutomationSection>
        </div>
      </div>

      <section className="flex flex-col gap-8">
        <div id="jobs" ref={registerSection('jobs')}>
          <AutomationSection
            title="Jobs configurats"
            description="Execució immediata, edició i activació sense sortir de la pestanya."
            open={openSections.jobs}
            onToggle={() => toggleSection('jobs')}
            actions={<span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-muted-foreground">{jobs.length} jobs</span>}
          >
            <div className="mt-4 flex flex-col gap-3">
              {jobs.length === 0 ? <p className="text-sm text-muted-foreground">Encara no hi ha jobs creats.</p> : jobs.map((job) => (
                <div key={job.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-base font-semibold text-foreground">{job.name}</span>
                        <span className={`rounded-full border px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${job.enabled ? 'border-green-500/20 bg-green-500/10 text-green-200' : 'border-slate-500/20 bg-slate-500/10 text-slate-300'}`}>{job.enabled ? 'actiu' : 'aturat'}</span>
                        <span className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{job.audit_type}</span>
                      </div>
                      <p className="mt-2 text-sm text-muted-foreground">Perfil {job.profile} · Planificació {job.schedule_type} · Timeout {job.timeout_seconds}s</p>
                      {(!job.audit_type || String(job.audit_type).startsWith('post_crq')) ? (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Checks {(job.checks || []).length} · Criticitat backend base · Concurrència {job.scheduler_options?.max_concurrency ?? '-'}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button type="button" onClick={() => { setEditingJobId(job.id); setForm(formFromJob(job)); }} className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10">Edita</button>
                      <button type="button" onClick={() => handleRunNow(job.id)} className="inline-flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/10 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-primary transition hover:bg-primary/20"><Play size={14} />Executa ara</button>
                      <button type="button" onClick={() => handleToggleJob(job)} className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-foreground transition hover:bg-white/10">{job.enabled ? 'Desactiva' : 'Activa'}</button>
                      <button type="button" onClick={() => handleDeleteJob(job.id)} className="inline-flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-red-200 transition hover:bg-red-500/20"><Trash2 size={14} />Esborra</button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </AutomationSection>
        </div>
      </section>
    </div>
  );
}
