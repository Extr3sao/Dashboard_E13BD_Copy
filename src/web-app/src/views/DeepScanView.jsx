import React, { Suspense, lazy } from 'react';
import clsx from 'clsx';
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Code,
  Database,
  Info,
  RefreshCcw,
  ShieldAlert,
  SlidersHorizontal,
  Terminal,
  Zap,
  ZapOff,
} from 'lucide-react';
import {
  asNum,
  calculateCustomScoring,
  getEffectiveBreakdown,
  getEffectiveScore,
  getQueryObjective,
  getQueryReason,
  hasMandatoryQueryErrors,
  signalByBlockerCount,
  signalByDaysSinceDDL,
  signalByLoginDays,
  signalByOutgoing,
  signalByRecentCount,
  signalByScore,
  signalCardClass,
  signalDotClass,
} from '../utils/deepScan.js';

const ScoringGuide = lazy(() => import('../components/ScoringGuide.jsx'));

export default function DeepScanView({
  profiles = [],
  selectedProfile = '',
  onProfileChange = () => {},
  auditData,
  selectedAuditIndex,
  setSelectedAuditIndex,
  schemaToAudit,
  setSchemaToAudit,
  runDeepAudit,
  isAuditing,
  handleTestDeepConnection,
  testStatusDeep,
  scoringHelpOpen,
  setScoringHelpOpen,
  scoringMenuOpen,
  setScoringMenuOpen,
  scoringConfig,
  setScoringConfig,
  DEFAULT_SCORING_CONFIG,
}) {
  const getScore = (item) => getEffectiveScore(item, scoringConfig);
  const getBreakdown = (item) => getEffectiveBreakdown(item, scoringConfig);
  const getScoreDetails = (item) => calculateCustomScoring(item, scoringConfig);

  return (
    <div className="deep-scan-view flex flex-col gap-8">
      <div className="glass-card deep-scan-hero p-8 flex flex-col md:flex-row gap-8 items-center justify-between">
        <div className="flex-1">
          <h3 className="text-3xl font-extrabold mb-4 text-primary tracking-tight">Anàlisi 360° {auditData.length > 1 ? 'Massiva' : "d'Esquema"}</h3>
          <p className="text-muted-foreground mb-6 font-medium">Investigació profunda d'obsolescència, dependències i activitat.</p>
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold uppercase tracking-wider opacity-60">Connexió activa</span>
                <select
                  value={selectedProfile}
                  onChange={(e) => onProfileChange(e.target.value)}
                  className="rounded-xl border border-border bg-white/5 p-4 text-lg outline-none focus:ring-2 focus:ring-primary appearance-none cursor-pointer"
                >
                  {profiles.length === 0 && <option value="">Sense perfils disponibles</option>}
                  {profiles.map((profile) => (
                    <option key={profile} value={profile}>{profile}</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-2">
                <span className="text-xs font-bold uppercase tracking-wider opacity-60">Esquema a auditar</span>
                <input
                  className="deep-scan-input w-full bg-white/5 border border-border p-4 rounded-xl font-mono text-lg focus:ring-2 focus:ring-primary outline-none"
                  placeholder="Ex: MGR_APP, USER_DB..."
                  value={schemaToAudit}
                  onChange={(e) => setSchemaToAudit(e.target.value.toUpperCase())}
                />
              </label>
            </div>

            <button
              onClick={runDeepAudit}
              disabled={isAuditing || !selectedProfile || !schemaToAudit}
              className="deep-scan-audit-btn w-fit bg-primary px-6 py-2.5 rounded-lg font-bold text-sm hover:scale-105 transition-all shadow-lg shadow-primary/10 flex items-center justify-center gap-2"
            >
              {isAuditing ? <RefreshCcw className="animate-spin" size={16} /> : <Zap size={18} />}
              Iniciar Auditoria
            </button>

            <div className="flex items-center gap-4">
              <button
                onClick={handleTestDeepConnection}
                className="deep-scan-test-btn text-xs font-bold uppercase tracking-wider text-muted-foreground hover:text-primary transition-all flex items-center gap-1"
              >
                <Database size={12} /> Test de connexió ràpida
              </button>
              {testStatusDeep && (
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${testStatusDeep.status === 'success' ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                  {testStatusDeep.msg}
                </span>
              )}
            </div>

            <div className="mt-2">
              <button
                onClick={() => setScoringHelpOpen((v) => !v)}
                className="deep-scan-help-btn w-full flex items-center justify-between px-3 py-2 bg-white/5 border border-border rounded-lg hover:bg-white/10 transition-all text-sm"
              >
                <span className="flex items-center gap-2 font-semibold">
                  <Info size={14} className="text-primary" />
                  Explicació del càlcul i què significa
                </span>
                {scoringHelpOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>

              {scoringHelpOpen && (
                <div className="deep-scan-help-panel mt-3 p-4 bg-white/5 border border-white/10 rounded-xl space-y-3 text-sm">
                  <Suspense fallback={<p className="text-sm text-muted-foreground">Carregant guia visual...</p>}>
                    <ScoringGuide />
                  </Suspense>
                </div>
              )}
            </div>

            <div className="mt-2">
              <button
                onClick={() => setScoringMenuOpen((v) => !v)}
                className="deep-scan-toggle-btn w-full flex items-center justify-between px-3 py-2 bg-white/5 border border-border rounded-lg hover:bg-white/10 transition-all text-sm"
              >
                <span className="flex items-center gap-2 font-semibold">
                  <SlidersHorizontal size={14} className="text-primary" />
                  Com es calcula el % d'obsolescència (configurable)
                </span>
                {scoringMenuOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>

              {scoringMenuOpen && (
                <div className="deep-scan-config-panel mt-3 p-4 bg-white/5 border border-white/10 rounded-xl space-y-3">
                  <p className="text-[11px] text-muted-foreground">
                    Modifica els barems i el % es recalcula en aquesta vista. Per defecte coincideix amb el model v4.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                    {[
                      { key: 'dmlNoActivityPts', label: 'Punts DML sense activitat', min: 0, max: 40, step: 1 },
                      { key: 'dependenciesMaxPts', label: 'Màxim punts dependències', min: 0, max: 50, step: 1 },
                      { key: 'inboundPenaltyPerDep', label: 'Penalització per dep. entrant', min: 0, max: 20, step: 1 },
                      { key: 'outboundPenaltyPerDep', label: 'Penalització per dep. sortint', min: 0, max: 10, step: 1 },
                      { key: 'loginInactivePts', label: 'Punts login inactiu', min: 0, max: 20, step: 1 },
                      { key: 'loginInactiveDays', label: 'Dies d\'inactivitat login', min: 30, max: 720, step: 10 },
                      { key: 'sizeTinyThresholdGb', label: 'Llindar mida petita (GB)', min: 0.01, max: 0.5, step: 0.01 },
                      { key: 'sizeTinyPts', label: 'Punts mida petita', min: 0, max: 30, step: 1 },
                      { key: 'sizeSmallThresholdGb', label: 'Llindar mida mitjana (GB)', min: 0.1, max: 5, step: 0.1 },
                      { key: 'sizeSmallPts', label: 'Punts mida mitjana', min: 0, max: 20, step: 1 },
                      { key: 'automationBonusPts', label: 'Bonus sense bloquejadors', min: 0, max: 30, step: 1 },
                      { key: 'automationPenaltyPerBlocker', label: 'Penalització per bloquejador', min: 0, max: 20, step: 1 },
                      { key: 'automationPenaltyCap', label: 'Topall penalització bloquejadors', min: 0, max: 80, step: 1 },
                    ].map((f) => (
                      <label key={f.key} className="flex flex-col gap-1">
                        <span className="font-semibold opacity-80">{f.label}: <span className="text-primary">{scoringConfig[f.key]}</span></span>
                        <input
                          type="range"
                          min={f.min}
                          max={f.max}
                          step={f.step}
                          value={scoringConfig[f.key]}
                          onChange={(e) => setScoringConfig((prev) => ({ ...prev, [f.key]: Number(e.target.value) }))}
                        />
                      </label>
                    ))}
                  </div>
                  <div className="flex justify-end">
                    <button
                      onClick={() => setScoringConfig(DEFAULT_SCORING_CONFIG)}
                      className="deep-scan-restore-btn text-xs px-3 py-1.5 rounded-lg bg-primary/20 text-primary border border-primary/20 hover:bg-primary/30"
                    >
                      Restaurar valors v4
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {auditData.length > 0 && auditData[selectedAuditIndex] && (
          <div className="deep-scan-score-card flex flex-col items-center p-6 bg-white/5 rounded-3xl border border-white/10">
            {hasMandatoryQueryErrors(auditData[selectedAuditIndex]) && (
              <div className="mb-3 text-[10px] font-bold uppercase tracking-wider text-red-400">
                Evidència insuficient: consultes obligatòries amb error
              </div>
            )}
            <div className="relative w-40 h-40 flex items-center justify-center">
              <svg className="w-full h-full transform -rotate-90">
                <circle cx="80" cy="80" r="70" fill="transparent" stroke="currentColor" strokeWidth="8" className="text-white/5" />
                <circle
                  cx="80" cy="80" r="70" fill="transparent" stroke="currentColor" strokeWidth="8"
                  strokeDasharray={440} strokeDashoffset={440 - (440 * getScore(auditData[selectedAuditIndex])) / 100}
                  className={`${getScore(auditData[selectedAuditIndex]) > 70 ? 'text-green-500' : getScore(auditData[selectedAuditIndex]) > 40 ? 'text-orange-500' : 'text-red-500'} transition-all duration-1000`}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-4xl font-black">{getScore(auditData[selectedAuditIndex])}%</span>
                <span className="text-[10px] uppercase font-bold tracking-tighter opacity-50">Obsolescència</span>
              </div>
            </div>
            <p className="mt-4 font-bold text-xs uppercase tracking-widest opacity-60">
              {getScore(auditData[selectedAuditIndex]) > 70 ? "Candidat segur per esborrar" : "Requereix verificació humana"}
            </p>
          </div>
        )}
      </div>

      {auditData.length > 1 && (
        <div className="deep-scan-selector-grid grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {auditData.map((data, idx) => (
            <button
              key={idx}
              onClick={() => setSelectedAuditIndex(idx)}
              className={`deep-scan-schema-btn p-4 rounded-xl border transition-all text-left flex flex-col gap-1 ${selectedAuditIndex === idx ? 'deep-scan-schema-btn-active bg-primary/20 border-primary ring-1 ring-primary' : 'bg-white/5 border-white/10 hover:bg-white/10'}`}
            >
              <span className="text-[10px] font-bold uppercase opacity-50 truncate">{data.username}</span>
              <div className="flex items-end justify-between">
                <span className="text-xl font-black">{getScore(data)}%</span>
                <div className={`w-2 h-2 rounded-full ${getScore(data) > 70 ? 'bg-green-500' : getScore(data) > 40 ? 'bg-orange-500' : 'bg-red-500'}`}></div>
              </div>
            </button>
          ))}
        </div>
      )}

      {auditData.length > 0 && auditData[selectedAuditIndex] && (
        <div className="deep-scan-results-grid grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 space-y-6">
            <div className="glass-card deep-scan-details-card p-6">
              <div className="flex justify-between items-center mb-4">
                <h4 className="text-xl font-bold flex items-center gap-2 text-primary font-bold"><Info size={20} /> Detalls: {auditData[selectedAuditIndex].username}</h4>
                <span className="text-[10px] bg-white/10 px-2 py-1 rounded font-mono">ID: {selectedAuditIndex + 1}</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
                <div className={clsx("p-4 rounded-xl border", signalCardClass(signalByScore(getScore(auditData[selectedAuditIndex]))))}>
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1 flex items-center justify-between">% Obsolescència <span className={clsx("w-2 h-2 rounded-full", signalDotClass(signalByScore(getScore(auditData[selectedAuditIndex]))))} /></p>
                  <p className="text-2xl font-black">{getScore(auditData[selectedAuditIndex])}%</p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1">Mida</p>
                  <p className="text-2xl font-black">{auditData[selectedAuditIndex].summary?.SIZE_GB || 0} GB</p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1">Objectes</p>
                  <p className="text-2xl font-black">{auditData[selectedAuditIndex].summary?.OBJECT_COUNT || 0}</p>
                </div>
                <div className={clsx("p-4 rounded-xl border", signalCardClass(signalByLoginDays(auditData[selectedAuditIndex].summary?.LAST_LOGIN_DAYS ?? auditData[selectedAuditIndex].summary?.LAST_LOGIN_DAYS_AGO)))}>
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1">Darrer Login</p>
                  <p className="text-2xl font-black">{auditData[selectedAuditIndex].summary?.LAST_LOGIN_DAYS ?? auditData[selectedAuditIndex].summary?.LAST_LOGIN_DAYS_AGO ?? 'N/A'} d</p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1">Antiguitat</p>
                  <p className="text-2xl font-black">{auditData[selectedAuditIndex].summary?.DAYS_OLD || 0} d</p>
                </div>
                <div className={clsx("p-4 rounded-xl border", signalCardClass(signalByBlockerCount(asNum(auditData[selectedAuditIndex].summary?.ACTIVE_JOBS, auditData[selectedAuditIndex].active_jobs?.length || 0))))}>
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1 flex items-center justify-between">Jobs Actius <span className={clsx("w-2 h-2 rounded-full", signalDotClass(signalByBlockerCount(asNum(auditData[selectedAuditIndex].summary?.ACTIVE_JOBS, auditData[selectedAuditIndex].active_jobs?.length || 0))))} /></p>
                  <p className="text-2xl font-black">{asNum(auditData[selectedAuditIndex].summary?.ACTIVE_JOBS, auditData[selectedAuditIndex].active_jobs?.length || 0)}</p>
                </div>
                <div className={clsx("p-4 rounded-xl border", signalCardClass(signalByBlockerCount(asNum(auditData[selectedAuditIndex].summary?.APEX_APPLICATIONS, auditData[selectedAuditIndex].apex_apps?.length || 0))))}>
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1 flex items-center justify-between">Apps APEX <span className={clsx("w-2 h-2 rounded-full", signalDotClass(signalByBlockerCount(asNum(auditData[selectedAuditIndex].summary?.APEX_APPLICATIONS, auditData[selectedAuditIndex].apex_apps?.length || 0))))} /></p>
                  <p className="text-2xl font-black">{asNum(auditData[selectedAuditIndex].summary?.APEX_APPLICATIONS, auditData[selectedAuditIndex].apex_apps?.length || 0)}</p>
                </div>
                <div className={clsx("p-4 rounded-xl border", signalCardClass(signalByBlockerCount(asNum(auditData[selectedAuditIndex].summary?.ENABLED_TRIGGERS, auditData[selectedAuditIndex].enabled_triggers?.length || 0))))}>
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1 flex items-center justify-between">Triggers Habilitats <span className={clsx("w-2 h-2 rounded-full", signalDotClass(signalByBlockerCount(asNum(auditData[selectedAuditIndex].summary?.ENABLED_TRIGGERS, auditData[selectedAuditIndex].enabled_triggers?.length || 0))))} /></p>
                  <p className="text-2xl font-black">{asNum(auditData[selectedAuditIndex].summary?.ENABLED_TRIGGERS, auditData[selectedAuditIndex].enabled_triggers?.length || 0)}</p>
                </div>
                <div className={clsx("p-4 rounded-xl border", signalCardClass(signalByDaysSinceDDL(auditData[selectedAuditIndex].summary?.DAYS_SINCE_NEWEST_DDL)))}>
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1 flex items-center justify-between">Dies des de l'últim DDL <span className={clsx("w-2 h-2 rounded-full", signalDotClass(signalByDaysSinceDDL(auditData[selectedAuditIndex].summary?.DAYS_SINCE_NEWEST_DDL)))} /></p>
                  <p className="text-2xl font-black">{auditData[selectedAuditIndex].summary?.DAYS_SINCE_NEWEST_DDL ?? 'N/A'}</p>
                </div>
                <div className={clsx("p-4 rounded-xl border", signalCardClass(signalByRecentCount(auditData[selectedAuditIndex].summary?.TABLES_STATS_RECENT_30D)))}>
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1 flex items-center justify-between">Taules amb stats &lt;30d <span className={clsx("w-2 h-2 rounded-full", signalDotClass(signalByRecentCount(auditData[selectedAuditIndex].summary?.TABLES_STATS_RECENT_30D)))} /></p>
                  <p className="text-2xl font-black">{auditData[selectedAuditIndex].summary?.TABLES_STATS_RECENT_30D ?? 0}</p>
                </div>
                <div className={clsx("p-4 rounded-xl border", signalCardClass(signalByRecentCount(auditData[selectedAuditIndex].summary?.TABLES_WITH_MODS_30D)))}>
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1 flex items-center justify-between">Taules amb DML 30d <span className={clsx("w-2 h-2 rounded-full", signalDotClass(signalByRecentCount(auditData[selectedAuditIndex].summary?.TABLES_WITH_MODS_30D)))} /></p>
                  <p className="text-2xl font-black">{auditData[selectedAuditIndex].summary?.TABLES_WITH_MODS_30D ?? 0}</p>
                </div>
                <div className={clsx("p-4 rounded-xl border", signalCardClass(signalByBlockerCount(auditData[selectedAuditIndex].summary?.INBOUND_REFERENCES)))}>
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1 flex items-center justify-between">Dep. Entrants <span className={clsx("w-2 h-2 rounded-full", signalDotClass(signalByBlockerCount(auditData[selectedAuditIndex].summary?.INBOUND_REFERENCES)))} /></p>
                  <p className="text-2xl font-black">{auditData[selectedAuditIndex].summary?.INBOUND_REFERENCES ?? 0}</p>
                </div>
                <div className={clsx("p-4 rounded-xl border", signalCardClass(signalByOutgoing(auditData[selectedAuditIndex].summary?.EXTERNAL_DEPENDENCIES_OUT)))}>
                  <p className="text-xs text-muted-foreground uppercase font-bold mb-1 flex items-center justify-between">Dep. Sortints <span className={clsx("w-2 h-2 rounded-full", signalDotClass(signalByOutgoing(auditData[selectedAuditIndex].summary?.EXTERNAL_DEPENDENCIES_OUT)))} /></p>
                  <p className="text-2xl font-black">{auditData[selectedAuditIndex].summary?.EXTERNAL_DEPENDENCIES_OUT ?? 0}</p>
                </div>
              </div>

              <div className="mt-6 border-t border-white/10 pt-6">
                <h5 className="text-sm font-bold uppercase tracking-wider mb-2 opacity-70 flex items-center gap-2"><Activity size={16} /> Com s'ha calculat la nota (v4)</h5>
                <p className="text-[11px] text-muted-foreground mb-4">
                  La nota és la suma de factors i es limita entre 0 i 100. Si tot és favorable (inactivitat, sense dependències, mida petita i sense automatismes), la suma arriba a 100.
                </p>
                {auditData[selectedAuditIndex].score_meta && (
                  <p className="text-[11px] text-muted-foreground mb-4">
                    Suma calculada: {getScoreDetails(auditData[selectedAuditIndex]).raw} | Nota final: {getScore(auditData[selectedAuditIndex])}
                    {getScoreDetails(auditData[selectedAuditIndex]).raw !== getScore(auditData[selectedAuditIndex]) ? " (ajustada al rang 0..100)" : ""}
                  </p>
                )}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  <div className="md:col-span-2 space-y-3">
                    {getBreakdown(auditData[selectedAuditIndex]).map((b, i) => (
                      <div key={i} className="deep-scan-breakdown-item flex items-center justify-between p-3 bg-white/5 rounded-xl border border-white/5">
                        <div className="flex flex-col">
                          <span className="text-[10px] font-bold uppercase opacity-40">{b.factor}</span>
                          <span className="text-xs font-medium">{b.desc}</span>
                        </div>
                        <span className={clsx("text-sm font-bold", b.pts > 0 ? "text-red-400" : "text-green-400")}>
                          {b.pts > 0 ? `+${b.pts}` : b.pts}
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="glass-card deep-scan-code-refs p-4 bg-primary/5 border-primary/10">
                    <h6 className="text-[10px] font-bold uppercase opacity-50 mb-3 flex items-center gap-2 text-primary">
                      <Code size={12} /> Referències en Codi Extern
                    </h6>
                    <div className="space-y-2 max-h-[220px] overflow-auto pr-1">
                      {auditData[selectedAuditIndex].code_refs?.length > 0 ? (
                        auditData[selectedAuditIndex].code_refs.map((ref, i) => (
                          <div key={i} className="deep-scan-code-ref-item p-2 bg-black/20 rounded border border-white/5 text-[10px]">
                            <div className="flex justify-between items-center mb-1">
                              <span className="font-bold text-primary">{ref.OWNER}</span>
                              <span className="opacity-40 text-[9px]">{ref.TYPE}</span>
                            </div>
                            <div className="truncate opacity-80">{ref.NAME}</div>
                          </div>
                        ))
                      ) : (
                        <div className="text-[10px] italic opacity-40 text-center py-4">Sense referències en dba_source</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="glass-card deep-scan-table-card p-6">
              <h4 className="text-xl font-bold mb-4 flex items-center gap-2 text-primary font-bold"><Database size={20} /> Activitat de Dades (DML)</h4>
              {auditData[selectedAuditIndex].activity?.dml?.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="text-[10px] uppercase opacity-40 border-b border-white/10">
                        <th className="pb-2">Taula</th>
                        <th className="pb-2">Tipus Activitat</th>
                        <th className="pb-2">Data</th>
                      </tr>
                    </thead>
                    <tbody className="text-xs">
                      {auditData[selectedAuditIndex].activity.dml.map((d, i) => (
                        <tr key={i} className="border-b border-white/5">
                          <td className="py-2 font-mono font-bold">{d.TABLE_NAME}</td>
                          <td className="py-2">{d.INFERRED_ACTIVITY || 'DML_RECENT'}</td>
                          <td className="py-2 opacity-60">{d.TIMESTAMP}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-8 text-center bg-white/5 rounded-2xl border border-dashed border-white/10 flex flex-col items-center gap-2">
                  <ZapOff size={32} className="opacity-20" />
                  <p className="text-sm text-balance italic opacity-40">Sense activitat de dades detectada en les logs de dba_tab_modifications</p>
                </div>
              )}
            </div>

            <div className="glass-card deep-scan-table-card p-6">
              <h4 className="text-xl font-bold mb-4 flex items-center gap-2 text-primary font-bold"><Activity size={20} /> Taules amb Estadístiques Recents (&lt;30 dies)</h4>
              {(auditData[selectedAuditIndex].table_stats || []).filter(t => Number(t.DAYS_SINCE_ANALYZED) <= 30).length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="text-[10px] uppercase opacity-40 border-b border-white/10">
                        <th className="pb-2">Taula</th>
                        <th className="pb-2">Dies Des de Analyze</th>
                        <th className="pb-2">Last Analyzed</th>
                        <th className="pb-2">Num Rows</th>
                      </tr>
                    </thead>
                    <tbody className="text-xs">
                      {(auditData[selectedAuditIndex].table_stats || [])
                        .filter(t => Number(t.DAYS_SINCE_ANALYZED) <= 30)
                        .slice(0, 30)
                        .map((t, i) => (
                          <tr key={i} className="border-b border-white/5">
                            <td className="py-2 font-mono font-bold">{t.TABLE_NAME}</td>
                            <td className="py-2">{t.DAYS_SINCE_ANALYZED}</td>
                            <td className="py-2 opacity-70">{t.LAST_ANALYZED}</td>
                            <td className="py-2">{t.NUM_ROWS ?? '-'}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-6 text-center bg-white/5 rounded-2xl border border-dashed border-white/10">
                  <p className="text-sm text-balance italic opacity-40">No s'han trobat taules amb estadístiques recents (&lt;30 dies).</p>
                </div>
              )}
            </div>

            <div className="glass-card deep-scan-table-card p-6">
              <h4 className="text-xl font-bold mb-4 flex items-center gap-2 text-primary font-bold"><Terminal size={20} /> Traçabilitat de Consultes (Q01..Q19)</h4>
              {auditData[selectedAuditIndex].executed_queries?.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="text-[10px] uppercase opacity-40 border-b border-white/10">
                        <th className="pb-2">Consulta</th>
                        <th className="pb-2">Objectiu</th>
                        <th className="pb-2">Estat</th>
                        <th className="pb-2">Motiu</th>
                      </tr>
                    </thead>
                    <tbody className="text-xs">
                      {auditData[selectedAuditIndex].executed_queries.map((q, i) => (
                        <tr key={i} className="border-b border-white/5">
                          <td className="py-2 font-mono font-bold">{q.query || '-'}</td>
                          <td className="py-2 opacity-80">{getQueryObjective(q.query)}</td>
                          <td className="py-2">
                            <span className={clsx(
                              "px-2 py-1 rounded text-[10px] uppercase font-bold",
                              q.status === 'ok' ? "bg-green-500/10 text-green-400" :
                                q.status === 'skipped' ? "bg-yellow-500/10 text-yellow-400" :
                                  "bg-red-500/10 text-red-400"
                            )}>
                              {q.status || 'n/a'}
                            </span>
                          </td>
                          <td className="py-2 opacity-70">{getQueryReason(q)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-6 text-center bg-white/5 rounded-2xl border border-dashed border-white/10">
                  <p className="text-sm text-balance italic opacity-40">Sense traçabilitat de consultes disponible.</p>
                </div>
              )}
            </div>
          </div>
          
          <div className="deep-scan-side-column space-y-6">
            <div className="glass-card deep-scan-side-card p-6">
              <h4 className="text-xl font-bold mb-4 flex items-center gap-2 text-primary font-bold"><Info size={20} /> Visibilitat Operativa</h4>
              <div className="space-y-3 text-sm">
                <div className="flex justify-between p-3 rounded-xl bg-white/5 border border-white/10">
                  <span>Hi ha jobs actius?</span>
                  <span className={clsx("font-bold", asNum(auditData[selectedAuditIndex].summary?.ACTIVE_JOBS, auditData[selectedAuditIndex].active_jobs?.length || 0) > 0 ? "text-red-400" : "text-green-400")}>
                    {asNum(auditData[selectedAuditIndex].summary?.ACTIVE_JOBS, auditData[selectedAuditIndex].active_jobs?.length || 0) > 0 ? `SI (${asNum(auditData[selectedAuditIndex].summary?.ACTIVE_JOBS, auditData[selectedAuditIndex].active_jobs?.length || 0)})` : "NO"}
                  </span>
                </div>
                <div className="flex justify-between p-3 rounded-xl bg-white/5 border border-white/10">
                  <span>Hi ha triggers habilitats?</span>
                  <span className={clsx("font-bold", asNum(auditData[selectedAuditIndex].summary?.ENABLED_TRIGGERS, auditData[selectedAuditIndex].enabled_triggers?.length || 0) > 0 ? "text-red-400" : "text-green-400")}>
                    {asNum(auditData[selectedAuditIndex].summary?.ENABLED_TRIGGERS, auditData[selectedAuditIndex].enabled_triggers?.length || 0) > 0 ? `SI (${asNum(auditData[selectedAuditIndex].summary?.ENABLED_TRIGGERS, auditData[selectedAuditIndex].enabled_triggers?.length || 0)})` : "NO"}
                  </span>
                </div>
                <div className="flex justify-between p-3 rounded-xl bg-white/5 border border-white/10">
                  <span>Nº d'aplicacions APEX</span>
                  <span className={clsx("font-bold", asNum(auditData[selectedAuditIndex].summary?.APEX_APPLICATIONS, auditData[selectedAuditIndex].apex_apps?.length || 0) > 0 ? "text-orange-400" : "text-green-400")}>
                    {asNum(auditData[selectedAuditIndex].summary?.APEX_APPLICATIONS, auditData[selectedAuditIndex].apex_apps?.length || 0)}
                  </span>
                </div>
                <div className="flex justify-between p-3 rounded-xl bg-white/5 border border-white/10">
                  <span>Dies des de l'últim DDL</span>
                  <span className="font-bold text-primary">{auditData[selectedAuditIndex].summary?.DAYS_SINCE_NEWEST_DDL ?? 'N/A'}</span>
                </div>
              </div>
            </div>

            <div className="glass-card deep-scan-side-card p-6">
              <h4 className="text-xl font-bold mb-4 flex items-center gap-2 text-primary font-bold"><AlertTriangle size={20} /> Dependències Crítiques</h4>

              <div className="mb-4">
                <h5 className="text-xs uppercase tracking-wider font-bold opacity-70 mb-2">Dependències entrants</h5>
                <div className="space-y-2">
                  {auditData[selectedAuditIndex].dependencies?.incoming?.length > 0 ? (
                    auditData[selectedAuditIndex].dependencies.incoming.map((d, i) => (
                      <div key={i} className="deep-scan-dep-item deep-scan-dep-in flex items-center justify-between p-3 bg-red-500/10 border border-red-500/20 rounded-xl">
                        <div>
                          <p className="text-sm font-bold">{d.DEPENDENT_OWNER || d.OWNER || '-'}.{d.DEPENDENT_NAME || d.NAME || '-'}</p>
                          <p className="text-[10px] uppercase opacity-50">{d.DEPENDENT_TYPE || d.TYPE || '-'} {'->'} {d.REFERENCED_OWNER || '-'}</p>
                        </div>
                        <ShieldAlert size={18} className="text-red-500" />
                      </div>
                    ))
                  ) : (
                    <div className="p-4 text-center text-muted-foreground italic opacity-50 bg-green-500/5 rounded-xl border border-green-500/10">
                      No s'han detectat dependències entrants.
                    </div>
                  )}
                </div>
              </div>

              <div>
                <h5 className="text-xs uppercase tracking-wider font-bold opacity-70 mb-2">Dependències sortints</h5>
                <div className="space-y-2">
                  {auditData[selectedAuditIndex].dependencies?.outgoing?.length > 0 ? (
                    auditData[selectedAuditIndex].dependencies.outgoing.map((d, i) => (
                      <div key={i} className="deep-scan-dep-item deep-scan-dep-out flex items-center justify-between p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-xl">
                        <div>
                          <p className="text-sm font-bold">{d.OWNER || '-'}.{d.NAME || '-'}</p>
                          <p className="text-[10px] uppercase opacity-50">{d.TYPE || '-'} {'->'} {d.REFERENCED_OWNER || '-'}{d.REFERENCED_NAME ? `.${d.REFERENCED_NAME}` : ''}</p>
                        </div>
                        <AlertTriangle size={18} className="text-yellow-400" />
                      </div>
                    ))
                  ) : (
                    <div className="p-4 text-center text-muted-foreground italic opacity-50 bg-green-500/5 rounded-xl border border-green-500/10">
                      No s'han detectat dependències sortints.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
